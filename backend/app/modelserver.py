"""Model inference server.

Hosts the fine-tuned classifier (Phase 2.1). NER and summarization land
in Phase 2.5 as additional endpoints.

Boot sequence:
  1. Configure structured logging.
  2. Load secrets from Vault.
  3. Download classifier artifacts from MinIO.
  4. Verify SHA-256 of weights against model_card.json.
  5. Refuse to boot if test_macro_f1 below threshold.
  6. Load model into torch, eval mode.

Endpoints:
  GET  /healthz             liveness probe
  POST /classify            issue classification
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import torch
from anthropic import AsyncAnthropic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import (
    AutoConfig,
    AutoModelForSequenceClassification,
    AutoTokenizer,
    pipeline,
)

from app.core.logging import configure_logging
from app.infra.object_storage import (
    ObjectStorageError,
    build_client,
    download_object,
    download_prefix,
    sha256_of_file,
)
from app.infra.vault import Secrets, VaultUnreachableError, load_secrets

# Refuse to boot if the trained model is worse than this on the test set.
# Committed threshold; revisit per phase.
MIN_TEST_MACRO_F1 = 0.60

# MinIO layout (matches push_classifier_to_minio.py)
BUCKET = "classifier-artifacts"
VERSION_PREFIX = "v1"
LABELS = ["bug", "feature", "docs", "question"]

# NER model — public HuggingFace model, no MinIO involvement
# (defended in DECISIONS D-014: third-party public weights have no SHA-against-self
# contract worth maintaining).
NER_MODEL = "dslim/bert-base-NER"

# Summarizer — Anthropic Haiku 4.5 (chosen over a local summarizer in D-014).
SUMMARIZER_MODEL = "claude-haiku-4-5"
SUMMARIZER_MAX_TOKENS = 250

# Limits
NER_MAX_INPUT_CHARS = 5000  # ~1200 tokens, enough for most issues
SUMMARIZE_MAX_INPUT_CHARS = 10000  # truncate before sending to Claude

logger = logging.getLogger(__name__)


class ModelServerStateError(RuntimeError):
    """Model state is invalid — refuse to boot."""


def _load_artifacts(
    secrets: Secrets,
) -> tuple[AutoModelForSequenceClassification, AutoTokenizer, dict[str, Any]]:
    """Download artifacts from MinIO, verify, load. Raises on any failure."""
    client = build_client(secrets.minio)

    # Working directory in the container for artifacts. /tmp is fine for now;
    # in production this would be a persistent volume so restarts don't re-download.
    workdir = Path(tempfile.mkdtemp(prefix="classifier-"))
    logger.info("downloading classifier artifacts to %s", workdir)

    # 1. model_card.json — small, defines what to expect.
    card_path = workdir / "model_card.json"
    try:
        download_object(client, BUCKET, f"{VERSION_PREFIX}/model_card.json", card_path)
    except ObjectStorageError as exc:
        raise ModelServerStateError(f"could not download model_card.json: {exc}") from exc

    card = json.loads(card_path.read_text())
    expected_sha = card["sha256"]
    expected_macro_f1 = card["test_macro_f1"]

    logger.info(
        "model card loaded — sha256=%s test_macro_f1=%.4f",
        expected_sha,
        expected_macro_f1,
    )

    # 2. Refuse to boot if quality is below threshold.
    if expected_macro_f1 < MIN_TEST_MACRO_F1:
        raise ModelServerStateError(
            f"REFUSING TO BOOT: test_macro_f1={expected_macro_f1:.4f} "
            f"below threshold {MIN_TEST_MACRO_F1:.4f}"
        )

    # 3. classifier.pt + verify SHA-256.
    weights_path = workdir / "classifier.pt"
    try:
        download_object(client, BUCKET, f"{VERSION_PREFIX}/classifier.pt", weights_path)
    except ObjectStorageError as exc:
        raise ModelServerStateError(f"could not download classifier.pt: {exc}") from exc

    actual_sha = sha256_of_file(weights_path)
    if actual_sha != expected_sha:
        raise ModelServerStateError(
            f"REFUSING TO BOOT: classifier.pt sha256 mismatch. "
            f"expected={expected_sha} actual={actual_sha}"
        )
    logger.info("classifier.pt sha256 verified")

    # 4. tokenizer/* into a directory.
    tokenizer_dir = workdir / "tokenizer"
    try:
        download_prefix(client, BUCKET, f"{VERSION_PREFIX}/tokenizer/", tokenizer_dir)
    except ObjectStorageError as exc:
        raise ModelServerStateError(f"could not download tokenizer: {exc}") from exc

    # 5. Load into HF objects.
    backbone = card["backbone"]
    num_labels = card["num_labels"]
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_dir)

    # Build the model architecture *without* downloading pretrained weights.
    # We're about to load fine-tuned weights from classifier.pt, so the
    # original DistilBERT bytes from HF Hub would be wasted bandwidth and disk.
    # AutoConfig.from_pretrained() only fetches the small (~500 B) JSON config,
    # which is needed to know the architecture's shape (n layers, hidden dim, etc.).
    config = AutoConfig.from_pretrained(
        backbone,
        num_labels=num_labels,
        id2label=dict(enumerate(LABELS)),
        label2id={lbl: i for i, lbl in enumerate(LABELS)},
    )
    model = AutoModelForSequenceClassification.from_config(config)  # type: ignore[no-untyped-call]
    model.load_state_dict(torch.load(weights_path, map_location="cpu"))
    model.eval()

    logger.info("classifier model loaded into memory")
    return model, tokenizer, card  # type: ignore[return-value]


def _load_ner_pipeline() -> object:
    """Load the NER pipeline from HuggingFace.

    `dslim/bert-base-NER` is fetched on first call and cached in
    ~/.cache/huggingface/hub for subsequent restarts. About 400MB.

    Note: passing task="token-classification" (the canonical name) instead
    of task="ner" so mypy can match the overload in the transformers stubs.
    At runtime both are equivalent; "ner" is just an alias.
    aggregation_strategy="simple" goes via **kwargs since it's not in the
    overload signature.
    """
    logger.info("loading NER pipeline: %s", NER_MODEL)
    ner = pipeline(
        task="token-classification",
        model=NER_MODEL,
        tokenizer=NER_MODEL,
        device=-1,
        aggregation_strategy="simple",  # passed through **kwargs to TokenClassificationPipeline
    )
    logger.info("NER pipeline ready")
    return ner


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: load secrets, fetch artifacts, init models. Refuse on failure."""
    configure_logging(service_name="modelserver")
    logger.info("modelserver startup — resolving secrets")

    try:
        secrets = load_secrets()
    except VaultUnreachableError as exc:
        logger.critical("REFUSING TO BOOT: %s", exc)
        raise

    # 1. Classifier (Phase 2.1)
    try:
        model, tokenizer, card = _load_artifacts(secrets)
    except ModelServerStateError as exc:
        logger.critical("%s", exc)
        raise

    # 2. NER (Phase 2.5)
    try:
        ner_pipeline = _load_ner_pipeline()
    except Exception as exc:
        logger.critical("REFUSING TO BOOT: NER load failed: %s", exc)
        raise

    # 3. Summarizer client (Phase 2.5) — Anthropic API client (not a model load)
    summarizer_client = AsyncAnthropic(api_key=secrets.anthropic.api_key)

    app.state.model = model
    app.state.tokenizer = tokenizer
    app.state.model_card = card
    app.state.device = torch.device("cpu")
    app.state.ner = ner_pipeline
    app.state.summarizer = summarizer_client
    logger.info("modelserver startup complete (classifier + NER + summarizer)")

    yield

    logger.info("modelserver shutdown")
    await summarizer_client.close()


