# Phase 5 — Exit Review (T65)

Date: 2026-08-23
Release: Aegis 0.5.0
Tag after merge: `phase-5-events-geo`

## Verdict

**PASS — Phase 5 is complete.** All five charter criteria are checked, and
none is deferred or weakened. Places and events are first-class, and the phase's
governing sentence held from the first commit to the last: *where something
happened, when, how precisely, and who was there are assertions; assertions are
claims; PostGIS is a cache.*

The phase adds **no canonical event table, no participation table, and no
geometry column anyone can update.** It is not a deployment authorization — the
pilot gate remains open and untouched (§Deployment boundary).

## Exit criteria — non-deferrable (ADR-025)

- [x] **The same incident renders consistently on map, timeline, and graph from
  one claim set; uncertainty is visually distinct at every zoom.**

  `tests/integration/test_incident_consistency.py` (10) and
  `ui/e2e/incident.spec.ts` (6) seed **one** arrest and then ask every surface
  about it. Nothing is seeded twice, which is the whole design: a test that
  seeded each surface separately could pass while the product disagreed with
  itself, which is the failure the criterion exists to catch.

  The map's `participant_count`, the timeline's participation rows and the
  graph's edges out of the event are three independent readings of one claim
  set, and all three say four. The time is an **interval** everywhere, because
  the source stated a day and a day is a range. Narrowing the window narrows all
  three the same way; widening it past the incident removes it from all three.

  "At every zoom" is proved twice. `ui/e2e/marks.spec.ts` (8) walks the whole
  `admin_level × derivation × geometry_kind × accuracy` matrix from the
  *generated* vocabularies and proves no administrative level can reach the
  point branch in any combination — and that the branch is reachable, because an
  exhaustive negative check that passes vacuously proves nothing. The browser
  journey then proves the rule survives the wiring at three zoom levels.

  **One asymmetry is asserted rather than hidden.** The map and timeline read
  claims; the graph reads `edge_projection`, a cache, so it lags until a rebuild
  (Article XIII). `test_the_graph_is_a_cache_and_says_so` asserts the lag rather
  than letting a fixture paper over it.

- [x] **An event with 3+ participants round-trips through API and UI.**

  `tests/integration/test_record_event.py` (16), `test_event_routes.py` (8).
  Four participants and a place become six claims through `POST /v1/events`,
  render in the **generic** object view with no type-specific code, and appear
  on each participant's own page.

  That last part needed spec 10 §13 and would otherwise have shipped a
  contradiction: participation claims are subjected to the event, so an arrest
  would have listed its participants and each participant's page would have
  shown no arrest at all. The inbound set is **generic, not event-shaped** — the
  same hole existed for `member_of` and the same field closes it, which is what
  the browser journey asserts on.

  The action is atomic or nothing: a half-recorded arrest reads as a complete
  account of a smaller incident.

- [x] **A location known only at admin-area level never renders as a point; a
  low-clearance viewer sees the authorized generalization, not exact geometry
  (M-18).**

  Both halves, and both enforced twice.

  *No false pin.* The store refuses the claim that would license one (spec 10
  §4.3 rules 5–7, `tests/unit/test_geo_values.py`, 28 cases), and the renderer
  has one point branch that is unreachable for an administrative level. A
  guarantee living only in React is a guarantee until someone writes a second
  screen.

  *Authorized generalization.* `tests/integration/test_geo_routes.py` (28). A
  location carries a `sensitive` building polygon and an `open` district
  polygon from two sources; the cleared viewer sees the building, and the
  uncleared viewer's **ordinary `claim_filters`** removes that row so the
  district is what remains. The server never computes a degraded geometry.

  The strongest case is `test_the_generalized_response_discloses_nothing_about_the_finer_one`:
  the generalized feature carries **exactly** the property set every other
  feature carries — no marker, no count, no "a finer geometry exists" field.

- [x] **A travel event ingested from a press report carries its source and
  appears only after review (Article VII unchanged for events).**

  `tests/integration/test_travel_suggestions.py` (10). Between
  `run_travel_pass` and `review_suggestion` there is **no event, no claim and no
  canonical row**; acceptance dispatches through `record_event` with the
  *reviewer* as actor (ADR-031 §2), and rejection leaves the queue row decided
  and the graph untouched.

  Article VII needed no new mechanism for events — `event_draft` is one enum
  value and one dispatch branch on the machinery claims already used. The
  producer refuses to invent coordinates, dates or identity: a place gets a name
  and no geometry, an unreadable date is *undated*, and an unadjudicated name
  rides as its mention anchor.

