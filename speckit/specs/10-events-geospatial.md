# Spec 10 — Events, geospatial & time

Status: **final** (authored 2026-08-19 by T54, the blocking re-validation that
opens Phase 5) · Charter: `../phases/phase-05-events-geo-time.md` ·
Constitutional basis: Articles I, VI, VIII, XI, XIII, XIV · GOAL.md §7.3,
§16, §17 · Findings closed here: B-13, H-21, M-17, M-18, M-19 ·
ADR-046…ADR-049

This spec has one governing sentence, and everything else is its consequence:

> **Where something happened, when, how precisely, and who was there are
> assertions. Assertions are claims. PostGIS is a cache.**

Phase 5 therefore adds **no canonical event table, no participation table, and
no geometry column anyone can update.** It adds four object types, a handful of
predicates, one projection table, three serving routes, and a map that cannot
draw a pin it has not been told it may draw.

---

## 0. What re-validation changed

`tasks/phase-05.md` was pre-authored 2026-07-17, before Phase 3 and Phase 4
existed, and was amended 2026-07-18 by ADR-033 without the task text being
rewritten. T54 walked both against the as-built system. Six divergences, each
dispositioned rather than absorbed silently:

| # | The plan said | As built / as required | Disposition |
|---|---|---|---|
| D1 | "Phase 1 already enabled the PostGIS extension (migration 0001)" (charter §Dependencies) | Migration `0001` is an empty baseline marker; `0002` creates `pg_trgm` and nothing else. **No migration has ever run `CREATE EXTENSION postgis`.** The image is right everywhere (`postgis/postgis:16-3.4` in `infra/docker-compose.yml` and in CI's integration and system jobs), so this is one line, not a dependency | Charter corrected; the extension lands in T56's migration. No ADR — a factual error in a charter is fixed, not decided |
| D2 | T56: "migrations: event objects with role-typed participant links … PostGIS `geometry` column + `precision` on location entities" | That is the canonical-table model B-13 rejected and ADR-033 already overruled. Events are **entities**, participation is **claims**, and the only new table is a projection | **ADR-046**. §3, §6 |
| D3 | T55: "add … a **required** `precision` property on `location`"; "the minor-bump diff check stays green"; "a location without `precision` fails validation" | Three problems. (a) H-21 rejects the single overloaded ladder outright. (b) Tightening optional→required is major under spec 01 §4, which the amended charter itself says. (c) **Nothing enforces `required` on an object-type property** — properties are claim-derived and no write path constructs an entity with a property set, so the AC could not be made true at any version class | **ADR-048** — `location.precision` is *removed*, the four axes arrive as one typed claim, and the composition goes to **2.0.0**. §4 |
| D4 | Field sensitivity and "which claim carries geometry" can be resolved from the ontology | `property_sensitivity` (`aegis/authz/filters.py`) matches a predicate name to a property name and otherwise guesses from the `identifier` flag. Spec 09 §6.4 already recorded this as "a documented heuristic, not a contract". M-18 requires map privacy to be **enforced**, and Article XIV requires the core to find geometry without naming a domain predicate. Neither can rest on a name coincidence | **ADR-047** — a literal-object predicate declares the property it carries. §5 |
| D5 | T59: "PostGIS-backed tiles"; charter: "evaluate MapLibre Martin before hand-building" | Evaluated and declined. A tile is a shared cache keyed by z/x/y; this system's read authorization is per claim (handling code × clearance × case membership × as-of). Correctness would require keying the cache by authorization context, which removes the benefit and adds a leak surface. Martin's headline feature — auto-publishing PostGIS tables and functions — is the thing H-21 explicitly forbids | **ADR-049** — authorized GeoJSON over the ordinary claim filter, with a measured trigger to revisit. §8 |
| D6 | T54 sketch: the event-vs-edge rule is ">2 parties or time/place-bearing → event" | M-17 is right that this over-fires: most claims carry a time and many carry a place. The rule is **independent identity**, and the corpus turns out to contain exactly **one** predicate that meets it | §2. Recorded in the spec rather than an ADR — nothing is being overruled, a rule is being written for the first time |

Two things the plan assumed and reality confirms, recorded so nobody re-checks
them: the DSL **already** has a `geo` property type (`PropertyType` in
`aegis/ontology/loader.py`, shipped by P3 and never used), and `PredicateSpec`
**already** retains `subject_interfaces`/`object_interfaces` after expansion —
which is what lets §3.2's discovery rules be structural instead of a name list.

---

## 1. Scope, and the one storage rule

Phase 5 makes places and events first-class. It does not make them special.

| Concept | What it is | Where it lives |
|---|---|---|
| An occurrence (meeting, arrest, travel, observation) | An **entity** whose type implements the `event` interface | `entity` — the table it has always been |
| Who was there, and as what | A **claim** whose subject is the event and whose predicate names the role | `claim` |
| Where it happened | A **claim** whose subject is the event and whose object is a `place` entity | `claim` |
| When it happened | The `event_time_earliest`/`event_time_latest` **already in the claim envelope** (ADR-008) | `claim` |
| What shape the place is, how accurately, at what administrative granularity, derived how | **One claim** carrying a four-field value (§4.2) | `claim` |
| Spatial indexes and geometry types | A **projection**, rebuilt from those claims | `location_geometry_projection` |

**The storage rule (B-13, binding).** No table outside `claim` may hold an
asserted geometry, precision, participant role, or event time that a user can
update. `aegis projections rebuild` must be able to `TRUNCATE` every table in
the right-hand column above and reproduce it exactly. A future canonical event
table requires an Article I amendment first, not a performance argument.

**What this buys, stated once.** Every capability the phase needs already
exists for claims and is therefore free and already tested: provenance panels,
grading on all three dimensions, contradiction display, retraction,
`?asOf=`/`?asOfRevision=`, case scoping, handling-code filtering, the audit
trail, and the review queue. A parallel event model would have had to re-earn
every one of them, and would have failed Article I on the way.

---

## 2. The event-vs-edge rule (M-17)

### 2.1 The rule

> Model an occurrence as an **event object** when it has **identity
> independent of any single pairwise assertion** — when "which occurrence?"
> and "which pair?" can have different answers.

Three operational tests. An occurrence is an event when **any** holds:

1. **It can be described without naming a pair.** "The 12 March arrest at
   Negombo" is a thing two sources can independently describe, disagree about,
   and be corrected on.
2. **It carries properties no pair owns.** A time span, a place, a summary, a
   handling code, a case — attached to the occurrence, not to any one
   relationship inside it.
3. **Participants can be added or removed without contradicting what was
   already recorded.** Learning of a fourth arrestee extends the event. Under a
   pairwise model it silently changes the meaning of the three edges already
   there.

> Keep a **binary predicate** when the assertion is genuinely about the pair
> and has no life apart from it.

Kinship, membership, control, alliance, rivalry: `sibling_of` names no
occurrence, and asking "when did the sibling-ness happen?" is a category error.
These stay predicates forever.

**">2 parties" is a symptom, not the rule.** A two-person meeting is an event
(it has independent identity); a fifty-member organisation is not.

### 2.2 Examples and counterexamples

| Case | Model | Why |
|---|---|---|
| An arrest naming four people | `arrest` event | Independent identity; a fifth name extends it |
| A meeting between two people | `meeting` event | Two sources may describe the same meeting differently; the meeting is the thing they disagree about |
| A border crossing on a stated date | `travel` event | Carries origin, destination, time, and a source |
| A surveillance observation | `observation` event | Has an observer, a subject, a place and a time, none of which belongs to a pair |
| "A is B's sibling" | `sibling_of` predicate | No occurrence |
| "A is a member of organisation O" | `member_of` predicate | A status, not an occurrence — even though it began at a moment |
| "A controls company C" | `controls` predicate | A standing relation; the claim's `valid_from`/`valid_to` already carry its span |
| "A and B were in the same prison block" | `co_located_in_prison_with`, computed | Derived from two remand windows; there is no occurrence to point at |
| "A and B were arrested together" | **`arrest` event** | This is the one existing predicate that names an occurrence (§2.4) |

### 2.3 Why there is no automatic pairwise derivation

M-17 permits "an event plus derived pairwise projection without duplicate
canon". Phase 5 **declines the permission**, and the reason is the one B-12
gave about edges:

An arrest with `k` participants would derive `k(k−1)/2` edges. Five people
become ten relationships in the graph, each of which a reader will count as
independent support. That is a single sourced occurrence being restated as ten
apparent connections — the "authoritative rumour engine" the project exists not
to be, arriving through a rendering choice rather than a claim.

The event **is** the rendering. The graph draws the event as a node with its
participants attached, which is both honest about arity and visibly one thing.

**Revisit when** a P6 analytic genuinely needs pairwise adjacency (centrality
over co-participation). Then it is computed inside the analytic, with the event
named in the finding's basis, and it is still not a claim.

### 2.4 The migration candidate list (enumerated here, dispositioned by T63)

Every predicate in `criminal-network.yaml` v1.2.1, against §2.1. This is the
complete list; T63 adds no candidates, it only decides the open rows.

| Predicate | Names an occurrence? | Recommendation | Reason |
|---|---|---|---|
| `co_arrested_with` | **Yes** | **Migrate to `arrest` events** | Every recorded instance is one arrest with two or more people in it. The projection snapshot carries **2 edges**; T63 confirms the count against the store before migrating |
| `masterminded_attack_with` | Yes | **Keep for P5; flag** | An attack is an occurrence, but `attack` is not among the four event types this phase declares, and inventing a fifth to hold two predicates is scope the charter did not fund. Flagged for the phase that declares it |
| `co_attacker_with` | Yes | **Keep for P5; flag** | Same |
| `ordered_killing_of` | Yes | **Keep; flag** | An occurrence, but recorded pairwise with no independent description in the corpus. Revisit with a `directive`/`incident` type |
| `killed_family_of` | Yes | **Keep; flag** | Same |
| `tipped_off_police_on` | Yes | **Keep; flag** | Same |
| `communicated_with` | Yes | **Keep — non-goal** | Communications-metadata events are explicitly out of scope (GOAL.md §14–15; charter §Non-goals). The event model must not preclude them, and does not |
| `provided_military_training_to` | Course of conduct | Keep | Not one occurrence |
| `trafficked_narcotics_with` | Course of conduct | Keep | Not one occurrence |
| `helped_establish_operations_of` | Course of conduct | Keep | Not one occurrence |
| `financed_and_supplied_materiel_to` | Course of conduct | Keep | Not one occurrence |
| `co_located_in_prison_with` | No | Keep | Computed from remand windows; §2.2 |
| `conspired_with`, `conspired_against` | No | Keep | Assessments about a relationship |
| `member_of`, `founded`, `pledged_allegiance_to`, `splinter_affiliate_of`, `successor_leader_of`, `affiliated_with` | No | Keep | Standing relations |
| `allied_with`, `partnered_with`, `close_associate_of`, `rival_of`, `controls`, `foreign_contact_of` | No | Keep | Standing relations |
| `sibling_of`, `spouse_of` | No | Keep | Kinship |
| `known_as`, `has_nic`, `born_on`, `registered_as`, `reachable_on`, `assessed_as_criminal_organization` | No | Keep | Property and identifier claims |

**Migration discipline (T63).** A migration is an audited transformation that
preserves every source, grading dimension, handling code, case scope, mention
anchor and recorded timestamp: for each `co_arrested_with` claim, create (or
reuse) the `arrest` event, write one `has_arrestee` claim per participant
carrying the original claim's full envelope, and retract the original with a
reason naming the event. Nothing is deleted. If the two claims prove to
describe two different arrests, they become two events — that decision is made
by a human, once, with the sources in view.

---

## 3. Events

### 3.1 An event is an entity

`meeting`, `arrest`, `travel`, `observation` are object types that
`implements: [event]`. They are not a separate registry.

The consequence is the point: an event gets `entity.label`, the generic object
view, search, the graph, provenance drill-down, identity columns and the
version banner **without one line of type-specific code** — which is also the
form of Article XIV's proof (T57's AC: "renders in the P4 object view with no
new type-specific React code").

The `event_types:` section spec 01 §2 reserved is **removed** (§12). It was
never populated and would have been a second object-type registry with none of
an object type's capabilities.

### 3.2 Participation is a claim; the role is the predicate

One predicate per role. `has_arrestee`, `has_arresting_officer`,
`has_attendee`, `has_traveller`, `has_observer`, plus the deliberately vague
`has_participant` for "they were there and we do not know in what capacity".

This is why roles are predicates and not a column:

- An undeclared role is an **undeclared predicate**, rejected by the claim
  validator that has existed since P1. T57's AC ("an undeclared role is
  rejected by validation") is satisfied by machinery already under test.
- A role that only makes sense for one event type says so in its declaration:
  `has_arrestee: {subject: [arrest], object: [person]}`. An arrestee at a
  meeting is a validation error, not a convention.
- Each participation carries its own source, grading, time, handling code and
  mention anchor, because it *is* a claim. Two sources naming different
  participants disagree visibly (Article VIII) instead of being merged into a
  participant list.

**Direction: the event is the subject.** `arrest --has_arrestee--> person`.
The event is the thing being described, and the same direction serves
`took_place_at`, so one rule covers participants and place.

**How the core finds these without naming a domain predicate** (Article XIV) —
four structural rules over the composed registry, evaluated on **expanded**
type lists so a declaration may name either an interface or concrete types:

| The core needs | The rule |
|---|---|
| Event entities | `entity.entity_type` implements `event` |
| Participation claims | every subject type of the predicate implements `event` **and** every object type implements `party` |
| Event-place claims | every subject type implements `event` **and** every object type implements `place` |
| Geometry claims | the predicate declares `property:` (§5) and that property's type is `geo` |

Nothing in `aegis/` names `arrest`, `has_arrestee` or `location`. The names it
does use — `event`, `place`, `party` — are **platform interfaces**, owned by
`ontology/modules/platform.yaml`, which is the core's own vocabulary. The
second-domain fixture proves the difference by implementing the same interfaces
under different type names.

### 3.3 Time rides the claim envelope

There is **no** event time column and no time predicate.
`claim.event_time_earliest` and `claim.event_time_latest` have existed since P1
and already express everything the charter asks for:

| Assertion | Encoding |
|---|---|
| Exactly 12 March 2019, 14:30 | `earliest == latest` |
| Some time on 12 March | `earliest = 00:00`, `latest = 23:59:59` |
| Some time in March | the month's bounds |
| After 12 March, end unknown | `earliest` set, `latest` null |
| Time unknown | both null |

An event's time is therefore **the set of intervals its claims assert**, with
each interval attributable to its source. It is never collapsed to a single
span (§6.3), because that is exactly the collapse B-12 caught in
`edge_projection`: two disjoint reports becoming one continuous occurrence.

A claim with no event time is **undated**, and undated is a state the UI shows
(§11), never a value it invents from `recorded_at`.

### 3.4 What makes an event exist

`record_event` (§12) creates the event entity **and at least one claim in the
same transaction**, or it creates nothing. An entity row is not an assertion
and carries no source; an event that no claim asserts would be a fact with no
provenance sitting in the entity table, which is the Article I failure this
whole phase is arranged to avoid.

The cheapest satisfying claim is `summarized_as` — the source's own sentence
about what happened, carrying the record, the grading and the time. Every event
should have one anyway.

### 3.5 Two reports of one occurrence make two events — and that is the honest state

Event entities are created only by `record_event` and carry no mentions, so no
entity-resolution path reaches them: the deterministic rules key off
`identifier: true` predicates and same-document mention keys, and events have
neither. Two press reports of the same arrest therefore produce two `arrest`
events until a human says otherwise.

This is stated rather than fixed because the alternative is worse. Automatic
occurrence merging is an identity decision made by a machine, and Article VII
and ADR-027 forbid exactly that. `record_event` accepts an existing `event_id`,
so the reviewer's move is to attach the second report's claims to the first
event — an ordinary, sourced, audited act.

**Revisit when** occurrence duplication is measured to be a real analytic
problem. The mechanism it would need is the identity ledger (ADR-028) extended
to non-person entities, which is a phase of its own, not a P5 deliverable.

---

## 4. Places and geometry

### 4.1 The `place` interface

`place` is a platform interface requiring one shared property, `geometry`
(type `geo`). `location` implements it. A second domain's `port` or `warehouse`
implements it and inherits every rule in this section without editing the
platform module (ADR-041).

Geometry belongs to places, not to events. An event with coordinates but no
named place creates a `location` entity for those coordinates — one geometry
model, one rendering path, one set of privacy rules. An event may reference
more than one place (`travelled_from` / `travelled_to`), and that is a property
of travel, not an exception.

### 4.2 One claim, four fields (H-21)

H-21's requirement is that geometry, uncertainty, administrative granularity
and derivation be modelled **separately**. It is not a requirement that they be
asserted separately, and they must not be: an accuracy radius without its
geometry means nothing, and a derivation method describes how *this* geometry
was obtained. Four independent claims could disagree with each other in ways
that have no interpretation.

So: **one predicate, `has_geometry`, whose literal value is a four-field
object.**

```jsonc
{
  "geometry":    { "type": "Polygon", "coordinates": [ /* … */ ] },  // required, RFC 7946
  "accuracy_m":  5000,                  // radius of positional uncertainty in metres, or null
  "admin_level": "locality",            // required — see the ladder below
  "derivation":  "admin_unit_centroid"  // required — see the vocabulary below
}
```

**`admin_level`** — a code-owned ordered ladder, coarse to fine, registered
beside the other code-owned vocabularies in `aegis/ontology/registries.py`:

```
country  >  subdivision  >  locality  >  site
```

plus the sentinel **`not_administrative`** for geometry that is not an
administrative unit at all — an instrument fix, a coverage polygon, a route.
The ladder is generic on purpose: `subdivision` covers a province, state or
district without the platform learning any country's hierarchy.

**`derivation`** — how the geometry was obtained, also code-owned:

| Value | Meaning |
|---|---|
| `instrument_fix` | GPS/technical fix with a stated accuracy |
| `source_stated_coordinates` | the source printed coordinates |
| `address_match` | matched to a street address |
| `admin_unit_boundary` | the boundary polygon of a named administrative unit |
| `admin_unit_centroid` | the centre of a named administrative unit — **not** a location |
| `coverage_area` | the area something covers (a cell, a patrol zone) |
| `analyst_estimate` | an analyst's reasoned estimate, with the reasoning in the excerpt |

These are code-owned rather than ontology-declared for the same reason
`SUBMISSION_CRITERIA` and `PAYLOAD_SCHEMAS` are: the renderer and the validator
must implement each value, so a value that could be declared before it could be
honoured would be a promise nothing keeps (spec 08 §6.3, H-13). Both lists are
exported to the client by `aegis ontology generate`, so no vocabulary is typed
into React either.

### 4.3 Validation (rejected at the write, not repaired at the read)

Coordinates are **WGS84 / EPSG:4326 only**, which is what RFC 7946 mandates for
GeoJSON. There is no CRS negotiation and no reprojection: a second CRS is a
second way to be wrong about where something is.

`record_claim` rejects a `has_geometry` value when:

1. the geometry is not a valid RFC 7946 geometry object, or names a `crs`
   member (removed from the standard), or contains a non-finite coordinate;
2. longitude is outside [−180, 180] or latitude outside [−90, 90];
3. a polygon ring is not closed, or has fewer than four positions;
4. a ring spans more than 180° of longitude — the antimeridian case RFC 7946
   §3.1.9 says must be split into two geometries rather than written as one
   that silently wraps the wrong way round the planet;
5. `derivation` is `admin_unit_centroid` or `coverage_area` and `accuracy_m` is
   absent — a centroid without a radius is a pin pretending to be a city;
6. the geometry is a `Point` and `admin_level` is administrative
   (`country`/`subdivision`/`locality`/`site`) while `derivation` is not
   `admin_unit_centroid` — the only honest way a Point represents an
   administrative area is as its stated centroid, with its radius;
7. `derivation` is `admin_unit_boundary` and the geometry is not a `Polygon` or
   `MultiPolygon`.

Rules 5–7 are the write-side half of "no bare pin exists" (§9): the renderer
cannot draw a false pin because the store will not accept the claim that would
license one.

**Topological validity** is checked at projection time, not at write time,
because `ST_IsValid` is PostGIS's answer and the write path must not depend on
the projection database. An invalid geometry is projected with
`is_valid = false` and its reason, is **never** repaired by `ST_MakeValid`, and
is served with `geometry: null` and that reason. Silently repairing a
self-intersecting polygon changes what a source said.

### 4.4 `location.precision` is removed

The v1.2.1 property `precision: {type: text}` — commented
`exact|centroid|area|city|country` — mixes epistemic precision (`exact`),
geometric representation (`centroid`, `area`) and administrative granularity
(`city`, `country`) in one string, which is precisely H-21's finding. Keeping
it beside the four-field model would leave a field that means the wrong thing
rendering on every location page.

It is removed. Removal is **major** under spec 01 §4 regardless of row counts —
the precedent is v1.0.0's removal of `merged_into`, which also had no rows — so
the composition goes to **2.0.0** (ADR-048, §12).

---

## 5. A literal-object predicate declares the property it carries (ADR-047)

`PropertySpec` and `PredicateSpec` are parallel vocabularies with no declared
mapping between them. `aegis/authz/filters.py::property_sensitivity` bridges
them by matching a predicate's *name* against a property's *name*, falling back
to the `identifier` flag. Spec 09 §6.4 recorded this as "a documented heuristic,
not a contract" and moved on, because in P4 nothing depended on it.

In P5 two things do:

- **M-18.** Field-level sensitivity on geometry has to be enforceable, and
  `has_geometry` does not match a property named `geometry` by that heuristic.
- **Article XIV.** The core has to find geometry claims without a hardcoded
  predicate name (§3.2).

So `PredicateSpec` gains an optional `property: <name>`:

```yaml
has_geometry: {subject: [place], object: literal, property: geometry, label: Geometry}
has_nic:      {subject: [person], object: literal, identifier: true, property: nic, label: Has NIC}
```

Loader rule (numbering continues spec 08 §9): **rule 15** — a declared
`property` must exist on **every** expanded subject type of the predicate, and
the predicate must allow a literal object. `property_sensitivity` consults the
declaration first and keeps the heuristic only for predicates that do not
declare one, so nothing that works today stops working.

Adding an optional field is additive (spec 08 §7.3). Declaring it on `has_nic`,
`reachable_on` and `registered_as` at the same time turns three existing
coincidences into three statements, which is worth doing while the mechanism is
being built.

---

## 6. Projections (Article XIII)

### 6.1 One new table, and why only one

```sql
CREATE TABLE location_geometry_projection (
  claim_id       TEXT PRIMARY KEY REFERENCES claim,
  place_id       TEXT NOT NULL REFERENCES entity,
  geom           geometry(Geometry, 4326),      -- NULL when is_valid = false
  geometry_kind  TEXT NOT NULL,                 -- ST_GeometryType, derived, never asserted
  admin_level    TEXT NOT NULL,
  accuracy_m     DOUBLE PRECISION,
  derivation     TEXT NOT NULL,
  is_valid       BOOLEAN NOT NULL,
  invalid_reason TEXT,
  -- every governance column the claim carries, so one filter serves both
  handling_code  TEXT NOT NULL,
  case_id        TEXT REFERENCES case_file,
  recorded_at    TIMESTAMPTZ NOT NULL,
  retracted_at   TIMESTAMPTZ,
  ontology_version TEXT NOT NULL
);
CREATE INDEX ON location_geometry_projection USING GIST (geom);
```

**One row per claim**, not one per place. That is what makes `claim_filters`
compose unchanged: two geometry claims for one place at different handling
codes are two rows, and a viewer sees whichever they may read (§7.2). A
one-row-per-place table would have had to pick a winner, and picking a winner is
where map privacy dies.

**No `event_projection`, and no participation projection.** Both would be a
straight copy of `claim` rows plus one derived column, and a projection that
buys nothing but duplication is duplication. This table exists because a GIST
index over `geometry(Geometry, 4326)` is something `claim.object_value` JSONB
genuinely cannot do. Event and participation queries read `claim` directly,
supported by an index on `(event_time_earliest, event_time_latest)`.

**Revisit when** an event query is measured over the corpus at p95 > 300 ms;
then a participation projection is added with the measurement recorded, the same
way any other trigger fires.

**As built (T56).** Two details the DDL above does not show. `geom` is
**nullable**, because an invalid geometry is stored with `is_valid = false`, its
`ST_IsValidReason`, and no geometry — a NOT NULL column would have forced the
choice between repairing it and losing the row, and both change what a source
said. And `handling_rank` is copied beside `handling_code`, because the filter
compares clearance levels and a rank computed at read time would have to consult
the ontology on every query.

Both projections rebuild in **one pass under one advisory lock**
(`POST /v1/projections/rebuild`, `aegis projections rebuild`). "Rebuild the
projections" that left one of them stale would be a worse answer than refusing.

### 6.2 Rebuild, and the B-13 spot check

`aegis projections rebuild` gains this table. Its contract is the phase's
headline governance test:

```
TRUNCATE location_geometry_projection;
aegis projections rebuild
→ the table is byte-identical to what it was
```

Nothing else in the system may write to it. The exit criterion "no canonical
mutable geometry/precision column exists" is asserted by this test plus a schema
sweep: no table outside the projection carries a `geometry` type, and
`aegis/store/models.py` declares no geometry column on `entity`.

### 6.3 Interval sets, never min/max (the B-12 discipline, applied early)

Wherever an event's time is presented — timeline, map popup, object view — it is
presented as **the set of asserted intervals with their sources**, exactly as
`rebuild_edge_projection` already segments `_intervals` rather than taking
`min(valid_from), max(valid_to)`.

Where a single span is needed to *filter* (a bbox-and-time query), the query
computes it inline and it is never returned in a response field a screen could
render. Any such derived bound that must be materialised is named
`filter_earliest`/`filter_latest`, and the naming is the documentation.

---

## 7. Authorization and map privacy (M-18)

### 7.1 The map is not a side door

Every geo route composes `claim_filters` — the same clearance, handling-code,
case-membership, retraction and as-of predicates that gate every other read —
and applies them in **candidate generation**, not after hydration. The authz
matrix (spec 06) is extended with each geo route, and the P4 sweep in
`tests/component/test_no_anonymous_surface.py` walks them like everything else.

### 7.2 Generalization is a recorded claim, never a runtime blur

GOAL.md §16.5 asks that a low-authority viewer see "country instead of exact
address". Phase 5 delivers that **without the server ever computing a degraded
geometry.**

A location may carry more than one geometry claim at different handling codes:

| Claim | Handling | Source |
|---|---|---|
| `has_geometry` — the building polygon, `site`, `address_match` | `sensitive` | the surveillance log |
| `has_geometry` — the district polygon, `subdivision`, `admin_unit_boundary` | `open` | the press report that named the district |

A `sensitive`-cleared analyst sees both and the map draws the finest. An
`open`-cleared analyst's filter removes the first row, and the map draws the
district — **the authorized generalization, arrived at by the ordinary filter.**

This is better than runtime blurring in three ways that matter here. The coarse
geometry has its **own source and its own grading**, because in practice it
comes from a different, more public document — so Article I holds rather than
being worked around. Nothing is synthesized, so no viewer is ever shown a shape
no source asserted. And the mechanism is `claim_filters`, which is already the
most-tested code path in the system.

**The operational rule** (for the runbook and the review queue): when a
location's exact geometry is handled above `open`, record the public coarse
geometry too. An unrecorded generalization is not a privacy failure — it is
simply a location the low-clearance viewer cannot place, which §7.3 handles
honestly.

### 7.3 What a viewer without permitted geometry sees

The location is returned with `geometry: null` and a `geometry_state` of
`none_permitted` (no readable geometry claim), `none_recorded` (no geometry
claim exists at all), or `invalid` (§4.3). It renders **in the location list,
never on the map**, and never at a guessed position.

`none_permitted` and `none_recorded` are distinguished because they are
different facts about the world and the analyst needs both. Whether the
distinction should itself be withheld is a **response-mode** question — omit
versus marked redaction versus counts — and that policy is P7's (H-25). P5
ships the honest default and records the switch point rather than inventing a
policy engine ahead of the phase that owns one.

### 7.4 Counts are computed after filtering

Any count a geo or timeline response returns — participants on an event,
features in a bbox — is computed over rows the caller can already read, which is
the rule spec 09 §6.5 established for the entity-360's case list. A count
computed before filtering is an existence leak wearing a number.

---

## 8. Serving (H-21, ADR-049)

### 8.1 GeoJSON, not vector tiles

| | Vector tiles (Martin or hand-built) | Authorized GeoJSON |
|---|---|---|
| Cache key | z/x/y — shared across viewers | none; every response is authorized |
| To be correct here | key the cache by (clearance × case set × as-of × handling), i.e. a cache of one | — |
| Failure mode | a mis-keyed cache serves sensitive geometry to the wrong viewer, silently | a filter bug, caught by the same authz matrix as every other route |
| Auto-publish | Martin's headline feature; H-21 forbids it for canonical tables | not a concept |
| Scale it is for | millions of features | this corpus: hundreds |

The trade is not close at this size, and the risk is asymmetric. **Trigger to
revisit** (roadmap trigger-table discipline): a bbox query returning > 5 000
features, or p95 > 500 ms over the real corpus. Then Martin is evaluated against
a **private per-authorization cache**, never a shared one.

### 8.2 Routes

All authenticated, case- and clearance-filtered, cursor-paginated, and returning
the as-of stamp `{as_of, identity_revision_id, ontology_version}` that P4
established.

| Route | Returns |
|---|---|
| `GET /v1/geo/locations` | GeoJSON `FeatureCollection`, one Feature per readable place. Properties: `entity_id`, `label`, `entity_type`, `admin_level`, `accuracy_m`, `derivation`, `geometry_kind`, `geometry_state`, `claim_id`, `handling_code`. Params: `bbox`, `caseId`, `asOf`, `asOfRevision`, `cursor` |
| `GET /v1/geo/events` | GeoJSON `FeatureCollection`, one Feature per readable event with a readable place. Properties add `event_type`, `time_intervals[]` (§6.3), `participant_count` (post-filter, §7.4), `place_id`, `place_role` (`took_place_at`/`travelled_from`/`travelled_to`). Params add `from`, `to`, `eventType` |
| `GET /v1/timeline` | Claim-level timeline items (§11), not GeoJSON. Params: `entityId`, `caseId`, `from`, `to`, `asOf`, `asOfRevision`, `cursor` |

`next_cursor` rides as a foreign member of the `FeatureCollection`, which
RFC 7946 §6.1 permits.

`bbox` is validated as four finite numbers in range; an inverted or malformed
box is a 422, not an empty collection, because an empty map is indistinguishable
from "you may see nothing" and one of those is a lie.

Any route change requires `make openapi` in the same commit — the contract test
fails on drift.

### 8.3 as-of composes from the first commit

The geo routes accept `asOf` and `asOfRevision` and carry the stamp on day one,
closing the geo half of P4's carryover ("`?asOf=` on graph and search"). T62
closes the graph half, because a time-synced map beside a graph that silently
answers as-of-now would be the inconsistency the phase is trying to eliminate.
Search stays with P6.

---

## 9. Rendering (T60)

### 9.1 The mark is chosen from the axes, never from one value

| Condition | Mark |
|---|---|
| `derivation = admin_unit_boundary`, Polygon/MultiPolygon | filled area with a distinct outline |
| `derivation = coverage_area` | hatched area |
| `derivation = admin_unit_centroid` | circle of radius `accuracy_m`, at every zoom |
| `derivation = analyst_estimate` | dashed outline (area) or dashed circle (point) |
| `instrument_fix` / `source_stated_coordinates` / `address_match`, `accuracy_m` ≤ point threshold or null | point mark |
| any of those with `accuracy_m` above the threshold | circle of radius `accuracy_m` |
| `geometry_state ≠ ok` | not drawn; listed with its reason |

### 9.2 There is no bare-pin code path

The point mark is emitted by exactly one branch, guarded by the conditions
above. It is unreachable for any administrative `admin_level`, because §4.3
rule 6 makes such a claim unwritable. The charter's criterion — "a
`country`-level location never renders as a point at any zoom" — is therefore
enforced twice: the store will not hold the claim, and the renderer has no
branch that would draw it.

Asserted in a browser test at three zoom levels, and in a unit test over the
mark-selection function that enumerates the whole `admin_level × derivation`
matrix — the browser proves the wiring, the unit test proves the coverage.

---

## 10. Base map and geocoding governance (M-19)

**No external service is contacted, by default or by accident.**

- **Base map.** The default style declares a plain background layer and the
  workspace's own GeoJSON sources. No basemap tiles ship in the repository
  (large binaries are not committed) and none are fetched. An operator may point
  `AEGIS_MAP_STYLE_URL` at a **self-hosted** style; the setting is unset by
  default, refused outside `dev` unless the origin is same-origin, and any other
  origin requires the CSP change to be made deliberately. Sending a viewport to
  a third party is telling that party which places an investigation is looking
  at.
- **Geocoding is manual or assisted, never automatic.** There is no geocoder
  integration and no address-to-coordinate call. An analyst enters coordinates
  or selects a geometry, and records the `derivation` that says how they got it.
  **No name, identifier, address or selector from any claim may be sent to any
  external geocoding service** — a prohibition, not a default.
- **CSP.** MapLibre GL JS creates its workers from a `blob:` URL by default,
  which `default-src 'self'` denies. The fix is to bundle the worker as a
  same-origin asset (`maplibregl.setWorkerUrl`) rather than to widen the policy.
  If that proves unworkable, `worker-src 'self' blob:` is added with the reason
  recorded — the `script-src 'self'` line does not move either way.
- **Attribution.** Whatever style an operator configures carries its own licence
  and attribution; the map renders the style's `attribution` string verbatim.
  The default style has nothing to attribute because it fetches nothing.

MapLibre GL JS itself is BSD-3, self-hosted from the bundle like every other
dependency, and adds no network egress of its own.

---

## 11. Timeline and the shared time filter

### 11.1 Timeline items are claims

`GET /v1/timeline` returns claim-level items — `{claim_id, subject, predicate,
object, earliest, latest, certainty, record_id, handling_code}` — where
`certainty` is derived from the interval: `exact` (`earliest == latest`),
`bounded` (both set, different), `open` (one set), `undated` (neither).

Events do not get separate timeline items. An event appears through its claims,
which is what makes "no duplicates" (T61's AC) structural rather than a
de-duplication pass: there is only ever one row per assertion.

`bounded` and `open` render visibly differently from `exact` — a range or a
faded edge, never a midpoint. Inventing a midpoint to place a bar is the
false-precision failure the charter's risk table names, in time instead of
space.

### 11.2 One filter, three surfaces

Map, timeline and graph share one time window held in the workspace router state
and passed to every read as `from`/`to`.

**Corrected at T62: "one filter" is one *event-time* filter, and the graph keeps
its validity filter beside it.** This section was written as though the three
surfaces had one time axis between them. They do not. The map and the timeline
filter `event_time_earliest`/`event_time_latest` — when the thing happened — and
the graph's existing `valid_from`/`valid_to` filters `edge_projection.segment_*`,
derived from `claim.valid_from`/`valid_to` — when a relationship was *true*
(ADR-008 has kept those axes apart since P1).

Collapsing them into one control would have produced exactly the failure this
task exists to remove: a single window that meant "was a member during 2019" on
the graph and "an arrest happened in 2019" on the map, so the same slider would
narrow three surfaces to three different things.

So the graph gains `event_from`/`event_to` as a **claim filter** — threaded into
`claim_filters`, so an edge's support summary is computed from the same narrowed
set its visibility is — and keeps `valid_from`/`valid_to` for the different
question it answers. The shared control drives the first. The second remains
available to the graph alone, because it is the only surface with a validity
model to filter.

The window rule itself lives in **one function**, `aegis/queries/window.py`,
which all three surfaces call. That is what makes "nothing renders on one
surface that the filter excludes on another" a property rather than a promise:
there is nothing to keep in step.

**The selection is shared the same way, and for the same reason.** Both the
window and the selected entity live in the **URL** rather than in component
state — three surfaces reading one `useSearchParams` cannot disagree, whereas
three surfaces pushing updates to each other can, on whichever path someone
forgets. It also makes a view a link: an analyst who has narrowed to a fortnight
and selected an incident can send that, and the recipient sees the same thing.

**Membership rule:** a claim is in the window when its asserted interval
**intersects** it. A claim with no event time is **not** in a bounded window and
is surfaced through a separate "undated" affordance with its count — never
silently dropped, and never placed at `recorded_at`, which records when we
learned something and not when it happened.

Because all three surfaces read the same claims through the same filter with the
same rule, "nothing renders on one surface that the filter excludes on another"
(T62's AC) follows from there being one implementation, and the test asserts it
over one seeded claim set.

---

## 12. The ontology change (T55's contract)

**Composition: 1.7.0 → 2.0.0. Major.** One removal makes it major
(`location.precision`, §4.4); the rest is additive. Requires, per spec 08 §7.3:
the proposal file, the history copy `ontology/history/aegis-1.7.0.yaml`, the
composed artifact `composed-1.7.0.json` (already present), and a migration
script — which here is a no-op with a comment, because the removed property was
never claimable and no row carries it. The no-op still ships: spec 01 §4 says a
major bump has a migration, and "there was nothing to migrate" is a statement
the file makes, not one a reader has to reconstruct.

**`platform` 1.3.0 → 1.4.0 (minor).**

```yaml
shared_properties:
  summary:  {type: text, label: Summary}
  geometry: {type: geo,  label: Geometry}

interfaces:
  event: {label: Event, properties: [summary]}
  place: {label: Place, properties: [geometry]}

actions:
  record_event:
    roles: [analyst, investigator]
    audit: true
    parameters:
      event_type:          {type: object_type, required: true}
      record_id:           {type: ref, to: source_record, required: true}
      summary:             {type: text, required: true}
      event_id:            {type: identifier}     # extend an existing event
      label:               {type: text}
      participants:        {type: json, payload_schema: event_participants}
      places:              {type: json, payload_schema: event_places}
      event_time_earliest: {type: timestamp}
      event_time_latest:   {type: timestamp}
      assertion_type:      {type: assertion_type, default: reported}
      excerpt:             {type: text}
      credibility_normalized: {type: grade, dimension: credibility, default: cannot_judge}
      verification_status: {type: grade, dimension: verification, default: unverified}
      handling_code:       {type: handling_code, default: open}
      case_id:             {type: ref, to: case}
    submission_criteria: [actor_holds_action_role, actor_is_case_member, required_text_is_substantive]
    side_effects:
      - refresh_projection: edge_projection
```

*(Corrected at T55: this section first named `location_geometry_projection`
here. `record_event` writes participation and place claims, which are edges;
geometry claims are written through `record_claim`, so the geometry
projection's refresh is declared there, at T56, beside the table it names.)*

`participants` is `[{role: <predicate>, entity_id, mention_id?}]` and `places`
is `[{role: <predicate>, entity_id}]`; both schemas are code-owned and
registered in `PAYLOAD_SCHEMAS`, which is what keeps `json` from becoming an
escape hatch. Every element becomes an ordinary claim through the ordinary
validator, with the action's envelope fields applied to each.

**`criminal_network` 1.2.1 → 2.0.0 (major — the removal).**

```yaml
categories:
  occurrence: {label: Occurrence, color: "#455a64"}
  place:      {label: Place,      color: "#2e7d32"}

object_types:
  meeting:     {implements: [event], properties: {summary: {shared: summary}, notes: {shared: notes}}, display: {title: summary}}
  arrest:      {implements: [event], …}
  travel:      {implements: [event], …}
  observation: {implements: [event], …}
  location:
    implements: [place]
    properties:
      name:     {type: text, required: true}
      geometry: {shared: geometry}
      notes:    {shared: notes}
      # precision: REMOVED (§4.4)

predicates:
  summarized_as:         {subject: [event], object: literal, property: summary, category: occurrence, label: Summary}
  has_participant:       {subject: [event], object: [party], category: occurrence, label: Participant}
  has_attendee:          {subject: [meeting, observation], object: [party], category: occurrence, label: Attendee}
  has_arrestee:          {subject: [arrest], object: [person], category: occurrence, label: Arrestee}
  has_arresting_officer: {subject: [arrest], object: [party], category: occurrence, label: Arresting officer}
  has_traveller:         {subject: [travel], object: [person], category: occurrence, label: Traveller}
  has_observer:          {subject: [observation], object: [party], category: occurrence, label: Observer}
  took_place_at:         {subject: [meeting, arrest, observation], object: [place], category: place, label: Took place at}
  travelled_from:        {subject: [travel], object: [place], category: place, label: Departed from}
  travelled_to:          {subject: [travel], object: [place], category: place, label: Arrived at}
  has_geometry:          {subject: [place], object: literal, property: geometry, category: place, label: Geometry}
```

`has_arrestee` names a role in one sourced, graded, retractable occurrence. It
is not a status about a person, which is what Article II forbids — the same
distinction that already lets `co_arrested_with` ship.

**Also in this bump:** `event_types:` is removed from the DSL and from
`criminal-network.yaml` (§3.1); `property:` is declared on `has_nic`,
`reachable_on` and `registered_as` (§5).

Regeneration covers all four codegen targets, and `ui/src/api/ontology.ts` gains
the new types, predicates, categories and the two code-owned geo vocabularies.

---

## 13. The object view gains inbound claims

`entity_provenance` (`aegis/queries/provenance.py`) selects
`Claim.subject_id.in_(entity_ids)` — **subject only**. With participation claims
subjected to the event, an arrest's page would list its participants and each
participant's page would show no arrest at all: one claim set, two contradictory
pages, which is the opposite of the phase's headline criterion.

`GET /v1/entities/{id}` therefore gains an **inbound** claim set — claims where
the entity is the object — as a separate, additively-named field, resolved
through the canonical map and pinned by `at_revision_id` exactly like the
outbound set, filtered by the same `filters`, and truncated by the same bound.
The object view renders it as a distinct region so a reader can always tell who
asserted what about whom.

This closes a general hole the phase made acute rather than created: an
organization's page has never shown its members (`member_of` points the other
way). The region is generic, so no type-specific code appears.

---

## 14. Test obligations

Each maps to a charter gate criterion or a finding closed here.

| # | Obligation | Layer |
|---|---|---|
| 1 | `TRUNCATE location_geometry_projection` + rebuild reproduces it exactly | integration |
| 2 | No table outside the projection declares a geometry column; `entity` has none | contract |
| 3 | An `arrest` with three participants round-trips: action → object view → `/v1/geo/events` → `/v1/timeline` → graph, from one claim set | integration + e2e |
| 4 | Each of the seven §4.3 rules rejects its malformed value with a 422 naming the field | component |
| 5 | The mark-selection function over the full `admin_level × derivation` matrix emits a point mark only where §9.1 permits | unit |
| 6 | A `country`-level location renders as an area at three zoom levels | e2e |
| 7 | An `open`-cleared viewer of a place with a `sensitive` site geometry and an `open` district geometry receives the district, with no field disclosing the finer one | integration |
| 8 | A place whose only geometry is `sensitive` returns `geometry: null`, `geometry_state: none_permitted`, and appears in no bbox response | integration |
| 9 | Every geo route rejects the anonymous caller and the non-member, byte-identically to a nonexistent id | integration |
| 10 | A travel event suggested from a press report reaches no canonical table until accepted; rejection leaves no trace | integration |
| 11 | Two disjoint asserted intervals for one event render as two intervals, never one span | unit + e2e |
| 12 | An undated claim is excluded from a bounded window on all three surfaces and appears in the undated affordance on each | integration + e2e |
| 13 | A geometry that fails `ST_IsValid` projects with `is_valid = false` and is served with its reason, unrepaired | integration |
| 14 | Adding an event type to the second-domain fixture yields a working object view and map feature with no code change | contract |
| 15 | No file under `aegis/` or `ui/src` names `arrest`, `meeting`, `travel`, `observation`, `location` or any P5 predicate | contract |

Governance cases carry `@pytest.mark.requirement(...)` and the traceability
matrix is updated in the same commit.

---

## 15. Exclusions

Communications-metadata and financial-event feeds (GOAL.md §14–15 — the model
must not preclude them, and §3.2's structural rules mean a future module adds
them by declaring types and predicates). Movement-correlation analytics and
route inference (P6+). Real-time feeds (the Kafka trigger is untouched).
deck.gl and heavy layers (P9 trigger). Automatic geocoding (§10). Occurrence
deduplication / event entity resolution (§3.5). Vector tiles (§8.1). Automatic
pairwise derivation from events (§2.3). Response-mode policy for withheld
geometry (§7.3 — P7, H-25). Compartments and sealing (P7).

---

## 16. Carryover dispositions (Phase 4 exit review)

| Carryover | Disposition |
|---|---|
| `?asOf=` on graph and search | **Geo routes: closed at T59** (§8.3). **Graph: closed at T62** — `as_of` and `as_of_revision` on `POST /v1/graph/expand`, threaded through `claim_filters` like every other read, with a revision above the head a 422 rather than clamped. **Search: stays with P6** |
| Claims picker for hypothesis links | Unchanged — P6, with object sets |
| Audit console | Unchanged — P7 (ADR-045) |
| `hypothesis`/`investigation_task` FGA types declared but not queried | Unchanged — P7 |
| FGA object-type stub codegen | Unchanged — P7. P5 declares no FGA relation on a domain type; event and place reads are gated by handling code and case membership, which are claim-level and need no FGA type |
| Python SDK | Unchanged — P8 |
| Functions execution + side-effect outbox | **Stays open, and P5 does not need it.** *(Corrected at T56: no `refresh_projection: location_geometry_projection` declaration was added. Nothing executes side effects — spec 08 §6.5 — and projections are rebuilt by `aegis projections rebuild` and `POST /v1/projections/rebuild`, never inline on a claim write, so the declaration would have been inert twice over and cost a second ontology bump inside one phase. It arrives with the outbox that would honour it.)* The first consumer that genuinely needs execution is P6's derived findings |
| Pilot gate | Unchanged and untouched. P5 adds no listener, and §10's refusal to contact any external service means it adds no egress either |
