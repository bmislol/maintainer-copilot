"""Smoke test for the classical baseline artifacts.

Verifies the saved vectorizer + classifier can be loaded and used for
prediction. Skipped if artifacts haven't been generated yet — run the
notebook backend/notebooks/02_classical_baseline.ipynb to produce them.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import pytest

ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "data" / "classical_baseline_artifacts"
LABELS = ["bug", "feature", "docs", "question"]


def _require_artifacts() -> None:
    for needed in ("vectorizer.pkl", "classifier.pkl", "comparison_report.json"):
        if not (ARTIFACT_DIR / needed).exists():
            pytest.skip(
                f"{ARTIFACT_DIR / needed} missing — "
                "run notebooks/02_classical_baseline.ipynb to generate artifacts"
            )


def test_comparison_report_has_required_fields() -> None:
    _require_artifacts()
    report = json.loads((ARTIFACT_DIR / "comparison_report.json").read_text())
    required = {
        "approach",
        "winner",
        "test_accuracy",
        "test_macro_f1",
        "per_class_f1",
        "compared_to_distilbert",
    }
    missing = required - report.keys()
    assert not missing, f"comparison_report missing required fields: {missing}"


def test_classical_baseline_inference_round_trip() -> None:
    """Load vectorizer + classifier in a fresh process and predict on one example."""
    _require_artifacts()

    with (ARTIFACT_DIR / "vectorizer.pkl").open("rb") as f:
        vectorizer = pickle.load(f)
    with (ARTIFACT_DIR / "classifier.pkl").open("rb") as f:
        classifier = pickle.load(f)

    text = "Random Forest fit fails with sparse input"
    features = vectorizer.transform([text])
    pred = classifier.predict(features)
    assert pred.shape == (1,)
    assert LABELS[int(pred[0])] in LABELS
