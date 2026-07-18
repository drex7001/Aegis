# Investigation workspace (Phase 4 — spec 07, GOAL.md §18/§29–30)

The React + TypeScript product UI, built on the generated TypeScript SDK
(`sdk/ts/`, Phase 3). Ontology-driven: generic components render entity pages,
claim details, and forms from generated UI descriptors — adding an object type
to `ontology/aegis.yaml` yields a working object view with no new UI code
(the Phase 4 exit criterion).

Planned surface (spec 07 §3):

- **Case workspace**: access-scoped cases (FGA membership), entities, claims,
  evidence, hypotheses (supporting *and* contradicting sides — Article VIII),
  tasks/leads.
- **Object views**: entity-360 — claim-derived properties, links, timeline,
  sources, cases; every displayed value traceable to its claims.
- **Views**: graph / timeline / map (Phase 5) / table, with as-of mode and a
  persistent banner when time-shifted.
- **Provenance panels**: "Why connected?" behind every edge; suggested (AI)
  material visually distinct (Article VII); metrics always show caveats
  (Article IX).

Until this lands, the interim UI is the legacy explorer (`legacy/app/`,
served by `aegis serve`) plus the Phase 2 review-queue/provenance panels.
This directory replaces and deletes the explorer at the Phase 4 gate
(ADR-023 — scope set by analyst needs, not legacy parity).
