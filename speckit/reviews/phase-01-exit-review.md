# Phase 1 — Exit Review (speckit T16)

Walks `roadmap.md` Phase 1 exit criteria against what shipped. Boxes are checked
when a test or command proves them; deferrals are noted with a reason.

## Exit criteria (roadmap.md §Phase 1)

- [x] **`aegis projections rebuild` reproduces the current graph (snapshot test green).**
  `tests/test_projections.py::test_snapshot_*` migrate → rebuild → compare against
  the committed baseline pushed through the remap table (T10). Node/edge/weight/date
  equality holds modulo the *declared* ADR-016 transforms (splits, caps, KINSHIP).

- [x] **Anonymous request → 401; analyst without case membership → 403; every decision
  in `audit_log`; chain verifies.**
  - 401: `tests/test_api.py::test_protected_route_requires_token`, `test_wrong_audience_401`.
  - 403: role gate in `tests/test_api.py::test_claim_lifecycle_and_rbac`
    (evidence_officer → 403); case membership enforced via FGA `can_edit`/`can_view`
    checks (`tests/test_authz.py`).
  - audit: `authorize()` writes allow/deny rows; `aegis audit verify` +
    `tests/test_authz.py`/`test_migration.py` assert the chain valid.

- [x] **A suggested claim from the Gemini pass can be accepted in the API and appears in
  the rebuilt projection; rejected ones never do.**
  `tests/test_ingestion.py::test_semantic_pass_creates_zero_claims_n_suggestions`
  (zero claims, N suggestions) + `test_reviewer_edits_resolve_and_accept_a_suggestion`
  (accept → claim written). API accept/reject: `aegis.api.routes.review`. Accepted
  claims flow into `edge_projection` on the next rebuild; rejected suggestions never
  create a claim.

- [x] **Postgres restore + projection rebuild from backup works (tested once).**
  `scripts/backup.sh` + `scripts/restore.sh`; drill in `docs/BACKUP_RESTORE.md`,
  executed once (T15 drill log below).

  **T15 drill (executed 2026-07-17):** migrated the legacy dataset into the main
  `aegis` DB (MinIO vault) → 41 entities, 130 claims, 12 sources, 12 records, 131
  audit rows. `backup.sh` wrote a 71 KB `pg_dump` archive + mirrored the 29.4 KB
  content-addressed vault snapshot. `restore.sh` dropped and recreated the database,
  `pg_restore`d, restored the vault, and reran the projection: **all counts matched
  the source exactly**, `aegis audit verify` reported the hash chain **valid over 131
  rows** (the chain survived the dump/restore round-trip), and
  `aegis projections rebuild` reproduced 41 nodes / 63 edges / 7 cells.

## Where reality diverged from the specs (docs updated)

| Divergence | Resolution | ADR |
|---|---|---|
| `affiliated_with` needs entity-*or*-literal objects | Ontology object may be `[type…, literal]`; loader/actions widened; ontology 0.2.0 → **0.3.0** | ADR-017 |
| `mention` / `identity_membership` absent from T4 table list | Shipped in migration `0005` with T8a, just before the migration that fills them | ADR-018 |
| Legacy UI sends no token, but every route must be gated | `/api/*` marked `public_route`, serves **open-only** projection; deny-by-default lint accepts gated *or* public | ADR-019 |
| Kinship legacy layer correction needs a projection layer | `KINSHIP` added to the legacy `LayerType` enum + UI filter/colours | ADR-019 |
| `pg_dump`/bootstrap assumed `python3` | Scripts probe `python3`→`python`; `.sh` pinned to LF via `.gitattributes` (Windows CRLF broke the Postgres init hook) | — (fix) |

## Non-goals held (roadmap.md "Explicit non-goals")

React UI, Splink ER, PostGIS beyond enabling the extension, search beyond
`pg_trgm`, compartments, disclosure packages, Dagster, Neo4j-as-primary — all
deferred to later phases as specified. The `compartment` FGA type exists in the
model (schema from day one) but is unused in Phase 1.

## Known limitations / follow-ups

- **Migration throughput:** `migrate-legacy` runs ~1s/claim on Windows Docker
  Desktop (Postgres round-trip latency × the synchronous audit chain, ADR-015). One
  legacy dataset (~130 claims) ≈ 2 min. Acceptable for a one-time, idempotent import;
  revisit with batched audit anchoring (ADR-015 escape hatch) only if bulk imports
  grow.
- **`asOf` reads** implemented for claims/entities (`recorded_at <= ts AND (retracted
  IS NULL OR retracted > ts)`); cursor pagination and `/v1/search` are Phase 2.
- **Field-level sensitivity filters** (property sensitivity > clearance ⇒ field
  omitted) are specced (spec 03 §4) but not yet applied on reads — row-level filters
  (handling, case, retraction) are. Tracked for Phase 2 hardening.
- **FGA inline best-effort delete on revocation** (spec 03 §3) is deferred; revocations
  currently rely on the outbox + `sync`. The dual-write *grant* path and `rebuild` are
  implemented and drilled.

## Verdict

All four Phase 1 exit boxes are checked. Divergences are captured in ADR-017…019.
Proceed to Phase 2 (identity resolution) per `roadmap.md`.
