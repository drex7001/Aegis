# Phase 5 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them; narrower dependencies are noted in the task text. Reference specs in
parentheses. Numbering continues from Phase 4 (T53).

> **Status: COMPLETE 2026-08-23.** All twelve tasks landed and all five gate
> criteria are checked — `../reviews/phase-05-exit-review.md`.
>
> Opened 2026-08-19 by T54. Phases 2–4 closed. T54
> re-validated this plan against the P3/P4-as-built system and against the
> 2026-07-18 charter amendment (ADR-033); its **six divergences** are recorded
> in `../specs/10-events-geospatial.md` §0 and in ADR-046…ADR-049, and the task
> text below has been corrected where it diverged. **Spec 10 is authoritative
> where this file and it disagree.** Charter:
> `../phases/phase-05-events-geo-time.md` · specs:
> `../specs/10-events-geospatial.md` (final), `../specs/02-data-model.md` §9.
>
> The three corrections that change what gets built:
>
> 1. **No canonical event or participation tables** (ADR-046). Events are
>    entities, participation is claims, roles are predicates, time is the claim
>    envelope. The only new table is one projection.
> 2. **The ontology change is major, 1.7.0 → 2.0.0** (ADR-048), because
>    `location.precision` is removed rather than tightened — the tightening T55
>    described is unenforceable and would have been major anyway.
> 3. **GeoJSON, not tiles** (ADR-049). Martin was evaluated and declined.

## Milestone A — Ontology & storage

**T54. ⛓ Spec 10 + the event-vs-edge rule** (charter §Specs) — **DONE
2026-08-19.** Re-validated this plan against the P3/P4-as-built system;
authored `specs/10-events-geospatial.md` (event interface, roles as predicates,
the four-axis geometry model, GeoJSON serving, map privacy, the timeline and
shared time filter, the ontology contract, test obligations); added
`specs/02-data-model.md` §9; enumerated the migration candidate list over every
predicate in `criminal-network.yaml` (§2.4 — exactly one recommended migrate:
`co_arrested_with`); dispositioned B-13, H-21, M-17, M-18, M-19 and every P4
carryover; appended ADR-046…ADR-049; corrected the charter's PostGIS claim.
AC: **met** — see spec 10 §0 for the six divergences and §16 for the carryover
dispositions.

**T55. ⛓ Ontology bump — events + geo** (spec 10 §12; P3 change management) —
declare `meeting`, `arrest`, `travel`, `observation` as object types
implementing the platform `event` interface; add the `place` interface and the
`geometry`/`summary` shared properties; add the role, place and geometry
predicates; **remove `location.precision` and the `event_types:` DSL section**;
add the optional `PredicateSpec.property` field with loader rule 15 (ADR-047);
register the code-owned `admin_level` and `derivation` vocabularies; proposal +
**major bump 1.7.0 → 2.0.0** + history copy + no-op migration + regen of all
four codegen targets.
AC: proposal file lands with the bump commit; `aegis ontology validate` lists
the four event types, both new interfaces and every new predicate;
`aegis ontology check-release` accepts the **major** class and would reject it
declared as minor; `ontology/history/aegis-1.7.0.yaml` exists; the generated TS
constants expose the new types, predicates, categories and both geo
vocabularies; `aegis ontology generate --check` is clean; a predicate declaring
`property:` for a property one of its subject types lacks fails validation with
the YAML path.

**T56. Geometry projection + PostGIS** (spec 02 §9; needs T55) — **the shape
changed (ADR-046)**: no event table and no participation table. One migration
adding `CREATE EXTENSION postgis` (never run before — spec 10 §0 D1), the
`location_geometry_projection` table with its GIST index, and the
`claim(event_time_earliest, event_time_latest)` index; wire the table into
`aegis projections rebuild`; implement the RFC 7946 / WGS84 value validator
(spec 10 §4.3) and the structural discovery rules (§3.2).
AC: migration up/down clean on a seeded DB; `TRUNCATE` + rebuild reproduces the
table exactly (charter exit №5); each of the seven §4.3 rules rejects its
malformed value with a 422 naming the field; an `ST_IsValid` failure projects
with `is_valid = false` and is never repaired; a schema sweep finds no geometry
column outside the projection; Phase 1–4 tests stay green.

## Milestone B — Actions & ingestion

**T57. ⛓ `record_event` action** (spec 10 §12, §13; needs T56) — create/extend
events; participants and places as role-typed references, where the role **is**
the predicate, so an undeclared role is an undeclared predicate the P1 validator
already rejects; time spans with uncertainty via the claim envelope; the entity
and at least one claim in one transaction or nothing (§3.4); actions-v2
parameters + submission criteria; audited. **Also here:** `entity_provenance`
gains the inbound claim set and `GET /v1/entities/{id}` returns it (§13) —
without it an event's participants show on the event's page and on nobody
else's.
AC: an event with 3+ participants is created through the action and every
participant claim carries its role, its source and its grading; an undeclared
role is rejected by validation; an action supplying no participants, places or
summary creates nothing; the event renders in the P4 object view with no new
type-specific React code, and each participant's page shows the event through
the inbound region; `make openapi` runs in the same commit.

