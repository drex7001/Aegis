# Phase 3 Charter — Ontology modules & contracts

Status: charter (narrowed 2026-07-18, ADR-033 — was "ontology v2: semantic &
kinetic completion") · tasks: `../tasks/phase-03.md` (T29–T40; re-validated by
T29 at phase start) · Constitutional basis: Articles XI, XIV ·
GOAL.md §7.8–7.10 · ADR-021, ADR-033 · Spec: `../specs/08-ontology-v2.md`

## Objective

Make **"domains are ontology modules" true** (Article XIV has no mechanism
behind it yet — B-07), and give the workspace a typed contract. After this
phase, the ontology is a composition of a small platform module plus domain
modules with namespaces, imports, and version constraints; a tiny second
fictional domain proves the core needs zero code change; and the P2-born
workspace consumes a generated TypeScript client from a stable OpenAPI
contract.

**Narrowing (ADR-033).** The v2 kinetic machinery moves out of this phase to
land with its first consumer: functions execution harness + prison co-location
derivation (first consumer: P5/P6 derived records), generalized side-effect
outbox (first consumer: the action that needs one), Python SDK (first
consumer: P8 producers). Actions v2 *schema* (parameters/criteria declared in
the ontology) stays, because the generated client and P4 forms need parameter
schemas; the side-effect execution engine does not.

## Architecture layers touched

- **Semantic:** interfaces + shared property types; module composition
  (namespaces, imports, manifests).
- **Kinetic (schema only):** actions v2 parameter/criteria declarations.
- **Consumption:** stable OpenAPI operation IDs; generated TypeScript client
  consumed by `ui/`.
- **Governance:** ontology change management (proposals, history, CI gates);
  codegen-drift gate; module-aware validation.

## Deliverables

1. **Module composition (headline — B-07).** The ontology becomes a
   composition: a small **platform module** (governance vocabulary: handling
   codes, grading, platform actions) plus **domain modules** (first:
   `criminal-network`), each with a manifest (name, namespace, version,
   imports/dependency constraints, type ownership). Loader resolves modules
   into one registry; conflicts (name collisions, cross-module references
   without import) are validation errors. Enable/disable semantics defined.
2. **Second-domain proof.** A tiny fictional domain module (e.g. border-cargo:
   2 object types, 3 predicates) lives in CI and loads against the same core
   with **zero core-code change** — the Article XIV test becomes executable.
3. **Interfaces + shared property types** (spec 08 §3–4): `party`,
   `identifiable` starter set; predicates may target interfaces; validator
   rules §9.
4. **Actions v2 schema**: `parameters` (typed, closed list) and
   `submission_criteria` declared and validated; enforcement of criteria in
   the actions layer; **no side-effect engine** (declarations parse, execution
   stays the existing hardcoded refresh paths until a consumer phase).
5. **Ontology change management** (spec 08 §7): proposals, history on major
   bumps, CI gates — release metadata carries proposal id + previous content
   hash (not commit archaeology — H-16).
6. **TypeScript client from OpenAPI**: stable operation IDs + error envelope
   in specs/06; client generated from the FastAPI OpenAPI document
   (adopt-before-build — H-11), typed with ontology-derived
   constants/schemas; `ui/` migrates from its P2 generated client with no
   screen rewrites; drift gate in CI.

## Dependencies

- Phase 2 complete (MVP shipped; identity model stable; workspace exists to
  consume the client).
- specs/08 finalized at phase start by T29 (narrowed scope).

## Exit criteria

- [ ] A new predicate added to a **domain module** via the proposal workflow
      flows to API validation and the TS client with zero hand-written domain
      code.
- [ ] The second-domain fixture module loads, validates, serves object/claim
      routes, and appears in the client types — with zero core-code change
      (Article XIV executable test).
- [ ] A cross-module reference without a declared import fails validation with
      a precise error.
- [ ] An action with declared `submission_criteria` rejects a non-qualifying
      actor in a test, and the rejection is audited.
- [ ] CI fails on codegen drift and on an ontology bump without proposal +
      history entry; all Phase 1–2 tests green on the modular ontology.

## Risks

| Risk | Mitigation |
|---|---|
| Module system over-engineering | Scope is manifests + namespaces + imports + validation — no dynamic loading, no marketplace; the second-domain fixture is the proof, not a product |
| DSL features without consumers | ADR-033 narrowing; anything without a named consumer stays in spec 08 §10 (exclusions) |
| Breaking change sneaks in as "additive" | Validator diff check against the previous release artifact (content hash), not git history |
| Client generation churn breaks the UI | Stable operation IDs are a specs/06 convention from P2; client regeneration is a CI gate, and UI type-checks against it |

## Specs to author or update

- `specs/08-ontology-v2.md` — finalize with the narrowed scope + module
  manifest format (T29).
- `specs/06-api.md` — stable operation IDs, error envelope, client-generation
  conventions.
- `specs/01-ontology.md` — v1 reference; add module-composition pointer.

## Explicit non-goals

Functions execution machinery and derived-record runs (P5/P6 with ADR-027
semantics), side-effect outbox engine (first consumer phase), Python SDK (P8),
object sets (P6), object views (P4), new domain predicates beyond the worked
examples, Foundry-style live branching, OPA policy-as-code.

## Task sketch (T-file re-validated at phase start)

- **A — Modules:** manifest format, loader composition, namespaces/imports,
  conflict validation, platform/domain split of `aegis.yaml`, second-domain
  CI fixture.
- **B — Semantic v2:** interfaces + shared properties.
- **C — Actions v2 schema:** parameters/criteria declarations + enforcement.
- **D — Change management:** proposals, history, release metadata, CI gates.
- **E — Contract & client:** operation IDs, error envelope, TS client
  generation + UI migration + drift gate.
