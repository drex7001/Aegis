# Phase 4 Charter — Investigation workspace & object views

Status: charter (tasks authored at phase start) · Constitutional basis: Articles
VI, VIII, XI · GOAL.md §18, §29–30, §7.8 (consumption layer) · specs/07

## Objective

Work moves inside access-scoped cases in a real product UI. The workspace is
**generated from the ontology, not hand-built per type**: screens derive from
UI descriptors and the TypeScript SDK (P3), so adding an object type to
`aegis.yaml` yields a working screen. The centerpiece is the **object view** —
the entity-360 surface where every displayed value traces back to its claims
and sources.

## Architecture layers touched

- **Consumption:** React + TypeScript workspace on the generated SDK; object
  views; timeline; as-of mode in the UI.
- **Operational plane:** case management UI, hypotheses, tasks/leads.
- **Kinetic:** actions v2 (P3) get their real front-end — parameters render as
  forms, submission criteria as disabled states with reasons.
- **Governance:** authz-scoped rendering (a non-member sees nothing), purpose
  capture on sensitive reads.

## Deliverables

1. **Workspace shell**: React + TypeScript app authenticated via Keycloak
   (OIDC), all data access through the generated TS SDK; ontology-driven
   navigation (types/interfaces from UI descriptors).
2. **Object views (entity-360)**: claim-derived properties (with grading and
   conflict badges — two DOBs render as two DOBs, Article VIII), links grouped
   by predicate category, source list, timeline strip, cases the entity appears
   in; every value opens its provenance (reuses the P2 why-connected API).
3. **Case UI**: create/join/manage cases (FGA-scoped membership via existing
   actions); claims and evidence linkable to cases; case-scoped graph view
   (embedded Cytoscape, reusing the projection API).
4. **Hypotheses**: hypothesis records with supporting/contradicting claim links
   and missing-information notes (GOAL.md §18); a hypothesis page always shows
   both sides.
5. **Tasks/leads**: lightweight status columns on cases — no workflow engine
   (plan §2).
6. **Timeline + as-of**: claim/event times with uncertainty rendering;
   `?asOf=` mode end-to-end in the UI ("what did we know on date X?").
7. **Review & adjudication surfaces migrated**: P2's review-queue, search, and
   provenance panels re-rendered inside the workspace (API unchanged).
8. **Legacy explorer deletion**: the workspace replaces the legacy explorer
   outright — its scope comes from what analysts need (graph, filters, detail
   panel), never from matching legacy features (ADR-023). `app/static`
   explorer and deprecated `app/server.py` removed.

## Dependencies

- P3: TypeScript SDK, UI descriptors, actions v2 (forms need parameter
  schemas).
- P2: why-connected, review, search APIs (consumed as-is).

## Exit criteria

- [ ] A non-member of a case cannot see its claims via any endpoint or screen
      (authz matrix test extended to the UI).
- [ ] A hypothesis page shows both supporting and contradicting claims
      (Article VIII).
- [ ] "What was recorded before date X?" returns a defensible as-of answer in
      the UI.
- [ ] Adding a test object type via ontology alone (plus regen) yields a
      working object view with properties, links, and provenance — no new
      React code.
- [ ] Legacy explorer removed; nothing in the repo serves unauthenticated
      graph data except the explicitly `public_route` open-only projection
      (ADR-019 reviewed at this gate: keep or retire).

## Risks

| Risk | Mitigation |
|---|---|
| UI scope explosion | Object-view-first: ship the generic screen, resist bespoke per-type pages; anything cosmetic is post-parity |
| Parity trap (designing against the legacy explorer) | Replacement, not parity (ADR-023): scope is a short analyst-needs list written up front (graph, filters, detail panel); legacy features absent from it are dropped without debate |
| SDK gaps discovered late | P3 exit criterion (ontology change → SDK with zero hand-code) is the guard; gaps found here are P3 regressions, fixed there |
| Hypotheses become vibes again | Hypothesis create/update is an audited action; missing-info note required on creation |

## Specs to author or update

- `specs/07-ui.md` — stage-3 (workspace) becomes the active spec; author the
  object-view descriptor contract as `specs/09-workspace-object-views.md` at
  phase start.
- `specs/06-api.md` — cursor pagination (deferred from Phase 1) lands here at
  the latest.

## Explicit non-goals

Map view (P5), full multilingual search and object sets (P6), compartment UX
(P7), collaboration features beyond case membership (comments, presence —
GOAL.md §31 stays future), mobile, offline.

## Task sketch (milestone level — T-file at phase start)

- **A — Shell:** React app, OIDC flow, SDK wiring, nav from descriptors.
- **B — Object views:** generic entity-360, provenance drill-down, conflict
  rendering.
- **C — Cases:** case screens, membership, case-scoped graph.
- **D — Hypotheses & tasks:** models (audited actions) + screens.
- **E — Time:** timeline component, as-of mode.
- **F — Cutover:** panel migration, analyst-needs checklist, explorer
  deletion, ADR-019 review.
