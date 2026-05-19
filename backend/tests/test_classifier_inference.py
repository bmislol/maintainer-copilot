"""Smoke test: load the saved classifier artifacts and run one inference.

Ensures the artifact contract (classifier.pt + tokenizer/ + model_card.json)
in data/classifier_artifacts/ remains loadable. The same code path is what
modelserver uses at startup (Sitting B).

Skipped if the artifacts haven't been generated yet — run the training
notebook to produce them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "data" / "classifier_artifacts"
LABELS = ["bug", "feature", "docs", "question"]


def _require_artifacts() -> None:
    """Skip the test if artifacts haven't been generated."""
    for needed in ("classifier.pt", "tokenizer", "model_card.json"):
        if not (ARTIFACT_DIR / needed).exists():
            pytest.skip(
                f"{ARTIFACT_DIR / needed} missing — "
                "run notebooks/01_train_classifier.ipynb to generate artifacts"
            )


def test_model_card_has_required_fields() -> None:
    _require_artifacts()
    card = json.loads((ARTIFACT_DIR / "model_card.json").read_text())

    required = {
        "sha256",
        "backbone",
        "tokenizer",
        "num_labels",
        "labels",
        "freeze_policy",
        "hyperparameters",
        "training_data_sha256",
        "test_accuracy",
        "test_macro_f1",
        "per_class_f1",
        "trained_at",
        "env_fingerprint",
    }
    missing = required - card.keys()
    assert not missing, f"model_card missing required fields: {missing}"

    assert card["labels"] == LABELS, "labels in model_card don't match expected"
    assert 0.0 <= card["test_macro_f1"] <= 1.0
    assert 0.0 <= card["test_accuracy"] <= 1.0


def test_sha256_matches_classifier_file() -> None:
    """The SHA-256 in model_card.json must match the actual classifier.pt file."""
    _require_artifacts()
    import hashlib

    card = json.loads((ARTIFACT_DIR / "model_card.json").read_text())
    expected_sha = card["sha256"]

    h = hashlib.sha256()
    with (ARTIFACT_DIR / "classifier.pt").open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    actual_sha = h.hexdigest()

    assert actual_sha == expected_sha, (
        f"classifier.pt SHA-256 ({actual_sha}) does not match model_card.json ({expected_sha})"
    )


# TODO(Phase 5): Add HTTP smoke test against running modelserver in integration CI.
# The /classify endpoint is exercised manually during Phase 2.1 closeout but has
# no automated assertion. Phase 5's docker-compose-integration job will add this.


def test_inference_round_trip() -> None:
    """Load artifacts in a fresh model and predict on one example."""
    _require_artifacts()
    pytest.importorskip("torch")
    pytest.importorskip("transformers")

    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    card = json.loads((ARTIFACT_DIR / "model_card.json").read_text())

    tokenizer = AutoTokenizer.from_pretrained(ARTIFACT_DIR / "tokenizer")
    model = AutoModelForSequenceClassification.from_pretrained(
        card["backbone"],
        num_labels=card["num_labels"],
        id2label=dict(enumerate(LABELS)),
        label2id={lbl: i for i, lbl in enumerate(LABELS)},
    )
    model.load_state_dict(torch.load(ARTIFACT_DIR / "classifier.pt", map_location="cpu"))
    model.eval()

    text = "Random Forest fit fails with sparse input"
    tokens = tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
    with torch.no_grad():
        logits = model(**tokens).logits
        probs = torch.softmax(logits, dim=-1)[0]

    assert probs.shape == (len(LABELS),)
    assert abs(probs.sum().item() - 1.0) < 1e-4, "softmax output should sum to ~1.0"
    predicted_idx = int(probs.argmax().item())
    predicted_label = LABELS[predicted_idx]
    assert predicted_label in LABELS


def test_min_macro_f1_threshold_committed() -> None:
    """The minimum threshold must be set above 0 and below 1."""
    from app.modelserver import MIN_TEST_MACRO_F1

    assert 0.0 < MIN_TEST_MACRO_F1 < 1.0
    # Sanity check that we're not shipping a too-permissive threshold.
    assert MIN_TEST_MACRO_F1 >= 0.50, (
        "threshold is suspiciously low — committed thresholds should be defended in DECISIONS.md"
    )


def test_model_card_passes_committed_threshold() -> None:
    """The shipped model card must exceed the modelserver's refuse-to-boot threshold."""
    _require_artifacts()
    from app.modelserver import MIN_TEST_MACRO_F1

    card = json.loads((ARTIFACT_DIR / "model_card.json").read_text())
    assert card["test_macro_f1"] >= MIN_TEST_MACRO_F1, (
        f"shipped model_card.test_macro_f1={card['test_macro_f1']:.4f} "
        f"is below committed threshold {MIN_TEST_MACRO_F1:.4f}; "
        "either retrain or lower the threshold and defend in DECISIONS"
    )
