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
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer

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
    model = AutoModelForSequenceClassification.from_config(config)  # type: ignore
    model.load_state_dict(torch.load(weights_path, map_location="cpu"))
    model.eval()

    logger.info("classifier model loaded into memory")
    return model, tokenizer, card  # type: ignore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: load secrets, fetch artifacts, init model. Refuse on failure."""
    configure_logging(service_name="modelserver")
    logger.info("modelserver startup — resolving secrets")

    try:
        secrets = load_secrets()
    except VaultUnreachableError as exc:
        logger.critical("REFUSING TO BOOT: %s", exc)
        raise

    try:
        model, tokenizer, card = _load_artifacts(secrets)
    except ModelServerStateError as exc:
        logger.critical("%s", exc)
        raise

    app.state.model = model
    app.state.tokenizer = tokenizer
    app.state.model_card = card
    app.state.device = torch.device("cpu")  # modelserver is CPU-only at the moment
    logger.info("modelserver startup complete")

    yield

    logger.info("modelserver shutdown")


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
    model: AutoModelForSequenceClassification = app.state.model
    tokenizer: AutoTokenizer = app.state.tokenizer
    device: torch.device = app.state.device

    text = request.title.strip()
    if request.body:
        text = f"{text}\n\n{request.body.strip()}"

    try:
        tokens = tokenizer(  # type: ignore
            text,
            return_tensors="pt",
            truncation=True,
            max_length=256,
            padding=False,
        ).to(device)
        with torch.no_grad():
            logits = model(**tokens).logits  # type: ignore
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
