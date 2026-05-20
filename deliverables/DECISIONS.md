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

- **D-011 — LLM classification baseline (prompt, structured output strategy, latency/cost budget).** Filled by Phase 2.3.
- **D-012 — Three-way classifier comparison and deployment choice.** Filled by Phase 2.3.
- **D-013 — Classification eval thresholds in `eval_thresholds.yaml`.** Filled by Phase 2.4.
- **D-014 — NER and summarization tool choices.** Filled by Phase 2.5.
- **D-015 — Embedding model and retrieval-quality number vs at least one alternative.** Filled by Phase 3.1.
- **D-016 — Chunking strategy.** Filled by Phase 3.2.
- **D-017 — Hybrid retrieval weighting.** Filled by Phase 3.3.
- **D-018 — Reranker choice.** Filled by Phase 3.3.
- **D-019 — Query transformation technique.** Filled by Phase 3.3.
- **D-020 — Metadata filter design.** Filled by Phase 3.3.
- **D-021 — RAG eval thresholds and judge model.** Filled by Phase 3.4.
- **D-022 — Redaction pattern list.** Filled by Phase 3.5 (cross-references SECURITY.md).
- **D-023 — Short-term memory TTL and justification.** Filled by Phase 4.3.
- **D-024 — Long-term memory type (episodic / semantic / procedural) and defense.** Filled by Phase 4.3.
- **D-025 — Widget bundle target size and any trade-offs accepted to hit it.** Filled by Phase 4.5.
