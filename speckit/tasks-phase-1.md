# Phase 1 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them. Reference specs in parentheses.

## Milestone A — Ground

**T1. ⛓ Infra compose** — `infra/docker-compose.yml` with postgres:16-postgis,
minio, keycloak, openfga; volumes; `.env.example` extended; `make up`, `make down`,
`make bootstrap` (create DB, buckets, Keycloak realm `aegis` + roles, FGA store +
model push).
AC: fresh clone → `make up bootstrap` → all healthchecks green.

**T2. ⛓ Package scaffold** — `aegis/` package per plan §3; SQLAlchemy + Alembic wired;
`aegis` CLI entrypoint (typer) with `db upgrade`, `audit verify`, `projections
rebuild` stubs; structlog JSON logging.
AC: `aegis db upgrade` runs empty migration against compose Postgres.

**T3. ⛓ Ontology loader** (specs/01) — parse + validate `ontology/aegis.yaml`;
registry API (`ontology.object_types`, `.predicates`, `.grading`, `.actions`);
pytest suite for validation failures; CI job.
AC: invalid predicate object-type reference fails validation with a precise error.

## Milestone B — Canonical store

**T4. ⛓ Core schema migration** (specs/02) — `source`, `source_record`, `entity`,
`claim`, `claim_relation`, `review_queue`, `case_file`, `case_member`, `authz_outbox`.
Ontology vocabularies (predicate, entity_type, grading, handling) are plain TEXT —
validated in the actions layer, never CHECK-constrained from the ontology (ADR-013);
DB CHECKs only for code-owned invariants (object XOR, self-claims, time sanity, fixed
relation/status values).
AC: migration up/down clean; a schema-inspection test proves no ontology-derived
constraints exist (vocabulary rejection itself is T7's AC).

**T5. Evidence schema + vault** (specs/02 §4, ADR-007) — `evidence_item`,
`derivative`, `custody_event`; `aegis.evidence` adapter (MinIO + local-FS fallback),
content-addressed put/get, provenance envelope.
AC: same bytes twice → one object; envelope JSON stored; hash recorded.

**T6. ⛓ Audit writer** (specs/03 §5) — hash-chained `audit_log`, INSERT-only DB grant
for app role, `aegis audit verify`. Chaining is synchronous inside the action
transaction — accepted serialization, ADR-015.
AC: tamper test — editing a row (as superuser) makes verify fail at that row.

**T7. Actions layer v1** — `record_claim`, `retract_claim`, `link_claims`
(corroborates/contradicts), `submit_suggestion`, `review_suggestion`,
`register_evidence`, `add_custody_event`, `open_case`, `assign_case_member`.
Every action: validate via ontology → write (+ `authz_outbox` rows for membership /
custody changes, ADR-014) → audit, one transaction.
AC: unit tests per action incl. invariants (time sanity, no self-claims); unknown
predicate/type/grading value rejected with a precise ontology-path error (ADR-013).

## Milestone C — Migration of the existing dataset

**T8. ⛓ Legacy migration script** (specs/02 §6) — `aegis migrate-legacy` +
`aegis/migration/legacy.py`, the only place legacy vocabulary lives (ADR-016):
`SOURCES` → source rows; curated nodes → entities (+`known_as` claims for aliases,
affiliation claims); curated edges → recorded claims via the verb-remap table
(compounds split into multiple claims, "suspected_" prefixes become credibility caps)
and the ConfidenceTag→grading map; provenance pointing at `real_dataset.py` snapshot
as a source record.
AC: counts reconcile per the remap table (41 entities; each edge → ≥1 claim; every
split/remap listed in the migration report); idempotent re-run.

**T9. Extraction rewire** (specs/04) — `structural_pass` and `semantic_pass` outputs
land as `suggested` review-queue rows (model/prompt metadata for LLM); `pipeline/
ingest.py` writes source_records via the vault instead of bare files.
AC: running the Gemini pass creates zero rows in `claim`; N rows in `review_queue`.

**T10. ⛓ Projection builder** (plan §4.4) — `edge_projection` matview; legacy graph
JSON emitter matching current `output/real_graph.json` schema exactly (nodes, edges,
cells, meta); Cypher export path preserved; clustering runs on the projection.
AC: snapshot test — migrated data → rebuild → semantically equal to committed
baseline JSON (same nodes/edges/weights/dates).

## Milestone D — Governed API

**T11. ⛓ AuthN** — OIDC bearer validation against Keycloak (JWKS), user context
(sub, roles, clearance claim).
AC: no token → 401; wrong audience → 401.

**T12. ⛓ AuthZ** (specs/03) — FGA model file + bootstrap tuples; `authorize()`
dependency; row-filter builder (handling ≤ clearance, case scope); purpose parameter
on sensitive reads; outbox dispatcher + `aegis authz sync` / `aegis authz rebuild`
(ADR-014).
AC: authz matrix test (role × handling × membership) passes; deny-by-default proven
by a route registered without the dependency failing CI (lint rule); dual-write drill —
stop FGA, `assign_case_member` still commits (outbox row pending), restart FGA, sync
drains → FGA check allows; `rebuild` from Postgres alone reproduces the tuple set.

**T13. API v1 routes** (specs/06) — entities, claims (+as-of), sources, review queue,
evidence, cases, graph projection (`/api/graph` kept for the legacy UI), audit query
(auditor only).
AC: OpenAPI docs render; legacy UI works against the new server unchanged.

**T14. Serve legacy UI from aegis-api** — mount `app/static`, point it at projection
endpoints; retire `app/server.py` (keep file with deprecation note until Phase 3).
AC: browser smoke test — graph loads, filters work, detail panel shows source.

## Milestone E — Close-out

**T15. Backup/restore drill** — script `pg_dump` + MinIO mirror; restore into a clean
compose stack; rebuild projections.
AC: documented runbook; drill executed once successfully.

**T16. Phase exit review** — walk `roadmap.md` Phase 1 exit criteria; update
speckit docs where reality diverged; append ADRs for any decision changed.
AC: all exit boxes checked or explicitly deferred with reason.

## Explicit non-goals for Phase 1

React UI, Splink ER, PostGIS features beyond enabling the extension, search beyond
`pg_trgm` on entity labels, compartments, disclosure packages, Dagster, Neo4j-as-primary.