- [x] **No canonical mutable geometry/precision column exists — geometry
  projections rebuild from claims alone (B-13 spot check).**

  `tests/integration/test_geometry_projection.py` (10): `TRUNCATE
  location_geometry_projection`, rebuild, and the table comes back
  byte-identical including `ST_AsGeoJSON(geom)`.
  `test_the_geometry_rebuilds_from_claims_alone` does the same through the map's
  own response.

  A metadata sweep is the other half —
  `test_geometry_lives_only_in_the_projection` walks every mapped table and
  asserts exactly one carries a geometry column — because the rebuild test would
  keep passing if someone added `entity.geom` beside it.

## What Phase 5 actually changed

| Task | Landed |
|---|---|
| T54 | Spec 10 authored; six divergences → ADR-046…049; the migration list enumerated |
| T55 | Composition **2.0.0** (major): events as object types, geometry as one claim, `PredicateSpec.property` |
| T56 | PostGIS enabled at last; the geometry projection; the seven write-side rules; structural discovery |
| T57 | `record_event`, atomic; inbound claims on the object view |
| T58 | Composition 2.1.0: `event_draft`, and the travel producer |
| T59 | `GET /v1/geo/locations`, `/geo/events` — authorized GeoJSON, not tiles |
| T60 | The MapLibre view; the mark matrix; no third-party origin |
| T61 | `GET /v1/timeline`; certainty derived and drawn |
| T62 | One window, one selection, three surfaces; `asOf` on the graph |
| T63 | Two co-arrest claims → two arrest events; the full list dispositioned |
| T64 | The consistency proof, and §3a of the demo runbook |

Ontology `1.7.0 → 2.1.0` across two bumps: `007` (**major** — the first since
1.0.0) and `008` (minor). Migrations `0011`, `0012`, `0013`. Eleven pull
requests, #60–#70.

## Decisions taken during the phase

Four ADRs, all from T54's re-validation:

- **ADR-046** — an event is an **entity**, participation is **claims** whose
  predicate is the role, time is the claim envelope. Events therefore inherit
  provenance, grading, contradiction display, retraction, as-of, case scoping
  and the review queue on the day they ship; a parallel model would have had to
  re-earn every one. Two costs are stated rather than hidden: a new role is an
  ontology proposal, and two reports of one occurrence make two events, because
  automatic occurrence merging would be a machine making an identity decision.
- **ADR-047** — a literal-object predicate **declares** the property it carries.
  Field sensitivity had been a name coincidence, and `has_geometry` matches no
  property called `has_geometry` — so a restricted geometry would have been
  readable by anyone, silently. The heuristic is *kept* beside the declaration,
  because deleting it would drop the sensitivity of every predicate relying on
  it the moment it landed.
- **ADR-048** — `location.precision` is **removed**, taking the composition to
  2.0.0. It conflated epistemic precision, geometric representation and
  administrative granularity in one string. The four axes now travel together in
  one claim, because an accuracy radius without its geometry means nothing.
- **ADR-049** — authorized **GeoJSON, not tiles**. A tile is a cache keyed by
  z/x/y and shared across viewers; read authorization here is per claim, so a
  correct tile cache is a cache of one. What remains is the failure mode: a
  mis-keyed tile serves sensitive geometry to the wrong viewer where no
  response-level test would see it.

## Defects and gaps found

Seven, and only the last was something the phase set out to look for.

1. **`CREATE EXTENSION postgis` had never run.** The charter said migration
   `0001` enabled it; `0001` is an empty baseline marker and `0002` creates only
   `pg_trgm`. The images were right everywhere, so the extension was one line
   away and nobody had written it. Found by T54 reading the migration instead of
   the charter.
2. **`record_event.participants` could not be satisfied by any caller.** The
   declaration said `json` and the generated model produced `dict[str, Any]`,
   where the value is a list. Corrected in 2.0.0 itself — unreleased, untagged,
   no claim stamps it — and **written into proposal 007**, because "the version
   was not released yet" is exactly the reasoning that erodes a gate when it is
   used without being written down.
