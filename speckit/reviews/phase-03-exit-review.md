# Phase 3 — Exit Review (T40)

Date: 2026-08-17
Release: Aegis 0.3.0
Tag after merge: `phase-3-ontology-modules`

## Verdict

**PASS — Phase 3 is complete.** All five charter criteria are checked;
none is deferred or weakened. Article XIV now has a mechanism behind it:
a domain is an ontology module, and a fictional second domain loads,
validates, and is served over the API by a core that has never heard of it.

This closes Milestone III's first half. It is not a deployment authorization —
the pilot gate remains open and untouched (§Deployment boundary).

## Exit criteria — non-deferrable (ADR-025)

- [x] **A new predicate added to a domain module via the proposal workflow flows
  to API validation and the TS client with zero hand-written domain code.**

  T39 landed `controls` (a *party* controlling an organization) through
  proposal 004 — the first proposal written *before* its change merged, and the
  first shipped predicate whose endpoint is an interface.
  `tests/contract/test_ontology_change_flow.py` (8 cases) and
  `tests/integration/test_ontology_change_flow.py` (6 cases) prove the API
  accepts it, the projection groups it under its declared category, the
  suggestion → review → accept path carries it, and the generated client
  exposes it with `subjectInterfaces: ["party"]` preserved beside the
  expansion. Sweeps assert no file under `aegis/` or `ui/src` names it.

- [x] **The second-domain fixture module loads, validates, serves object/claim
  routes, and appears in the client types — with zero core-code change.**

  `tests/fixtures/ontology/border-cargo.yaml` is two object types, three
  predicates and one interface implementation, composed against the **real**
  platform module. `tests/contract/test_second_domain.py` (7 cases) includes a
  sweep over every file in `aegis/` for the fixture's vocabulary;
  `tests/integration/test_second_domain.py` (4) covers claim record/read and
  the projection; `tests/integration/test_second_domain_routes.py` (5) covers
  the routes — an ordinary app with one line changed (`app.state.ontology`)
  serves `cleared_at`, refuses `member_of` with `predicates.member_of`, and
  returns the T36 error envelope for a domain it has never seen. The fixture's
  own generated constants are asserted in
  `test_the_fixture_domain_generates_without_core_changes`.

  The route half was **added at T40**: T31 had covered the action layer and the
  projection but not the API, and the criterion says *serves routes*. Adding it
  was the honest reading of the gate, not a stretch of it.

- [x] **A cross-module reference without a declared import fails validation with
  a precise error.**

  `tests/contract/test_ontology_modules.py` (26 cases). The error names both
  modules and the YAML path — `harbour.predicates.moored_at.subject: 'vessel'
  is owned by module 'platform', which 'harbour' does not import`. Covered for
  type references, handling-code references via property sensitivity, interface
  implementation, and shared-property references; plus collisions, version-pin
  mismatches, unsatisfiable specifiers, import cycles, and enable/disable.

- [x] **An action with declared `submission_criteria` rejects a non-qualifying
  actor in a test, and the rejection is audited.**

  `tests/integration/test_actions_v2.py` (13 cases). An auditor calling
  `open_case` is refused with
  `actions.open_case.submission_criteria.actor_holds_action_role`, a
  `decision="deny"` audit row records the actor, the failed criterion and the
  reason, and nothing is written. The denial is written in its own session, so
  it survives a rolled-back caller transaction — asserted directly.

- [x] **CI fails on codegen drift and on an ontology bump without proposal +
  history entry; all Phase 1–2 tests green on the modular ontology.**

  `aegis ontology generate --check` and `aegis ontology check-release` are CI
  steps and `make lint-ontology` targets; both are also contract tests, so
  drift fails the fast suite rather than only the pipeline.
  `tests/contract/test_ontology_release.py` (27 cases) exercises each gate
  against its own failure mode. Phase 1–2 green: **282 integration tests pass
  unchanged** on the composed registry, which was T30's acceptance criterion
  and is the strongest evidence in this review.

## What Phase 3 actually changed

