# Aegis — Technical Plan

## 1. Shape of the system

One modular Python application + off-the-shelf platform services, per GOAL.md §37
("do not begin with 60 microservices") and Article XII (adopt before build).

```
┌────────────────────────────────────────────────────────────────┐
│  UI (ADR-032: one durable app from Phase 2)                     │
│  Phase 2+: React+TS workspace (auth shell, ingest/review/       │
│           adjudication, Cytoscape graph + provenance panel)     │
│  Phase 4+: same app grows object views, cases, hypotheses,      │
│           timeline; P5 adds MapLibre map                        │
└──────────────────────────────┬─────────────────────────────────┘
                               │ OIDC (Keycloak)
┌──────────────────────────────▼─────────────────────────────────┐
│  aegis-api (FastAPI)                                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────────┐  │
│  │ domain   │ │ actions  │ │ queries  │ │ authz middleware  │  │
│  │ (pure)   │ │ (write + │ │ (read +  │ │ OpenFGA check +   │  │
│  │          │ │  audit)  │ │  filter) │ │ SQL row filters   │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────────┘  │
│  Ports: ClaimRepo │ EvidenceStore │ PolicyPort │ SearchPort     │
└───────┬───────────────┬───────────────┬────────────────────────┘
        │               │               │
┌───────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐ ┌─────────────┐
│ PostgreSQL16 │ │ MinIO (S3)  │ │ OpenFGA     │ │ Keycloak    │
│ +PostGIS     │ │ evidence    │ │ ReBAC store │ │ identity    │
│ claims, ent, │ │ vault, raw  │ └─────────────┘ └─────────────┘
│ cases, audit │ │ landing     │
└───────┬──────┘ └─────────────┘
        │ rebuildable projections (Article XIII)
        ├──▶ graph JSON (feeds existing UI)
        ├──▶ Cypher / Neo4j push (optional, exists)
        ├──▶ edge_projection matview (recursive-CTE traversal)
        └──▶ search tsvector/pg_trgm indexes
```

Extraction (`legacy/pipeline/`) becomes a set of **producers of suggested claims**
feeding a review queue; the only path into canonical tables is a human-executed action.

## 2. Stack decisions (now vs GOAL.md end-state)

| Concern | Reference choice (ADR-020) | Trigger-gated end-state | Objective upgrade trigger |
|---|---|---|---|
| Language/framework | Python 3.12 + FastAPI | — (permanent; JVM rewrite withdrawn, ADR-020) | — |
| System of record | PostgreSQL 16 | PostgreSQL | — (permanent) |
| Graph traversal | Recursive CTEs over `edge_projection` matview | Neo4j Enterprise | Traversal is dominant access pattern AND CTE p95 > 2 s on benchmarked realistic data (GOAL.md §11.5) |
| Spatial | PostGIS | PostGIS | — |
| Search | Postgres FTS + `pg_trgm` (+ ICU) | OpenSearch | Multilingual fuzzy/phonetic quality fails on Sinhala/Tamil test set, or corpus ≫ 10⁶ docs |
| Entity resolution | Splink (DuckDB backend) | Splink + custom models | — |
| Identity (authN) | Keycloak (OIDC, docker) | Agency IdP via OIDC/SAML | Deployment into an agency |
| Authorization | OpenFGA (ReBAC) + handling-code row filters | OPA + SpiceDB/OpenFGA | Policy-as-code needs beyond relationships |
| Evidence store | MinIO, content-addressed, versioned buckets | S3 + object lock + KMS | Cloud/agency deployment |
| Raw event lake | Parquet + DuckDB | Iceberg + Trino/Spark | Event volume > single-node DuckDB comfort (~10⁸ rows) |
| Orchestration | CLI (`aegis` command) + Makefile | Dagster | ≥ 3 scheduled pipelines or lineage questions we can't answer |
| Workflow engine | none (DB status columns) | Temporal | Multi-step human approvals across days/agencies |
| Streaming | none — batch | Kafka + Flink | A real continuous feed exists |
| Graph viz | Cytoscape.js (exists) | Sigma.js if WebGL scale needed | > ~5k rendered elements janky |
| Map | MapLibre GL JS + PostGIS tiles | + deck.gl | Large event layers |
| Deploy | Docker Compose | Kubernetes + Argo CD | Multi-node or multi-agency cell |
| Observability | structlog JSON + healthz | OpenTelemetry stack | First real second user |

Each row that diverges from GOAL.md has an ADR in `decisions.md`.

## 3. Repository layout (ADR-024 — greenfield structure, scaffolded to the roadmap)

