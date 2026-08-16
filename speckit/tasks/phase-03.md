# Phase 3 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them; narrower dependencies are noted in the task text. Reference specs in
parentheses. Numbering continues from Phase 2 (T28).

> **Status: ACTIVE — T29 complete (2026-08-17).** Phase 2 passed the ★ MVP gate
> on 2026-07-20. This file was rewritten 2026-07-18 to the narrowed charter
> (ADR-033) and **re-validated by T29** against the P2-as-built system; T29's
> six divergences are dispositioned in spec 08 §0 and ADR-037…040, and the
> tasks below carry the corrections. Charter:
> `../phases/phase-03-ontology-v2.md` · spec: `../specs/08-ontology-v2.md`
> (final) · contract conventions: `../specs/06-api.md` §7.

## Milestone A — Spec finalization & module composition

**T29. ⛓ Spec 08 finalization (narrowed) — DONE (2026-08-17)** — walked the
draft against the P2-as-built system; specified the module manifest format
(spec 08 §2), closed the parameter type list (§6.2) and the submission-criteria
registry (§6.3), moved functions execution / side-effect engine / Python SDK to
the future-consumers appendix (§11) with trigger phases, and added the
operation-id and error-envelope conventions to specs/06 §7.

Divergences found and dispositioned: **ADR-037** (composition, unprefixed
names, `ontology_version` = composition version), **ADR-038** (spec 01 §5's
three codegen targets never existed — codegen is built per consumer),
**ADR-039** (the generated TS client stays in `ui/`; the error envelope joins
the OpenAPI contract), **ADR-040** (action declarations become the write-side
gate: parameters, criteria, and audited denials). Spec 01 §5 and §4 corrected.

AC met: spec 08 status draft → final with the module section; every retained v2
feature names its consumer; excluded machinery listed in §11 with its trigger
phase.

**T30. ⛓ Module loader & composition — DONE (2026-08-17)** (spec 08 §2, §9 rules 8–12; needs T29) —
loader resolves the composition manifest into one registry: module manifests,
PEP 440 import constraints, cross-module reference validation, name-collision
detection, derived `owner_module`, enable/disable. Split `ontology/aegis.yaml`
into the manifest plus `ontology/modules/platform.yaml` +
`ontology/modules/criminal-network.yaml` per the §2.2 split (platform owns
handling codes, grading, source types, actions; the domain module owns object
types, predicates, categories). Pure reorganization — no vocabulary change.
Add the startup check that refuses to serve when a disabled module's vocabulary
appears in recorded claims (§2.6).
AC: the composed registry is substitutable for today's `Ontology` and all
Phase 1–2 tests pass unchanged; a fixture with a cross-module reference and no
declared import fails with an error naming both modules and the YAML path; a
name collision across modules fails validation; a pinned version that
contradicts an importer's specifier fails; `aegis ontology validate` reports
per-module names, namespaces and versions.

**T31. Second-domain proof fixture — DONE (2026-08-17)** (Article XIV, ADR-037; needs T30) — a tiny
fictional `border-cargo` module (≈2 object types, 3 predicates, 1 interface
implementation once T32 lands) in `tests/fixtures/ontology/`; CI loads
platform + fixture module and runs claim record/read + projection round-trip
against it.
AC: the fixture round-trips through actions, API, and projection with **zero
core-code change** — the test fails if any file under `aegis/` needs a domain
edit; disabling the module removes its vocabulary from validation; the
criminal-network module is not loaded for this run and nothing breaks.

