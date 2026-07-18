# Phase 5 Charter — Events, geospatial & time

Status: charter (amended 2026-07-18, ADR-033 — claims-first storage, B-13) ·
tasks pre-authored: `../tasks/phase-05.md` (T54–T65; re-validated by T54 at
phase start, which also dispositions the 2026-07 review findings tagged P5:
B-13, M-17, M-18, M-19, H-21) · Constitutional basis: Articles I, VIII, XI ·
GOAL.md §7.3, §16, §17 · plan §2 (PostGIS, MapLibre)

## Objective

Places and events become first-class, with honest precision. Where reality
involves more than two parties, or where time and place carry the meaning, a
binary edge is the wrong shape — this phase introduces **event objects with
participants** and gives `location` real geometry, so one claim set renders
consistently as graph, map, and timeline.

**Storage boundary (B-13, binding).** Asserted geometry, precision,
participant roles, and event/location links are **typed claims** (Article I).
PostGIS event/location tables are **projections** rebuilt from claims
(Article XIII) — no canonical mutable geometry or precision column exists.
Any future canonical event table requires an explicit Article I amendment
first. Tightening an existing optional property to required is a **major**
ontology change (or a migration lands first), never a minor bump.

## Architecture layers touched

- **Semantic:** `event_types` section of the ontology filled (meeting, arrest,
  travel, observation) — via the P3 interface mechanism (`event` interface:
  time span + participants + optional location); `location` gains `geo`
  property type + `precision`.
- **Consumption:** MapLibre map view in the workspace, synced with timeline and
  graph selection; time-aware projections.
- **Kinetic:** `record_event` action (participants as role-typed references);
  movement/travel ingestion path emitting event suggestions.

## Deliverables

1. **Event model**: event objects with participant links (role-typed:
   attendee, arrestee, arresting-officer, traveller…), time spans with
   uncertainty, optional location reference. Participation is claim-backed like
   everything else (Article I). Existing multi-party binary edges (e.g.
   co-arrest chains) get a documented migration path to events where >2 parties
   or uncertainty matter (GOAL.md §7.3) — binary predicates stay for true
   pairwise relations.
2. **Geospatial locations**: geometry claimed on `location` entities and
   projected into PostGIS tables; the representation model separates
   **geometry type, administrative level, accuracy/uncertainty, and derivation
   method** (H-21 — not one overloaded `precision` enum); geocoding is
   manual/assisted, never silently precise.
3. **Map view**: MapLibre GL JS + PostGIS tiles in the workspace — tiles serve
   only authorization-scoped projection tables (never auto-published canonical
   tables; evaluate MapLibre Martin before hand-building — H-21); selection
   synced with graph and timeline; uncertainty rendered visually distinct
   (point vs circle vs admin area); **privacy-aware generalization for
   low-clearance viewers ships in this phase, not P7** (M-18); base-map/
   geocoder governance decided (offline/self-hosted default — M-19).
4. **Timeline v2**: events and claims on one timeline; uncertainty rendering;
   map/timeline/graph share one time filter.
5. **Movement/travel ingestion**: press/border-report-derived travel events
   through the standard suggestion path with sources.
6. **Ontology bump** (minor): event interface + types, `geo` property type;
   proposal + regen per P3 change management.

## Dependencies

- P3: interfaces (the `event` shape), DSL `geo` type slot, SDK regen.
- P4: workspace (map and timeline live there).
- Phase 1 already enabled the PostGIS extension (migration 0001).

## Exit criteria

- [ ] The same incident renders consistently on map, timeline, and graph from
      one claim set; uncertainty is visually distinct at every zoom.
- [ ] An event with 3+ participants round-trips through API and UI (create via
      action, render in object view, appear on map + timeline).
- [ ] A location known only at admin-area level never renders as a point; a
      low-clearance viewer sees the authorized generalization, not exact
      geometry (M-18).
- [ ] A travel event ingested from a press report carries its source and
      appears only after review (Article VII unchanged for events).
- [ ] No canonical mutable geometry/precision column exists — geometry
      projections rebuild from claims alone (B-13 spot check).

## Risks

| Risk | Mitigation |
|---|---|
| False precision from geocoding | Uncertainty/derivation fields default coarse; UI renders the uncertainty, never a bare pin |
| Event/edge double-modeling confusion | Spec rule based on whether the occurrence has identity/properties/provenance independent of one pairwise assertion (M-17 — ">2 parties" is guidance, not the rule); examples + counterexamples listed; migration list reviewed once |
| Map effort balloons | MapLibre + PostGIS tiles only; deck.gl and heavy layers stay behind the P9 trigger |

## Specs to author or update

- `specs/10-events-geospatial.md` — author at phase start: event interface,
  participant roles, precision ladder, tile serving.
- `specs/02-data-model.md` — event/participation storage addendum.

## Explicit non-goals

Communications-metadata and financial-event feeds (GOAL.md §14–15 — no such
source exists yet; the event model must merely not preclude them), movement
correlation analytics (P6+), route inference, real-time feeds (Kafka trigger),
deck.gl.

## Task sketch (expanded into `../tasks/phase-05.md`, T54–T65)

- **A — Ontology & storage:** event interface + types, geo/precision columns,
  proposal + migration + regen.
- **B — Actions & ingestion:** record_event, participant validation, travel
  suggestion path.
- **C — Map:** tiles, MapLibre view, precision rendering.
- **D — Sync:** shared time filter across map/timeline/graph; timeline v2.
- **E — Migration:** multi-party edge → event review list; exit tests.
