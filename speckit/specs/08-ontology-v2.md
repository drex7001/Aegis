# Spec 08 — Ontology DSL v2: interfaces, functions, actions v2, change management, SDKs

Status: draft for Phase 3 — **narrowed 2026-07-18 (ADR-033)**: module
composition is added as the headline (manifest format specced by T29);
functions *execution*, the side-effect engine, and the Python SDK move to
their first consumer phases; `system_claim` mode is **removed** (ADR-027 —
where this draft still mentions it, the ADR wins until T29's rewrite). ·
Constitutional basis: Articles VII, X, XI, XIV · GOAL.md §7.8–7.10 · ADR-021,
ADR-027, ADR-033 · Extends spec 01 (which remains the v1 reference)

## 1. Purpose

Phase 3 grows `ontology/aegis.yaml` from a vocabulary file into the full
ontology-platform artifact described in GOAL.md §7.8: semantic layer
(+ interfaces, shared properties), kinetic layer (+ functions, actions v2),
consumption layer (+ generated SDKs), governance layer (+ change management).
This spec pins the design decided with roadmap v2 while the Foundry research is
fresh; it is finalized at Phase 3 start. Everything here is **additive** to the
v1 DSL — existing sections keep their spec-01 semantics.

## 2. Top-level structure (v2 additions marked)

```yaml
version: <semver>
namespace: aegis.lk
handling_codes: [...]
grading: {...}
source_types: [...]
categories: {...}
shared_properties: {...}     # NEW
interfaces: {...}            # NEW
object_types: {...}          # may now reference interfaces + shared properties
predicates: {...}            # subject/object may name interfaces
event_types: {...}           # Phase 5 (uses the event interface)
functions: {...}             # NEW
actions: {...}               # extended schema (v2)
```

## 3. `shared_properties`

A property defined once, referenced by many object types — one definition of
type, sensitivity, conflict policy, and display.

```yaml
shared_properties:
  alias:
    type: text
    many: true
  registered_identifier:
    type: identifier
    sensitivity: restricted
  notes:
    type: text

object_types:
  person:
    properties:
      name:    {type: text, required: true}
      aliases: {shared: alias}          # reference, not redefinition
      nic:     {shared: registered_identifier}
```

Validator: a `shared:` reference may not override `type` or `sensitivity`
(display hints may be specialized). Rule of three (GOAL.md §7.9): the third
duplicated inline property definition should become a shared property —
enforced in review, not by the validator.

## 4. `interfaces`

Named shapes over object types — polymorphism for predicates, workflows,
object sets, and SDK types. Composition over wide types.

```yaml
interfaces:
  party:                       # person-or-organization
    members: [person, organization]
    properties: [alias]        # shared properties every member must carry
  identifiable:
    members: [person, vehicle, phone_number]
    properties: [registered_identifier]
  # event: Phase 5 — time span + participants + optional location
```

- `members` is explicit (no structural inference); adding a member is a minor
  bump.
- Predicates may target interfaces: `subject: [party]` expands to member
  types at validation time.
- FGA stubs, UI descriptors, and SDKs emit interface types alongside object
  types.
- Validator: members exist; every member carries the interface's required
  shared properties; no interface cycles.

## 5. `functions`

Declared, versioned derivations over the ontology — the kinetic-layer analog
of Foundry functions, constrained by Article VII.

```yaml
functions:
  derive_prison_co_location:
    version: 1
    inputs:
      - claim_pattern: {predicate: remanded_in, object: location}   # illustrative
    output:
      predicate: co_located_in_prison_with
      mode: derived_record      # suggestion (default) | derived_record
    trigger: rebuild            # rebuild | on_write
    implementation: prison_overlap_v1   # registered function id (allowlist, H-13) — not an arbitrary import path
```

Rules:
- **Attribution.** Every output row records source_type `algorithmic`,
  function name + version, and input claim IDs. Anonymous derivation is a
  defect.
- **Mode (ADR-027).** `suggestion` (default) routes through the review queue
  (Article VII). `derived_record` writes rows into **rebuildable derived
  tables** (projections/findings, Article XIII), typed and displayed as
  derived — never rows in `claim`. There is no machine path into canonical
  tables. Reproducibility = canonical-digest equality over inputs + config +
  output (not byte-identical DB rows — H-14).
- **Supersedes `computed: true`.** The v1 predicate flag remains as a marker;
  the function entry is where the derivation actually lives. First real
  function: prison co-location from remand-window overlap (lands with its
  consumer phase, P5/P6 — ADR-033).
- **Implementation allowlist (H-13).** The ontology selects a *registered*
  function id + version from a code-side registry with declared capabilities
  and input/output schemas; arbitrary import paths are rejected (an ontology
  deployer must not be able to select unreviewed code).
- Validator: output predicate exists; implementation id registered; version
  bump required when implementation hash changes (CI check).

## 6. `actions` v2

The v1 schema (`roles`, `audit`, `dual_control_for`) extends with parameters,
submission criteria, and side effects — all declared here, enforced in
`aegis/actions/`.

```yaml
actions:
  record_claim:
    roles: [analyst, investigator]
    audit: true
    parameters:
      subject_id:   {type: ref, required: true}
      predicate:    {type: predicate, required: true}
      object:       {type: ref_or_literal, required: true}
      grading:      {type: grading, required: true}
    submission_criteria:
      - actor_has_case_membership     # named predicates evaluated by the actions layer
      - target_not_sealed
    side_effects:
      - refresh_projection: edge_projection
  assign_case_member:
    roles: [supervisor]
    audit: true
    parameters:
      case_id: {type: ref, required: true}
      user_id: {type: ref, required: true}
      role:    {type: enum, values: [supervisor, investigator, analyst], required: true}
    side_effects:
      - notify: case_supervisors      # notification hook; webhook stubs allowed
```

- `parameters` generate the action's Pydantic request model and the SDK call
  signatures; undeclared parameters are rejected.
- `submission_criteria` are named, testable predicates (actor + target state);
  failures are audited denials, not silent 403s.
- `side_effects` run post-commit (outbox pattern, ADR-014 precedent);
  failures never roll back the action — they retry.
- Validator: every action still declares `roles` + `audit: true`
  (spec 01 §6.5); parameter types come from the closed type list; criteria
  and side-effect names must exist in the actions-layer registry.

## 7. Change management

Scaled-to-one-repo version of Foundry's proposals/branching:

1. A change starts as `ontology/proposals/NNN-short-title.md`: motivation, the
   YAML diff, **competency questions** the change answers (GOAL.md §7.9),
   migration plan if major.
2. Review happens on the PR; approval merges proposal + ontology bump
   together.
3. Semver rules unchanged (spec 01 §4). Major bumps additionally require the
   migration script in the same change and the prior version copied to
   `ontology/history/`.
4. CI enforces: version monotonicity; minor/patch bumps introduce no
   removals/renames (diff check against the previous committed version);
   major bumps have history copy + migration; a proposal file is referenced in
   the bump commit.

## 8. Codegen targets (extends spec 01 §5)

| Target | Output | Used by | Phase |
|---|---|---|---|
| Pydantic validators | `aegis/ontology/_generated/models.py` | actions, API bodies | P1 (exists) |
| FGA object-type stubs | `infra/fga/_generated.fga` | authz model review | P1 (exists) |
| UI descriptors | `aegis/api/_generated/ui_meta.json` | generic screens | P1 (exists) → P4 |
| **TypeScript client** | `sdk/ts/` (npm workspace; generated from the FastAPI OpenAPI document + ontology constants — ADR-033/H-11) | P2-born workspace, P4 screens | P3 |
| **Python SDK** | `sdk/python/aegis_sdk/` | P8 AI producers (its first consumer — ADR-033) | P8 |

SDK contents: typed object/interface models, predicate constants, action call
wrappers (from `parameters`), query/object-set builders (P6 extends). Auth:
tokens scoped to app grant ∩ user permission (GOAL.md §7.8). Generated files
are committed; CI fails if regeneration diffs (spec 01 §5 discipline
unchanged).

## 9. Validation rules added to the loader

1. Interface members exist; required shared properties present on every
   member; no cycles.
2. `shared:` references resolve; no type/sensitivity overrides.
3. Predicates targeting interfaces expand to valid member sets.
4. Function output predicates exist; output mode ∈ {suggestion,
   derived_record} (no canonical-write mode exists — ADR-027); implementation
   id is registered in the code-side allowlist.
5. Action parameters use closed types; criteria/side-effect names registered.
6. v2 sections are optional — a v1-shaped file (with empty new sections) still
   validates, so the bump to 0.4.0 is minor.

## 10. What this spec deliberately excludes

Object sets (specced in P6 with their own file — they are consumption-layer,
not ontology DSL), Foundry-style live branching (proposals suffice for one
repo), per-property ABAC beyond `sensitivity` (P7 territory), OPA integration.
