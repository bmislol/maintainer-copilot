"""Refuse-to-boot test: api should refuse to start if eval thresholds are zero or missing."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.lifespan import _check_eval_thresholds


def test_passes_when_thresholds_are_positive(tmp_path: Path) -> None:
    yaml_path = tmp_path / "eval_thresholds.yaml"
    yaml_path.write_text("classification:\n  macro_f1: 0.90\n  per_class_min_f1: 0.50\n")
    _check_eval_thresholds(yaml_path)  # should not raise


def test_refuses_when_file_missing(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"
    with pytest.raises(RuntimeError, match="not found"):
        _check_eval_thresholds(missing)


def test_refuses_when_threshold_is_zero(tmp_path: Path) -> None:
    yaml_path = tmp_path / "eval_thresholds.yaml"
    yaml_path.write_text("classification:\n  macro_f1: 0\n  per_class_min_f1: 0.50\n")
    with pytest.raises(RuntimeError, match="macro_f1=0"):
        _check_eval_thresholds(yaml_path)


def test_refuses_when_threshold_is_negative(tmp_path: Path) -> None:
    yaml_path = tmp_path / "eval_thresholds.yaml"
    yaml_path.write_text("classification:\n  macro_f1: -0.1\n")
    with pytest.raises(RuntimeError, match="must be > 0"):
        _check_eval_thresholds(yaml_path)


def test_refuses_when_threshold_is_non_numeric(tmp_path: Path) -> None:
    yaml_path = tmp_path / "eval_thresholds.yaml"
    yaml_path.write_text("classification:\n  macro_f1: 'high'\n")
    with pytest.raises(RuntimeError, match="must be > 0"):
        _check_eval_thresholds(yaml_path)
