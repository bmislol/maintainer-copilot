"""Judge agreement script — Phase 3.4 (D-021).

Tests Claude Haiku's agreement with human-curated ground truth on the
first 5 triples of the RAG golden set.  Human judgment for all 5 is
"yes" (verified at curation time).

Output:
  prints a table to stdout
  saves data/eval/judge_agreement.json

Run from backend/:
    ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY ../.env | cut -d= -f2-) \\
        uv run python scripts/judge_agreement.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_BACKEND = Path(__file__).resolve().parent.parent
_EVAL_FILE = _BACKEND / "data" / "eval" / "eval_rag.jsonl"
_OUT_FILE = _BACKEND / "data" / "eval" / "judge_agreement.json"

N_JUDGE = 5
MODEL = "claude-haiku-4-5"

_SYSTEM = (
    "You are evaluating whether a retrieved passage correctly answers "
    "a question about scikit-learn."
)

_USER_TMPL = """Question: {question}

Passage: {ground_truth_text}

Does this passage correctly answer the question? Answer "yes" or "no" on the first line, then one sentence explaining why."""


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY not set.")

    if not _EVAL_FILE.exists():
        raise SystemExit(f"Eval file not found: {_EVAL_FILE}")

    triples = [json.loads(line) for line in _EVAL_FILE.read_text().splitlines() if line.strip()]
    sample = triples[:N_JUDGE]

    from anthropic import Anthropic
    from anthropic.types import TextBlock

    client = Anthropic(api_key=api_key)

    results = []
    print(f"\n{'─' * 72}")
    print(f"{'ID':<8} {'Human':>6} {'Claude':>6}  {'':>2}  Reason")
    print(f"{'─' * 72}")

    for triple in sample:
        qid: str = triple["question_id"]
        question: str = triple["question"]
        text: str = triple["ground_truth_text"]

        user_msg = _USER_TMPL.format(question=question, ground_truth_text=text)
        response = client.messages.create(
            model=MODEL,
            max_tokens=150,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = next((b.text for b in response.content if isinstance(b, TextBlock)), "")
        lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
        verdict = lines[0].lower().rstrip(".") if lines else "unknown"
        reason = lines[1] if len(lines) > 1 else ""

        agree = verdict == "yes"
        results.append(
            {
                "question_id": qid,
                "question": question,
                "human": "yes",
                "claude": verdict,
                "agree": agree,
                "reason": reason,
            }
        )

        mark = "✓" if agree else "✗"
        print(f"{qid:<8} {'yes':>6} {verdict:>6}  {mark}   {reason[:52]}")

    print(f"{'─' * 72}")
    n_agree = sum(1 for r in results if r["agree"])
    print(f"\nAgreement: {n_agree}/{N_JUDGE} ({n_agree / N_JUDGE:.0%})")

    payload = {
        "n_judged": N_JUDGE,
        "n_agree": n_agree,
        "agreement_pct": round(n_agree / N_JUDGE * 100, 1),
        "model": MODEL,
        "human_label": "yes",
        "triples": results,
    }
    _OUT_FILE.write_text(json.dumps(payload, indent=2))
    print(f"Saved to {_OUT_FILE}")


if __name__ == "__main__":
    main()
