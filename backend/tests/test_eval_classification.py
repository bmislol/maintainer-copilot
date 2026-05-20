"""Eval gate: Haiku 4.5 on the classification golden set.

Runs Haiku on each example in eval_classification.jsonl and asserts:
  - macro-F1 >= thresholds['classification']['macro_f1']
  - per-class F1 >= thresholds['classification']['per_class_min_f1']

This test is marked @pytest.mark.eval so it does NOT run in the default
pytest invocation. CI runs it explicitly via `pytest -m eval`.

Costs: ~25 Haiku API calls per run, ~$0.05 each run.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
import yaml

# Skip the entire module if anthropic isn't importable (CI without secrets).
anthropic = pytest.importorskip("anthropic")
from anthropic import AsyncAnthropic  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
EVAL_FILE = Path(__file__).resolve().parent.parent / "data" / "eval" / "eval_classification.jsonl"
THRESHOLDS_FILE = Path(__file__).resolve().parent.parent / "eval_thresholds.yaml"

LABELS = ["bug", "feature", "docs", "question"]
HAIKU_MODEL = "claude-haiku-4-5"
MAX_OUTPUT_TOKENS = 200
MAX_CONCURRENT = 5

CLASSIFY_TOOL = {
    "name": "classify_issue",
    "description": "Record your classification of the GitHub issue. Choose exactly one label.",
    "input_schema": {
        "type": "object",
        "properties": {
            "label": {"type": "string", "enum": LABELS},
            "reasoning": {"type": "string"},
        },
        "required": ["label", "reasoning"],
    },
}

# Identical to the prompt used in Phase 2.3 (D-011).
SYSTEM_PROMPT = """You are classifying GitHub issues for the scikit-learn maintainers.

Each issue is one of:
- bug: existing functionality fails, raises an unexpected error, or produces wrong output
- feature: a request for new capability or enhancement
- docs: documentation is missing, unclear, or incorrect; or improvements to docstrings/examples
- question: the author is asking how something works, needs help using the library, or the issue lacks enough detail to categorize (often these are user questions miscategorized as issues)

Edge cases:
- "Improve performance of X" → feature (it's an enhancement)
- "X documentation says Y but does Z" → bug (incorrect docs that mislead users)
- "How do I make X do Y?" → question
- Issues with detailed reproductions, tracebacks, and stack traces → bug

Be concise. Call the classify_issue tool exactly once."""


@pytest.mark.eval
def test_haiku_golden_set_meets_thresholds() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    if not EVAL_FILE.exists():
        pytest.skip(f"{EVAL_FILE} missing")

    thresholds = yaml.safe_load(THRESHOLDS_FILE.read_text())["classification"]
    required_macro_f1 = thresholds["macro_f1"]
    required_per_class = thresholds["per_class_min_f1"]

    # Load the golden set.
    with EVAL_FILE.open() as f:
        examples = [json.loads(line) for line in f]
    assert len(examples) > 0, "golden set is empty"

    # Run Haiku on each example.
    async def run_all() -> list[dict]:
        sem = asyncio.Semaphore(MAX_CONCURRENT)

        async def one(client: AsyncAnthropic, ex: dict) -> dict:
            async with sem:
                title = (ex.get("title") or "").strip()
                body = (ex.get("body") or "").strip()
                if len(body) > 1500:
                    body = body[:1500] + "\n[... truncated ...]"
                text = f"Title: {title}\n\nBody: {body}" if body else f"Title: {title}"

                resp = await client.messages.create(
                    model=HAIKU_MODEL,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    system=SYSTEM_PROMPT,
                    tools=[CLASSIFY_TOOL],
                    tool_choice={"type": "tool", "name": "classify_issue"},
                    messages=[{"role": "user", "content": text}],
                )
                tool_block = next(b for b in resp.content if b.type == "tool_use")
                return {
                    "issue_id": ex["issue_id"],
                    "gold": ex["gold_label"],
                    "predicted": tool_block.input["label"],
                }

        async with AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"]) as client:
            return await asyncio.gather(*[one(client, ex) for ex in examples])

    results = asyncio.run(run_all())

    # Compute macro-F1 and per-class F1.
    from sklearn.metrics import classification_report, f1_score

    gold = [r["gold"] for r in results]
    pred = [r["predicted"] for r in results]

    macro = f1_score(gold, pred, average="macro", labels=LABELS, zero_division=0)
    report = classification_report(
        gold,
        pred,
        labels=LABELS,
        output_dict=True,
        zero_division=0,
    )
    per_class_f1 = {lbl: report[lbl]["f1-score"] for lbl in LABELS}

    print(f"\nHaiku golden set — macro-F1: {macro:.4f}")
    for lbl, f1 in per_class_f1.items():
        marker = "✓" if f1 >= required_per_class else "✗"
        print(f"  {lbl:10s}: {f1:.4f} {marker}")
    print(f"required macro_f1: {required_macro_f1}")
    print(f"required per-class min: {required_per_class}\n")

    # Per-class first — gives better error message than macro.
    failures = [lbl for lbl, f1 in per_class_f1.items() if f1 < required_per_class]
    assert not failures, (
        f"per-class F1 below threshold {required_per_class} for: {failures}\n"
        f"actual per-class: {per_class_f1}"
    )

    assert macro >= required_macro_f1, (
        f"macro-F1 {macro:.4f} below threshold {required_macro_f1}\nper-class: {per_class_f1}"
    )
