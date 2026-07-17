# Phase 3 Charter — Ontology v2: semantic & kinetic completion

Status: charter · tasks pre-authored: `../tasks/phase-03.md` (T29–T40; re-validated
by T29 at phase start) · Constitutional basis: Articles VII, X, XI ·
GOAL.md §7.8–7.10 · ADR-021 · Spec: `../specs/08-ontology-v2.md`

## Objective

`ontology/aegis.yaml` grows from a vocabulary file into a full ontology-platform
artifact — the Foundry-class layer (GOAL.md §7.8) that P4's workspace, P6's
object sets, and P8's AI grounding are built on. After this phase, the ontology
declares not only *what exists* (object types, predicates) but *what shapes
recur* (interfaces, shared properties), *what can happen* (actions with
parameters, criteria, side effects), *what is derived* (functions), and *how the
ontology itself changes* (proposals, versioning, migration).

## Architecture layers touched

- **Semantic:** interfaces + shared property types in the DSL; loader,
  validator, and registry extended.
- **Kinetic:** functions registry (declared derivations); actions v2 schema
  enforced by the actions layer.
- **Consumption:** generated typed SDKs (Python + TypeScript) — the OSDK
  analog; existing codegen targets (Pydantic, FGA stubs, UI meta) extended.
- **Governance:** ontology change-management workflow; codegen-drift CI gate.

## Deliverables

1. **DSL v2 — interfaces.** `interfaces:` section: named shapes (starter set:
   `party` over person/organization; `identifiable` for anything with registry
   identifiers; `locatable` reserved for P5). Predicates may target interfaces;
   the validator expands them to member types. Composition over wide types
   (GOAL.md §7.9).
2. **DSL v2 — shared property types.** `shared_properties:` defined once
   (e.g. `alias`, `registered_identifier`, `notes`) and referenced by object
   types; single definition of type, sensitivity, and display.
3. **Functions registry.** `functions:` section declaring versioned
   derivations: name, inputs (claim patterns), derivation logic reference,
   output predicate, output mode (`suggestion` | `system_claim`), trigger
   (on-write | rebuild). First real implementation:
   `co_located_in_prison_with` computed from remand-window overlap claims,
   replacing the bare `computed: true` flag. Function outputs are attributed to
   an `algorithmic` source with function name + version (Article VII: outputs
   default to suggestions; `system_claim` mode is reserved for deterministic,
   fully-derived facts and still records provenance).
4. **Actions v2.** Action declarations gain `parameters` (typed, validated),
   `submission_criteria` (declarative predicates over actor + target state:
   role, case membership, record status), and `side_effects` (projection
   refresh, notification hooks, webhook stubs). The actions layer enforces all
   three; the validator rejects undeclared parameters.
5. **Ontology change management.** Proposal workflow scaled to a single repo:
   a change lands as `ontology/proposals/NNN-title.md` (motivation, diff,
   competency questions it answers, migration plan) → review → semver bump +
   migration script + previous version copied to `ontology/history/`. CI
   enforces: version monotonicity, history copy on major bumps, proposal
   reference in the commit.
6. **Generated SDKs.** `aegis ontology generate` gains two targets: a typed
   Python client (`aegis_sdk/`) and a TypeScript client package
   (`sdk/ts/`), both generated from the ontology + API surface — object types,
   interfaces, predicates, actions as typed calls. Tokens are scoped to app
   grant ∩ user permission (GOAL.md §7.8). Generated files are committed; CI
   fails on drift.

## Dependencies

- Phase 2 complete (MVP shipped; identity model stable so SDK entity APIs are
  meaningful).
- specs/08-ontology-v2.md (drafted with this roadmap) finalized at phase start.

## Exit criteria

- [ ] A new predicate added to an interface flows to API validation, FGA stubs,
      and both SDKs with **zero hand-written domain code**.
- [ ] `co_located_in_prison_with` regenerates deterministically from remand
      claims; deleting its outputs and re-running the function reproduces them
      byte-for-byte; every output row carries function name + version.
- [ ] An action with declared `submission_criteria` rejects a non-qualifying
      actor in a test, and the rejection is audited.
- [ ] CI fails on codegen drift and on an ontology bump without proposal +
      history entry.
- [ ] Ontology bumped one minor version (interfaces + shared properties are
      additive); all Phase 1–2 tests still green.

## Risks

| Risk | Mitigation |
|---|---|
| DSL over-engineering (features nothing consumes) | Only ship DSL features with a named consumer in P4–P6; everything else stays in spec 08 as future |
| Codegen maintenance burden | Generators are template-driven and covered by golden-file tests; drift gate keeps them honest |
| Breaking change sneaks in as "additive" | Validator diff check: minor bumps may not remove/rename; CI compares against previous committed version |
| Functions blur Article VII | Output-mode default is `suggestion`; `system_claim` requires an ADR naming the derivation deterministic |

## Specs to author or update

- `specs/08-ontology-v2.md` — finalize (exists as draft).
- `specs/01-ontology.md` — keep as v1 reference; add pointer note to 08.
- `specs/06-api.md` — SDK-facing conventions (stable operation IDs, error
  envelopes).

## Explicit non-goals

Object sets (P6), object views/React UI (P4), new domain predicates beyond the
worked examples, ontology branching à la Foundry (single-repo proposals
suffice), OPA policy-as-code.

## Task sketch (expanded into `../tasks/phase-03.md`, T29–T40)

- **A — DSL v2 core:** interfaces + shared properties in loader/validator/
  registry; ontology 0.4.0.
- **B — Functions:** registry, execution harness, prison co-location
  derivation, provenance stamping.
- **C — Actions v2:** parameters/criteria/side-effects schema + enforcement in
  `aegis/actions/service.py`.
- **D — Change management:** proposals dir, CI gates, history discipline.
- **E — SDKs:** Python + TypeScript codegen, drift gate, example scripts.
