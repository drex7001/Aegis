# Phase 3 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them; narrower dependencies are noted in the task text. Reference specs in
parentheses. Numbering continues from Phase 2 (T28).

> **Status: PRE-AUTHORED, NOT ACTIVE.** Phase 2 (T17–T28) must close the ★ MVP
> gate first. Authored 2026-07-17 ahead of phase start; T29 re-validates this
> plan and spec 08 against whatever Phase 2 actually shipped before any other
> task starts. Charter: `../phases/phase-03-ontology-v2.md` · spec:
> `../specs/08-ontology-v2.md`.

## Milestone A — DSL v2 core (semantic layer)

**T29. ⛓ Spec 08 finalization** (specs/08, charter §Specs) — walk the draft
against the P2-as-built system and the named consumers (P4 workspace, P6 object
sets, P8 AI grounding); close the open surfaces: the closed parameter type list
(spec 08 §6), the submission-criteria and side-effect registry names, SDK
package layouts (`sdk/python/aegis_sdk/`, `sdk/ts/`); add SDK-facing API
conventions (stable operation IDs, error envelope) to specs/06. Divergences
from the draft become ADRs.
AC: spec 08 status flips draft → final; every v2 DSL feature in it names its
consumer phase (charter risk: no feature without a consumer); specs/06 has the
SDK conventions section; anything dropped is listed in spec 08 §10.

**T30. ⛓ Shared properties + interfaces** (specs/08 §3–4, §9) — extend loader,
validator, and registry: parse `shared_properties:` and `interfaces:`;
validation rules §9.1–9.3 and §9.6 (a v1-shaped file still validates);
predicates may target interfaces, expanded to member types at validation time;
registry exposes interface → members. Ontology **0.4.0** (minor — additive)
ships the starter set: shared `alias`, `registered_identifier`, `notes`;
interfaces `party` (person, organization), `identifiable` (person, vehicle,
phone_number). Version-pin test updated.
AC: `aegis ontology validate` lists interfaces and shared properties; a claim
whose predicate declares `subject: [party]` validates for both member types
and rejects a non-member; a `shared:` reference overriding type or sensitivity
fails validation; all Phase 1–2 tests green on 0.4.0.

**T31. Codegen v2 for existing targets** (specs/08 §8; needs T30) — the three
Phase-1 targets emit the v2 semantics: Pydantic models for interface types,
FGA stubs including interface object types, UI descriptors carrying
interface/shared-property metadata for P4's generic screens.
AC: `aegis ontology generate` touches only `_generated` files; the committed
outputs regenerate byte-identical in CI (drift gate green); FGA stub diff shows
the interface types.

## Milestone B — Functions (kinetic layer: derivations)

**T32. Functions registry + execution harness** (specs/08 §5; needs T30) —
parse/validate `functions:` (output predicate exists, implementation path
importable, `system_claim` mode carries an ADR reference field); harness
executes `trigger: rebuild` functions; every output row records source_type
`algorithmic`, function name + version, and input claim IDs; `suggestion` mode
routes to the review queue (Article VII); CI check: implementation-hash change
without a function version bump fails.
AC: a fixture function in suggestion mode lands fully-attributed rows in
`review_queue`; validator rejects a function with a missing predicate,
unimportable path, or `system_claim` without an ADR ref; the hash-vs-version
CI check fails on a doctored fixture.

**T33. Prison co-location derivation** (specs/08 §5; needs T32) —
`derive_prison_co_location` v1 (`aegis/functions/prison_overlap.py`) computes
`co_located_in_prison_with` from remand-window overlap claims, replacing the
bare `computed: true` flag as the place the derivation lives. Electing
`system_claim` mode requires the ADR naming the derivation deterministic
(charter risk table) — write it in this task or default to `suggestion`.
AC: deleting the function's outputs and re-running reproduces them
byte-for-byte (exit criterion); every output row carries function name +
version + input claim IDs; the projection renders the derived edges with their
algorithmic source visible.

## Milestone C — Actions v2 (kinetic layer: writes)

