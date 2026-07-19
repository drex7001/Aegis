# Aegis

[![ci](https://github.com/drex7001/Aegis/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/drex7001/Aegis/actions/workflows/ci.yml)

**Aegis is an ontology-driven, governed intelligence platform.** A single
declared ontology — object types, properties, links, events, actions, and
governance rules ([`ontology/aegis.yaml`](ontology/aegis.yaml)) — powers every
analytical domain built on the platform. **Criminal-network analysis over a
Sri Lankan OSINT corpus is the first application domain, not the platform's
identity** (ADR-023). Comparable in concept to Palantir's ontology-centred
systems, but open-stack, independently auditable, and built for Sri Lanka's
legal and trilingual (Sinhala / Tamil / English) context.

The core principle:

> **Entities are not facts. Relationships are not facts. Intelligence consists
> of claims supported, contradicted, or contextualized by evidence and
> sources.**

| | |
|---|---|
| Vision (north star) | [`GOAL.md`](GOAL.md) |
| Constitution | [`speckit/constitution.md`](speckit/constitution.md) — 14 non-negotiable articles |
| Build path | [`speckit/`](speckit/README.md) — roadmap v2 (P0–P9), phase charters, ADRs, detailed specs |
| Domain artifact | [`ontology/aegis.yaml`](ontology/aegis.yaml) — the single source of domain truth (Article XI) |
| Contributing | [`docs/GIT_WORKFLOW.md`](docs/GIT_WORKFLOW.md) — GitHub Flow: branch → PR → green CI → squash |

## What exists today

**Milestone I (Phases 0–1) is complete**, including the ADR-033 closure
addendum (T16a–T16d, closed 2026-07-18 — see `speckit/tasks/phase-01.md`).
Phase 2 is underway: its blocking design pack (T17a–T17d) is done and
Milestone B is the active work. The governed foundation:

- **Claim store** (PostgreSQL + PostGIS): every relationship and attribute is a
  claim with source, grading, time window, and handling code — never a bare fact.
- **Evidence vault** (MinIO): content-addressed originals, hash ledger,
  derivative tracking (Article IV).
- **AuthN/AuthZ**: Keycloak OIDC + OpenFGA ReBAC + handling-code row filters.
  **Every route carries an authorization dependency, with no exemptions**
  (Article VI): the anonymous `/api/*` projection surface and the
  `public_route` marker that excused it were deleted at Phase 2 T22
  (ADR-026).
- **Audit**: append-only, hash-chained event log with chain verification
  (Article X).
- **Governed extraction**: the LLM/structural extraction passes emit *suggested
  claims* into a review queue — humans adjudicate; nothing algorithmic writes
  to canon (Article VII).
- **Projections**: rebuildable caches (Article XIII) — time-segmented edges
  carrying a support summary, never an aggregate weight (ADR-030).
- **Workspace** (`ui/`): React + TypeScript, Keycloak OIDC with PKCE, served by
  `aegis serve` on the same origin as the API.
- **API v1 + `aegis` CLI**, migrations, backup/restore runbook.

**Active phase: Phase 2 — the ★ MVP gate** (identity decision ledger, durable
React workspace with the full ingest → review → adjudicate → graph loop,
provenance panels, basic search; recomposed 2026-07-18 per ADR-025…033 — see
[`speckit/tasks/phase-02.md`](speckit/tasks/phase-02.md)). The full roadmap to
production is [`speckit/roadmap.md`](speckit/roadmap.md); the external-review
disposition is
[`speckit/reviews/2026-07-18-external-review-disposition.md`](speckit/reviews/2026-07-18-external-review-disposition.md).

## Quickstart

Prerequisites: Docker + Compose v2, Python 3.12, and
[`uv`](https://docs.astral.sh/uv/).

```bash
make up && make bootstrap        # compose stack: postgres+postgis, minio, keycloak, openfga
make install                     # locked aegis package + dev environment
.venv/bin/aegis db upgrade       # alembic migrations
.venv/bin/aegis migrate-legacy   # one-time: import the curated OSINT corpus as claims
.venv/bin/aegis projections rebuild
.venv/bin/aegis serve            # API at http://127.0.0.1:8000 — /docs for OpenAPI
```

The investigation workspace is a separate build; `aegis serve` mounts it once
it exists (see [`ui/README.md`](ui/README.md)):

```bash
cd ui && npm ci && npm run build  # → ui/dist, served at / by `aegis serve`
```

Verify the build the way CI does:

```bash
make test-fast          # unit + component + contract; no services required
make test-integration   # requires AEGIS_TEST_DATABASE_URL (disposable PostgreSQL)
make up && make bootstrap
make test-system        # real PostgreSQL + OpenFGA governance checks
make test-coverage      # all blocking layers, line + branch coverage
make lint-ontology      # Article XI gate
```

## Testing

Tests are organized by the boundary they exercise, then by subject:

```text
tests/
├── unit/          # pure rules and validation
├── component/     # in-process API/CLI with replaced external boundaries
├── contract/      # ontology, schema, OpenAPI, and governance invariants
├── integration/   # PostgreSQL-backed behavior
├── system/        # real multi-service behavior such as OpenFGA convergence
├── e2e/           # reserved for Phase 2 browser journeys
├── fixtures/      # deterministic fictional inputs
├── snapshots/     # reviewed expected outputs
└── support/       # test-only factories, constants, and paths
```

The complete process is in [`docs/testing/`](docs/testing/README.md):
[strategy](docs/testing/TESTING_STRATEGY.md),
[quality criteria and traceability](docs/testing/TESTING_CRITERIA.md), and
[best practices](docs/testing/BEST_PRACTICES.md).

Every feature or fix must include tests at the lowest useful layer. Cover the
success and failure paths plus authorization, audit, provenance, rollback, and
idempotency where they apply. Governance and phase-gate tests carry a
`requirement` marker. New test data must be fictional and deterministic; do not
let a blocking suite silently skip missing infrastructure. Include the exact
commands and results in the pull request.

## Repository map

| Path | What |
|---|---|
| `ontology/` | **The domain artifact** (`aegis.yaml`) everything derives from (Article XI), plus change proposals and version history (Phase 3) |
| `aegis/` | Platform core package — domain-neutral (Article XIV): ontology loader/codegen, actions, queries, authz, audit, store, evidence, ingestion, ER, projections, API, plus scaffolded homes for functions (P3), search/analytics (P6), sharing (P7), and controlled AI (P8) |
| `sdk/` | Generated Python + TypeScript clients (Phase 3, spec 08) — committed codegen output, never hand-edited |
| `ui/` | React + TypeScript investigation workspace (ADR-032) — the single durable UI, landed at Phase 2 T22 and grown in place from there |
| `migrations/` | Alembic schema migrations |
| `infra/` | Compose stack + bootstrap (PostgreSQL/PostGIS, MinIO, Keycloak, OpenFGA) |
| `tests/` | Layered unit, component, contract, integration, system, and future E2E suites; see [`docs/testing/`](docs/testing/README.md) |
| `docs/` | Active runbooks: git workflow, backup/restore, governed ingestion, and testing |
| `data/` | Corpora: `data/real/` (public-reporting OSINT — **read [`data/real/README.md`](data/real/README.md) first**) and `data/sample/` (fictional) |
| `speckit/` | Constitution, spec, plan, decisions (ADRs), roadmap, phase charters, detailed specs |
| `scripts/` | Operational helpers (backup/restore, ingestion setup) |
| `Files/` | Legacy prototype raw drop zone (gitignored; unsafe for governed data) |
| `legacy/` | **Quarantined pre-Aegis prototype** (ADR-023) — see below |

## Data & ethics

Two strictly separated tracks: `data/sample/` is **fictional**; `data/real/`
is compiled **only from public reporting** about documented cases, every claim
cited. The platform never stores national-ID numbers for real persons, never
renders association as guilt (Article IX), and never lets AI output become fact
without human adjudication (Article VII). Rules and source list:
[`data/real/README.md`](data/real/README.md).

## Legacy prototype

Aegis grew out of a prototype — *"Sri Lanka Illicit Networks — Temporal
Multiplex Graph"*: a regex + LLM extraction pipeline and a Cytoscape.js
explorer over a static graph JSON. Per **ADR-023 it is replaced, never
extended**: it is quarantined under [`legacy/`](legacy/README.md) and runs
only as scaffolding. **Its explorer and the anonymous `/api/*` surface were
deleted at Phase 2 T22** (ADR-026/ADR-032), replaced by `ui/`; the extraction
pipeline is the last substantial piece and goes with extraction v2. Its
documentation is kept for reference:
[`legacy/ARCHITECTURE.md`](legacy/ARCHITECTURE.md) (component tour) ·
[`legacy/RUNNING.md`](legacy/RUNNING.md) (commands) ·
[`legacy/ADDING_DATA.md`](legacy/ADDING_DATA.md) (data recipes) ·
[`legacy/INGESTION.md`](legacy/INGESTION.md) (historical raw-file ingestion).
For new governed sources, use [`docs/INGESTION.md`](docs/INGESTION.md).

![The retired prototype explorer](legacy/explorer-screenshot.png)

*The prototype explorer, kept as a picture of where this started. It served an
open graph to anyone who could reach the port; the workspace that replaced it
authenticates every caller and bounds every query.*