**T58. Travel/movement suggestion path** (specs/04; needs T57) — extraction
producer emits travel/movement **event suggestions** (with sources) from
press/border-report-derived text through the standard review-queue path —
Article VII unchanged for events.
AC: a seeded press report yields a travel-event suggestion carrying its
source record; the event reaches canonical tables only after human acceptance
(charter exit №4); rejection leaves no canonical trace.

## Milestone C — Map

**T59. ⛓ Geo serving API** (spec 10 §7, §8; needs T56) — `GET /v1/geo/locations`
and `GET /v1/geo/events` as authorized GeoJSON (ADR-049 — no tiles), filtered by
`claim_filters` **in candidate generation**, cursor-paginated, carrying the
as-of stamp and accepting `asOf`/`asOfRevision` from the first commit (§8.3,
closing the geo half of P4's carryover).
AC: a user sees only geometry their handling/case grants allow (authz matrix
extended to both routes; the anonymous and non-member responses are
byte-identical to a nonexistent id); every feature carries all four axes plus
`geometry_state`; a viewer with only the coarse geometry receives it with no
field disclosing that a finer one exists (§7.2); a malformed `bbox` is a 422,
not an empty collection; counts are computed after filtering (§7.4);
`make openapi` runs in the same commit.

**T60. Map view with honest precision** (spec 10 §9, §10; needs T59; workspace
from P4) — MapLibre GL JS view in the workspace; the mark is selected from the
four axes by one function (§9.1), and the point branch is the only one that
draws a pin; **no basemap is fetched and no external service is contacted**
(§10 — self-hosted style only, no geocoder, worker bundled same-origin so the
CSP does not move).
AC: a `country`-level location **never renders as a point** at any zoom
(charter exit №3, asserted at three zoom levels in a browser test); a unit test
over the full `admin_level × derivation` matrix proves the point branch is
unreachable for administrative levels; the seven derivations are visually
distinguishable; a location with `geometry_state ≠ ok` is listed with its reason
and never drawn; map selection opens the entity's object view; the built bundle
requests no third-party origin.

## Milestone D — Sync

**T61. Timeline v2** (needs T56) — events and claims on one timeline;
time-span uncertainty rendered honestly (fuzzy edges / ranges, not invented
exact dates).
AC: an event and its underlying claims appear coherently (no duplicates); an
uncertain span renders visually distinct from an exact one; timeline items
link to their provenance.

**T62. Shared time filter + selection sync** (spec 10 §11.2; needs T60, T61) —
map, timeline, and graph share one time filter and one selection model; the
as-of mode (P4) composes with it, which means **the graph route gains `asOf` /
`asOfRevision` here** (closing the graph half of P4's carryover — a time-synced
map beside an as-of-now graph is the inconsistency this phase exists to remove).
A claim is in the window when its interval *intersects* it; an undated claim is
excluded from a bounded window and surfaced through the same "undated"
affordance on all three surfaces, never placed at `recorded_at`.
AC: selecting an incident highlights it on all three surfaces; narrowing the
time filter updates all three consistently **from one claim set**; nothing
renders on one surface that the filter excludes on another.

## Milestone E — Migration & close-out

**T63. Multi-party edge → event migration** (spec 10 §2.4; needs T57) — the
list is already enumerated over **every** predicate in the domain module and
recommends exactly one migration (`co_arrested_with`, 2 edges in the projection
snapshot) plus five predicates flagged for a future event type. T63 confirms the
counts against the store, decides the open rows once (risk-table discipline),
and performs the audited, source-preserving transformation described in §2.4:
create or reuse the `arrest` event, write one `has_arrestee` claim per
participant carrying the original envelope, retract the original with a reason
naming the event. Nothing is deleted.
AC: every row on the §2.4 list is dispositioned in writing (migrated or kept,
with reason); migrated incidents lose no source, grading dimension, handling
code, case scope, mention anchor or recorded timestamp; the projection renders
migrated events without dangling edges; the real-graph snapshot baseline is
updated with the diff explained.

**T64. Consistency proof** (charter exits №1–2; needs T62, T63) — the owning
task for the phase's headline criteria, as an automated/scripted
demonstration: one incident (an arrest with 3+ participants, a located,
time-bounded event) renders consistently on map, timeline, and graph from one
claim set, created via the action and verified through the UI.
AC: the round-trip (record via action → object view → map + timeline + graph)
passes as a repeatable test; precision is visually distinct at every zoom in
the captured evidence; the script joins the demo runbook.

**T65. Phase exit review** — walk the charter's gate criteria (non-deferrable,
ADR-025); update speckit docs where reality diverged; append ADRs; write
`../reviews/phase-05-exit-review.md`; tag `phase-5-events-geo` per the git
workflow.
AC: every gate criterion checked; non-blocking deliverables carried over with
owner + target phase recorded.

## Explicit non-goals for Phase 5

Communications-metadata and financial-event feeds (GOAL.md §14–15 — the event
model must merely not preclude them), movement-correlation analytics and route
inference (P6+), real-time feeds (Kafka stays behind its P9 trigger), deck.gl
and heavy map layers (P9 trigger), geocoding automation beyond
manual/assisted entry (false precision is worse than none).
