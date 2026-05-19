"""Test that the dataset splits exist, have the right shape, and respect time ordering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

SPLITS_DIR = Path(__file__).resolve().parent.parent / "data" / "issues" / "splits"
SPLIT_NAMES = ["train", "val", "test"]


def _load_split(name: str) -> list[dict]:
    path = SPLITS_DIR / f"{name}.jsonl"
    if not path.exists():
        pytest.skip(f"{path} not generated yet — run scripts/build_dataset.py")
    with path.open() as f:
        return [json.loads(line) for line in f]


def test_all_splits_exist() -> None:
    for name in SPLIT_NAMES:
        rows = _load_split(name)
        assert len(rows) > 0, f"{name} is empty"


def test_each_row_has_required_fields() -> None:
    required = {"issue_id", "number", "title", "body", "label", "created_at"}
    for name in SPLIT_NAMES:
        rows = _load_split(name)
        for row in rows:
            missing = required - set(row)
            assert not missing, f"{name} row missing fields: {missing}"


def test_test_strictly_newer_than_train() -> None:
    train = _load_split("train")
    test = _load_split("test")
    train_latest = max(r["created_at"] for r in train)
    test_earliest = min(r["created_at"] for r in test)
    assert train_latest < test_earliest, (
        f"test must be strictly newer than train; "
        f"train latest={train_latest}, test earliest={test_earliest}"
    )


def test_all_four_classes_present_in_each_split() -> None:
    expected = {"bug", "feature", "docs", "question"}
    for name in SPLIT_NAMES:
        rows = _load_split(name)
        labels = {r["label"] for r in rows}
        assert labels == expected, f"{name} has labels {labels}, expected {expected}"
