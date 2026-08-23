# Phase 5 Charter — Events, geospatial & time

Status: **COMPLETE 2026-08-23** — all five gate criteria checked
(`../reviews/phase-05-exit-review.md`). Opened 2026-08-19 (charter amended 2026-07-18, ADR-033
— claims-first storage, B-13; re-validated 2026-08-19 by T54, whose six
divergences are recorded in `../specs/10-events-geospatial.md` §0 and
ADR-046…ADR-049) · tasks: `../tasks/phase-05.md` (T54–T65) · spec:
`../specs/10-events-geospatial.md` (final) · Constitutional basis: Articles I,
VI, VIII, XI, XIII, XIV · GOAL.md §7.3, §16, §17 · plan §2 (PostGIS, MapLibre)

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

- **Semantic:** meeting, arrest, travel and observation declared as **object
  types implementing the platform `event` interface** — the P3 interface
  mechanism the charter already named. The reserved `event_types:` section is
  *removed* rather than filled: an event needs identity, display, claims and an
  object view, all of which an object type already has and a parallel registry
  would not (spec 10 §3.1). `location` implements a `place` interface carrying
  the `geo` property; the overloaded `precision` string is removed (ADR-048).
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
   manual/assisted, never silently precise. *(Spec 10 §4: the four axes are
   modelled separately but asserted together, in one claim, because an accuracy
   without its geometry means nothing. Geometry type is derived from the
   geometry, never asserted. WGS84 only.)*
3. **Map view**: MapLibre GL JS in the workspace over **authorized GeoJSON, not
   tiles** — Martin was evaluated at T54 and declined, because a tile cache is
   shared across viewers while this system's read authorization is per claim
   (ADR-049); selection
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

- P3: interfaces (the `event` shape), DSL `geo` type slot, SDK regen. Both
  confirmed present by T54 and both previously unused.
- P4: workspace (map and timeline live there).
- ~~Phase 1 already enabled the PostGIS extension (migration 0001).~~
  **Corrected 2026-08-19 (T54, spec 10 §0 D1): it did not.** Migration `0001` is
  an empty baseline marker and `0002` creates only `pg_trgm`; no migration has
  ever run `CREATE EXTENSION postgis`. The compose and CI images are
  `postgis/postgis:16-3.4` everywhere, so this is one line in T56's migration,
  not a dependency.

## Exit criteria

- [x] The same incident renders consistently on map, timeline, and graph from
      one claim set; uncertainty is visually distinct at every zoom.
- [x] An event with 3+ participants round-trips through API and UI (create via
      action, render in object view, appear on map + timeline).
- [x] A location known only at admin-area level never renders as a point; a
      low-clearance viewer sees the authorized generalization, not exact
      geometry (M-18).
- [x] A travel event ingested from a press report carries its source and
      appears only after review (Article VII unchanged for events).
- [x] No canonical mutable geometry/precision column exists — geometry
      projections rebuild from claims alone (B-13 spot check).

## Risks

| Risk | Mitigation |
|---|---|
| False precision from geocoding | Uncertainty/derivation fields default coarse; UI renders the uncertainty, never a bare pin |
| Event/edge double-modeling confusion | Spec rule based on whether the occurrence has identity/properties/provenance independent of one pairwise assertion (M-17 — ">2 parties" is guidance, not the rule); examples + counterexamples listed; migration list reviewed once |
| Map effort balloons | MapLibre + PostGIS tiles only; deck.gl and heavy layers stay behind the P9 trigger |

## Specs to author or update

- [x] `specs/10-events-geospatial.md` — authored 2026-08-19 (T54): the event
      interface, roles as predicates, the four-axis geometry model, GeoJSON
      serving (ADR-049 supersedes "tile serving"), the event-vs-edge rule, and
      the migration candidate list.
- [x] `specs/02-data-model.md` §9 — event/participation/geometry addendum
      (2026-08-19, T54): no new canonical table, one new projection table.

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