3. **The workspace re-declared the geo feature shapes by hand.** The repository
   sweep refused it and was right: a GeoJSON Feature's `properties` is
   open-ended by the standard, so the server had left it untyped. The fix is the
   one the test's docstring names — describe it in the contract — not an
   exemption.
4. **The map double-drew a place that also hosts an event.** The API returns a
   feature per (event, place, role) on purpose, but two overlapping circles for
   one location read as two locations and a reader counting shapes would count
   wrong.
5. **`drillLink` asked why an entity was connected to itself.** It read
   `object_id` unconditionally, which is the far end only for an *outbound*
   claim. The inbound region made it reachable.
6. **Five tests pinned the current release state**, on top of the three P4
   found and the four T55 fixed: the committed ontology version, the proposal
   list, two release-gate cases, the claim stamp's source, and `pyproject.toml`
   itself in the P4 exit suite. Each now asserts the durable fact.
7. **`is_stale` cannot report claim-staleness.** It answers "was any row built
   at an older *identity revision*" — which is what its docstring says and what
   it was written for — not "are there claims this projection has never seen".
   Recording an event advances no revision, so an operator cannot detect that
   the graph is behind. Asserted as the absence it is (T64) and **carried
   below**, rather than widened as a test fix: changing what `is_stale` means is
   a decision.

## Constitution conformance

| Article | Finding | Evidence |
|---|---|---|
| I — claims, not facts | **Pass, extended** | Geometry, participation, place and time are claims; no canonical event or geometry column exists; `record_event` writes an entity *and* a claim or nothing |
| II — no inherent derogatory status | Pass | `has_arrestee` names a role in one sourced, graded, retractable occurrence, not a status about a person; grading carries the doubt |
| III — grading dimensions separate | Pass | Every participation claim carries all three; the migration enumerates them rather than spot-checking |
| IV — evidence is not intelligence | Pass | Untouched |
| V — reversible identity | Pass | Events carry no mentions, so no ER path reaches them; occurrence merging is explicitly a human act (spec 10 §3.5) |
| VI — authorization at query time | **Pass, extended** | The map is not a side door: `claim_filters` in candidate generation on every geo route; a bbox cannot probe for unreadable geometry; counts computed after filtering |
| VII — machines suggest, humans decide | **Pass, extended to events** | `event_draft` dispatches through `record_event` with the reviewer as actor; between the producer and the decision there is no event, no claim and no canonical row |
| VIII — disagreement preserved | Pass | An event's time is the **set** of asserted intervals, never min/max; two reports of one occurrence keep both summaries |
| IX — association is not guilt | **Pass, defended** | No automatic pairwise derivation from events (§2.3): `k` participants would become `k(k−1)/2` edges a reader counts as independent support |
| X — everything audited | Pass | `record_event` audited with what it created; the migration leaves one row per write, not one summary row |
| XI — ontology is domain truth | Pass | Two proposals, two bumps, four codegen artifacts; the geo vocabularies reach React generated |
| XII — adopt before build | Pass | MapLibre adopted; Martin **declined with reasons**; a 15-line `Geometry` type instead of geoalchemy2, because geometry never becomes a Python object here |
| XIII — projections are caches | **Pass, proved** | `TRUNCATE` + rebuild is byte-identical; the graph's cache lag is asserted rather than hidden |
| XIV — core is domain-neutral | **Pass, extended** | Events, places, participation and geometry are found by **structural** rules over interfaces; a fictional `port` implementing `place` is recognised by every one with no code change |

## Deliverables and reality check

Every charter deliverable landed. Three were **narrowed or redirected with
reasons recorded**:

- **The `event_types:` DSL section was removed rather than filled.** An
  occurrence needs identity, display, claims, provenance and an object view —
  all of which an object type already has and a parallel registry would have had
  to re-earn.
- **No vector tiles** (ADR-049), against the task's "PostGIS-backed tiles". The
  trigger to revisit is recorded and measured: >5 000 features in a bbox, or p95
  > 500 ms.
- **No `refresh_projection` side-effect declaration.** Nothing executes side
  effects (spec 08 §6.5) and projections are never refreshed inline on a claim
  write, so it would have been inert twice over and cost a second ontology bump
  inside one phase.

