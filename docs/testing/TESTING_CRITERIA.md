# Testing Criteria and Quality Gates

## Definition of Done

A feature or fix is complete only when:

- acceptance criteria are mapped to automated tests at the appropriate layers;
- success, invalid input/failure, and regression paths pass;
- authorization, audit, provenance, review-queue, rollback, and idempotency
  paths are covered wherever applicable;
- test data is fictional and deterministic;
- fast, affected integration/system, coverage, and ontology commands are green;
- no unexplained skip, warning, flaky retry, or weakened assertion is added;
- documentation, manual procedure, and traceability status are updated when the
  user-visible workflow or phase gate changes.

The PR description records commands and results. A test gap is acceptable only
when it is non-blocking, explicitly justified, owned, and scheduled. A
constitutional or phase-exit gate cannot be deferred without a superseding ADR.

## Coverage policy

Coverage is measured over `aegis/` with line and branch tracking. The first
green reorganized full-suite run on Linux CI measured 80.88% combined coverage,
so CI enforces the rounded-down initial 80% repository floor. It must never
decrease; raise the floor when sustained coverage improves.

Long-term expectations are at least 90% line coverage and 80% branch coverage.
New and materially changed behavior should meet those levels in its owning
modules. Constitutional invariants and phase-gate acceptance criteria require
complete behavioral coverage regardless of aggregate percentages.

Excluded code requires a narrow `# pragma: no cover` plus review justification;
generated code, unreachable defensive branches, and platform guards are the
only normal candidates.

## Gate criteria

| Gate | Required evidence |
|---|---|
| Pull request | Fast suite, affected integration/system suites, requirement mapping, coverage non-regression |
| Ontology/schema change | Contract tests, migration up/down test, `aegis ontology validate`, required semver/proposal/history changes |
| Security/governance change | Allow and deny matrix, no-existence-leak checks, audit outcome, real policy-engine system test when wiring changes |
| Phase exit | Every charter criterion executable or authorized manual evidence recorded; no planned blocking row below |
| Release/pilot | Full CI, migrations, backup/restore and authorized smoke evidence required by the active gate |

## Traceability matrix

Status means **implemented**, **planned in the active phase**, or **later
phase/not yet applicable**. A path identifies the owning executable suite, not
a duplicated catalog of individual test steps.

