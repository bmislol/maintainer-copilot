"""Interactive curation tool for the classification golden set.

Reads test.jsonl + Haiku's predictions, samples candidates stratified
across the four classes, and shows you each one for a yes/no/skip vote.
Writes accepted picks to backend/data/eval/eval_classification.jsonl.

Strategy: prioritize examples where Haiku ALREADY got the label right.
The golden set's job is to detect future regressions, so the "floor" is
defined by what currently works. If Haiku breaks one of these in a future
PR, CI catches it immediately.

Resumable: re-running picks up from where you left off.

Run from backend/:

    uv run python scripts/curate_golden_set.py
"""

from __future__ import annotations

import json
import random
import textwrap
from collections import Counter
from pathlib import Path

# Targets per class — defends "stratified golden set".
TARGETS = {"bug": 7, "feature": 7, "docs": 6, "question": 5}
TOTAL = sum(TARGETS.values())

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TEST_FILE = DATA_DIR / "issues" / "splits" / "test.jsonl"
HAIKU_FILE = DATA_DIR / "llm_baseline_artifacts" / "predictions_haiku.jsonl"

EVAL_DIR = DATA_DIR / "eval"
EVAL_DIR.mkdir(parents=True, exist_ok=True)
EVAL_FILE = EVAL_DIR / "eval_classification.jsonl"
REJECTED_FILE = EVAL_DIR / ".rejected_ids.json"  # so we don't re-show on resume

SEED = 42


def _load_jsonl(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f]


def _load_rejected() -> set[int]:
    if REJECTED_FILE.exists():
        return set(json.loads(REJECTED_FILE.read_text()))
    return set()


def _save_rejected(rejected: set[int]) -> None:
    REJECTED_FILE.write_text(json.dumps(sorted(rejected)))


def _load_accepted() -> list[dict]:
    if not EVAL_FILE.exists():
        return []
    return _load_jsonl(EVAL_FILE)


def _append_accepted(row: dict) -> None:
    with EVAL_FILE.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _format_issue(issue: dict, haiku_pred: dict | None) -> str:
    body = (issue.get("body") or "").strip()
    if len(body) > 800:
        body = body[:800] + "\n[... truncated ...]"
    body = textwrap.indent(body, "  ")

    haiku_line = ""
    if haiku_pred is not None:
        haiku_label = haiku_pred["predicted_label"]
        reasoning = (haiku_pred.get("reasoning") or "")[:200]
        match = "✓" if haiku_label == issue["label"] else "✗"
        haiku_line = f"Haiku said:  {haiku_label} {match}\n  reasoning: {reasoning}\n"

    return (
        f"================================================================\n"
        f"Issue #{issue['number']}  (issue_id={issue['issue_id']})\n"
        f"True label:  {issue['label']}\n"
        f"Raw labels:  {issue.get('raw_labels', [])}\n"
        f"{haiku_line}"
        f"----------------------------------------------------------------\n"
        f"TITLE: {issue['title']}\n"
        f"\nBODY:\n{body}\n"
        f"================================================================"
    )


def main() -> None:
    random.seed(SEED)

    test = _load_jsonl(TEST_FILE)
    haiku_preds = _load_jsonl(HAIKU_FILE)
    haiku_by_id = {p["issue_id"]: p for p in haiku_preds}

    accepted = _load_accepted()
    accepted_ids = {a["issue_id"] for a in accepted}
    rejected_ids = _load_rejected()

    accepted_counter = Counter(a["label"] for a in accepted)

    print(f"\nGolden set targets: {TARGETS} (total {TOTAL})")
    print(f"Already accepted:   {dict(accepted_counter)}")
    print(f"Already rejected:   {len(rejected_ids)} ids\n")

    # Pool: examples Haiku got right, never seen before.
    # We'll fall back to ones Haiku got wrong if pool is too small.
    candidates_correct: dict[str, list[dict]] = {label: [] for label in TARGETS}
    candidates_wrong: dict[str, list[dict]] = {label: [] for label in TARGETS}

    for issue in test:
        if issue["issue_id"] in accepted_ids or issue["issue_id"] in rejected_ids:
            continue
        label = issue["label"]
        if label not in TARGETS:
            continue
        haiku = haiku_by_id.get(issue["issue_id"])
        if haiku is None:
            continue
        if haiku["predicted_label"] == label:
            candidates_correct[label].append(issue)
        else:
            candidates_wrong[label].append(issue)

    for label in TARGETS:
        random.shuffle(candidates_correct[label])
        random.shuffle(candidates_wrong[label])

    while sum(accepted_counter[lbl] for lbl in TARGETS) < TOTAL:
        # Find the class furthest from its target.
        needs = {
            lbl: TARGETS[lbl] - accepted_counter[lbl]
            for lbl in TARGETS
            if accepted_counter[lbl] < TARGETS[lbl]
        }
        if not needs:
            break
        target_label = max(needs, key=lambda lbl: needs[lbl])

        # Prefer candidates Haiku got right; fall back to wrong if exhausted.
        pool = candidates_correct[target_label]
        if not pool:
            pool = candidates_wrong[target_label]
            if pool:
                print(
                    f"  [info] no more correct Haiku predictions for '{target_label}', "
                    f"falling back to ones Haiku got wrong\n"
                )
        if not pool:
            print(f"  [warn] no more candidates for '{target_label}'; skipping")
            accepted_counter[target_label] = TARGETS[target_label]  # mark as done
            continue

        issue = pool.pop()
        haiku = haiku_by_id.get(issue["issue_id"])

        print("\n" + _format_issue(issue, haiku))
        print(f"\nProgress: {dict(accepted_counter)} / {TARGETS}\n")
        print(f"Want this in golden set as '{target_label}'?")
        choice = input("  y(es) / n(o) / s(kip - revisit later) / q(uit): ").strip().lower()

        if choice == "y":
            row = {
                "issue_id": issue["issue_id"],
                "number": issue["number"],
                "title": issue["title"],
                "body": issue["body"],
                "gold_label": issue["label"],
                "raw_labels": issue.get("raw_labels", []),
                "selection_notes": (
                    "Hand-verified from test.jsonl. "
                    f"Haiku 4.5 prediction at curation time: "
                    f"{haiku['predicted_label']} "
                    f"({'matched' if haiku['predicted_label'] == issue['label'] else 'did not match'} gold label)."
                ),
            }
            _append_accepted(row)
            accepted_counter[target_label] += 1
            print(f"  → accepted as '{target_label}'\n")
        elif choice == "n":
            rejected_ids.add(issue["issue_id"])
            _save_rejected(rejected_ids)
            print("  → rejected, will not show again\n")
        elif choice == "q":
            print("\n  Quit. Resume any time by re-running this script.\n")
            return
        else:  # 's' or anything else
            print("  → skipped (back to pool, may resurface)\n")

    print(f"\nGolden set complete: {dict(accepted_counter)}")
    print(f"Saved to: {EVAL_FILE}")
    print(f"Total examples: {len(_load_accepted())}")


if __name__ == "__main__":
    main()
