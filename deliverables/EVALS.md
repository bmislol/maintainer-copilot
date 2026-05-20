# EVALS.md

Last updated: 2026-05-18

Two golden eval suites gate CI. Thresholds live in `eval_thresholds.yaml` at the repo root. A regression below threshold blocks merge. Every run writes an `eval_report.json` to MinIO and is diffed against the previous green build.

### 1. Classification (Phase 2.1 + Phase 2.2)

Three-classifier comparison plan from D-012 (Phase 2.3): classical / fine-tuned / LLM.
Phase 2.2 ships the first two; Phase 2.3 adds the LLM.

| Classifier | Test Accuracy | Test Macro-F1 | F1 bug | F1 feature | F1 docs | F1 question |
|---|---|---|---|---|---|---|
| **DistilBERT (fine-tuned)** | **0.8478** | **0.7462** | 0.9255 | 0.8148 | 0.8845 | 0.3600 |
| LogReg + TF-IDF (classical) | 0.8201 | 0.6977 | 0.8961 | 0.7826 | 0.8562 | 0.2558 |
| Claude (LLM, structured output) | TBD Phase 2.3 | — | — | — | — | — |

**Splits:** 2690 train / 576 val / 578 test, time-based (test strictly newer than train). See D-008.

**Threshold:** modelserver refuses to boot if `test_macro_f1 < 0.60`. Currently 0.7462 — 14 points of headroom (see D-009).

**Notable observation.** Both classifiers struggle most on the `question` class (F1 0.36 / 0.26). This is expected and documented in D-007 — the question label is a maintainer-workflow proxy (`Needs Triage` + `help wanted`), not a literal question tag, so the class signal is noisy by construction. Phase 2.3's LLM baseline is expected to outperform here because Claude can reason about "is this a question?" without depending on label cleanness.

**Per-class outliers.** `question` at F1 0.36 reflects the noisy proxy labeling defined in D-007 (`Needs Triage` + `help wanted` mapped to `question`). The fine-tuned model struggles with the class as expected. Phase 2.3's LLM baseline is the comparison point — Claude is expected to outperform on this class.

### 1.1 Golden Set

- 25 examples, hand-curated.
- Stored at `backend/app/eval/classification/golden_set.jsonl`.
- Each row: `{ "issue_id", "title", "body", "label" }`.
- **Strict separation:** golden-set examples are not in the training set, the validation set, or the test set used in the three-way model comparison. They are an independent held-out slice.

### 1.2 Models Evaluated

The same golden set is scored against all three classifiers from the deep-learning track:

1. Classical ML baseline (TF-IDF + linear model). Phase 2.2.
2. Fine-tuned transformer encoder. Phase 2.1.
3. Claude LLM baseline. Phase 2.3.

### 1.3 Metrics

- Accuracy.
- Macro-F1.
- Per-class F1 (bug, feature, docs, question).
- Confusion matrix.

Latency (p50, p95) and cost-per-call are reported for the deployed model only.

### 1.4 Thresholds

Committed in `eval_thresholds.yaml`. Filled by Phase 2.4 once real numbers exist. Initial reserved keys:

```yaml
classification:
  macro_f1_min: TBD
  per_class_f1_min:
    bug: TBD
    feature: TBD
    docs: TBD
    question: TBD
```

A threshold of zero is rejected by the API's refuse-to-boot check.

### 1.5 CI Gate

Job: `.github/workflows/eval-classification.yml` (added in Phase 2.4).

On every push to `main` and every pull request:

1. Build the modelserver image.
2. Boot the modelserver container.
3. Run `python -m app.eval.classification.run_eval` against the golden set.
4. Compare results to `eval_thresholds.yaml`.
5. Upload `eval_report.json` as a CI artifact and to MinIO.
6. Fail the job if any threshold regresses.

---

## 2. RAG Eval

### 2.1 Golden Set

- 25 question / ideal-answer / ground-truth-chunks triples.
- Stored at `backend/app/eval/rag/golden_set.jsonl`.
- Each row: `{ "question", "ideal_answer", "ground_truth_chunks": [chunk_id, ...] }`.

### 2.2 Metrics

**Retrieval metrics** (computed against ground-truth chunk IDs):

- Hit@5.
- MRR@10.

**Generation metrics** (computed against the ideal answer):

- Faithfulness (the answer is grounded in the retrieved chunks).
- Answer relevancy (the answer is on-topic for the question).

Tool: RAGAS or a frozen Claude judge. Choice and justification: TBD (Phase 3.4).

### 2.3 Human Agreement Check

5 of the 25 golden items are hand-labeled by the project owner against the same metrics. The agreement number between the human labels and the judge's labels is reported in DECISIONS.md (Phase 3.4). If agreement is low, the judge model is reconsidered.

### 2.4 Thresholds

Committed in `eval_thresholds.yaml`. Filled by Phase 3.4. Reserved keys:

```yaml
rag:
  hit_at_5_min: TBD
  mrr_at_10_min: TBD
  faithfulness_min: TBD
  answer_relevancy_min: TBD
```

### 2.5 CI Gate

Job: `.github/workflows/eval-rag.yml` (added in Phase 3.4).

On every push to `main` and every pull request:

1. Build the api image.
2. Boot api + db + redis + modelserver.
3. Run `python -m app.eval.rag.run_eval` against the golden set.
4. Compare results to `eval_thresholds.yaml`.
5. Upload `eval_report.json` as a CI artifact and to MinIO.
6. Fail the job if any threshold regresses.

---

## 3. Redaction Test (Separate CI Job)

Not a golden-set eval but on the same blocking-merge tier. Added in Phase 3.5.

A single test asserts that a message containing a fake API key (e.g. `sk-test-FAKE-not-real`) does not appear unredacted in:

- structured log output,
- Langfuse trace spans (input/output captures),
- memory writes (short-term Redis values, long-term pgvector rows).

The test exercises a full chatbot turn so the redaction layer is hit at every boundary.

---

## 4. Final Submission Numbers

Filled by Phase 5.1.

| Metric | Value |
|---|---|
| Classification — Classical macro-F1 | TBD |
| Classification — Fine-tuned macro-F1 | TBD |
| Classification — LLM macro-F1 | TBD |
| Deployed model | TBD |
| Embedding model | TBD |
| RAG hit@5 | TBD |
| RAG MRR@10 | TBD |
| RAG faithfulness | TBD |
| RAG answer relevancy | TBD |
| Long-term memory type | TBD |
| Widget bundle size (gzipped) | TBD |