| Task | Landed |
|---|---|
| T29 | Spec 08 finalized against the as-built system; six divergences → ADR-037…040 |
| T30 | Composition manifest + module loader; `aegis.yaml` split platform/domain |
| T31 | `border-cargo` second-domain fixture, in CI |
| T32 | Shared properties + interfaces (ADR-041 flipped their direction) |
| T33 | `aegis ontology generate` — composed artifact, release metadata, TS constants |
| T34 | Action parameters + submission criteria enforced at the write, denials audited |
| T35 | Proposals, release chain, six compatibility gates |
| T36 | RFC 7807 envelope in the OpenAPI contract; breaking-change gate (ADR-042) |
| T37/T38 | Workspace consumes generated error and request types |
| T39 | `controls` through the proposal workflow — the end-to-end proof |

Ontology `1.2.0 → 1.6.0` across four bumps, each with a proposal.

## Decisions taken during the phase

Six ADRs, each because implementation contradicted a plan written before the
code existed:

- **ADR-037** — the ontology is a composition. Names stay **unprefixed**:
  `claim.predicate` is an immutable TEXT column, so lexical namespacing would
  have meant rewriting recorded rows. Collisions are errors instead.
- **ADR-038** — spec 01 §5's three "Phase 1" codegen targets were never built.
  Codegen is built per consumer; P3 shipped three, P4/P7/P8 own the rest.
- **ADR-039** — the TS client was already OpenAPI-generated, so `sdk/ts/` waits
  for an out-of-repo consumer. The real gap was the error envelope.
- **ADR-040** — action declarations become the write-side gate. Ontology
  `roles` had fired for one action in thirteen.
- **ADR-041** — interfaces are implemented by the object type. A `members:`
  list would have forced the platform module to import a domain.
- **ADR-042** — the API contract diffs against a git ref while the ontology
  diffs against a committed artifact, because claims stamp the ontology version
  and nothing stamps an API version. Spec 06 §7.3 claimed a symmetry that does
  not hold.

## Defects found and fixed

Three, none of which the phase set out to look for:

1. **`build_graph` emitted edges to nodes it had excluded** (an entity
   tombstoned by a canonical-map rebuild the projection had not caught up
   with), using the raw entity id as the node reference — killing
   `detect_cells` with an opaque `KeyError` instead of returning a graph.
   Found by the second-domain test; the regression case was verified to
   reproduce the exact failure with the fix reverted.
2. **Review acceptance bypassed the declared defaults.** `_dispatch_acceptance`
   called `_create_claim` with the raw draft, so a claim recorded directly got
   the ontology's defaults and the identical claim accepted from the queue did
   not. Acceptance now dispatches through `record_claim`'s declared parameters,
   as ADR-031 §2 always said it should.
3. **T33's drift gate would have shipped inoperative — twice.** `.gitignore`
   ignores `*.json` wholesale, so the release artifacts were silently
   untracked; and `core.autocrlf=true` would have failed `--check` on any fresh
   Windows checkout. Both found by testing the gate rather than trusting it.

## Constitution conformance

| Article | Finding | Evidence |
|---|---|---|
| I — claims, not facts | Pass | No canonical property store added; `controls` is a claim like any other |
| II — no inherent derogatory status | Pass | Proposal 004 argues the point explicitly; `controls` is neutral and the doubt stays in the grading |
| III — grading dimensions separate | Pass | Untouched; `grade` parameters name a dimension each, never a composite |
| IV — evidence is not intelligence | Pass | Untouched |
| V — reversible identity | Pass | Untouched; adjudication tests green throughout |
| VI — authorization at query time | Pass | Route gates unchanged; the 403 documentation is now **derived** from those gates, asserted in both directions |
| VII — machines suggest, humans decide | Pass | `side_effects` declared and **not executed** — asserted as an absence; acceptance still dispatches through a human-executed action |
| VIII — disagreement preserved | Pass | Untouched |
| IX — association is not guilt | Pass | Proposal 004 records that `controls` is claimed, never derived; no `computed` flag |
| X — everything audited | Pass | The actions layer gained a `decision="deny"` path it did not have |
| XI — ontology is domain truth | **Pass, strengthened** | The artifact is now a composition with per-name ownership; four CI gates guard it |
| XII — adopt before build | Pass | `packaging` for version specifiers, `openapi-typescript` retained rather than swapped |
| XIII — projections are caches | Pass | Unchanged; the graph-builder fix makes a stale projection render honestly rather than crash |
| XIV — core is domain-neutral | **Pass, now executable** | Two sweeps over `aegis/` for domain vocabulary, plus a second domain served over the API |