Explicit non-goals held: no communications-metadata or financial-event feeds, no
movement-correlation analytics, no route inference, no real-time feeds, no
deck.gl, no automatic geocoding, no occurrence deduplication, no automatic
pairwise derivation, and no response-mode policy for withheld geometry.

## Carryovers

| Item | Owner | Target | Dependency impact |
|---|---|---|---|
| **`is_stale` cannot report claim-staleness** | P6 owner | With the first analytic whose run manifest needs a projection snapshot (H-23) | None today: the graph shows its stamps and an admin can rebuild. It matters when a *finding* has to name the projection it was computed over |
| Five occurrence-naming predicates flagged, not migrated | The phase that declares `attack` / `incident` / `directive` | Recorded in `phase-05-migration-dispositions.md` | None; the rule that applies to them is decided, only the vocabulary is missing |
| `?asOf=` on **search** | P6 owner | With the historical questions search raises | None; geo closed at T59 and graph at T62 |
| Claims picker for hypothesis links | P6 owner | With object sets | None (P4 carryover, unchanged) |
| Audit console | P7 owner | With sealing and break-glass (ADR-045) | None (P4 carryover, unchanged) |
| Response-mode policy for withheld geometry | P7 owner | H-25 | None; P5 ships the honest default (`none_permitted` vs `none_recorded`) and records the switch point |
| `hypothesis`/`investigation_task` FGA types declared but not queried | P7 owner | When a direct check becomes meaningful | None (P4 carryover, unchanged) |
| FGA object-type stub codegen | P7 owner | When a **domain** type first gets an FGA relation | None. P5 declares none: geo reads are gated by handling code and case membership, which are claim-level |
| Python SDK | P8 owner | P8 producers | None (ADR-033, unchanged) |
| Functions execution + side-effect outbox | P6 owner | Spec 08 §11.1–11.2 | None; P5 needed neither |
| Pilot gate | Deployment owner | Before any non-loopback listener or second real user | Blocks deployment, not P6 development |

## Verification

Run on the exact reviewed tree, against PostgreSQL 16 on `127.0.0.1:5433`:

```
uv run pytest -q tests/unit tests/component tests/contract   # 488 passed
uv run pytest -q tests/integration                           # 443 passed
uv run aegis ontology validate                               # OK v2.1.0, 2 modules
uv run aegis ontology generate --check                       # OK: 4 artifacts current
uv run aegis ontology check-release                          # OK: v2.1.0 (minor, proposal 008, from 2.0.0)
uv run aegis api check-contract                              # OK: 0 breaking
uv run alembic heads                                         # 0013 (head)
uv lock --check                                              # clean
cd ui && npm run typecheck && npm run build && npx playwright test   # clean; 125 passed
```

**System tests were not runnable on the development machine** — the OpenFGA
container cannot bind its port there — so CI's `system-tests` job is their only
execution. It passed on every one of the eleven Phase 5 pull requests (#60–#70).
This is the same arrangement T28, T40 and T53 recorded, stated again for the
same reason: the reader should know which evidence came from where.

Phase 5 added **173 tests** (488 + 443 against P4's 433 + 336), plus 33 browser
journeys (125 against 92).

## Deployment boundary

Unchanged and unauthorized. 0.5.0 is a localhost development release. The pilot
gate's seven items are all still open, `aegis serve` still refuses a non-loopback
bind without an explicit override, and nothing in this phase may be represented as pilot-ready.

The map **strengthens** the boundary rather than testing it. It contacts no external service
by default or by accident — no basemap tiles, no glyph server, no geocoder — and
sending a name or selector to a public geocoder is prohibited outright rather
than merely unconfigured.

## Release action

`pyproject.toml` and `uv.lock` advance from 0.4.0 to **0.5.0**. After the review
PR is squash-merged, tag that master commit:

```bash
git tag -a phase-5-events-geo -m "Phase 5 exit: events, geospatial and time"
git push origin phase-5-events-geo
```

## Final decision

All five gate criteria are checked. Phase 5 is complete and **Phase 6 — search,
object sets & governed analytics** may begin with its own re-validation task
(T66), which should disposition the carryovers above before anything else — in
particular the `is_stale` gap, which P6's run manifests are the first thing to
need.
