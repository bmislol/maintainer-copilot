# Contributing

Personal-project conventions. The point is consistency, not bureaucracy.

## Branch Naming

`feat/<NN>-<short-slug>` — `NN` is the phase number from `CLAUDE.md`, slug is kebab-case.

Examples:

- `feat/01-foundations`
- `feat/06-dataset-fetch`
- `feat/14-rag-eval-golden`

One branch per phase. If a phase grows mid-flight, do not bleed work into the same branch — finish, merge, and open a new one.

## Commit Messages — Conventional Commits

Format:
<type>(<scope>): <short imperative summary>
<optional body explaining the why, wrapped at ~72 cols>

Types used in this repo:

| Type      | When                                                  |
|-----------|-------------------------------------------------------|
| `feat`    | New functionality                                     |
| `fix`     | Bug fix                                               |
| `refactor`| Internal restructuring, no behaviour change           |
| `docs`    | Documentation only (README, CLAUDE.md, deliverables/) |
| `chore`   | Tooling, config, dependency bumps                     |
| `test`    | Adding or changing tests                              |
| `ci`      | GitHub Actions / workflow changes                     |

Scope is optional but useful. Examples:

- `feat(api): add /chat/send endpoint`
- `fix(rag): correct BM25 scoring weight`
- `docs(arch): fill RAG architecture table`
- `chore(deps): pin pydantic to 2.x`
- `ci: add eval-classification gate`

Imperative present tense ("add" not "added"), no trailing period, 50-char soft limit on the subject line.

## Pull Requests

- Always open a PR, even when working solo. The audit trail matters.
- CI must be green before merge.
- Squash merge to `main` — one commit per merged phase keeps history readable.
- Use the PR template at `.github/pull_request_template.md`.

## Phase Workflow

1. `git pull main`
2. `git checkout -b feat/<NN>-<slug>`
3. Read the relevant phase in `CLAUDE.md` §5 and any referenced deliverables sections.
4. Work the phase. Commit small, commit often.
5. Push. Open PR using the template.
6. Wait for CI green. Squash merge. Tick the phase in `CLAUDE.md`.