## Deliverables and reality check

Every charter deliverable landed. Two were **narrowed with reasons recorded**
rather than dropped:

- **`sdk/ts/` as a package** — deferred to its first out-of-repo consumer
  (ADR-039, spec 08 §11.4). The generated surface lives in `ui/` where its only
  consumer is.
- **UI-descriptor and FGA-stub codegen** — moved to P4 and P7 (ADR-038). The
  FGA generator would emit an empty file today: `infra/fga/model.fga` declares
  no domain object type.

The T39 "example script" was dropped outright: `ui/src` is the example, it
exercises every generated type on real screens, and its type-check is in CI. A
toy script beside it would be a second thing to keep working.

Explicit non-goals held. No functions execution, no side-effect engine, no
Python SDK, no object sets or views, no events or geometry, no compartments, no
AI capability.

## Carryovers

| Item | Owner | Target | Dependency impact |
|---|---|---|---|
| Bundle/server ontology-version mismatch surfaced in the UI | P4 owner | With the generic screens that read `ui_meta.json` | None — the constants already carry `ONTOLOGY_VERSION`; nothing today renders the comparison |
| UI-descriptor codegen (`ui_meta.json`) | P4 owner | P4 generic screens | None on P3; the vocabulary route serves what P2 needs |
| FGA object-type stub codegen | P7 owner | When a domain type first gets an FGA relation | None; the generator has nothing to emit until then |
| Python SDK | P8 owner | P8 producers | None (ADR-033, unchanged) |
| Functions execution + side-effect outbox | P5/P6 and first-consumer owners | Spec 08 §11.1–11.2 | None; declarations parse and nothing runs them |
| Pilot gate (TLS, secrets, restore boundary, Object Lock, health/throughput) | Deployment owner | Before any non-loopback listener or second real user | Blocks deployment, not P4 development |

## Verification

Run on the exact reviewed tree, against PostgreSQL 16 on `127.0.0.1:5433`:

```
uv run pytest -q tests/unit tests/component tests/contract   # 355 passed in 11.32s
uv run pytest -q tests/integration                           # 282 passed in 78.29s
uv run aegis ontology validate                               # OK v1.6.0, 2 modules
uv run aegis ontology generate --check                       # OK: 4 artifacts current
uv run aegis ontology check-release                          # OK: v1.6.0 (minor, proposal 004, from 1.5.0)
uv run aegis api check-contract                              # OK: 0 additive, 0 breaking
cd ui && npm run typecheck && npm run build && npm run test:e2e   # clean; 42 passed
```

**System tests were not runnable on the development machine** — the OpenFGA
container cannot bind its port there — so CI's `system-tests` job is their only
execution. It passed on every one of the nine Phase 3 pull requests (#39–#47),
which is the same arrangement T28 recorded for Phase 2 and is stated here for
the same reason: the reader should know which evidence came from where.

Phase 3 added **160 tests** (355 + 282 against P2's 219 + 258).

## Release action

`pyproject.toml` and `uv.lock` advance from 0.2.0 to **0.3.0**. After the
review PR is squash-merged, tag that master commit:

```bash
git tag -a phase-3-ontology-modules -m "Phase 3 exit: ontology modules and contracts"
git push origin phase-3-ontology-modules
```

## Final decision

All five gate criteria are checked. Phase 3 is complete and **Phase 4 —
investigation workspace v2 & object views** may begin with its own re-validation
task (T41), which should disposition the carryovers above before anything else.
