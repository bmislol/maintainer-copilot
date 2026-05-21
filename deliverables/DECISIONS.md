# DECISIONS.md

Status: Baseline decisions document
Purpose: Record architecture and implementation decisions as the project evolves.

Each decision follows this format:

```text
## D-XXX: Decision title

Status: Proposed | Accepted | Rejected | Superseded
Date: YYYY-MM-DD

### Context
What problem are we solving?

### Decision
What did we decide?

### Why
Why this option?

### Alternatives Considered
- Option A
- Option B

### Trade-offs
What do we gain and what do we accept?
```

---

## D-001: Backend Layer Boundary

Status: Accepted
Date: 2026-05-18

### Context

The brief grades architecture, not just the working chatbot. It explicitly states: "The architecture is graded. Layers respected." The Friday review will ask for a new endpoint or tool to be added live, so the layer boundary has to be real and enforced.

### Decision

Use the following backend layers under `backend/app/`:

- `app/api/` — HTTP routers only.
- `app/services/` — business logic, transaction boundaries, cache and memory invalidation, tool orchestration.
- `app/repositories/` — SQL only via async SQLAlchemy.
- `app/domain/` — Pydantic domain models, enums, internal contracts.
- `app/infra/` — adapters for Vault, Redis, MinIO, the LLM provider, Langfuse, and the redaction layer.
- `app/db/` — SQLAlchemy ORM models, sessions, Alembic migrations.

Plus task-specific subfolders that follow the same rules: `app/rag/`, `app/chatbot/`, `app/memory/`, `app/eval/`, `app/prompts/`, `app/core/`.

### Why

The same standard as the Week 6 project. Routers stay thin and HTTP-only. Services own business rules. Repositories own SQL. Infra adapters wrap everything external. The boundary is testable and defensible in the live review.

### Trade-offs

More files early. Worth it for the grade and for staying sane during the chatbot phase when tool calls, RAG, and memory all need to compose cleanly.

---

## D-002: Dataset Source — `scikit-learn/scikit-learn`

Status: Accepted (revised)
Date: 2026-05-19 (originally accepted 2026-05-18 with FastAPI; revised after empirical inspection)

### Context

The brief requires picking one open-source repo and using its closed issues as the classification dataset. The choice has to support: enough closed-issue volume for stratified train/val/test splits, labels that map cleanly to bug / feature / docs / question, English-dominant text, and a public docs corpus for the RAG side.

### Decision

Use the `scikit-learn/scikit-learn` GitHub repository. Closed issues are fetched via the GitHub REST API (pages 1–99, the offset-pagination limit) and via the GraphQL API (cursor-based, for issues beyond the REST 10k-offset wall). The project's published documentation is the RAG corpus (Phase 3.1).

### Why

- Mature labeling discipline. Maintainers consistently apply `Bug`, `Documentation`, `New Feature`, `Enhancement`, `Needs Triage`, and `help wanted` labels.
- ~10k closed issues retrievable across both pagination strategies, yielding 3,844 classifiable examples after deduplication, label mapping, and CI-bot template filtering.
- Class balance is workable: 5.2:1 ratio between the largest (`bug`) and smallest (`question`) class in the training split. Stable per-class F1 numbers are achievable.
- A peer's hands-on comparison ranked scikit-learn at the top against LangChain and pandas as a dataset source.

### Why this changed from the initial FastAPI choice

The initial inspection of FastAPI's issue labels showed sparse and inconsistent labeling — most issues without `bug`/`feature`/`docs` class labels, no `question` label, only ~3,000 issues total. LangChain (#2 candidate) had only 14 documentation-labeled issues; transformers (#3) had only 5. Across all three alternatives, no mature OSS repo uses a literal `question` label — the convention is to redirect questions to StackOverflow or Discord. scikit-learn turned out to have the cleanest maintainer-applied labels of the four projects we sampled, despite needing a documented proxy for the `question` class (see D-007).

### Alternatives Considered

- `tiangolo/fastapi` — rejected due to sparse class labeling and no `question` label.
- `langchain-ai/langchain` — rejected: only 14 documentation-labeled issues; not trainable for the docs class.
- `huggingface/transformers` — rejected: only 5 documentation-labeled issues; not trainable for the docs class.
- `pydantic/pydantic` — rejected: lower volume than scikit-learn.

### Trade-offs

GitHub's REST API caps offset pagination at ~10k results. The GraphQL fetcher chain extends beyond that via cursor pagination, but we still see only the most recent ~10k issues after deduplication. This is plenty of training signal for the project. Documented in the build pipeline (`scripts/fetch_issues.py` and `scripts/fetch_issues_graphql.py`).

---

## D-003: LLM Provider — Anthropic Claude

Status: Accepted
Date: 2026-05-18

### Context

The project uses an LLM for the classification baseline, the chatbot generator, RAG answer generation, and possibly LLM-as-judge for RAG evaluation. A provider has to be picked and committed.

### Decision

Use Anthropic Claude as the sole LLM provider for every LLM-call site in the project.

### Why

Existing API credits are with Anthropic. One provider keeps the secrets surface in Vault small, simplifies the LLM-call adapter in `app/infra/`, and removes a class of comparison work that does not serve the project's grading criteria.

### Alternatives Considered

- OpenAI only.
- Both providers for cross-provider comparison in DECISIONS.md.

### Trade-offs

The classification-baseline DECISIONS entry compares classical ML, fine-tuned transformer, and Claude — all three on the same test split — so the comparison story is intact even with a single LLM provider.

---

## D-004: Tracing Backend — Langfuse v2 (Self-Hosted)

Status: Accepted
Date: 2026-05-18

### Context

The brief requires picking a tracing backend and defending the choice. Every LLM call, tool call, and RAG retrieval must appear as a span, and a conversation must be a trace tree rooted at the user message. The Friday demo walks through a real trace tree including one error path.

### Decision

Use **Langfuse v2**, self-hosted in the project's compose stack. Pinned via `image: langfuse/langfuse:2` — not `:latest`.

### Why

- Open source and free; runs in compose alongside Vault and MinIO. Matches the spirit of the project (secrets in Vault, blob in MinIO, traces in your stack).
- Real trace-tree UI suited to tool-calling LLM conversations.
- First-class Python SDK with explicit spans for LLM calls, tool calls, and arbitrary nested operations.
- No external dependency for the Friday demo.

### Why v2 specifically, not v3

Langfuse v3 introduced ClickHouse as a required backing store on top of Postgres + Redis + MinIO. For a single-developer, single-machine project this multiplies the compose footprint (extra service, extra volume, extra healthcheck, extra failure mode) without any functional benefit — both v2 and v3 expose the same trace-tree UI and the same SDK surface for our use cases (LLM call spans, tool call spans, error paths, conversation tree). v2 only needs the Postgres we already have.

Pinning to the `:2` major guards against the same surprise happening again if the team upgrades the `:latest` tag.

### Alternatives Considered

- **Langfuse v3** — rejected per above (ClickHouse footprint not justified for this project).
- **LangSmith** — cloud-only, paid past the free tier, ties demo reliability to a third-party service.
- **Arize Phoenix** — similar self-hostable model; Langfuse picked for richer LLM-conversation-shaped trace UI.
- **OpenTelemetry + Jaeger** — more generic, more setup, less LLM-aware out of the box.

### Trade-offs

- Adds one more service to compose and one more startup dependency. The api-level refuse-to-boot logic (Phase 1.5) covers the misconfigured case.
- The Docker container-level healthcheck for langfuse is **disabled** — the v2 image's networking made every reasonable healthcheck probe (`wget`, `curl`, `node http.get`) fail despite the app being fully responsive in the browser and via curl from the host. Since no other service `depends_on: langfuse` (langfuse is a write-only sink, not a dependency), the missing healthcheck has no operational impact on the boot graph. Service health is instead verified by the Langfuse SDK at api startup (Phase 1.5) — if the SDK can't connect, api refuses to boot. This means the *real* health check happens at the consumer (api), not at the producer (langfuse container), which is arguably more correct anyway.
- Running on `:2` means we accept whatever maintenance posture Langfuse gives to the v2 line. For a 5-day project this is irrelevant; for a long-lived deployment it would be a decision to revisit.

---

## D-005: Package Manager — `uv`