app = FastAPI(
    title="Maintainer's Copilot — Model Server",
    version="0.1.0",
    description="Inference server for classifier (Phase 2.1), NER and summarizer (Phase 2.5).",
    lifespan=lifespan,
)


class ClassifyRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    body: str = Field(default="", max_length=10_000)


class ClassPrediction(BaseModel):
    label: str
    probability: float


class ClassifyResponse(BaseModel):
    label: str
    confidence: float
    top4: list[ClassPrediction]


@app.get("/healthz", tags=["health"])
async def healthz() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.post("/classify", tags=["inference"], response_model=ClassifyResponse)
async def classify(request: ClassifyRequest) -> ClassifyResponse:
    """Classify an issue title+body into one of bug/feature/docs/question."""
    model = app.state.model
    tokenizer = app.state.tokenizer
    device = app.state.device

    text = request.title.strip()
    if request.body:
        text = f"{text}\n\n{request.body.strip()}"

    try:
        tokens = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=256,
            padding=False,
        ).to(device)
        with torch.no_grad():
            logits = model(**tokens).logits
            probs = torch.softmax(logits, dim=-1)[0].tolist()
    except Exception as exc:
        logger.exception("classify failed")
        raise HTTPException(status_code=500, detail="inference failed") from exc

    pairs = sorted(zip(LABELS, probs, strict=True), key=lambda p: -p[1])
    top_label, top_prob = pairs[0]
    return ClassifyResponse(
        label=top_label,
        confidence=top_prob,
        top4=[ClassPrediction(label=lbl, probability=p) for lbl, p in pairs],
    )