```
Aegis/
├── ontology/                   # THE domain artifact (Article XI)
│   ├── aegis.yaml
│   ├── proposals/              # ontology change proposals (P3, spec 08 §7)
│   └── history/                # prior versions kept on major bumps (P3)
├── aegis/                      # platform core package (domain-neutral, Article XIV)
│   ├── ontology/               # loader, validator, codegen (pydantic/FGA/UI meta)
│   ├── domain/                 # pure domain logic; no infra imports
│   ├── actions/                # the only write path: record_claim, review_suggestion,
│   │                           # adjudicate_identity, register_evidence ... (write + audit)
│   ├── queries/                # authorized reads: expand, paths, as-of, why-connected
│   ├── authz/                  # OpenFGA client, row-filter builders, outbox (ADR-014)
│   ├── audit/                  # hash-chained append-only writer + verifier
│   ├── store/                  # SQLAlchemy models
│   ├── evidence/               # content-addressed vault (MinIO/S3 + local fallback)
│   ├── ingestion/              # landing zone, idempotency, suggested-claim intake
│   ├── er/                     # splink jobs, cluster model, adjudication (P2)
│   ├── functions/              # declared derivations registry (P3, spec 08 §4)
│   ├── projections/            # graph JSON, edge matview refresh, cypher, search vectors
│   ├── search/                 # global search behind SearchPort (P6, ADR-012)
│   ├── analytics/              # governed analytics → AnalyticFinding (P6, Article IX)
│   ├── sharing/                # disclosure/export, compartments, break-glass (P7)
│   ├── assist/                 # controlled AI producers — suggest-only (P8, Article VII)
│   ├── migration/              # one-time legacy adapters (T8) — only place legacy vocab lives (ADR-016)
│   └── api/                    # FastAPI routers (thin; call actions/queries)
├── sdk/                        # generated typed clients — committed codegen
│   ├── python/                 # aegis_sdk package (P8 — first consumer, ADR-033)
│   └── ts/                     # OpenAPI-generated client (P3, spec 08 §8), consumed by ui/
├── ui/                         # React+TS investigation workspace (P2, ADR-032, spec 07)
├── infra/
│   ├── docker-compose.yml      # postgres+postgis, minio, keycloak, openfga
│   └── fga/model.fga           # authorization model
├── migrations/                 # alembic
├── data/
│   ├── real/                   # OSINT corpus — public reporting only (untracked; README tracked)
│   └── sample/                 # fictional test data
├── docs/                       # runbooks
├── scripts/                    # backup/restore, ingestion setup
├── speckit/                    # this kit
├── tests/
└── legacy/                     # quarantined pre-Aegis prototype (ADR-023/ADR-024)
    ├── pipeline/               # extraction passes — still feed the review queue
    └── app/                    # explorer UI — deleted at P2 T22 (ADR-026/ADR-032)
```

`legacy/pipeline/` keeps working throughout — Phase 1 changed its **sink** (Postgres
suggested claims instead of JSON edges), not its extraction logic; it is deleted
piecewise as the platform replaces each piece (`legacy/README.md` tracks the schedule).

## 4. Key mechanisms

### 4.1 Ontology-driven everything (Article XI)
`aegis.ontology` loads `aegis.yaml`, validates it (unique names, predicate
subject/object types exist, grading values closed), and exposes a registry. From the
registry we generate: Pydantic claim-payload validators, OpenFGA object types, API
route metadata, and UI form/display descriptors. Vocabulary validation happens at
write time against the registry itself — never as DB DDL (ADR-013), so ontology
changes don't require migrations. Generation is idempotent and diff-able; generated
files are committed.

### 4.2 Claim lifecycle
```
extraction/LLM/analyst draft ──▶ suggested (review queue)
                                     │ human action: accept / edit+accept / reject
                                     ▼
                              recorded  ──▶ retracted (soft) / superseded (link)
```
Only `recorded` claims feed projections. `assertion_type` ∈ observed | reported |
inferred | assessed. Suggested-by-AI is a queue status, not an assertion type — on
acceptance the human picks the correct assertion type.

### 4.3 Authorization path (Article VI)
1. OIDC JWT (Keycloak) → user id, roles, clearance.
2. Route dependency: `authorize(action, resource_type, resource_id?, purpose?)`
   → OpenFGA check (case membership, compartment) — deny fails fast.
3. Query layer appends row filters: `handling_code <= user.clearance`,
   case scoping, `retracted_at IS NULL` unless auditor.
4. Decision (+purpose) written to audit either way.

### 4.4 Projection rebuild (Article XIII)
`aegis projections rebuild` recomputes: `edge_projection` (v2 semantics per
ADR-029/030 — identity-revision resolution, time-segmented aggregation,
support summary, revision/version stamps), the workspace graph JSON, optional
Cypher/Neo4j push, and search vectors. The legacy-shaped
`output/real_graph.json` emitter survives only until P2 T22 deletes the
explorer it feeds.

### 4.5 Audit chain (Article X)
`audit_log(entry_hash = sha256(prev_hash || canonical_json(event)))`; verification
command walks the chain; DB role for the app has INSERT-only on this table.

## 5. Environments

- **dev**: docker compose (postgres, minio, keycloak, openfga) + `uvicorn --reload`.
  Single `make up` / `make bootstrap` (creates realms, FGA store, buckets, migrations).
- **research**: notebooks/DuckDB against Parquet exports — never writes canonical data
  (GOAL.md §38's research/shadow/production split, scaled).
- **prod (later)**: same compose on a hardened host; Kubernetes only at federation
  phase.

## 6. Testing strategy

- Ontology validation tests (CI gate).
- Property tests on claim invariants (time sanity, grading enums) — porting the spirit
  of `demo.py prove_guardrails()`.
- Migration test: legacy dataset → claims → rebuild projection → compare against
  committed `output/real_graph.json` snapshot (see spec.md §6.6).
- Authz tests: matrix of (role, handling, case-membership) × endpoint — deny by
  default.
- Audit chain verifier in CI against test fixtures.