| Requirement | Current evidence | Status |
|---|---|---|
| Article IV — immutable evidence/provenance | `tests/unit/test_evidence_vault.py`, `tests/contract/test_evidence_schema.py`, `tests/integration/test_evidence_migration.py` | Implemented |
| Article VI — authorization at query time | `tests/component/test_auth.py` (incl. clock-skew leeway bounds), `tests/component/test_route_gating.py` (no ungated route, no `public_route` symbol, only the workspace bundle is mounted), `tests/contract/test_authorization_matrix.py` (all 37 shipped operations' role/purpose policies), `tests/component/test_workspace_serving.py` (API prefixes never fall back to the SPA), `tests/integration/test_api.py`, `tests/integration/test_authz.py`, `tests/integration/test_graph_routes.py`, `tests/integration/test_ingest_routes.py`, `tests/integration/test_identity_routes.py`, `tests/system/test_authz_openfga.py` | Implemented with no exemption: T24 adds ontology-field omission, role × handling × membership × sensitivity coverage, no-count/404 cases and purpose enforcement for case creation |
| Article VII — machines suggest, humans decide | `tests/integration/test_ingestion.py`, `tests/integration/test_actions.py`, `tests/integration/test_review_envelope.py`, `tests/unit/test_suggestion_idempotency.py` | Implemented: the typed envelope ships in T17, so acceptance dispatches per kind and every kind is either acceptable or explicitly refused by name; identity-candidate dispatch lands with `adjudicate_identity` in T20, UI in T23b |
| Article VIII — disagreement/retraction preserved | `tests/integration/test_actions.py`, `tests/integration/test_api.py` | Implemented for claim retraction; contradiction UI planned in T23 |
| Article X — append-only audit | `tests/contract/test_audit_schema.py`, `tests/integration/test_audit.py`, `tests/integration/test_actions.py` | Implemented |
| Article XI — ontology is domain truth | `tests/contract/test_ontology.py`, `tests/contract/test_schema.py`, ontology CI gate | Implemented for ontology v1; module/codegen drift planned in Phase 3 |
| Article XIII — rebuildable projections | `tests/integration/test_graph_routes.py` (bounded traversal over the projection: hop/element budgets, disjoint segments, build stamps and staleness), `tests/integration/test_edge_projection.py` (all seven `speckit/specs/02-data-model.md` §7.1 blocking cases plus adjacency, both-endpoint merge, retraction and id-stable idempotency), `tests/unit/test_edge_segmentation.py` (interval algebra), `tests/unit/test_projection_weights.py`, `tests/integration/test_projections.py` | Implemented: v2 lands in T21 — identity resolution through mention anchors then the canonical map, time-segmented rows, support summary, revision/ontology/builder stamps, no aggregate weight column |
| Article XIV — core is domain-neutral | `tests/component/test_core_independence.py` (AST sweep: `aegis` imports `legacy.*` only at the two enumerated ADR-023 exemptions, and never from `projections`/`analytics`) | Implemented for the import boundary (H-36, T21); ontology-module neutrality is Phase 3 |
| Phase 2 reversible identity/stale revision | `tests/integration/test_adjudication.py` (all seven `speckit/specs/05-entity-resolution.md` §8 cases, plus role and dual-control gates), `tests/unit/test_canonical_lineage.py` (chain resolution, cycle guard), `tests/integration/test_identity_ledger.py`, `tests/integration/test_edge_projection.py` (projection-side merge collapse and split restore), `tests/contract/test_schema.py`, `tests/integration/test_schema.py` | Implemented: T17 schema, T20 adjudication + canonical map, T21 projection-side reversal |
| Phase 2 deterministic ER proposes, never merges | `tests/integration/test_er_rules.py` (every case asserts no membership moved and no decision was written), `tests/contract/test_ontology.py` (identifier predicates are declared, not hardcoded) | Implemented in T18; Splink producer T19, adjudication T20 |
| Phase 2 provenance panel/contradictions | `tests/integration/test_why_connected.py` (claims, three separate grading dimensions, corroboration beside contradiction, mention anchors, identity-decision line, clearance filtering applied in the query, 404-not-403), `tests/integration/test_entity_provenance.py` (11 cases: contradictory DOBs grouped under one predicate, each naming the other in *both* directions, corroboration not cancelling contradiction on the same claim, uncontested predicates carrying no relations, the three grading dimensions apart with no combined score, source and record per claim, claims written against a merged-away id still appearing, a followed stale id reporting `resolved_entity_id`, a restricted claim absent for a junior analyst, 404-not-403, auth required), `ui/e2e/provenance.spec.ts` (12 cases: edge click opening the panel with its tally and sources, the identity-decision line, gradings apart, node click opening its claims, both DOBs rendering with a visible `contradicts` badge, a contested group marked *and* an uncontested one not, both disagreeing sources named, selection not re-laying out the graph, close, search-then-focus seeding the canvas, a phonetic hit labelled "sounds like", and no query below the minimum length) | Implemented T23c. The node panel needed `GET /v1/entities/{id}` to carry claim relations at all (ADR-036); the same read was dropping claims written against merged-away ids, which the merge case now pins |
| Phase 2 entity search | `tests/integration/test_search.py` (16 cases: label/alias/near-miss matching, a romanized query finding a Sinhala name **and** a guard proving the stored keys are why, a Sinhala query, an over-clearance entity *absent rather than ranked last*, clearance not narrowing what is otherwise visible, a case-scoped entity invisible to a non-member and findable once they join, an entity with no readable claim unreachable, tombstoned entities excluded, noise and empty queries returning nothing, auth required, query length bounded, results ordered and bounded), `tests/integration/test_translit_key_migration.py` (backfill computes the same keys the ER pipeline uses; downgrade drops the columns and keeps the mention) | Implemented T23c against ADR-035's stored keys. Authorization is a subquery applied in candidate generation, so the result *count* carries no signal either (ADR-012, B-17) |
| Phase 2 projection rebuild route | `tests/integration/test_projection_routes.py` (8 cases: an admin rebuilding and being told the anchor/map split, the build stamp equal to the ledger's active revision, idempotence across two runs, analyst **and** supervisor refused — the gate is the admin role, not rank — anonymous 401, the allow audited with the report as its detail, the deny audited too, and a second concurrent rebuild refused with 409 against a real advisory lock then recovering once released) | Implemented T23c. Spec 06 §2.6's "1 concurrent" is enforced with a transaction-scoped Postgres advisory lock, so a failed rebuild releases it on rollback rather than wedging the route |
| Phase 2 transliteration quality thresholds | `tests/unit/test_mention_normalize.py` (blocking keys preserve Sinhala/Tamil, stay slugify-compatible on Latin), `tests/unit/test_translit.py` (Latin/script/phonetic keys), `tests/integration/test_splink_pipeline.py` (seeded Sinhala/English pair scores above threshold with its waterfall persisted; the hard negative is not proposed), `tests/integration/test_mention_extraction.py` | Implemented T17/T19. The emission threshold is live in `aegis/er/settings.py`; the golden-set precision/recall gates in `speckit/specs/05-entity-resolution.md` §6 still need the T26 harness |
| Phase 2 field sensitivity and route matrix | `tests/contract/test_authorization_matrix.py` (exact operation set + role/purpose policy), `tests/integration/test_authz.py` (handling, membership, retraction and an open row carrying a restricted ontology field), `tests/integration/test_ingest_routes.py` (restricted suggestions absent without a count; governance seams stored/returned; cursor concurrent-insert regression), `tests/integration/test_identity_routes.py` (restricted identifier candidate absent), existing provenance/graph/search suites (shared claim-query boundary), `tests/component/test_route_gating.py` (zero anonymous exemptions) | Implemented T24a/T24b; restricted means absent, never marked, counted or hinted |
| Phase 2 cursor pagination | `tests/unit/test_pagination.py` (opaque route scope, malformed/wrong-scope rejection, bounds), `tests/integration/test_ingest_routes.py` (stable iteration across an intervening insert and no total), `ui/e2e/*.spec.ts` + production TypeScript build (paged response contracts and list rendering) | Implemented T24c on review queue, identity candidates, entity search, sources, source records and audit; every cursor is re-authorized |
| Phase 2 workspace shell and governed graph view | `ui/e2e/smoke.spec.ts` (unauthenticated visit → PKCE redirect → shell → canvas drawn from `/v1/graph/expand`; bearer token attached; nothing in web storage), `tests/component/test_security_headers.py`, `tests/contract/test_openapi.py` (operation-id stability, committed-document drift) | Implemented T22. The smoke journey stubs Keycloak and the API at the network boundary; the live-stack loop is T25/T27 |
| Phase 2 source landing, derivatives and extraction | `tests/integration/test_ingest_routes.py` (29 cases: idempotent re-land, version-conflict and oversize quarantine with reasons accumulating, transport `413` landing nothing, clearance floor on landing and on reads, 404-not-403 above clearance, derivative reuse, replay adding no duplicate suggestions, **zero claims written**, quarantine blocking extraction, release unblocking it, audit rows for land and extract), `tests/unit/test_derivatives.py` (unsupported media type and missing type refused before any I/O, scanned PDF named as needing OCR, text records get no derivative), `ui/e2e/sources.spec.ts` (land a PDF and a pasted note, no-op re-upload, quarantine reason, release, bearer token, refusal surfaced) | Implemented T23a. The fixture PDF is generated by `tests/support/pdf.py`, not committed. Browser stubs are hermetic; MinIO-backed landing and extraction were run against the live stack via the CLI |
| Phase 2 review queue, adjudication and identity routes | `tests/integration/test_identity_routes.py` (21 cases: both candidate bands with their waterfall verbatim, each side's current entity, disposition/producer filters, the revision the list was read at, authorization on all three routes, a confirm recording the human as `decided_by`, note required on every mode, `evidence_basis` typed onto reject alone, a reject moving no membership, audit rows, **409 with the intervening decisions as data** and a disjoint scope that is *not* a conflict, batch-confirm writing one decision per pair, refusing the probabilistic band, reporting partial outcomes, bounded at 100, and idempotent against a settled candidate), `tests/integration/test_adjudication.py` (stale scope now asserted structurally, not by substring), `ui/e2e/review.spec.ts` (13 cases: producer metadata that makes a suggestion checkable, edit-then-accept recorded as an edit, reject requiring a reason, the two-directional waterfall, "no score" rather than an invented one, batch offered only for the pre-verified band, all three pair decisions including "cannot tell", and a stale decision re-presented rather than retried) | Implemented T23b. The three suites spec 06 §2.2 names by name are `test_identity_candidates`, `test_batch_confirm`, `test_concurrency`; browser stubs are hermetic and keep the service's rules |
| Phase 2 fictional ingest-to-projection UI loop | Future `tests/e2e/` MVP journey using `data/sample/mvp/` | Planned: T25/T27 |

## Running the suite locally

Point `AEGIS_TEST_DATABASE_URL` at a disposable database and use
**`127.0.0.1`, never `localhost`**. On Windows `localhost` resolves to `::1`
first while the compose ports publish IPv4 only, so every connection stalls
~2 s on the failed IPv6 attempt before falling back. Nothing errors — it is
pure latency, invisible per call and ruinous in aggregate:

| Same 244 tests | Wall clock |
|---|---|
| `localhost` | 1:59:59 |
| `127.0.0.1` | 0:00:37 |

`make test*` exports the correct URL by default, and
`tests/unit/test_config_defaults.py` fails if a local-service default
regresses to `localhost`. The one deliberate exception is `keycloak_url`,
which is the OIDC **issuer identity** and must match the `iss` claim Keycloak
mints — an IP there 401s every request.

If a local run takes minutes per module, check this before suspecting the
tests.

## Manual test case format

Use IDs such as `MAN-P2-001`. Record requirement, owner, environment,
preconditions, fictional or authorized dataset, steps, expected results,
evidence location, cleanup, result, and execution date. Manual real-corpus
smokes must follow `data/real/README.md`, capture no sensitive output, and
remain non-blocking unless the phase charter explicitly says otherwise.