# ─── NER ──────────────────────────────────────────────────────────


class NERRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=NER_MAX_INPUT_CHARS)


class Entity(BaseModel):
    label: str  # PER, LOC, ORG, MISC
    text: str
    start: int
    end: int
    score: float


class NERResponse(BaseModel):
    entities: list[Entity]
    model: str = NER_MODEL


@app.post("/ner", tags=["inference"], response_model=NERResponse)
async def ner(request: NERRequest) -> NERResponse:
    """Extract named entities from a chunk of issue text.

    Uses dslim/bert-base-NER (CoNLL-03 4-class scheme: PER, LOC, ORG, MISC).
    Returns spans with byte offsets and confidence scores.
    """
    pipeline = app.state.ner

    try:
        raw_results = pipeline(request.text)
    except Exception as exc:
        logger.exception("NER failed")
        raise HTTPException(status_code=500, detail="NER inference failed") from exc

    entities = [
        Entity(
            label=r["entity_group"],
            text=r["word"],
            start=int(r["start"]),
            end=int(r["end"]),
            score=float(r["score"]),
        )
        for r in raw_results
    ]
    return NERResponse(entities=entities, model=NER_MODEL)


# ─── Summarize ────────────────────────────────────────────────────


class SummarizeRequest(BaseModel):
    text: str = Field(..., min_length=20, max_length=SUMMARIZE_MAX_INPUT_CHARS)


class SummarizeResponse(BaseModel):
    summary: str
    original_chars: int
    summary_chars: int
    model: str = SUMMARIZER_MODEL


SUMMARIZE_SYSTEM = (
    "You are summarizing a GitHub issue for a maintainer. "
    "Produce a 2-3 sentence summary that captures: (a) what is happening, "
    "(b) what library/module/feature is affected if mentioned, "
    "(c) the user's primary concern. "
    "Be concrete, do not editorialize, and stay under 60 words."
)


@app.post("/summarize", tags=["inference"], response_model=SummarizeResponse)
async def summarize(request: SummarizeRequest) -> SummarizeResponse:
    """Summarize an issue thread in 2-3 sentences.

    Calls Anthropic Haiku via the Anthropic SDK (no local model). The
    cost-quality argument is in DECISIONS D-014.
    """
    client = app.state.summarizer
    try:
        response = await client.messages.create(
            model=SUMMARIZER_MODEL,
            max_tokens=SUMMARIZER_MAX_TOKENS,
            system=SUMMARIZE_SYSTEM,
            messages=[{"role": "user", "content": request.text}],
        )
    except Exception as exc:
        logger.exception("summarize failed")
        raise HTTPException(status_code=500, detail="summarize inference failed") from exc

    # Anthropic returns a list of content blocks; for non-tool-use it's just text.
    text_blocks = [b for b in response.content if getattr(b, "type", None) == "text"]
    if not text_blocks:
        raise HTTPException(
            status_code=500,
            detail="summarize: no text content in Anthropic response",
        )
    summary = text_blocks[0].text.strip()

    return SummarizeResponse(
        summary=summary,
        original_chars=len(request.text),
        summary_chars=len(summary),
        model=SUMMARIZER_MODEL,
    )