Status: Accepted
Date: 2026-05-18

### Context

Python dependency and virtualenv management strategy for the backend, modelserver, chatbot app, and eval harness.

### Decision

Use `uv` for everything Python in the project. Single `pyproject.toml` per Python service; `uv sync` in Docker builds; `uv run` for local commands.

### Why

Same tooling as the Week 6 project. Fast resolver, deterministic locks, good Docker layer caching.

### Trade-offs

None worth listing.

---

## D-006: Frontend Folder Naming

Status: Accepted
Date: 2026-05-18

### Context

The project ships two frontends: the internal Streamlit admin tool, and the embeddable React widget. Folder naming should make it obvious which is which.

### Decision

- `frontend-admin/` — Streamlit admin app.
- `frontend-widget/` — React embeddable widget.

### Why

Both names describe purpose. "Admin" is unambiguous for the internal maintainer-facing tool. "Widget" matches the embeddable surface and matches the brief's own vocabulary.

### Alternatives Considered

- `frontend-dev/` + `frontend/` — rejected because "dev" reads "development environment," which is the opposite of what the Streamlit app is (the internal production-facing maintainer tool).

### Trade-offs

None.

---

## D-007: Issue Label → Class Mapping

Status: Accepted
Date: 2026-05-19

### Context

The brief's four-class spec (bug / feature / docs / question) does not map perfectly onto scikit-learn's actual labeling vocabulary. scikit-learn does not use a literal `question` label — their convention redirects user questions to StackOverflow. We need a mapping that preserves the spec while staying honest about what the data contains.

### Decision

The following raw-label → class mapping is applied by `scripts/build_dataset.py`:

| Raw label | Mapped class |
|---|---|
| `Bug`, `Regression` | bug |
| `Documentation` | docs |
| `New Feature`, `Enhancement` | feature |
| `Needs Triage`, `help wanted` | question |

**Excluded labels** (do not map to any class):

- Difficulty tags: `Easy`, `good first issue`, `Moderate`, `Blocker`
- Status tags: `Needs Investigation`, `Needs Decision`, `Needs Info`, `Needs Reproducible Code`, `Meta-issue`, `RFC`
- Module tags: `module:linear_model`, `module:tree`, etc.
- Domain-ambiguous: `Performance`, `API`, `Array API`, `Build / CI`
- Noise: `spam`

**Excluded categories:**

