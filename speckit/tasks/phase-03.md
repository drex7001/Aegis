# Phase 3 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them; narrower dependencies are noted in the task text. Reference specs in
parentheses. Numbering continues from Phase 2 (T28).

> **Status: READY FOR T29 RE-VALIDATION, NOT ACTIVE.** Phase 2 passed the ★ MVP
> gate on 2026-07-20. Rewritten 2026-07-18 to the narrowed
> charter (ADR-033): module composition is the headline; functions execution,
> side-effect engine, and the Python SDK moved out to their consumer phases.
> T29 re-validates this plan and spec 08 against what Phase 2 actually shipped
> before any other task starts; no Phase 3 implementation is active yet.
> Charter: `../phases/phase-03-ontology-v2.md` · spec:
> `../specs/08-ontology-v2.md`.

## Milestone A — Spec finalization & module composition

**T29. ⛓ Spec 08 finalization (narrowed)** — walk the draft against the
P2-as-built system; specify the **module manifest** format (name, namespace,
version, imports + version constraints, type ownership, enable/disable);
close the closed parameter type list (spec 08 §6) and submission-criteria
registry names; move functions execution, side effects, and Python SDK
sections to an explicit "future consumers" appendix (spec 08 §10); add stable
operation IDs + error envelope to specs/06. Divergences become ADRs.
AC: spec 08 status flips draft → final with the module section; every retained
v2 feature names its consumer; excluded machinery is listed in §10 with its
trigger phase.

**T30. ⛓ Module loader & composition** (spec 08 §modules; needs T29) — loader
resolves a set of module files (platform + domains) into one registry:
namespace prefixes, import resolution, cross-module reference validation
(reference without declared import = precise error), name-collision detection,
per-module versions in the release metadata. Split the current `aegis.yaml`
into `ontology/platform.yaml` + `ontology/modules/criminal-network.yaml`
(pure reorganization — no vocabulary change; claims' `ontology_version`
interpretation unchanged).
AC: composed registry passes all Phase 1–2 tests; a fixture with a
cross-module reference and no import fails with a precise error; a name
collision across modules fails validation; `aegis ontology validate` reports
per-module versions.

**T31. Second-domain proof fixture** (Article XIV; needs T30) — a tiny
fictional `border-cargo` module (≈2 object types, 3 predicates, 1 interface
implementation) in `tests/fixtures/ontology/`; CI loads core + fixture module,
runs claim record/read + projection round-trip against it.
AC: the fixture round-trips through actions, API, and projection with **zero
core-code change** (the test fails if any `aegis/` file needs domain edits);
disabling the module removes its vocabulary from validation.

## Milestone B — Semantic layer v2

**T32. ⛓ Shared properties + interfaces** (spec 08 §3–4, §9; needs T30) —
extend loader/validator/registry: `shared_properties:` and `interfaces:`;
predicates may target interfaces (expanded at validation); starter set:
shared `alias`, `registered_identifier`, `notes`; interfaces `party`,
`identifiable`. Ontology minor bump via the T35 proposal workflow once it
lands (sequence the bump after T35 if needed).
AC: a predicate with `subject: [party]` validates for member types and rejects
non-members; a `shared:` reference overriding type/sensitivity fails; all
prior tests green.

**T33. Codegen v2 for existing targets** (spec 08 §8; needs T32) — Pydantic
models, FGA stubs, and UI descriptors emit interface + shared-property +
module metadata for P4's generic screens.
AC: `aegis ontology generate` touches only `_generated` files; committed
outputs regenerate byte-identical in CI; FGA stub diff shows interface types.

## Milestone C — Actions v2 schema

**T34. ⛓ Actions v2 declarations + enforcement** (spec 08 §6, §9.5) —
`parameters` (closed type list → generated Pydantic request models; undeclared
parameters rejected) and `submission_criteria` (named predicates evaluated in
`aegis/actions/`; failures are audited denials); migrate all existing actions
to declared parameters. **No side-effect engine** — existing hardcoded
refresh paths stay; `side_effects:` keys parse and are stored for the future
consumer phase.
AC: an undeclared parameter is rejected with the generated model's error; a
non-qualifying actor fails a declared criterion and the denial is audited
(charter exit); validator rejects unknown parameter types/criteria names.

## Milestone D — Change management

**T35. Proposals, history, release metadata, CI gates** (spec 08 §7; needs
T30) — `ontology/proposals/NNN-title.md` template (motivation, diff,
competency questions, migration plan); `ontology/history/`; **release
metadata** carries proposal id + previous content hash + compatibility class
(compared against the previous release artifact, not git history — H-16); CI:
version monotonicity per module, minor/patch bumps introduce no
removals/renames, major bumps carry history copy + migration. Backfill
proposal 001 documenting the modularization bump itself.
AC: a bump without a proposal reference in release metadata fails CI; a minor
bump removing a predicate fails the diff check; proposal 001 exists.

## Milestone E — Contract & TypeScript client

**T36. ⛓ API contract conventions** (specs/06; needs T29) — stable operation
IDs on every route, uniform RFC 7807 error envelope, versioned OpenAPI
document committed as an artifact; contract-diff check in CI (breaking API
change fails unless flagged).
AC: OpenAPI artifact committed + regenerated cleanly; a renamed operation ID
fails the contract-diff check.

**T37. ⛓ TypeScript client generation** (spec 08 §8 narrowed; needs T33, T34,
T36) — client generated from the OpenAPI document (openapi-typescript-class
generator — adopt-before-build, H-11), enriched with ontology-derived
constants (predicates, kinds, handling codes) from codegen; committed under
`sdk/ts/`; drift gate.
AC: generated package type-checks in CI; an example script lists entities with
correct types; ontology constants match the registry; CI fails on drift.

**T38. UI migration to the generated client** (needs T37) — `ui/` swaps its
P2-era generated client for `sdk/ts/` with no screen rewrites (types only);
action calls use generated parameter types from T34.
AC: UI type-checks and its e2e smoke passes against the new client; no
hand-written request/response types remain in `ui/src`.

**T39. Ontology-change end-to-end proof** (charter exit №1; needs T35–T38) —
land a new test predicate on an interface **in a domain module via the
proposal workflow**: the change flows to API validation and the TS client
with zero hand-written domain code.
AC: the change's diff touches only the module file, the proposal, and
regenerated artifacts; a test proves the API accepts the new predicate and
the client exposes it; reproducible in CI.

**T40. Phase exit review** — walk the charter's gate criteria (non-deferrable,
ADR-025); update speckit docs where reality diverged; append ADRs; write
`../reviews/phase-03-exit-review.md`; tag per the git workflow.
AC: every gate criterion checked; non-blocking deliverables carried over with
owner + target phase recorded.

## Explicit non-goals for Phase 3

Functions execution machinery and derived-record runs (P5/P6, ADR-027
semantics), side-effect outbox engine (first consumer phase), Python SDK (P8),
object sets (P6), object views / workspace features (P4), new domain
predicates beyond the worked examples, events/geometry (P5), Foundry-style
live branching, OPA policy-as-code, compartments (P7), any new AI capability
(P8).
