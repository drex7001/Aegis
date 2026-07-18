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

**Milestone I (Phases 0–1) is complete, with a closure addendum open**
(T16a–T16d — see `speckit/tasks/phase-01.md`; verdict revised 2026-07-18 per
ADR-033). The governed foundation:

- **Claim store** (PostgreSQL + PostGIS): every relationship and attribute is a
  claim with source, grading, time window, and handling code — never a bare fact.
- **Evidence vault** (MinIO): content-addressed originals, hash ledger,
  derivative tracking (Article IV).
- **AuthN/AuthZ**: Keycloak OIDC + OpenFGA ReBAC + handling-code row filters;
  every `/v1/*` route carries an authorization dependency (Article VI). This
  does **not** yet cover every HTTP route: the legacy explorer's read-only
  `/api/*` projection surface remains anonymous, contained by T16a and
  **deleted at Phase 2 T22** (ADR-026).
- **Audit**: append-only, hash-chained event log with chain verification
  (Article X).
- **Governed extraction**: the LLM/structural extraction passes emit *suggested
  claims* into a review queue — humans adjudicate; nothing algorithmic writes
  to canon (Article VII).
- **Projections**: rebuildable caches (Article XIII) that currently also feed
  the legacy explorer UI.
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
.venv/bin/aegis serve            # API (+ legacy explorer) at http://127.0.0.1:8000 — /docs for OpenAPI
```

Verify the build the way CI does:

```bash
make test              # pytest (integration tests need the compose test DB)
make lint-ontology     # aegis ontology validate — the Article XI gate
```

## Repository map

| Path | What |
|---|---|
| `ontology/` | **The domain artifact** (`aegis.yaml`) everything derives from (Article XI), plus change proposals and version history (Phase 3) |
| `aegis/` | Platform core package — domain-neutral (Article XIV): ontology loader/codegen, actions, queries, authz, audit, store, evidence, ingestion, ER, projections, API, plus scaffolded homes for functions (P3), search/analytics (P6), sharing (P7), and controlled AI (P8) |
| `sdk/` | Generated Python + TypeScript clients (Phase 3, spec 08) — committed codegen output, never hand-edited |
| `ui/` | React + TypeScript investigation workspace (Phase 2, ADR-032) — the single durable UI; replaces the legacy explorer at T22 |
| `migrations/` | Alembic schema migrations |
| `infra/` | Compose stack + bootstrap (PostgreSQL/PostGIS, MinIO, Keycloak, OpenFGA) |
| `tests/` | Unit + integration suites (CI runs both) |
| `docs/` | Active runbooks: git workflow, backup/restore, governed ingestion |
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
only as scaffolding (the explorer is served by `aegis serve` from a
rebuildable projection, loopback-bound per T16a) until the Phase 2 workspace
deletes it at T22 (ADR-026/ADR-032). Its
documentation is kept for reference:
[`legacy/ARCHITECTURE.md`](legacy/ARCHITECTURE.md) (component tour) ·
[`legacy/RUNNING.md`](legacy/RUNNING.md) (commands) ·
[`legacy/ADDING_DATA.md`](legacy/ADDING_DATA.md) (data recipes) ·
[`legacy/INGESTION.md`](legacy/INGESTION.md) (historical raw-file ingestion).
For new governed sources, use [`docs/INGESTION.md`](docs/INGESTION.md).

![Legacy explorer screenshot](legacy/explorer-screenshot.png)
