# Phase 2 — Exit Review (T28)

Date: 2026-07-20  
Release: Aegis 0.2.0  
Tag after merge: `phase-2-mvp`

## Verdict

**PASS — Phase 2 is complete and the ★ MVP gate is closed.** All five charter
criteria are checked; none is deferred or weakened. The result is a governed
localhost MVP, not a pilot or production authorization. Phase 3 is ready for
its mandatory T29 re-validation but is not active until explicitly started.

The evidence baseline is `df13d11` (T27, PR #37). Its required GitHub checks
all passed: fast/contracts, PostgreSQL integration, OpenFGA system behavior,
coverage/governance/ontology, and workspace type-check/build/browser smoke.
This review changes status and release metadata only; its own PR must pass the
same protected-branch matrix before this verdict can reach `master`.

## MVP gate — non-deferrable criteria

- [x] **Merge → intervening edits → split restores mention-attributable state;
  stale concurrent decisions are rejected and re-presented.**

  `tests/integration/test_adjudication.py` exercises all seven reversal cases
  from spec 05 §8, including intervening claim edits, partial splits, later
  mentions, scoped optimistic concurrency, and the human evidence/audit
  requirements. `tests/integration/test_edge_projection.py` proves the graph
  collapses on merge and restores on split without rewriting claim rows;
  `tests/unit/test_canonical_lineage.py` pins deterministic lineage replay and
  its cycle guard.

- [x] **Every rendered edge is explainable; grading dimensions remain separate;
  contradictions render side by side.**

  `tests/integration/test_why_connected.py` and
  `tests/integration/test_entity_provenance.py` prove at least one authorized
  source record per edge, reliability/credibility/verification as distinct
  fields, corroboration and contradiction counts, identity lineage, and
  query-time clearance filtering. `ui/e2e/provenance.spec.ts` covers the edge
  and node panels, three separate grading rows, two contradictory DOB claims
  with visible `contradicts` status, both source records, and no combined
  confidence score.

- [x] **The Sinhala/English variant clears the numeric threshold, is adjudicated
  in the UI, and the rebuilt graph reflects revision 1; the namesakes remain
  distinct.**

  T26 records pre-verified precision **1.000**, seeded transliteration recall
  **1.000**, and review load **33.33/1,000** against the 0.95 / 0.70 / 50 gates.
  `tests/integration/test_splink_pipeline.py` persists the feature waterfall
  and graph snapshot; `tests/integration/test_er_evaluation.py` proves the two
  fictional Ruwan Silva records remain in distinct active entities with zero
  automatic decisions. During `MAN-P2-001`, the workspace displayed the
  Nimal Perera / නිමල් පෙරේරා candidate at **0.99**, recorded the named
  analyst's evidence note, warned that the projection was stale, rebuilt it at
  identity revision 1, returned one Nimal result, and returned two Ruwan
  results.

- [x] **Restricted fields are absent for low-clearance callers on every shipped
  route; every route is authorized and no public exemption exists.**

  The executable spec-06 matrix in
  `tests/contract/test_authorization_matrix.py` covers all 37 shipped
  operations. `tests/component/test_route_gating.py` rejects any route without
  an authorization dependency and contains no `public_route` branch.
  `tests/integration/test_authz.py`, `test_ingest_routes.py`,
  `test_identity_routes.py`, `test_search.py`, `test_graph_routes.py`,
  `test_why_connected.py`, and `test_entity_provenance.py` exercise handling,
  case membership, no-existence-leak behavior, and the shared property
  sensitivity boundary. The fictional restricted `has_nic` claim is omitted,
  never marked, counted, ranked, or hinted.

- [x] **A non-builder completes ingest → suggest → review → accept → projection
  from the UI by following `docs/MVP_DEMO.md` on the fictional fixture.**

  T27's fresh browser/operator run used a disposable `aegis_mvp_demo`
  database and the served production bundle. The agent operator had not built
  T17–T26. It landed `data/sample/mvp/remand-register.txt`, ran structural
  extraction, observed one waiting suggestion and zero machine-written
  claims, accepted it as `dev-analyst` with an evidence note, handed off to
  `dev-admin`, rebuilt one edge/segment, returned as the analyst, and opened
  the governed graph. It then loaded the complete T25 fixture and executed the
  identity observations above. The exact path, local roles, expected labels,
  cleanup, and pass record are frozen in `docs/MVP_DEMO.md` and guarded by
  `tests/contract/test_mvp_demo_runbook.py`; the admin rebuild and graph
  refresh are pinned hermetically in `ui/e2e/provenance.spec.ts`.

## Constitution conformance

Every Article was checked. Articles VI and VII receive the explicit exit
spot-check required by T28.

| Article | Exit finding | Evidence |
|---|---|---|
| I — claims, not facts | Pass | Claim actions require source records; projections read accepted claims rather than bare relationships |
| II — no inherent derogatory status | Pass | Ontology contract validation; no criminal/terrorist/fraudster object type or universal risk score |
| III — grading dimensions separate | Pass | Provenance API/integration suites and UI panel cases expose three dimensions with no stored combined score |
| IV — evidence is not intelligence | Pass | Vault/derivative unit tests; extraction keeps originals immutable and proposals outside evidence |
| V — reversible identity | Pass | Seven adjudication reversal cases, ledger revisions, negative constraints, projection split restore |
| **VI — authorization at query time** | **Pass** | **37-operation matrix, zero-exemption route lint, OpenFGA system tests, row/field filtering and 404/no-count cases** |
| **VII — machines suggest, humans decide** | **Pass** | **Structural/semantic extraction writes zero claims; ER rules/Splink write candidates only; identity decisions require a human actor/note; T25/T27 accept through named reviewers** |
| VIII — disagreement preserved | Pass | Retractions remain rows; contradictory Maya DOB claims and relation render together |
| IX — association is not guilt | Pass | No leadership/guilt inference or metric was added; graph labels remain claimed predicates |
| X — everything audited | Pass | Allow/deny and adjudication integration cases assert audit rows; chain verification remains blocking |
| XI — ontology is domain truth | Pass | `aegis ontology validate` is a required CI gate; P2 ontology bumps followed versioning/history rules |
| XII — adopt before build | Pass | Keycloak, OpenFGA, Splink, PostgreSQL/MinIO, React/Vite, and maintained OIDC/OpenAPI tooling are used at their boundaries |
| XIII — projections are caches | Pass | Edge/canonical projections rebuild from canon, carry revision/version stamps, and are idempotent |
| XIV — core is domain-neutral | Pass | AST independence test permits only the two ADR-023 migration/extraction exemptions and forbids legacy imports in analytics/projections |

### Article VI/VII spot-check execution

The definitive full-stack execution evidence is the green PR #37
required-check matrix on the exact pre-review code. T28 also reran **22
service-free Article VI/VII assertions** from the route lint, authorization
matrix, suggestion-idempotency, and ER-evaluation suites; all passed. Creation
of a separate local PostgreSQL database was unavailable in the managed Windows
environment, so the existing development database was deliberately left
untouched rather than reused. The T28 review PR's fresh Linux PostgreSQL,
OpenFGA, coverage, ontology, and workspace jobs are therefore the final
executable spot-check and merge gate.

## Deliverables and reality check

| Charter group | Result |
|---|---|
| A — design pack | Complete: ADR-028…031 models and specs 02/05/06 landed before implementation |
| B — identity core | Complete: mentions, deterministic/Splink candidates, ledger adjudication, negative constraints, concurrency |
| C — workspace/governed loop | Complete: durable authenticated React workspace, ingest/review/identity/graph/provenance/search, legacy explorer and `/api/*` removed |
| D — quality/close-out | Complete: sensitivity, cursors, authz matrix, numeric ER gates, fictional fixture, operator runbook, exit review |

Implementation discoveries are already reflected in specs and ADR-034…036:
synchronous bounded ingestion, stored transliteration search keys, and entity
detail relations/canonical resolution. T27's exact Keycloak logout origins and
admin rebuild control implement ADR-032 and the existing route matrix; they do
not change a load-bearing decision. **No new ADR is required by T28.**

The explicit Phase 2 non-goals held: no object-view/case/hypothesis expansion,
ontology modules, events/PostGIS product behavior, OpenSearch, object sets,
compartments/disclosure, hosted AI capability, or cosmetic workspace rewrite
was pulled forward.

One stale testing note said an automated live-stack browser file would land in
`tests/e2e/` with T27. Reality is the chartered three-boundary proof: T25's
real-PostgreSQL automated loop, the hermetic `ui/e2e/` workspace suite, and
the live `MAN-P2-001` non-builder usability run. `tests/e2e/README.md` now says
that directly. This is not a deferred gate: automation proves backend and UI
behavior, while the manual observation proves the human runbook criterion the
charter actually asks for.

## Owned carryovers and deployment boundary

These are non-blocking deliverables or already-chartered future work, not
deferred Phase 2 exit criteria:

| Item | Owner | Target | Dependency impact |
|---|---|---|---|
| Authorized real-OSINT smoke `MAN-P2-002` | Phase owner / authorized operator | Before any real-corpus demonstration; repeat per authorization | None on P3; manual, non-blocking, no captured sensitive output or hosted egress |
| Enforce P2 governance seams (legal authority, purpose vocabulary, retention/disposition) | Phase 7 owner | P7 T78 must assign the exact implementation tasks; T85 already owns legal-authority objects | None on P3–P6; blocks any claim that P7 governance is complete |
| Retire the final governed wrapper around legacy extraction | Phase 8 owner | P8 T90–T93 extraction-v2 contract/schema/runner | None on P3; the ADR-023 exemption stays enumerated and may not grow |
| Pilot gate (TLS, secret storage, complete encrypted restore boundary, Object Lock/checkpoints, health/throughput review) | Deployment owner | Before any non-loopback listener or second real user | Blocks deployment, not local Phase 3 development |

The pilot gate remains open. Aegis 0.2.0 may not be represented as pilot-ready
or production-ready.

## Release action

`pyproject.toml` and `uv.lock` advance from 0.1.0 to **0.2.0**, matching the
Phase 2 release boundary. After the protected review PR is squash-merged, tag
that master commit with the annotated tag:

```bash
git tag -a phase-2-mvp -m "Phase 2 exit: MVP gate passed"
git push origin phase-2-mvp
```

## Final decision

All hard boxes are checked. Phase 2 and Milestone II are complete. Proceed
only to **T29**, which re-validates Phase 3's pre-authored module-composition
plan against this as-built MVP; no later Phase 3 task starts first.
