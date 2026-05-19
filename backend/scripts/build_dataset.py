"""Build train/val/test JSONL files from cached raw issues.

Reads both REST (page_*.json) and GraphQL (gql_batch_*.json) caches,
dedupes by issue number, applies the label mapping, performs stratified
time-based splits, and writes splits to data/issues/splits/.

Run from backend/:

    uv run python scripts/build_dataset.py
"""

from __future__ import annotations

import collections
import glob
import hashlib
import json
import logging
from collections.abc import Iterator
from pathlib import Path

REPO_OWNER = "scikit-learn"
REPO_NAME = "scikit-learn"

# Label mapping — defended in DECISIONS.md (D-007).
LABEL_TO_CLASS: dict[str, str] = {
    "Bug": "bug",
    "Regression": "bug",
    "Documentation": "docs",
    "New Feature": "feature",
    "Enhancement": "feature",
    "Needs Triage": "question",
    "help wanted": "question",
}

# If an issue has multiple labels that map to DIFFERENT classes, it's ambiguous
# and we exclude it from training. If multiple labels map to the SAME class,
# that's fine — we pick that class.

# Split fractions (test most recent; train oldest).
TRAIN_FRAC = 0.70
VAL_FRAC = 0.15
TEST_FRAC = 0.15

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("build_dataset")


def _raw_dir() -> Path:
    here = Path(__file__).resolve().parent.parent
    return here / "data" / "issues" / "raw" / f"{REPO_OWNER}__{REPO_NAME}"


def _splits_dir() -> Path:
    here = Path(__file__).resolve().parent.parent
    out = here / "data" / "issues" / "splits"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _load_all_issues() -> Iterator[dict]:
    """Yield issues from both REST and GraphQL cache files."""
    raw = _raw_dir()
    files = sorted(glob.glob(str(raw / "page_*.json"))) + sorted(
        glob.glob(str(raw / "gql_batch_*.json"))
    )
    if not files:
        raise FileNotFoundError(f"no cached issue files in {raw}")
    for f in files:
        yield from json.loads(Path(f).read_text())


def _classify(issue: dict) -> str | None:
    """Return the class name, or None if the issue is not classifiable."""
    label_names = {lbl["name"] for lbl in issue.get("labels", [])}
    matched_classes = {LABEL_TO_CLASS[name] for name in label_names if name in LABEL_TO_CLASS}
    if len(matched_classes) == 1:
        return next(iter(matched_classes))
    return None


def _hash_jsonl(rows: list[dict]) -> str:
    """SHA-256 over the canonical JSON serialization of the sorted rows."""
    h = hashlib.sha256()
    for row in rows:
        h.update(json.dumps(row, sort_keys=True).encode())
        h.update(b"\n")
    return h.hexdigest()


def build() -> None:
    # Dedupe by issue number — newer pages may overlap with older
    by_number: dict[int, dict] = {}
    pr_count = 0
    ci_bot_count = 0
    for issue in _load_all_issues():
        if "pull_request" in issue:
            pr_count += 1
            continue
        # Filter out scikit-learn's CI failure bot issues. These are templated
        # machine-generated reports auto-labeled 'Needs Triage' and would
        # otherwise pollute the question class. Title starts with a warning
        # emoji followed by 'CI failed'.
        title = (issue.get("title") or "").strip()
        if "CI failed" in title[:30]:
            ci_bot_count += 1
            continue
        by_number[issue["number"]] = issue
    logger.info(
        "loaded %d unique issues (filtered %d PRs, %d CI bot reports)",
        len(by_number),
        pr_count,
        ci_bot_count,
    )

    # Classify
    classified = []
    excluded_unlabeled = 0
    excluded_ambiguous = 0
    for issue in by_number.values():
        cls = _classify(issue)
        if cls is None:
            label_names = {lbl["name"] for lbl in issue.get("labels", [])}
            matched = {LABEL_TO_CLASS[n] for n in label_names if n in LABEL_TO_CLASS}
            if len(matched) > 1:
                excluded_ambiguous += 1
            else:
                excluded_unlabeled += 1
            continue
        classified.append(
            {
                "issue_id": issue["id"],
                "number": issue["number"],
                "title": issue.get("title", "") or "",
                "body": issue.get("body") or "",
                "label": cls,
                "created_at": issue["created_at"],
                "raw_labels": sorted({lbl["name"] for lbl in issue.get("labels", [])}),
            }
        )

    logger.info(
        "classified %d  |  excluded unlabeled %d  |  excluded ambiguous %d",
        len(classified),
        excluded_unlabeled,
        excluded_ambiguous,
    )

    # Sort by created_at ASCENDING (oldest first) for time-based split.
    classified.sort(key=lambda r: r["created_at"])

    n = len(classified)
    n_train = int(n * TRAIN_FRAC)
    n_val = int(n * VAL_FRAC)
    train = classified[:n_train]
    val = classified[n_train : n_train + n_val]
    test = classified[n_train + n_val :]

    # Sanity: test must be strictly more recent than train.
    assert train[-1]["created_at"] < val[0]["created_at"], "train/val temporal overlap"
    assert val[-1]["created_at"] < test[0]["created_at"], "val/test temporal overlap"

    # Class distribution per split — useful for verifying stratification by accident.
    def class_dist(rows: list[dict]) -> dict[str, int]:
        return dict(collections.Counter(r["label"] for r in rows))

    logger.info("train (%d): %s", len(train), class_dist(train))
    logger.info("val   (%d): %s", len(val), class_dist(val))
    logger.info("test  (%d): %s", len(test), class_dist(test))

    # Hash the training set for the model card (Phase 2.1).
    training_hash = _hash_jsonl(train)
    logger.info("training data SHA-256: %s", training_hash)

    # Write JSONL files.
    out = _splits_dir()
    for name, rows in [("train", train), ("val", val), ("test", test)]:
        path = out / f"{name}.jsonl"
        with path.open("w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        logger.info("wrote %s (%d rows)", path, len(rows))

    # Write metadata file alongside the splits.
    meta = {
        "repo": f"{REPO_OWNER}/{REPO_NAME}",
        "total_classified": n,
        "splits": {
            "train": {"n": len(train), "distribution": class_dist(train)},
            "val": {"n": len(val), "distribution": class_dist(val)},
            "test": {"n": len(test), "distribution": class_dist(test)},
        },
        "train_date_range": [train[0]["created_at"], train[-1]["created_at"]],
        "val_date_range": [val[0]["created_at"], val[-1]["created_at"]],
        "test_date_range": [test[0]["created_at"], test[-1]["created_at"]],
        "training_data_sha256": training_hash,
        "label_mapping": LABEL_TO_CLASS,
        "exclusions": {
            "no_classifying_label": excluded_unlabeled,
            "ambiguous_multi_class": excluded_ambiguous,
            "pull_requests": pr_count,
            "ci_bot_reports": ci_bot_count,
        },
    }
    (out / "metadata.json").write_text(json.dumps(meta, indent=2))
    logger.info("wrote metadata.json")


if __name__ == "__main__":
    build()
