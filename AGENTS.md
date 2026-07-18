# AGENTS.md — instructions for AI agents in this repository

This is **Aegis** — an ontology-driven, governed intelligence platform; its
first application domain is criminal-network analysis over a Sri Lankan OSINT
corpus. The vision is `GOAL.md`; the buildable path is `speckit/` (read
`speckit/README.md` first). Work is phase-gated: check `speckit/roadmap.md`
for the current phase and its charter in `speckit/phases/` before starting
anything. The pre-Aegis prototype (quarantined under `legacy/`) is
scaffolding: **replace, never extend** (ADR-023, ADR-024).

## Git rules (binding — full doc: `docs/GIT_WORKFLOW.md`)

- **Never commit or push directly to `master`.** It is branch-protected;
  every change lands via a Pull Request with green CI, squash-merged.
- Branch per task: `<type>/<slug>` — `feat/`, `fix/`, `docs/`, `test/`,
  `chore/`; reference task IDs (e.g. `feat/t17-mention-extraction`).
- Conventional commit messages; PR titles in the same format (they become the
  squash-commit subject). Keep the `Co-Authored-By:` trailer on AI-assisted
  commits.
- Before pushing: `make test-fast` plus every affected integration/system
  suite and, if the ontology changed, `aegis ontology validate` + a semver
  bump (spec 01 §4).
- Never rewrite pushed history; undo on master is `git revert`.
- Never commit secrets (`.env` stays untracked) or large binaries.
- **AI-agent rules** (GIT_WORKFLOW.md §AI-assisted development): when the user
  authorizes publishing or merging, an agent may squash-merge its own PR after
  every required check is green. Human review is optional unless requested or
  enforced by branch protection. Never push directly to `master`, force-push,
  use `--no-verify`/`[skip ci]`, or bypass protection; stage only task files,
  report exact verification, and require explicit direction for destructive Git.

## Governance rules (from `speckit/constitution.md` — non-negotiable)

- The 14 Articles are checked on every schema/feature change. Highlights:
  claims-not-facts (I), no inherent derogatory status (II), AI output goes to
  the review queue, never directly to canonical tables (VII), every route has
  an authorization dependency (VI), projections are rebuildable caches (XIII),
  the core is domain-neutral — domains arrive as ontology modules (XIV).
- `ontology/aegis.yaml` is the single domain artifact (XI): never hand-write a
  domain type the ontology doesn't declare. Changes follow the versioning
  rules in `speckit/specs/01-ontology.md` (v2: `specs/08-ontology-v2.md`).
- Load-bearing decisions live in `speckit/decisions.md` (ADRs, append-only).
  If implementation diverges from a spec, append an ADR — don't silently
  drift.

## Commands

```bash
make up && make bootstrap        # compose stack: postgres+postgis, minio, keycloak, openfga
aegis db upgrade                 # alembic migrations
make test-fast                   # unit + component + contract
make test-integration            # dedicated PostgreSQL test database
make test-system                 # real compose/OpenFGA behavior
make test-coverage               # full line + branch coverage gate
aegis ontology validate          # Article XI gate (also in CI)
aegis projections rebuild        # regenerate all projections (Article XIII)
aegis serve                      # FastAPI dev server
```

CI (`.github/workflows/ci.yml`) runs pytest + ontology validation
automatically on every push/PR — do not merge on red.

## Testing rules

- Read `docs/testing/README.md` before adding or moving tests. Place each test
  in the lowest layer that proves the behavior; directory placement applies
  its pytest layer marker automatically.
- Every feature/fix includes success, failure, and regression coverage plus
  authorization, audit, provenance, rollback, and idempotency checks when
  applicable. Tag governance and phase-gate cases with
  `@pytest.mark.requirement(...)` and update the traceability matrix.
- Blocking integration/system tests fail when infrastructure is missing; do
  not replace failures with skips. Use only fictional deterministic fixtures.
- PR bodies list exact test commands and results. Never weaken assertions,
  hide warnings, blindly update snapshots, or add retries merely to get green.

## Data ethics

Open-source-only corpus about real people: never add national-ID numbers for
real persons, never present association as guilt, follow
`data/real/README.md`. Fictional test data lives in `data/sample/`.