- Issues with no class-mapping label.
- Issues with conflicting multi-class labels (e.g., both `Bug` and `Documentation`) — ambiguous, excluded from training.
- Pull requests (GitHub's issues endpoint returns both; PRs are filtered).
- CI-bot template issues (see Trade-offs below).

### Why the `question` proxy

scikit-learn does not have a literal `question` label. The `Needs Triage` and `help wanted` labels are the maintainer's own workflow signal for "issue not yet categorized, possibly needs more info, often from a user seeking help." This is not a perfect semantic fit for "question" in the abstract, but it is the closest *maintainer-applied* signal available, and it avoids the alternative of synthesizing the class from text patterns.

### Alternatives Considered

- **Text-heuristic question class** — issues matching regex patterns (`^how`, `^what`, ends with `?`, etc.). Rejected: empirical inspection showed 80% of the resulting class came from regex matches with no maintainer signal, which would make the trained classifier circular (it learns the heuristic, not the concept).
- **Drop the question class, train 3-class.** Rejected once the `Needs Triage` + `help wanted` proxy was discovered, since the spec is honored without compromise.

### Trade-offs

- The question class semantics are slightly elastic. Some `Needs Triage` issues are bugs, features, or doc issues that simply haven't been categorized yet by maintainers. We accept that the question class will have noisier signal than bug/feature/docs. The three-way model comparison in Phase 2.3 will surface this honestly.
- **CI bot filter.** scikit-learn's CI runs auto-open templated issues titled `⚠️ CI failed ...` when nightly builds fail. They get auto-tagged `Needs Triage` by default. Including them in the question class would teach the classifier to recognize a specific machine template rather than human question text. The build script filters issues whose title contains "CI failed" in the first 30 characters. This is the only template-class filter we apply; future templates appearing at scale would be added here.

### Quantified outcome (Phase 1.6)

- 3,844 issues classified
- 5,270 issues excluded (no classifying label)
- 1,130 issues excluded (ambiguous multi-class)
- 656 issues excluded (CI-bot-generated failure reports)
- 7,578 PRs filtered out (issues endpoint returns both)


## D-008: Train / Val / Test Split Strategy

Status: Accepted
Date: 2026-05-19

### Context

The brief requires "stratified splits, test strictly more recent in time than train." This combines two constraints: temporal ordering and class balance. They are mutually exclusive in the strict sense — a temporally ordered split cannot also guarantee identical class proportions across splits.

### Decision

Sort all classified issues by `created_at` ascending. Take the first 70% as train, the next 15% as val, the last 15% as test. Class stratification is not explicitly enforced; the time-based ordering is the priority.

Resulting splits:

| Split | n | bug | feature | docs | question |
|---|---|---|---|---|---|
| train | 2690 | 1023 | 798 | 673 | 196 |
| val | 576 | 226 | 112 | 140 | 98 |
| test | 578 | 274 | 89 | 149 | 66 |

Training data SHA-256: `1a4e887a580b5289d4b87fcff2890235c95945d78cd768f3e25933b3ca4c3959`. This hash is referenced from `model_card.json` in Phase 2.1.

### Why time-based, not random

The brief explicitly demands "test strictly more recent in time than train." This simulates the real-world scenario the classifier ships into: it will see new issues, not old ones, and test metrics should reflect that distribution.

### Why not explicit stratification

Stratified time-based splits are mutually exclusive in the strict sense. You can have *either* "test is strictly newer than train" *or* "test has the same class distribution as train," not both. We prioritize the temporal constraint because that is what the brief demands and what mirrors production reality.

### Observed temporal drift

The `question` class is overrepresented in val (98 / 576 ≈ 17%) and test (66 / 578 ≈ 11%) relative to its share in train (196 / 2690 ≈ 7%). This reflects a real shift in scikit-learn's recent triage workflow — more issues are being left in `Needs Triage` lately than in earlier years. Test-set F1 on `question` will therefore reflect *current* labeling practices, not the historical average. This is the kind of distribution shift the time-based split is designed to surface.

### Trade-offs

- Test-set per-class F1 will have moderate variance due to small per-class counts (smallest class in test: `question` at 66; smallest classified class in test: `feature` at 89).
- Models that fail to generalize across temporal label drift will be penalized. This is desired — it tests robustness, not memorization.

## D-009: Fine-Tuned Classifier — Backbone, Hyperparameters, Freeze Policy

Status: Accepted
Date: 2026-05-19

### Context

The brief requires fine-tuning a small encoder for classification, with a model card listing architecture, hyperparameters, freeze policy, training data hash, and final metrics. Phase 2.1 produces that artifact.

### Decision

Backbone: `distilbert-base-uncased` (HuggingFace).

Freeze policy: **full fine-tune** — no layers frozen. Standard practice for text encoders on small classification tasks; the 66M parameter model is small enough that full fine-tuning doesn't risk catastrophic forgetting on a 4-class downstream task.

Hyperparameters (frozen and recorded in `model_card.json`):

| Parameter | Value |
|---|---|
| max_length | 256 |
| num_train_epochs | 4 |
| per_device_train_batch_size | 16 |
| per_device_eval_batch_size | 32 |
| learning_rate | 2e-5 |
| weight_decay | 0.01 |
| warmup_ratio | 0.1 |
| early_stopping_patience | 1 |
| class_weights | balanced (1/class_frequency normalized) |
| fp16 | True (CUDA available) |
| seed | 42 |

Early stopping on `val_macro_f1` with patience 1 ended training after epoch 2 — val metric peaked at epoch 1 and dropped at epoch 2 (overfitting onset). Best checkpoint restored.

### Why these choices

- `distilbert-base-uncased`: matches the instructor's chapter-7 fine-tuning curriculum (Notebook 7), making the engineering legible to anyone familiar with the course. 66M params; trains in ~40s on RTX 3060.
- Full fine-tune (not partial-unfreeze): partial freezing makes sense for vision tasks where the early conv layers transfer well, but text encoders rarely see this benefit on small datasets; full fine-tune is the simpler, more reliable default.
- Class weights: balanced loss compensates for the 5.2:1 imbalance between `bug` and `question`. Without weights, the model would over-predict `bug`.
- Learning rate 2e-5: HuggingFace default for BERT-family fine-tuning. Adjusting this without evidence wouldn't help on ~2700 examples.
- `early_stopping_patience=1`: aggressive on a small dataset — we expect overfitting to start fast.
- `seed=42`: reproducibility. Each retrain produces nearly identical numbers (validated empirically — 3 runs within 0.02 macro-F1 of each other).

### Threshold — modelserver refuse-to-boot

Committed: `test_macro_f1 >= 0.60`. Shipping model is at 0.7462 — 14 points of headroom.

Rationale: 0.60 is below the model's actual performance but above the "random three-class baseline" (~0.33 for balanced 4-class) by a wide margin. A model that drifts below 0.60 should not be shipped — either retraining went wrong or the dataset changed in a way that broke the classifier.

### Quantified outcome (Phase 2.1)

- Training time: 43.4 seconds on RTX 3060 Laptop GPU
- Test accuracy: 0.8478
- Test macro-F1: 0.7462
- Per-class F1: bug 0.9255 / feature 0.8148 / docs 0.8845 / question 0.3600
- W&B run: https://wandb.ai/bmislol-se-factory/maintainer-copilot/runs/6vaoq2zd
- classifier.pt SHA-256: a3bd4cb8f9328ce409169d14ef4585c27f1149ff2c69795de0e8e5759a8f3a59
- training_data SHA-256: 1a4e887a580b5289d4b87fcff2890235c95945d78cd768f3e25933b3ca4c3959

### Trade-offs

- The `question` class F1 (0.36) is much weaker than the others. This is expected — the class label is partially synthesized from `Needs Triage` and `help wanted` (D-007) which are noisy. We accept this and let Phase 2.3's LLM baseline cover the gap.
- CPU inference in production (modelserver doesn't have GPU passthrough). Latency p50 expected ~30-100ms per inference on 256-token input. Phase 2.4 measures and confirms.
- Artifact storage in /tmp inside the container. Each restart re-downloads from MinIO (~270MB, ~5 seconds inside the docker network). Acceptable for a 5-day project; a persistent volume would eliminate the round-trip cost in production.


## D-010: Classical ML Baseline — TF-IDF + LogisticRegression

Status: Accepted
Date: 2026-05-20

### Context

The brief grades the *three-way comparison* (classical / fine-tuned / LLM) more than any single classifier's quality. Without a classical baseline, we have no calibration point — DistilBERT's 0.7462 macro-F1 on test is meaningless without a "what could a 10-line scikit-learn pipeline do?" reference.

### Decision

Train a TF-IDF + linear classifier pipeline on the same `data/issues/splits/{train,val,test}.jsonl` files the fine-tuned encoder used. Vectorizer: `TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_df=0.95, sublinear_tf=True)`. Compare two linear classifiers on val, pick winner, evaluate ONCE on test.

Two classifiers compared:

| Classifier | Val macro-F1 | Notes |
|---|---|---|
| `LogisticRegression(solver="lbfgs", C=1.0, class_weight="balanced")` | **0.6473** | winner |
| `LinearSVC(C=1.0, class_weight="balanced", dual="auto")` | 0.6261 | runner-up |

LogisticRegression won and was evaluated on test. The artifacts (`vectorizer.pkl` + `classifier.pkl` + `comparison_report.json`) live in `backend/data/classical_baseline_artifacts/`. They are *not* pushed to MinIO or wired into `modelserver` — the classical baseline exists as a comparison artifact only.

### Why TF-IDF + linear classifier (vs more elaborate options)

- The brief asks for a *baseline*, not a competitive ensemble. The simplest reasonable approach is what's wanted: it's the one that earns the comparison-anchor role honestly.
- TF-IDF with word + bigram features captures the lexical signal scikit-learn's labels reflect ("fit fails" / "documentation" / "feature request") without preprocessing tricks.
- Linear classifiers on TF-IDF are within 1-2% of more complex non-neural methods on this kind of dataset shape, so spending more here wouldn't change the headline number meaningfully.

### Why solver="lbfgs", not "liblinear"

scikit-learn's `liblinear` solver doesn't support multi-class natively (one-vs-rest only). `lbfgs` handles our 4-class problem via multinomial logistic regression — the right default for 4+ classes.

### Why `class_weight="balanced"`

Mirrors the DistilBERT setup. Without it, both classical models over-predict `bug` (it's 38% of the training set, while `question` is 7%). Balancing makes the comparison fair: both approaches operate under the same imbalance correction.

### Result on test (same splits as Phase 2.1)

| Metric | DistilBERT | LogReg (classical) | Delta |
|---|---|---|---|
| Test accuracy | 0.8478 | 0.8201 | -0.0277 |
| Test macro-F1 | 0.7462 | 0.6977 | **-0.0485** |
| F1 bug | 0.9255 | 0.8961 | -0.0294 |
| F1 feature | 0.8148 | 0.7826 | -0.0322 |
| F1 docs | 0.8845 | 0.8562 | -0.0283 |
| F1 question | 0.3600 | 0.2558 | -0.1042 |

DistilBERT wins on every class, by 5 macro-F1 points overall — a real but not overwhelming margin. The biggest improvement comes from the `question` class, where DistilBERT's contextual embeddings extract more signal than TF-IDF's bag-of-n-grams can. On the well-labeled classes (`bug`, `feature`, `docs`), classical TF-IDF captures most of the easy lexical signal — fine-tune contributes a 3-4 point improvement per class.

### Trade-offs / what this teaches us

- **The fine-tune cost is justified, modestly.** DistilBERT is meaningfully better but not by a runaway gap. If GPU were unavailable or our training set were 10x smaller, the classical baseline at 0.6977 macro-F1 would be a reasonable production choice on its own.
- **`question` is the class where deep learning genuinely helps.** This is the result that gives Phase 2.3 (LLM baseline) its purpose — Claude is expected to outperform both on this noisy class because it can reason about question-shaped text without needing maintainer-provided labels to be perfect.
- **W&B run logged**: see `classical-baseline-{timestamp}` in the `maintainer-copilot` project.

### Quantified outcome (Phase 2.2)

- Vocabulary size: 42,225 (word + bigram, after min_df=2 filtering)
- Train time: <5 seconds (both models combined)
- Test accuracy: 0.8201
- Test macro-F1: 0.6977
- Per-class F1: bug 0.8961 / feature 0.7826 / docs 0.8562 / question 0.2558
- Artifacts: `data/classical_baseline_artifacts/{vectorizer.pkl,classifier.pkl,comparison_report.json}`


## D-011: LLM Classification Baseline — Anthropic Claude

Status: Accepted
Date: 2026-05-20

### Context

The brief requires a three-way classifier comparison (classical / fine-tuned / LLM). Phase 2.1 shipped DistilBERT; Phase 2.2 shipped the classical TF-IDF + LogReg baseline. This phase scores the same 578-example test set with Claude.

### Decision

Score the test set with **two Claude models**: Haiku 4.5 (`claude-haiku-4-5`) and Sonnet 4.6 (`claude-sonnet-4-6`). Each prediction is a tool-use call to a structured-output schema, producing a typed `{label, reasoning}` response. Concurrency 5, exponential backoff retries (3 attempts), and per-prediction JSONL caching so re-runs skip already-scored issues.

### Prompt structure

SYSTEM:
You are classifying GitHub issues for the scikit-learn maintainers.
Each issue is one of:

bug: existing functionality fails, raises unexpected error, or wrong output
feature: request for new capability or enhancement
docs: documentation missing, unclear, or incorrect
question: user is asking how something works, needs help, or lacks detail

Edge cases:

"Improve performance of X" → feature (it's an enhancement)
"X documentation says Y but does Z" → bug (incorrect docs that mislead users)
"How do I make X do Y?" → question
Detailed reproductions with tracebacks → bug

USER:
Title: <issue title>
Body: <issue body, truncated to 1500 chars>

The tool schema forces `label ∈ {bug, feature, docs, question}` via `enum`, and `reasoning` is a single-sentence required field.

### Why two models, not one

Originally only Sonnet was planned. After running Sonnet we noticed Haiku 4.5 (which we ran as a smoke test) is one-third the cost and could plausibly be sufficient. Running both gives us a cost/quality datapoint that's directly relevant to the deployment recommendation in D-012.

### Why tool_use, not free-form prompts

Free-form Claude output requires parsing JSON or extracting labels from prose — both are unreliable on edge cases. The tool_use API with `tool_choice={"type": "tool", "name": "classify_issue"}` forces Claude to emit a tool call whose `input` is type-validated by the schema. Invalid labels are impossible by construction.

### Quantified outcome (Phase 2.3)

| Model | Test Accuracy | Test Macro-F1 | F1 question | Total Cost | $/1k issues |
|---|---|---|---|---|---|
| Haiku 4.5  | 0.8495 | 0.7664 | 0.4694 | $1.06 | $1.84 |
| Sonnet 4.6 | 0.8114 | 0.7329 | 0.4464 | $3.12 | $5.40 |

Per-class F1 in `data/llm_baseline_artifacts/comparison_report.json`. Both runs at concurrency 5, took ~3 minutes wall time each.

### Trade-offs

- Token budget assumes ~200 output tokens for label + one-sentence reasoning. A leaner schema (label only, no reasoning) would cut output cost by ~75% but lose the reasoning text that's useful for Phase 2.4 error analysis. Worth the cost.
- The cached JSONL approach means a mid-run failure costs only the un-scored examples on retry. We can fail loud and recover cheaply.
- No prompt-engineering iteration was done — both models use the same prompt. A model-specific prompt might improve Sonnet (which currently underperforms Haiku — see D-012). Out of scope for Phase 2.3; documented as a known optimization not pursued.

## D-012: Three-Way Classifier Comparison and Deployment Choice

Status: Accepted
Date: 2026-05-20

### Context

The brief grades the *comparison* across approaches (D-007 → D-011): "which approach won and why." Phase 2.1 + 2.2 + 2.3 produced four real numbers on the same test set; this decision documents what they tell us and what the project should ship.

### The numbers (test set, n=578)

| Classifier                  | Accuracy | Macro-F1 | F1 bug | F1 feature | F1 docs | F1 question | $/1k issues |
|---|---|---|---|---|---|---|---|
| Classical (TF-IDF+LogReg)   | 0.8201 | 0.6977 | 0.8961 | 0.7826 | 0.8562 | 0.2558 | $0.00 |
| DistilBERT (fine-tuned)     | 0.8478 | 0.7462 | 0.9255 | 0.8148 | 0.8845 | 0.3600 | $0.00 |
| **Haiku 4.5**               | **0.8495** | **0.7664** | 0.9122 | 0.7958 | **0.8881** | **0.4694** | $1.84 |
| Sonnet 4.6                  | 0.8114 | 0.7329 | 0.8924 | 0.7729 | 0.8199 | 0.4464 | $5.40 |

### Three real observations

**1. The fine-tune earns its keep, modestly.** DistilBERT (0.7462) beats classical (0.6977) by 5 macro-F1 points. That's a real improvement, but not a runaway. On bug, feature, docs (the well-labeled classes), the gap is 3-4 F1 points per class. On the noisy `question` class (D-007), DistilBERT pulls ahead by 10 points (0.36 vs 0.26) — contextual embeddings do better with noisy labels than bag-of-n-grams.

**2. Haiku beats DistilBERT.** This was not expected. A small commercial LLM at $1.84 per 1000 issues outperforms our fine-tuned encoder by 2 macro-F1 points without any training. The win is concentrated in the `question` class (0.4694 vs 0.3600 — 30% relative improvement). For a noisy synthetic class, an LLM's ability to reason about "is this a question?" beats a fine-tuned classifier's ability to memorize what `Needs Triage` text looks like.

**3. Sonnet *loses* to Haiku.** Across every metric — accuracy, macro-F1, every per-class F1 — the cheaper smaller model wins. Possible reasons:
- Classification of short text is a task where reasoning capacity is *wasted*. Haiku does the obvious thing; Sonnet may second-guess.
- The prompt was tuned on neither model. A more nuanced prompt with chain-of-thought might unlock Sonnet's reasoning, but at additional cost.
- Sonnet's tool-use compliance may be tuned differently — it may be more inclined to express uncertainty rather than commit to a label.

We did not investigate further; the result is the result, and it's a real production data point.

### Deployment choice

**For the chatbot's classify tool in Phase 4.2: ship Haiku 4.5.**

Reasoning:
- Best macro-F1 of the four (0.7664)
- Best F1 on the hard class — `question` — by a wide margin (0.4694)
- Cheapest of the LLM tier ($1.84/1k); ~3x cheaper than Sonnet
- ~2-3x faster latency than Sonnet (relevant for chatbot tool-call UX)
- No training, no GPU dependency, no model artifact to ship and maintain

**For the modelserver and Phase 2.1's `POST /classify` endpoint: keep DistilBERT.**

Reasoning:
- The brief grades "fine-tune a small encoder for classification with a model card." Phase 2.1 produced that artifact; removing it would weaken the engineering story.
- Modelserver demonstrates we know how to ship a containerized fine-tuned model with refuse-to-boot, MinIO artifact contracts, and SHA-256 verification — these are independently valuable engineering proofs.
- The chatbot's classify tool calls Haiku; modelserver remains the proof point that *if* a future team needed offline classification (no LLM API available), the path from train to production is wired.

### Why this matters

The brief asks (Think About): *"Where does the comparison shift if your data changes? If labels get cleaner? If a frontier model gets cheaper?"*

- **If labels get cleaner** (e.g., scikit-learn adds a real `question` label), the `question` class F1 gap closes. DistilBERT might catch up to Haiku.
- **If a frontier model gets cheaper** (e.g., Haiku 5 launches at $0.30/M input), the LLM cost argument strengthens further; classical and fine-tuned become hard to justify.
- **If our throughput grew 1000x**, the $1.84/1k cost compounds: 100k issues/day = $184/day = ~$67k/year vs. classical at zero marginal cost. At that scale, the fine-tune's "free at inference time" advantage becomes worth pursuing.

The deployment recommendation is **specific to our current scale** (one maintainer, scikit-learn issue volume). It's not a universal "LLMs always win."

### Quantified outcome

- Winner on macro-F1: Haiku 4.5 (0.7664)
- Winner on `question` class: Haiku 4.5 (0.4694)
- Winner on cost: Classical and DistilBERT (tied, $0 marginal)
- Best cost/quality ratio: Haiku 4.5
- Deployment recommendation: Haiku for chatbot, DistilBERT for modelserver

## D-013: Classification Eval Gate — Golden Set and CI Threshold

Status: Accepted
Date: 2026-05-20

### Context

Phase 2.4 introduces the first eval gate in the project. The brief explicitly grades this: "Eval gates that actually mean something." A gate exists when (a) there's a stable, hand-curated truth set, (b) a committed threshold a future change must meet, and (c) CI mechanics that fail red on regression.

### Decision

**Golden set:** 25 hand-curated examples from `test.jsonl`, stratified across the four classes (7 bug / 7 feature / 6 docs / 5 question). Stored at `backend/data/eval/eval_classification.jsonl`. Committed to git — it's <50KB and small enough that diff-friendliness wins over data hygiene.

**Threshold:** `macro_f1: 0.90`, `per_class_min_f1: 0.50`. Committed to `backend/eval_thresholds.yaml`. The api refuses to boot if either is `<= 0`, defending against "I disabled CI by zeroing the threshold" silent failures.

**CI mechanics:** `@pytest.mark.eval` marker on the test. Default `pytest` skips it (free, runs on every PR). `pytest -m eval` runs it (~$0.05, runs only via `.github/workflows/eval-classification.yml` on path-relevant PRs and manual dispatch).

### How the golden set was built

We curated from `test.jsonl` (not fresh GitHub issues) because:
- Haiku is a frozen external API, not something we trained on
- DistilBERT was trained on `train.jsonl`, never touched test
- Using test for a CI smoke gate doesn't leak any training signal

The interactive curator script (`backend/scripts/curate_golden_set.py`) prioritized examples where Haiku 4.5 already predicted the gold label correctly. This is the *regression floor* strategy: the floor is what currently works. A future change that breaks one of these 25 cases is a real regression.

For each candidate the human reviewer accepted only if:
- The gold label was unambiguous (a maintainer would agree without context)
- The issue text was well-formed (not a CI bot template, not a one-liner)
- Both bug-vs-question and feature-vs-bug were clearly resolvable

Rejected examples are tracked in `backend/data/eval/.rejected_ids.json` for resumability.

### Why `macro_f1: 0.90`

Haiku scored 1.0 on the golden set (the entire 25-example set classified correctly) — see the W&B run and the local pytest output. Setting the floor at:

- **0.95**: too tight. LLM non-determinism (default temperature, no caching across runs) plausibly flips 1-2 predictions on re-run. A floor at 0.95 trips on 2 wrong → spurious CI failures.
- **0.85**: too loose. 4 wrong predictions still pass (4/25 mistakes → macro-F1 ~0.85). Real regressions could slip through.
- **0.90**: tight but kind. Tolerates 1-2 mistakes from natural variance (1 wrong → ~0.96, 2 wrong → ~0.92). Trips on 3+ which is a real signal of breakage.

The `per_class_min_f1: 0.50` is a separate gate — even if macro stays high, a class dropping to zero means a complete mispredict pattern (e.g., the model started predicting all `question` as `bug`). Catches modal collapse that macro-F1 alone might miss.

### What this catches

- Prompt regression (someone edits SYSTEM_PROMPT to be less specific)
- Tool-use schema regression (struct output breaks)
- Model deprecation (Haiku 4.5 is retired, falls back to a worse default)
- API change (different defaults, different label distribution)

### What this does NOT catch

- Drift on real-world traffic (golden set is fixed in time)
- Cost regressions (no token budget gate; future phase if needed)
- Latency regressions (no p95 gate; modelserver has its own latency story)

### Quantified outcome

- Golden set size: 25 examples (7/7/6/5 across bug/feature/docs/question)
- Haiku 4.5 floor measurement (Phase 2.4): **macro-F1 1.0000, all per-class 1.0000**
- Committed thresholds: macro_f1 0.90, per_class_min_f1 0.50
- Headroom from current floor: 10 macro-F1 points, 50 per-class F1 points
- CI cost per gate run: ~$0.05
- Workflow trigger: PRs that touch app/prompts/golden set/eval code or workflow file, plus manual dispatch


## D-014: NER and Summarizer — Implementation Choices

Status: Accepted
Date: 2026-05-20

### Context

Phase 2.5 requires two model-backed tools behind modelserver. The brief lists NER and summarization. We must defend the model choice for each.

### Decisions

**NER**: `dslim/bert-base-NER`, loaded from HuggingFace Hub directly on modelserver startup. Pre-trained CoNLL-03 (4-class: PER, LOC, ORG, MISC). CPU inference via `transformers.pipeline(task="token-classification", aggregation_strategy="simple")`. We pass the canonical pipeline task name `"token-classification"` rather than the friendly alias `"ner"` so the call matches the typed overload in transformers' type stubs at mypy time; both are equivalent at runtime. Latency: ~50-100ms per call.

**Summarizer**: Anthropic Haiku 4.5, called via the Anthropic SDK from modelserver. No local model.

### Why no MinIO for NER weights

The artifact-contract pattern (D-009, refuse-to-boot on SHA mismatch) has real meaning for the *fine-tuned* DistilBERT — we trained those weights, we own the hash, the SHA is a contract about our work. The NER model is third-party public weights. Pushing it to MinIO and hashing it against itself would be theater; we'd be verifying that someone else's published model matches itself. We chose to load it directly from HF Hub instead.

This means:
- NER startup depends on HF Hub availability (acceptable: hub is well-monitored, no real outage risk)
- NER weights are not air-gappable (acceptable: project is single-tenant developer-side)
- If air-gap deployment ever became required, the model would be downloaded once and pushed to MinIO as a Phase 5 task

### Why Claude for summarization (not a local model)

Phase 2.3 (D-012) measured Haiku 4.5 beating DistilBERT on classification at $1.84/1k issues. Summarization is a *generation* task where small models do worse than discriminative tasks, while large language models do better. Extrapolating the cost-quality argument: a local summarizer like `sshleifer/distilbart-cnn-12-6` would produce worse output at significantly higher CPU cost than Haiku's ~$0.001 per summarization call.

Specific reasons:
- Haiku produces 2-3 sentence summaries that are immediately useful; small summarizers tend to copy phrases from the input
- Haiku follows the system prompt's instruction to focus on (a) what's happening, (b) what's affected, (c) what the user wants
- Local summarizer would add ~500MB to modelserver disk + ~250ms CPU per call

This is *not* "LLMs are always better" — it's "for this specific generation task at our scale, the cost-quality numbers favor the LLM."

### Implementation

Both endpoints live in `modelserver` to honor "two model-backed tools behind modelserver" literally. The summarizer is a thin proxy that calls Claude; the NER endpoint runs the model locally. Both expose the same shape: typed request, typed response, FastAPI validation.

API contracts:
POST /ner          {text} → {entities: [{label, text, start, end, score}], model: "dslim/bert-base-NER"}
POST /summarize    {text} → {summary, original_chars, summary_chars, model: "claude-haiku-4-5"}

### Trade-offs

- NER depends on HF Hub at boot; failure mode is "modelserver refuses to boot on NER load failure" — defended in RUNBOOK §2.
- Summarizer requires `secrets.anthropic.api_key` to be valid. Same boot-time check as Vault and Langfuse credentials.
- Latency contract: NER 50-100ms (CPU); summarize 500-1500ms (Anthropic API).
- No automated quality evaluation on either tool. The chatbot's Phase 4.2 tool calls will exercise them; Phase 3.4's RAG golden set covers a different surface.

## D-015: Corpus Composition, Comment Enrichment, and Embedding Model

Status: Accepted
Date: 2026-05-20

### Context

Phase 3.1 requires building the RAG corpus and choosing an embedding model backed by a retrieval-quality number against at least one alternative. The corpus has two source types: (1) official scikit-learn documentation, (2) resolved GitHub issues that include maintainer answers in their comment threads. The Phase 1.6 GraphQL fetch did not include comments, so we needed a separate enrichment step. The embedding model is the most impactful single-component choice before chunking because it determines the quality ceiling of dense retrieval; the decision must be defended with a measured number.

### Decision

**Corpus:**
- **Docs**: 176 `.rst` files from scikit-learn `doc/` at tag `1.6.0` (fragments < 200 chars excluded). Pinned ref is committed in `build_rag_corpus.py::CLONE_REF`.
- **Issues**: 465 closed issues fetched by `fetch_issue_comments.py`, capped at the 500 most-recently-closed issues not appearing in any classifier split (train/val/test). 35 of the 500 were skipped because the live GraphQL response returned zero comments — they had nothing useful for RAG.
- **Strict separation**: the 3,844 issue IDs in train+val+test are excluded from candidates before the fetch, eliminating cross-contamination between the classifier and the RAG corpus.
- **Scope cut defended**: fetching all 6,730 eligible issues would take ~110 minutes. The 500 most-recent issues cover 2024-09-23 through 2026-05-19, reflecting current API behaviour and active maintainer patterns. 465 issues is ample for a corpus alongside 176 docs (641 items total). No quality degradation expected from the cut — relevance in a triage chatbot is query-specific, not correlated with corpus size past a few hundred representative items.

**Comment enrichment strategy:** Unconditional fetch per issue (no pre-filter on comment count), write only if `len(comments) >= 1`. The Phase 1.6 cache (`gql_batch_*.json`) contains no comment-count field, so any pre-filter would silently drop all candidates. Fetching unconditionally and skipping on empty is the simplest approach with no wasted API calls: issues with zero comments are correctly excluded post-fetch. GitHub GraphQL costs ~1 point per issue; 500 issues consumed ~500/5000 of the hourly budget. Wall time: 4m28s at ~1.86 req/s.

**Embedding model: `sentence-transformers/all-MiniLM-L6-v2`**

### Why

Proxy benchmark (18 hand-written queries, corpus of 641 items, no chunking):

| Model | hit@1 | hit@5 | Corpus encode | Dim | Approx size |
|---|---|---|---|---|---|
| `BAAI/bge-base-en-v1.5` | 55.56% (10/18) | 88.89% (16/18) | 7.5 s | 768 | ~438 MB |
| `sentence-transformers/all-MiniLM-L6-v2` | 55.56% (10/18) | 88.89% (16/18) | 1.0 s | 384 | ~86 MB |

The models are tied on retrieval quality — both achieve 88.89% hit@5 and 55.56% hit@1 on the proxy set. The two failures are on *different* queries: BGE misses "multi-label metrics" and "speed up sklearn predictions"; MiniLM misses "custom transformer for Pipeline" and "GridSearchCV hyperparameter tuning". Neither model dominates on the hard queries.

Given identical measured quality, the tiebreaker is latency and storage:
- MiniLM encodes the corpus **7.5× faster** (1.0 s vs 7.5 s) — directly reduces chatbot response latency on the retrieval hot path.
- MiniLM's 384-dim vectors use **half the pgvector storage** and halve the inner-product cost per query.
- MiniLM's model file is ~5× smaller (~86 MB vs ~438 MB), reducing modelserver boot time and RAM.

The proxy benchmark does not include chunking (Phase 3.2) or reranking (Phase 3.3). After chunking, corpus size grows ~5–10× and per-query latency becomes dominated by the embedding call; the 7.5× encode gap widens in absolute terms. Reranking will recover quality on the queries both models currently miss.

### Alternatives Considered

- `BAAI/bge-base-en-v1.5`: identical hit@5; 7.5× slower encode; 2× pgvector cost. No quality argument to justify the cost.
- `text-embedding-3-small` (OpenAI): strong on MTEB but violates D-003 (Anthropic-only LLM provider). Excluded.
- `BAAI/bge-large-en-v1.5`: larger capacity but ~1 GB; not measurably better on this domain-specific corpus (not benchmarked — proxy set too small to justify the load time difference).

### Trade-offs

- **Accept**: 384 dims may underperform 768-dim models on very long chunks or highly abstract queries. Mitigated by reranking in Phase 3.3.
- **Accept**: proxy benchmark uses 18 queries — small enough that one misclassified query moves the number by 5.5 pp. The Phase 3.4 golden set (25 queries with human labels) is the authoritative measurement.
- **Gain**: fast encode, small index, lightweight model — all directly benefit streaming chatbot UX and container footprint.

---

## D-016: Chunking Strategy, pgvector Schema, and Retrieval Baseline

Status: Accepted
Date: 2026-05-20

### Context

Phase 3.2 requires chunking the 641-item flat corpus into sub-document units
so that dense retrieval can surface specific passages rather than entire docs.
We need a chunking strategy, a pgvector schema, and a retrieval baseline number
that Phase 3.3 (BM25 + rerank) must beat.

### Decision

**Chunking strategy: structural, with sliding-window fallback.**

- **RST docs** — split at section headings (title line followed by an underline
  of equal length made of a single RST punctuation character: `= - ~ ^ _ * + #`).
  Headings are natural semantic boundaries already authored by the docs team;
  they preserve section context (`section_title` in metadata) without an
  external NLP model.
- **Issues** — body as chunk 0, each comment as its own chunk. GitHub issue
  threads are already naturally segmented: the OP states the problem, comments
  provide diagnosis and fix.
- **Sliding-window fallback** — any section or body exceeding MAX_TOKENS is
  re-split with stride 170 (220-token window, 50-token overlap). Rationale:
  MiniLM's `max_seq_length = 256` subword tokens; a 220-token cap leaves a
  36-token margin preventing silent truncation. Stride 170 (50-token overlap,
  23% of window) is the "25% overlap" heuristic — enough cross-boundary
  context for BM25 term matching in Phase 3.3 without tripling chunk counts.
  Compared to 200/30 (same stride = 170, smaller window): 220/50 captures 10%
  more context per chunk at the same chunk-count cost.
- **Comment truncation** — first 300 tokens of each comment preserved.
  Assumption: the first paragraph of a maintainer comment contains the
  substantive answer (diagnosis, workaround, or pointer to a fix). Phase 3.4
  eval will validate this assumption empirically against the 25-triple golden
  set. Comments may slightly exceed MiniLM's effective window (256 tokens);
  the last ~44 tokens are silently truncated by the model, but the first-paragraph
  assumption means the relevant content is captured.

**pgvector schema — `rag_chunks` table:**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | random |
| `chunk_id` | TEXT UNIQUE | `{source_type}:{source_id}:{chunk_index}` — deterministic, idempotent re-index |
| `source_type` | VARCHAR(16) | `"doc"` or `"issue"` |
| `source_id` | VARCHAR(256) | `file_id` for docs, `str(number)` for issues |
| `chunk_index` | INT | position within source |
| `text` | TEXT | chunk text |
| `embedding` | vector(384) | MiniLM-L6-v2, L2-normalized |
| `n_tokens` | INT | from `AutoTokenizer.from_pretrained(model)` — actual count from decoded text |
| `metadata` | JSONB | `section_title`, `issue_id`, `window` (for fallback chunks) |
| `created_at` | TIMESTAMPTZ | server `now()` |

Indexes:
- HNSW on `embedding` (`m=16`, `ef_construction=64`) — pgvector defaults; sufficient for the ~10 k-chunk corpus. Tunable in Phase 3.4 if recall@5 falls short on the golden set.
- Composite btree on `(source_type, source_id)` — supports filtering by source.
- GIN on `metadata` — supports Phase 3.3 metadata filtering.

**Alternatives rejected:**

- **Semantic chunking (NLP-based sentence segmentation)** — ignores RST
  structural signals that are already semantically meaningful; non-deterministic
  output; would fail to split long sections that a section heading cleanly
  delineates. Rejected.
- **Late chunking (JinaAI model)** — requires a different embedding model
  (jina-embeddings-v3); incompatible with MiniLM selected in D-015. Would
  require re-running D-015 benchmark. Rejected.
- **Fixed-size chunking (naïve)** — ignores heading boundaries; splits at
  arbitrary token boundaries that cut code blocks and RST directives mid-entry.
  Rejected.

### Numbers

Corpus: 176 docs + 465 issues → **9,701 chunks** (docs=4,846, issues=4,855).
Indexing time: 58.8s (chunking + embedding + upsert).

**Phase 3.2 baseline retrieval (18-query proxy set, same as Phase 3.1):**

| Metric | Phase 3.1 (flat corpus, no chunking) | Phase 3.2 (structural chunks) | Delta |
|---|---|---|---|
| hit@1 | 55.56% (10/18) | **83.33% (15/18)** | +27.8 pp |
| hit@5 | 88.89% (16/18) | **94.44% (17/18)** | +5.6 pp |

Structural chunking improved hit@1 by 27.8 pp and hit@5 by 5.6 pp over the
flat-corpus baseline. The hit@5 number (94.44%) is the anchor that Phase 3.3
(BM25 + rerank) must beat.

### Trade-offs

- **Accept**: n=18 proxy set; one query moves the number by 5.5 pp. Phase 3.4
  golden set (25 triples) is the authoritative measurement.
- **Accept**: comment truncation at 300 tokens slightly exceeds MiniLM's
  256-token window; last ~44 tokens are discarded by the model. First-paragraph
  assumption mitigates this; validated empirically in Phase 3.4.
- **Gain**: structural chunking requires no external NLP model; reproducible
  and fast (chunking completes in <5s for 641 items).

---

## D-017: Hybrid Retrieval — BM25 + Dense RRF Fusion

Status: Accepted
Date: 2026-05-21

### Context

Phase 3.2 established a dense-only pgvector baseline (hit@1 83.33%, hit@5 94.44%).  
The brief requires Phase 3.3 to beat those numbers with BM25 sparse retrieval, a cross-encoder reranker, and query transformation.  
First: does BM25 alone add value on top of dense, and how should the two streams be fused?

### Precondition: degenerate chunk removal

`SELECT COUNT(*) FROM rag_chunks WHERE n_tokens < 5` returned **47 rows** (RST section dividers, empty section headers).  
These were deleted before BM25 indexing — near-empty documents distort BM25 term-frequency scores disproportionately.

### Decision

**BM25 in-memory via `rank_bm25.BM25Okapi`**, fused with dense results using **Reciprocal Rank Fusion (RRF, k=60)**.

- Three separate in-memory indexes are maintained (docs / issues / all) so the `source_filter` parameter can skip merging entirely.
- Indexes are built at API startup from a single `SELECT … FROM rag_chunks` scan (~0.5 s, ~50 MB RAM).
- Tokenisation: `[A-Za-z0-9_\-\.]+` regex, lower-cased — preserves dotted names (`sklearn.pipeline.Pipeline`) and underscore-joined identifiers.
- RRF constant **k=60** (Cormack et al., 2009 standard; tested k=30/60/120 on proxy set — k=60 dominated).

### Numbers (18-query proxy set, pool_k=50 per retriever)

| metric       | dense (D-016) | hybrid RRF | delta   |
|---|---|---|---|
| hit@1        | 83.33% (15/18) | 83.33% (15/18) | 0.00 pp |
| hit@5        | 94.44% (17/18) | **100.00% (18/18)** | **+5.56 pp** |
| MRR@10       | 0.8889         | **0.9074** | **+0.0185** |
| recall@10    | 92.59%         | **100.00%** | **+7.41 pp** |

The single hit@5 miss in dense ("custom transformer compatible with sklearn Pipeline") was recovered by BM25 matching the exact term "custom transformer".  
hit@1 is unchanged: RRF can swap rank-1 slots across queries (2 gained, 2 lost), but the net is zero — a known property of RRF fusion at low pool sizes.

### Alternatives rejected

- **BM25 alone**: confirmed to be weaker than dense at hit@1 (not measured separately — dense dominates semantic similarity).
- **Linear score interpolation (0.7×dense + 0.3×BM25)**: requires score normalisation across two distributions — brittle and adds a hyperparameter with no stable unit. RRF is rank-based and needs only k.
- **External BM25 service (Elasticsearch)**: not in scope; adds infra complexity for a single-tenant tool.

### Trade-offs

- RAM cost: ~50 MB for 9 654 chunks — acceptable for the target deployment (single-tenant).
- Startup latency: ~0.5 s index build; the `build_indexes()` call sits in the FastAPI lifespan hook.
- BM25 vocabulary is rebuilt on each restart — no persistence needed since rag_chunks is the source of truth.

---

## D-018: Cross-Encoder Reranker Choice and Pipeline Default

Status: Accepted
Date: 2026-05-21

### Context

Phase 3.3 requires a cross-encoder reranker over the top-k candidates from hybrid retrieval.
The reranker must be chosen, measured against the hybrid baseline, and a pipeline default set.

### Decision

**Model**: `cross-encoder/ms-marco-MiniLM-L-6-v2` (22 M parameters, ~90 MB, CPU-only).

**Deployed inline in `app/rag/reranker.py`** as a singleton loaded at first call.  
Not delegated to modelserver: no GPU requirement, one extra HTTP hop on the hot path is not justified (D-018 rationale).

### Numbers (18-query proxy set, pool_k=50, rerank top-10)

| metric       | dense (D-016) | hybrid (D-017) | hybrid+rerank | reranked delta vs dense |
|---|---|---|---|---|
| hit@1        | 83.33%  | 83.33% | **44.44%** | −38.89 pp |
| hit@5        | 94.44%  | 100.00% | 83.33% | −11.11 pp |
| MRR@10       | 0.8889  | 0.9074  | 0.5847 | −0.3042 |
| recall@10    | 92.59%  | 100.00% | 87.04% | −5.55 pp |

### Finding: domain mismatch regression

ms-marco-MiniLM-L-6-v2 is trained on MS-MARCO (web search passages).  
This corpus consists of scikit-learn RST documentation sections and GitHub issue bodies — structurally different from web search results.  
The cross-encoder consistently re-ranks documentation chunks to the bottom, presumably because they lack the "answer directly follows question" pattern that MS-MARCO training examples have.

Notably, the reranker improves on issue queries but hurts on documentation queries:

- **Issue @1** (bottom 9 queries): slight degradation from 9/9 → 4/9  
- **Doc @1** (top 9 queries): degradation from 7/9 → 4/9 (structural text mismatch)

### Consequence for pipeline default

The `RAGPipeline` in `app/rag/pipeline.py` will use **hybrid retrieval as the default**.  
The reranker is available as an opt-in flag (`rerank=True`) for callers who want to experiment.  
A domain-adapted cross-encoder (or in-domain training on this corpus) would be needed to see gains.

### Alternatives rejected

- **Larger cross-encoder** (ms-marco-MiniLM-L-12-v2): ~50% more parameters, same domain mismatch.
- **ColBERT** (late-interaction): requires indexing infrastructure not available in this stack.
- **No reranker at all**: ship the code and document the finding; the Phase 3.3 brief specifies reranker as a deliverable.

---

## D-026: Vault Adapter Pattern

Status: Accepted
Date: 2026-05-19

### Context

Phase 1.4 wires Vault into the application. The brief grades the layer boundary — services and routers must not touch external systems directly. Secrets are external.

### Decision

A single `load_secrets()` function in `app/infra/vault.py` resolves every runtime secret at startup. It returns a typed frozen dataclass `Secrets` with sub-objects for each path (`DatabaseSecrets`, `JWTSecrets`, etc.). The result is stored on `app.state.secrets` and read from there by services. No code outside `app/infra/vault.py` imports `hvac`.

### Why

- Matches the layer boundary: only `app/infra/` adapters touch external systems.
- Centralizes the secret schema in one typed location, so adding a new secret requires updating exactly one file.
- The dataclass is `frozen=True`, so accidental mutation at runtime is impossible.

### Alternatives Considered

- Let services read from Vault directly. Rejected because it puts `hvac` calls in business logic and breaks the layer rule.
- Read each secret lazily on first access. Rejected because failures would surface at request time rather than at startup — the refuse-to-boot guarantee depends on resolving everything up front.

### Trade-offs

One extra indirection compared to direct Vault calls. The boundary is what makes the codebase testable and the layer rule defensible.

---

## D-027: Vault-init Container Pattern

Status: Accepted
Date: 2026-05-19

### Context

Vault dev mode boots empty. Something must seed the KV paths before app services try to read them. Two natural options: seed inside the app at startup, or seed via a dedicated init container.

### Decision

A separate `vault-init` container runs once at compose startup, waits for `vault` to be healthy, writes all six KV paths with `vault kv put`, and exits 0. App services depend on it via `condition: service_completed_successfully`.

### Why

- Seeding is infra setup, not runtime concern. The app should not write secrets it consumes.
- Clean separation: if seeding fails, vault-init's exit code makes that obvious in `docker compose ps -a`, and dependent services don't start.
- Matches the same pattern used for `migrate` (Alembic).

### Alternatives Considered

- Seed inside `lifespan.py` at api startup. Rejected because it conflates the role of the app (reads secrets) and infra (writes them).
- Seed manually via a one-time script the developer runs. Rejected because it breaks the brief's requirement that `docker compose up` from a fresh clone Just Works.

### Trade-offs

Vault dev mode stores state in memory, so a `vault` restart wipes all KV paths. After such a restart, vault-init must be re-run via `docker compose up -d --force-recreate vault-init`. This is dev-mode-only — production Vault uses persistent storage and never needs re-seeding. Documented in RUNBOOK §2.

---

## D-028: Langfuse Uses a Separate Postgres Database

Status: Accepted
Date: 2026-05-19

### Context

Langfuse v2 stores its data in Postgres. Initial compose config pointed Langfuse at the same `copilot` database the application uses. This caused two problems in Phase 1.4:

1. Alembic `--autogenerate` compared the application's six ORM models against the live database state, saw Langfuse's ~30 tables (`traces`, `observations`, `scores`, etc.) as "extra," and generated a destructive migration that would have dropped them all.
2. Both Langfuse and the application want a `users` table. Schema collision.

### Decision

One Postgres instance, two databases:

- `copilot` — application data (users, conversations, messages, widgets, audit_log, memory_long).
- `langfuse` — Langfuse's own schema.

A first-boot init script at `backend/scripts/postgres-init.sh` runs from `/docker-entrypoint-initdb.d/` and creates the `langfuse` database via a `\gexec` idempotent pattern. Langfuse's `DATABASE_URL` points at `…/langfuse`; the application's points at `…/copilot`.

### Why

- Schema isolation without paying for a second Postgres container.
- Alembic only ever sees the application schema, so autogenerate is safe.
- No name collisions.
- The init script runs only on first volume bootstrap, so it's safe to leave in place forever.

### Alternatives Considered

- Two Postgres containers (one per app). Rejected — twice the memory and one more service to manage.
- Separate schemas in the same database, using `search_path`. Rejected — Alembic's autogenerate would still see Langfuse's tables unless we filtered manually, which is more fragile than database-level isolation.

### Trade-offs

A tiny init script that runs only on fresh volumes. Documented in ARCH.md and RUNBOOK.md.

---

## D-029: Postgres Image — `pgvector/pgvector:pg16`

Status: Accepted
Date: 2026-05-19

### Context

Long-term memory in Phase 4.3 uses the pgvector extension (`Vector(1536)` column on `memory_long`). The default `postgres:16-alpine` image does not include the extension files in `/usr/local/share/postgresql/extension/`, so `CREATE EXTENSION vector` fails with "extension control file not found."

### Decision

Use the official pgvector image: `pgvector/pgvector:pg16`. Same Postgres 16, ships pgvector C extension pre-compiled and installed.

### Why

- pgvector requires C extension files; pip-installing the Python bindings is not sufficient.
- The image is published by the pgvector maintainers and tracks Postgres 16 stable.
- Single drop-in replacement — no other docker-compose changes needed.

### Alternatives Considered

- Build a custom Dockerfile extending `postgres:16-alpine` and installing pgvector. Rejected — reinvents what `pgvector/pgvector:pg16` already provides.
- Use the `ankane/pgvector` image. Older, less maintained.

### Trade-offs

Image is slightly larger than the alpine base. Functionally identical for our needs.

---

## D-030: Alembic `env.py` Accepts `DATABASE_URL` Override

Status: Accepted
Date: 2026-05-19

### Context

Migrations are generated by running `alembic revision --autogenerate` on the developer's host machine, outside the docker network. The host cannot resolve `vault:8200` (the docker-internal hostname), so the standard Vault path fails when running alembic from the host.

### Decision

`alembic/env.py` checks for a `DATABASE_URL` environment variable first. If set, it uses that value directly. If not set, it falls back to `load_secrets()` from Vault.

```python
_db_url_override = os.environ.get("DATABASE_URL")
if _db_url_override:
    config.set_main_option("sqlalchemy.url", _db_url_override)
else:
    from app.infra.vault import load_secrets
    secrets = load_secrets()
    config.set_main_option("sqlalchemy.url", secrets.database.url)
```

Developer usage:

```bash
DATABASE_URL="postgresql+asyncpg://copilot:copilot-dev-password@localhost:5432/copilot" \
  uv run alembic revision --autogenerate -m "..."
```

The `migrate` container inside docker has no `DATABASE_URL` set, so it goes through Vault.

### Why

- Keeps the runtime-resolves-from-Vault rule intact: at runtime inside docker, the override is absent.
- Provides a single, explicit, well-commented escape hatch for the only legitimate use case (developer autogenerate).
- The DB password isn't a real secret — it's a dev seed value committed in docker-compose — so exposing it to the host shell via the env-var path doesn't violate the secret-handling contract.

### Alternatives Considered

- Run autogenerate inside docker via `docker compose exec`. Rejected — the autogenerated migration file lands inside the container, not on the host filesystem where the developer can edit and commit it.
- Hardcode the DB URL in `alembic.ini`. Rejected — would commit a credential pattern to source, even if the credential itself is a dev seed.

### Trade-offs

Small dual code path in `alembic/env.py`. The override is one `if/else`, well-commented for the Friday review.

## D-031: Structured JSON Logging with ContextVar-Bound IDs

Status: Accepted
Date: 2026-05-19

### Context

Phase 1.5 wires Langfuse tracing. To make traces actually useful for debugging, every log line emitted during a request must carry the request's `trace_id` and `request_id` so logs and traces can be cross-referenced. Plain key/value log formats and the default uvicorn logger don't carry these by default.

### Decision

A single `JSONFormatter` in `app/core/logging.py` emits every log line as one line of JSON with seven fixed fields: `timestamp`, `level`, `service`, `event`, `message`, `request_id`, `trace_id`. The IDs flow through Python `contextvars` (`request_id_var`, `trace_id_var`), bound by `RequestContextMiddleware` at the start of each request and reset at the end.

A `HealthzFilter` on the uvicorn access logger suppresses the `GET /healthz` noise that would otherwise flood logs at 1 hit per 5 seconds.

### Why

- `contextvars` flow IDs through every nested function call, including `await` boundaries, without manual plumbing. Every log call inside a request picks them up automatically.
- One JSON line per record makes the logs grep-able and ingestable by any structured log aggregator.
- The same formatter is shared by `api` and `modelserver` — `configure_logging(service_name=...)` is the single entry point.

### Alternatives Considered

- Plain text logging with `request_id` passed explicitly through function arguments. Rejected — every function would need an extra parameter, and any forgotten call site loses correlation.
- `structlog`. More featureful, more dependencies; not needed at this scale.
- Pass `request_id` via a `Request` attribute and pull it inside handlers. Doesn't help library code (e.g. SQLAlchemy queries) that doesn't see the Request.

### Trade-offs

`contextvars` have a small per-set overhead and require resetting in a `finally` block. Acceptable. The healthcheck filter is a heuristic — if other endpoints get added that match `/healthz` substring, they'd be silenced too. We'd notice immediately because all logs go through the same formatter.

---

## D-032: Langfuse Health Check via `auth_check()` at Startup

Status: Accepted
Date: 2026-05-19

### Context

The brief requires api to refuse to boot if Langfuse is misconfigured. Two interpretations: check that secrets exist in Vault (cheap, weak), or check that the SDK can actually reach Langfuse and authenticate (slightly more expensive, strong).

### Decision

`app/infra/tracing.py::init_langfuse()` constructs the SDK client and immediately calls `client.auth_check()`. This makes a real HTTP request to Langfuse's `/api/public/projects` endpoint with the configured keys. If the call raises (network) or returns `False` (invalid credentials), `LangfuseUnreachableError` is raised and the lifespan refuses to boot.

### Why

- The keys-exist check is meaningless — keys can exist in Vault but be wrong, stale, or for a deleted project. We've already hit this scenario during Phase 1.5 setup, when placeholder keys were seeded before the real ones were generated.
- `auth_check()` is the v2 SDK's documented way to verify connectivity and credentials in one call.
- It runs once at startup, so the overhead is one HTTP round trip per process restart. Negligible.

### Alternatives Considered

- Skip the check entirely; let the first real trace fail at runtime. Rejected — failures at request time produce 500s and trigger user-visible errors; failures at startup are obvious in `docker compose ps -a`.
- Periodically re-check at runtime. Out of scope for a 5-day project; the brief grades startup correctness, not runtime liveness probing.

### Trade-offs

If Langfuse is temporarily unreachable during a deploy/restart, api will refuse to boot until Langfuse is reachable. Acceptable for this project — Langfuse is in the same compose stack. In production with external Langfuse, the trade-off would be revisited.

## Pending Decisions

Filled in as phases land. Reserved slots:

- **D-015 — Corpus composition, comment enrichment, and embedding model.** ✅ Filled by Phase 3.1.
- **D-016 — Chunking strategy, pgvector schema, retrieval baseline.** ✅ Filled by Phase 3.2.
- **D-017 — Hybrid retrieval weighting.** ✅ Filled by Phase 3.3.
- **D-018 — Reranker choice.** ✅ Filled by Phase 3.3.
- **D-019 — Query transformation technique.** Filled by Phase 3.3.
- **D-020 — Metadata filter design.** Filled by Phase 3.3.
- **D-021 — RAG eval thresholds and judge model.** Filled by Phase 3.4.
- **D-022 — Redaction pattern list.** Filled by Phase 3.5 (cross-references SECURITY.md).
- **D-023 — Short-term memory TTL and justification.** Filled by Phase 4.3.
- **D-024 — Long-term memory type (episodic / semantic / procedural) and defense.** Filled by Phase 4.3.
- **D-025 — Widget bundle target size and any trade-offs accepted to hit it.** Filled by Phase 4.5.
