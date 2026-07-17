# Phase 5 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them; narrower dependencies are noted in the task text. Reference specs in
parentheses. Numbering continues from Phase 4 (T53).

> **Status: PRE-AUTHORED, NOT ACTIVE.** Phases 2–4 must close first (P3 supplies
> the `event` interface mechanism, `geo` type slot, and SDK regen; P4 supplies
> the workspace the map and timeline live in). Authored 2026-07-17 ahead of
> phase start; T54 re-validates this plan against the P3/P4-as-built system
> before any other task starts. Charter:
> `../phases/phase-05-events-geo-time.md` · specs: `../specs/10-events-geospatial.md`
> (authored by T54), `../specs/02-data-model.md` (addendum).

## Milestone A — Ontology & storage

**T54. ⛓ Spec 10 + the event-vs-edge rule** (charter §Specs) — re-validate
this plan against the P3/P4-as-built system (interface mechanism, SDK shape,
workspace layout); author `specs/10-events-geospatial.md`: the `event`
interface (time span + participants + optional location), participant role
vocabulary, the precision ladder (exact / centroid / area / city / country,
GOAL.md §16.4), tile serving approach; write the **event-vs-edge rule** into
the spec (>2 parties or time/place-bearing → event; true pairwise → binary
predicate) with the one-time migration list of existing multi-party edges;
add the event/participation storage addendum to specs/02.
AC: spec 10 exists and covers interface, roles, precision, tiles, and the
rule; the migration candidate list is enumerated (review happens in T63);
divergences from this plan are ADR'd.

**T55. ⛓ Ontology bump — events + geo** (specs/10; P3 change management) —
fill the ontology's `event_types` (meeting, arrest, travel, observation) via
the `event` interface; add the `geo` property type and a **required**
`precision` property on `location`; proposal + minor bump + regen of all
codegen targets and both SDKs.
AC: proposal file lands with the bump commit; `aegis ontology validate` lists
the event types and interface; both SDKs expose typed event objects after
regen; the minor-bump diff check stays green; a location without `precision`
fails validation.

**T56. Event & participation storage** (specs/02 addendum; needs T55) —
migrations: event objects with role-typed participant links, participation
claim-backed like everything else (Article I — each participation row traces
to a source); PostGIS `geometry` column + `precision` on location entities.
AC: migration up/down clean on a seeded DB; a participation row without a
source reference is impossible (constraint or action-layer test); geometry
round-trips with correct SRID; Phase 1–4 tests stay green.

## Milestone B — Actions & ingestion

**T57. ⛓ `record_event` action** (specs/10; needs T56) — create/update events
with participants as role-typed references validated against the ontology's
role vocabulary; time spans with uncertainty; optional location reference;
actions-v2 parameters + submission criteria; audited.
AC: an event with 3+ participants is created through the action and every
participant link carries its role and source; an undeclared role is rejected
by validation; the event renders in the P4 object view with no new
type-specific React code.

**T58. Travel/movement suggestion path** (specs/04; needs T57) — extraction
producer emits travel/movement **event suggestions** (with sources) from
press/border-report-derived text through the standard review-queue path —
Article VII unchanged for events.
AC: a seeded press report yields a travel-event suggestion carrying its
source record; the event reaches canonical tables only after human acceptance
(charter exit №4); rejection leaves no canonical trace.

## Milestone C — Map

**T59. ⛓ Geo serving API** (specs/10; needs T56) — location/event geometry
served to the workspace (PostGIS-backed tiles or GeoJSON per spec 10's
decision), **authorization-filtered before return** (Article VI — the map is
not a side door past row filters); `precision` always in the payload.
AC: a user sees only geometry their handling/case grants allow (authz matrix
extended to geo endpoints); every feature carries `precision`; response format
matches spec 10.

**T60. Map view with honest precision** (needs T59; workspace from P4) —
MapLibre GL JS view in the workspace; precision rendered visually distinct —
point (exact) vs circle (centroid/area) vs admin area (city/country); no
"bare pin" rendering path exists.
AC: a `precision: country` location **never renders as a point** at any zoom
(charter exit №3, asserted in a UI test); the five precision levels are
visually distinguishable; map selection opens the entity's object view.

## Milestone D — Sync

**T61. Timeline v2** (needs T56) — events and claims on one timeline;
time-span uncertainty rendered honestly (fuzzy edges / ranges, not invented
exact dates).
AC: an event and its underlying claims appear coherently (no duplicates); an
uncertain span renders visually distinct from an exact one; timeline items
link to their provenance.

**T62. Shared time filter + selection sync** (needs T60, T61) — map,
timeline, and graph share one time filter and one selection model; the as-of
mode (P4) composes with it.
AC: selecting an incident highlights it on all three surfaces; narrowing the
time filter updates all three consistently **from one claim set**; nothing
renders on one surface that the filter excludes on another.

## Milestone E — Migration & close-out

**T63. Multi-party edge → event migration** (the T54 list; needs T57) —
review the enumerated migration candidates once (risk-table discipline):
migrate where >2 parties or time/place matter (e.g. co-arrest chains), keep
binary predicates for true pairwise relations; each migration is an audited,
source-preserving transformation.
AC: every candidate on the list is dispositioned (migrated or kept, with
reason); migrated incidents lose no sources or gradings; the projection
renders migrated events without dangling edges.

**T64. Consistency proof** (charter exits №1–2; needs T62, T63) — the owning
task for the phase's headline criteria, as an automated/scripted
demonstration: one incident (an arrest with 3+ participants, a located,
time-bounded event) renders consistently on map, timeline, and graph from one
claim set, created via the action and verified through the UI.
AC: the round-trip (record via action → object view → map + timeline + graph)
passes as a repeatable test; precision is visually distinct at every zoom in
the captured evidence; the script joins the demo runbook.

**T65. Phase exit review** — walk the charter's exit criteria; update speckit
docs where reality diverged; append ADRs; write
`../reviews/phase-05-exit-review.md`; tag `phase-5-events-geo` per the git
workflow.
AC: all exit boxes checked or explicitly deferred with reason.

## Explicit non-goals for Phase 5

Communications-metadata and financial-event feeds (GOAL.md §14–15 — the event
model must merely not preclude them), movement-correlation analytics and route
inference (P6+), real-time feeds (Kafka stays behind its P9 trigger), deck.gl
and heavy map layers (P9 trigger), geocoding automation beyond
manual/assisted entry (false precision is worse than none).