**T34. ⛓ Actions v2 schema + enforcement** (specs/08 §6, §9.5) — extend the
`actions:` schema with `parameters` (closed type list → generated Pydantic
request models; undeclared parameters rejected), `submission_criteria` (named
predicates over actor + target state, evaluated in `aegis/actions/`; failures
are audited denials), and declared `side_effects`; migrate all 12 existing
actions to declare their parameters. Blocks the SDKs (T37–T39): call wrappers
are generated from `parameters`.
AC: a request with an undeclared parameter is rejected with the generated
model's error; a non-qualifying actor fails a declared criterion and the
denial appears in audit (exit criterion); validator rejects an unknown
parameter type, criterion, or side-effect name; ontology bump stays within
0.4.x (additive).

**T35. Side-effect outbox** (specs/08 §6; needs T34) — post-commit execution
via the outbox pattern (ADR-014 precedent): built-ins `refresh_projection` and
`notify` (log-backed stub; webhook stub allowed); failures retry, never roll
back the action; execution audited.
AC: accepting a suggestion via an action declaring
`refresh_projection: edge_projection` refreshes the projection through the
outbox; a side effect that throws retries without affecting the committed
action; effect runs visible in audit.

## Milestone D — Change management (governance layer)

**T36. Proposals, history, CI gates** (specs/08 §7; needs T30) —
`ontology/proposals/NNN-title.md` template (motivation, YAML diff, competency
questions, migration plan); `ontology/history/`; CI enforces: version
monotonicity, minor/patch bumps introduce no removals/renames (diff vs the
previous committed version), major bumps carry history copy + migration
script, a bump commit references a proposal. Backfill **proposal 001**
documenting the 0.4.0 v2 bump itself, so the discipline is self-hosting from
its first version.
AC: a test fixture with a version bump and no proposal fails CI; a minor bump
that removes a predicate fails the diff check; proposal 001 exists and the
0.4.0 commit references it.

## Milestone E — Generated SDKs (consumption layer)

**T37. ⛓ Python SDK** (specs/08 §8; needs T31, T34) — `aegis ontology
generate` target `python-sdk` → `sdk/python/aegis_sdk/`: typed object +
interface models, predicate constants, action call wrappers generated from
`parameters`, thin OIDC-authed HTTP client (token = app grant ∩ user
permission, GOAL.md §7.8). Generated files committed; drift gate.
AC: an example script records a claim end-to-end through a typed action
wrapper against the dev server; interface types importable and correct; CI
fails on drift.

**T38. TypeScript SDK** (specs/08 §8; needs T31, T34) — target `ts-sdk` →
`sdk/ts/` (npm workspace): the same surface for the P4 workspace; `tsc
--noEmit` type-check wired into CI.
AC: the generated package type-checks in CI; an example node script lists
entities with correct types; drift gate covers `sdk/ts/`.

**T39. Ontology-change end-to-end proof** (charter exit №1; needs T36–T38) —
land a new test predicate on an interface **via the proposal workflow**, as
the automated demonstration that the platform is ontology-driven: the change
flows to API validation, FGA stubs, and both SDKs with zero hand-written
domain code.
AC: the change's diff touches only the ontology, the proposal, and regenerated
files; a test proves the API accepts the new predicate and both SDKs expose
it; the run is reproducible in CI (this test is the codegen-drift gate's
positive case).

**T40. Phase exit review** — walk the charter's exit criteria; update speckit
docs where reality diverged; append ADRs for changed decisions; write
`../reviews/phase-03-exit-review.md`; tag `phase-3-ontology-v2` per the git
workflow.
AC: all exit boxes checked or explicitly deferred with reason.

## Explicit non-goals for Phase 3

Object sets (P6), object views / React workspace (P4 — the TS SDK ships here,
its consumer does not), new domain predicates beyond the worked examples
(prison co-location, the T39 test predicate), events/geometry (P5), Foundry-
style live ontology branching (single-repo proposals suffice), OPA
policy-as-code, compartments (P7), any new AI capability (P8).
