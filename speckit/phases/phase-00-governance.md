# Phase 0 Charter — Governance before code

Status: **COMPLETE** (retrospective record — this phase predates the charter
format; kept so `phases/` covers the whole P0–P9 pipeline) · Constitutional
basis: all Articles (this phase wrote them) · GOAL.md §40 M-I

## Objective

Decide the rules before schemas exist: the constitution, the spec kit, the
grading and handling schemes, and the starter ontology — so that every later
feature can be traced to a governing article and no access-control or
provenance discipline has to be retrofitted.

## Delivered

- The spec kit itself: constitution (the Articles), `spec.md`, `plan.md`,
  `decisions.md` (ADR log), roadmap, detailed specs 01–07.
- Starter ontology `ontology/aegis.yaml`: object types, predicates, grading
  schemes, handling codes, actions (Article XI from day one).
- Grading normalization confirmed against the sources actually used —
  exercised by the Phase 1 legacy migration (ConfidenceTag → credibility/
  verification map, ADR-011/ADR-016).
- Handling-code ladder for an OSINT-only deployment, shipped in ontology
  0.3.0: `open < restricted < sensitive`.

## Exit criteria — met

Kit reviewed; ontology validates in CI; every feature idea traceable to a
governing article.

## Record

Roadmap: `../roadmap.md` Milestone I. Load-bearing decisions of this phase:
ADR-001…ADR-016 (`../decisions.md`).
