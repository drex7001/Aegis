# Phase 4 Charter — Investigation workspace v2 & object views

Status: charter (amended 2026-07-18, ADR-032/ADR-033 — the workspace *grows
here*, it does not start here) · tasks pre-authored: `../tasks/phase-04.md`
(T41–T53; re-validated by T41 at phase start, which also dispositions the
2026-07 review findings tagged P4: H-17, H-18, H-19 remainder, B-11) ·
Constitutional basis: Articles VI, VIII, XI · GOAL.md §18, §29–30, §7.8
(consumption layer) · specs/07

## Objective

Work moves inside access-scoped cases. The P2-born React workspace (ADR-032)
grows its operational surfaces, **generated from the ontology, not hand-built
per type**: screens derive from UI descriptors and the P3 TypeScript client,
so adding an object type to a domain module yields a working screen. The
centerpiece is the **object view** — the entity-360 surface where every
displayed value traces back to its claims and sources. The
**investigation-domain model is specced before its UI** (H-17): cases,
hypotheses, tasks/leads get storage, actions, and authorization definitions
first.

## Architecture layers touched

- **Consumption:** React + TypeScript workspace on the generated SDK; object
  views; timeline; as-of mode in the UI.
- **Operational plane:** case management UI, hypotheses, tasks/leads.
- **Kinetic:** actions v2 (P3) get their real front-end — parameters render as
  forms, submission criteria as disabled states with reasons.
- **Governance:** authz-scoped rendering (a non-member sees nothing), purpose
  capture on sensitive reads.

## Deliverables

1. **Investigation-domain spec first** (H-17): `specs/09` defines case
   linking semantics, hypothesis records (versions, evidence basis),
   tasks/leads (owner, status, dates), their actions and authorization —
   model/API tasks separated from UI tasks so acceptance is testable.
2. **Object views (entity-360)**: claim-derived properties (with grading and
   conflict badges — two DOBs render as two DOBs, Article VIII), links grouped
   by predicate category, source list, timeline strip, cases the entity appears
   in — **case references independently authorized: only visible cases listed,
   no counts of hidden ones, no timing/ranking leak (H-18)**; every value opens
   its provenance (reuses the P2 why-connected API).
3. **Case UI**: create/join/manage cases (FGA-scoped membership via existing
   actions); claims and evidence linkable to cases; case-scoped graph view
   (embedded Cytoscape, reusing the projection API).
4. **Hypotheses**: hypothesis records with supporting/contradicting claim links
   and missing-information notes (GOAL.md §18); a hypothesis page always shows
   both sides.
5. **Tasks/leads**: lightweight status columns on cases — no workflow engine
   (plan §2).
6. **Timeline + as-of (narrowed — B-11)**: claim/event times with uncertainty
   rendering; `?asOf=` mode end-to-end in the UI, defined precisely as the
   **claim-recording snapshot**: claims recorded and unretracted at the
   timestamp, resolved under a pinned identity revision, response stamped with
   snapshot + identity revision + ontology version. The banner states what the
   view does and does not hold constant (labels, source evaluations, and
   policy are current-state — full multi-axis as-of stays north-star).
7. **Review & adjudication surfaces refined**: P2's screens re-organized into
   the case-centric layout (API unchanged; no rewrite — same app, ADR-032).

## Dependencies

- P3: TypeScript client, UI descriptors, actions v2 parameter schemas (forms).
- P2: workspace shell, why-connected, review, search APIs (consumed as-is).

## Exit criteria

- [ ] A non-member of a case cannot see its claims via any endpoint or screen,
      and cannot learn the case exists (no existence/count/timing leak —
      H-18; authz matrix extended to the UI).
- [ ] A hypothesis page shows both supporting and contradicting claims
      (Article VIII).
- [ ] "What was recorded before date X?" returns the defined claim-recording
      snapshot, stamped with snapshot + identity revision + ontology version
      (B-11 narrowed promise).
- [ ] Adding a test object type via ontology alone (plus regen) yields a
      working object view with properties, links, and provenance — no new
      React code.
- [ ] Re-verified: no unauthenticated read surface exists anywhere in the repo
      (ADR-026 held through the phase).

## Risks

| Risk | Mitigation |
|---|---|
| UI scope explosion | Object-view-first: ship the generic screen, resist bespoke per-type pages; anything cosmetic is post-parity |
| Parity trap (designing against the legacy explorer) | Replacement, not parity (ADR-023): scope is a short analyst-needs list written up front (graph, filters, detail panel); legacy features absent from it are dropped without debate |
| SDK gaps discovered late | P3 exit criterion (ontology change → SDK with zero hand-code) is the guard; gaps found here are P3 regressions, fixed there |
| Hypotheses become vibes again | Hypothesis create/update is an audited action; missing-info note required on creation |

## Specs to author or update

- `specs/09-investigation-domain.md` — author **first** (H-17): cases,
  hypotheses, tasks/leads model, actions, authorization; then the object-view
  descriptor contract (same file or `specs/09b`).
- `specs/07-ui.md` — workspace-v2 sections (case layout, object views,
  timeline/as-of banner semantics).

## Explicit non-goals

Map view (P5), full multilingual search and object sets (P6), compartment UX
(P7), collaboration features beyond case membership (comments, presence —
GOAL.md §31 stays future), mobile, offline.

## Task sketch (expanded into `../tasks/phase-04.md`, T41–T53 — T41
re-validates against this amended charter)

- **A — Investigation model:** specs/09, storage + actions + authz for cases/
  hypotheses/tasks (model tasks separate from UI tasks).
- **B — Object views:** generic entity-360 from descriptors, provenance
  drill-down, conflict rendering, leak-free case references.
- **C — Cases:** case screens, membership, case-scoped graph.
- **D — Hypotheses & tasks:** screens over the Milestone-A actions.
- **E — Time:** timeline component, narrowed as-of mode + banner.
- **F — Layout & polish:** case-centric navigation, descriptor-driven nav,
  P2-screen reorganization.
