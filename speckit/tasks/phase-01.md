# Phase 1 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them. Reference specs in parentheses.

> **Status: COMPLETE with closure addendum.** T1–T16 all delivered (Milestones
> A–E); Milestone F (T16a–T16d, added 2026-07-18 per ADR-033) is open and blocks
> Phase 2's implementation milestones (not its design tasks). See
> `../reviews/phase-01-exit-review.md` for the exit-criteria walkthrough and ADR-017…019 in
> `decisions.md` for decisions changed during implementation. Divergences from the
> original task text: the identity tables (`mention`, `identity_membership`) shipped
> with T8 (migration 0005) rather than T4 (ADR-018); `affiliated_with` gained an
> entity-or-literal object and the ontology bumped to 0.3.0 (ADR-017); the legacy
> `/api/*` surface was public and open-only (ADR-019 — **superseded by ADR-026**,
> retirement scheduled in P2 T22).

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
AC: every gate criterion checked (gate criteria are non-deferrable, ADR-025);
non-blocking deliverables carried over with owner + target phase recorded.
*(Executed 2026-07-17 under the old deferral language; verdict revised
2026-07-18 — see the closure addendum below.)*

## Milestone F — Closure addendum (added 2026-07-18, ADR-033)

Blocks Phase 2 Milestones B–D (implementation); Phase 2 Milestone A (design
pack) may run in parallel.

**T16a. Interim exposure containment** (ADR-026 §2) — `aegis serve` binds to
loopback by default (explicit opt-out flag logs a warning); legacy `/api/*`
routes gain response-size caps and basic rate limiting. This is containment,
not authorization — full retirement is P2 T22.
AC: default serve refuses non-loopback binds without the flag; an oversized
`/api/graph` response is truncated/rejected per the cap; both behaviors tested.

**T16b. Revocation safety** (ADR-014; Phase-1 exit-review follow-up) —
implement the inline best-effort FGA delete on revocation paths
(`assign_case_member` removal, custody change); document the measured maximum
revocation staleness (outbox drain interval) and add a test that a revoked
member is denied after the inline delete even with the dispatcher stopped.
AC: revocation test green with dispatcher paused; staleness bound recorded in
specs/03 §3.

**T16c. Dependency lockfile** (H-33 minimum) — commit a resolved lockfile
(`uv lock` or `pip-tools`); CI installs from it; document the update policy in
`docs/GIT_WORKFLOW.md`.
AC: CI fails when the lockfile and `pyproject.toml` disagree; a fresh clone
installs identical versions.

**T16d. Documentation honesty pass** (B-15, M-01, M-25) — README and speckit
statuses match reality (no "every route is authorized" claim until T22 makes
it true again); legacy-only runbooks (`docs/INGESTION.md` §legacy paths,
`docs/RUNNING.md` LLM-merge instructions) move under `legacy/` with an
"unsafe for governed data" banner; the active ingestion runbook is rewritten
around `aegis ingest`; `docs/GIT_WORKFLOW.md` drops `[skip ci]` (conflicts
with AGENTS.md) and parameterizes AI attribution.
AC: no living doc instructs writing to `data/real` outside the governed path;
grep for `[skip ci]` in workflow docs is clean; README status section matches
the roadmap.

## Explicit non-goals for Phase 1

React UI, Splink ER, PostGIS features beyond enabling the extension, search beyond
`pg_trgm` on entity labels, compartments, disclosure packages, Dagster, Neo4j-as-primary.