AC met by `tests/contract/test_second_domain.py` (6 cases, including the
string sweep over every file in `aegis/`) and
`tests/integration/test_second_domain.py` (4 cases: claim round-trip, literal
predicate, validation still constrains, projection builds a graph grouped by
the fixture's own category). **One defect found and fixed in the process**:
`build_graph` emitted a segment whose endpoint the graph had excluded (an
entity tombstoned by a canonical-map rebuild that the projection had not caught
up with), using the raw entity id as the node reference — which made
`detect_cells` die with an opaque `KeyError` instead of returning a graph. Such
segments are now dropped, with a regression case in
`tests/integration/test_edge_projection.py` that reproduces the exact failure
without the fix.

## Milestone B — Semantic layer v2 & generation

**T32. ⛓ Shared properties + interfaces** (spec 08 §3–4, §9 rules 13–14; needs
T30) — extend loader/validator/registry: `shared_properties:` and
`interfaces:`; predicates may target interfaces (expanded at validation, and
the **expansion** is what claims record); starter set: shared `alias`,
`registered_identifier`, `notes`; interfaces `party`, `identifiable`, declared
in the platform module. Sequence the ontology minor bump after T35 so it
carries a proposal.
AC: a predicate with `subject: [party]` validates for member types and rejects
non-members; a `shared:` reference overriding type or sensitivity fails; an
interface member missing a required shared property fails; all prior tests
green.

**T33. `aegis ontology generate` — the P3 codegen targets** (spec 08 §8,
ADR-038; needs T32) — **rewritten by T29**: the three targets spec 01 §5 called
Phase 1 deliverables were never built, so this is not "codegen v2 for existing
targets" but the first generator. Build the command and exactly two targets
here: the normalized composed registry + `ontology/release.json` (consumer:
T35's gates) and `ui/src/api/ontology.ts` constants — predicates, object types,
interfaces, categories, handling codes, source types, owner module per name
(consumer: T37/T38). UI descriptors (P4), FGA stubs (P7) and the Python SDK
(P8) are **not** built here.
AC: `aegis ontology generate` writes only its declared outputs; committed
outputs regenerate byte-identical in CI; the constants file matches the
composed registry; generation is deterministic across runs and platforms
(sorted keys, LF endings).

## Milestone C — Actions v2 schema

**T34. ⛓ Actions v2 declarations + enforcement** (spec 08 §6, §9 rules 15–17;
ADR-040; needs T33) — `parameters` (closed type list → generated Pydantic
request models emitted as a third `aegis ontology generate` target; undeclared
parameters rejected) and `submission_criteria` (the three registered predicates
of §6.3); migrate all thirteen existing actions to declared parameters, in the
platform module. **Two gaps T29 found must close in this task**, or the
declarations stay decorative: every action call passes its `ActionContext` (the
ontology `roles` gate currently fires for `adjudicate_identity` only), and the
actions layer gains a `decision="deny"` audit path (`_audit` writes `"allow"`
unconditionally today, and `_require_action` raises before any row exists).
**No side-effect engine** — existing hard-coded refresh paths stay;
`side_effects:` keys parse and are stored (§6.5).
AC: an undeclared parameter is rejected by the generated model's error; a
non-qualifying actor fails a declared criterion and **the denial is audited**
with actor, action, failed criterion and target (charter exit); the validator
rejects unknown parameter types, missing type modifiers, a `json` parameter
with no registered schema, and unregistered criterion names; every Phase 1–2
call site passes context and stays green.

## Milestone D — Change management

**T35. Proposals, history, release metadata, CI gates** (spec 08 §7; needs T33
for the release artifact — a re-ordering T29 introduced, since the gates
compare generated artifacts) — `ontology/proposals/NNN-title.md` template
(motivation, diff, competency questions, migration plan);
`ontology/history/composed-<version>.json` written on **every** bump, not only
major ones (§7.2 — a minor bump changes what a stamped `ontology_version` means
just as a major one does); `release.json` carries proposal id, per-module
versions, compatibility class, content hash and previous content hash;
CI: version monotonicity per module and composition, minor/patch bumps
introduce no removals or renames (compared against the committed artifact, not
git history — H-16), major bumps carry the history copy + migration. Backfill
proposal 001 documenting the modularization bump (1.2.0 → 1.3.0, minor).
AC: a bump without a proposal reference in `release.json` fails CI; a minor
bump removing a predicate fails the diff check; proposal 001 exists and the
modularization diff shows no vocabulary change.

## Milestone E — Contract & TypeScript client

**T36. ⛓ API contract conventions** (specs/06 §7; ADR-039; needs T29) — the
operation-id rules are already satisfied on all 37 routes, so the work here is
the part P2 did not ship: the **RFC 7807 envelope enters the OpenAPI document**
as a component schema with its two documented extensions (the 422 validation
path, the typed 409 stale-revision body), each route documents the error
responses it can actually return, and a contract-diff check compares against
the committed document.
AC: OpenAPI artifact regenerates cleanly and every operation documents its real
error responses; the error schema appears in `ui/openapi.json`; a renamed
operation id, a removed response code, or a parameter becoming required fails
the contract-diff check; documenting a status a route cannot return also fails.

**T37. TypeScript client generation** (spec 08 §8, ADR-039; needs T33, T34,
T36) — **rescoped by T29**: `ui/` already generates `src/api/schema.d.ts` from
the committed OpenAPI document with a drift gate, so there is no client to
build from scratch and none to migrate off. Land the generated
`ui/src/api/ontology.ts` constants beside it under the same gate, and regenerate
`schema.d.ts` against T36's document so the error envelope and action request
types are typed.
AC: the generated files type-check in CI; ontology constants match the
registry; CI fails on drift in either file; an example script lists entities
with correct types.

**T38. UI consumes the generated surface** (needs T37) — delete the
hand-written `ProblemDetail` and `StaleRevisionProblem` from
`ui/src/api/client.ts` in favour of the generated error types; replace
hard-coded or fetched vocabulary reads with the generated constants; action
calls use the generated parameter types from T34. No screen rewrites — types
only.
AC: UI type-checks and its e2e smoke passes; **no hand-written request or
response type remains in `ui/src`** (the client keeps only the fetch wrapper
and the `ApiError` class); the `asStaleRevision` narrowing reads a generated
shape.

**T39. Ontology-change end-to-end proof** (charter exit №1; needs T35–T38) —
land a new test predicate on an interface **in a domain module via the proposal
workflow**: the change flows to API validation and the TS client with zero
hand-written domain code.
AC: the change's diff touches only the module file, the proposal, and
regenerated artifacts; a test proves the API accepts the new predicate and the
client exposes it; reproducible in CI.

**T40. Phase exit review** — walk the charter's gate criteria (non-deferrable,
ADR-025); update speckit docs where reality diverged; append ADRs; write
`../reviews/phase-03-exit-review.md`; tag per the git workflow.
AC: every gate criterion checked; non-blocking deliverables carried over with
owner + target phase recorded.

## Explicit non-goals for Phase 3

Functions execution machinery and derived-record runs (P5/P6, ADR-027
semantics; design retained in spec 08 §11.1), side-effect outbox engine (first
consumer phase, §11.2), Python SDK (P8, §11.3), a published `sdk/ts/` package
(§11.4), UI descriptor codegen (P4) and FGA stub codegen (P7) per ADR-038,
object sets (P6), object views / workspace features (P4), new domain predicates
beyond the worked examples, events/geometry (P5), Foundry-style live branching,
OPA policy-as-code, compartments (P7), any new AI capability (P8).
