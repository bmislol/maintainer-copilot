"""Smoke test for the LLM baseline artifacts.

Verifies the comparison report exists, has the expected shape, and that
Haiku's metrics are present. Skipped if artifacts haven't been generated yet —
run notebooks/03_llm_baseline.ipynb to produce them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "data" / "llm_baseline_artifacts"
LABELS = ["bug", "feature", "docs", "question"]


def _require_artifacts() -> None:
    if not (ARTIFACT_DIR / "comparison_report.json").exists():
        pytest.skip(
            f"{ARTIFACT_DIR / 'comparison_report.json'} missing — "
            "run notebooks/03_llm_baseline.ipynb to generate artifacts"
        )


def test_comparison_report_has_required_fields() -> None:
    _require_artifacts()
    report = json.loads((ARTIFACT_DIR / "comparison_report.json").read_text())
    required = {
        "comparison",
        "winner_on_macro_f1",
        "winner_on_question_class",
        "deployment_recommendation",
        "haiku_full_metrics",
    }
    missing = required - report.keys()
    assert not missing, f"comparison_report missing required fields: {missing}"


def test_comparison_includes_all_four_classifiers() -> None:
    _require_artifacts()
    report = json.loads((ARTIFACT_DIR / "comparison_report.json").read_text())
    names = {r["name"] for r in report["comparison"]}
    expected = {
        "Classical (TF-IDF + LogReg)",
        "DistilBERT (fine-tuned)",
        "Haiku 4.5",
        "Sonnet 4.6",
    }
    assert expected <= names, f"missing classifiers: {expected - names}"


def test_haiku_metrics_have_all_classes() -> None:
    _require_artifacts()
    report = json.loads((ARTIFACT_DIR / "comparison_report.json").read_text())
    per_class = report["haiku_full_metrics"]["per_class_f1"]
    assert set(per_class.keys()) == set(LABELS)
    for _label, f1 in per_class.items():
        assert 0.0 <= f1 <= 1.0
