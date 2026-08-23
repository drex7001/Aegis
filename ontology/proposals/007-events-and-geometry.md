# 007 — Occurrences and geometry: events as object types, one geometry claim with four fields

- **Bump**: `1.7.0` → `2.0.0` (`major`)
- **Modules**: `platform` `1.3.0` → `1.4.0` (minor) · `criminal_network`
  `1.2.1` → `2.0.0` (major)
- **Task / ADR**: T55 · ADR-046, ADR-047, ADR-048 · spec 10
- **Amended at T57, before release**: `record_event.participants` and `.places`
  gained `many: true`. They were always lists of role references — the
  declaration said `json` and the generated model produced `dict[str, Any]`,
  which no caller could have satisfied. Corrected in **2.0.0 itself** rather
  than as a 2.0.1, because 2.0.0 has never been merged to `master`, never
  tagged, and no claim outside the authoring branch stamps it: there is nothing
  to reinterpret, which is the only thing the version discipline protects
  (ADR-013). Recorded here rather than fixed silently, because "the version
  was not released yet" is exactly the reasoning that erodes a gate if it is
  used without being written down.

The first **major** bump since `1.0.0` removed `merged_into`, and the first one
to run forwards: `1.0.0`'s proposal was backfilled, this one is written before
the change merges.

## Motivation

Three things the ontology cannot currently express, and one it expresses wrongly.

**It cannot say an occurrence happened.** An arrest naming four people has to be
recorded as six `co_arrested_with` claims between pairs. Nothing holds the
arrest itself, so nothing can carry its time, its place, its handling code, or
the fact that two sources describe *the same arrest* differently. Learning of a
fifth arrestee silently changes what the six existing claims mean. The
occurrence has identity — you can ask "which arrest?" and get a different answer
than "which pair?" — and the ontology has no way to give it one (spec 10 §2.1).

**It cannot say what role someone played.** Arrestee and arresting officer are
not the same relationship, and a symmetric pairwise predicate flattens them into
one.

**It cannot say where anything is.** `location` has a name and nothing else.
There is no geometry, so there is no map.

And the field that was *supposed* to become the map's precision model says three
incompatible things at once. `location.precision` is a free text property
commented `exact | centroid | area | city | country`: `exact` is a statement
about *epistemic* confidence, `centroid` and `area` about *geometric
representation*, and `city` and `country` about *administrative* granularity.
No consumer can reason about any of the three, and a renderer reading it has to
guess which question it is answering (H-21). It has also never been claimable —
properties are claim-derived and no predicate carried it — so nothing was ever
recorded under it.

## Competency questions (GOAL.md §7.9)

1. Which arrest was this, who else was in it, and what role did each person
   play?
2. Do two sources describe the same arrest differently — and where exactly do
   they disagree: the time, the place, or who was there?
3. Where did this meeting happen, how precisely do we know that, and how did we
   come to know it?
4. Which of these locations is a district boundary and which is a building, so
   that neither is drawn as the other?
5. What did this person travel — from where, to where, and when?
6. What can a viewer with `open` clearance be shown about a `sensitive`
   location, without inventing a position no source asserted?
7. Which occurrences fall inside this time window, and which claims about them
   carry no time at all?

## Diff

### `platform` 1.3.0 → 1.4.0 (minor — additive)

```yaml
shared_properties:
  summary:  {type: text, label: Summary}     # what a source says happened
  geometry: {type: geo,  label: Geometry}    # the `geo` slot P3 added, first use

interfaces:
  event: {label: Event, properties: [summary]}
  place: {label: Place, properties: [geometry]}

actions:
  record_event:                              # declared here; handler lands at T57
    roles: [analyst, investigator]
    audit: true
    parameters:
      event_type: {type: object_type, required: true}
      record_id:  {type: ref, to: source_record, required: true}
      summary:    {type: text, required: true}
      event_id:   {type: identifier}                                   # extend an occurrence
      label:      {type: text}
      participants: {type: json, payload_schema: event_participants}
      places:       {type: json, payload_schema: event_places}
      event_time_earliest: {type: timestamp}
      event_time_latest:   {type: timestamp}
      assertion_type: {type: assertion_type, default: reported}
      excerpt:        {type: text}
      credibility_normalized: {type: grade, dimension: credibility, default: cannot_judge}
      verification_status:    {type: grade, dimension: verification, default: unverified}
      analytic_confidence:    {type: grade, dimension: analytic_confidence}
      handling_code:  {type: handling_code, default: open}
      case_id:        {type: ref, to: case}
    submission_criteria: [actor_holds_action_role, actor_is_case_member, required_text_is_substantive]
    side_effects:
      - refresh_projection: edge_projection
```

### `criminal_network` 1.2.1 → 2.0.0 (major — one removal)

```yaml
categories:
  occurrence: {label: Occurrence, color: "#455a64"}
  geospatial: {label: Geospatial, color: "#2e7d32"}

object_types:
  meeting:     {label: Meeting,     implements: [event], properties: {summary: {shared: summary}, notes: {shared: notes}}, display: {title: summary}}
  arrest:      {label: Arrest,      implements: [event], …}
  travel:      {label: Travel,      implements: [event], …}
  observation: {label: Observation, implements: [event], …}

  location:
    implements: [place]
    properties:
      name:     {type: text, required: true}
      geometry: {shared: geometry}          # added
      notes:    {shared: notes}             # added
    # precision: {type: text}               # REMOVED — this is what makes the bump major

predicates:
  summarized_as:         {subject: [event], object: literal, property: summary, category: occurrence, label: Summary}
  has_participant:       {subject: [event], object: [party], category: occurrence, label: Participant}
  has_attendee:          {subject: [meeting, observation], object: [party], category: occurrence, label: Attendee}
  has_arrestee:          {subject: [arrest], object: [person], category: occurrence, label: Arrestee}
  has_arresting_officer: {subject: [arrest], object: [party], category: occurrence, label: Arresting officer}
  has_traveller:         {subject: [travel], object: [person], category: occurrence, label: Traveller}
  has_observer:          {subject: [observation], object: [party], category: occurrence, label: Observer}
  took_place_at:         {subject: [meeting, arrest, observation], object: [place], category: geospatial, label: Took place at}
  travelled_from:        {subject: [travel], object: [place], category: geospatial, label: Departed from}
  travelled_to:          {subject: [travel], object: [place], category: geospatial, label: Arrived at}
  has_geometry:          {subject: [place], object: literal, property: geometry, category: geospatial, label: Geometry}

  # `property:` declared on the three predicates that already worked by name
  # coincidence, so the correspondence is a statement (ADR-047):
  has_nic:       {…, property: nic}
  registered_as: {…, property: registration}
  reachable_on:  {…, property: number}

# event_types: {}    # REMOVED with the DSL section it named
```

### Three DSL changes that ship with it

- **`PredicateSpec.property`** — optional; loader rule 15 requires the named
  property to exist on every expanded subject type and the predicate to allow a
  literal object (ADR-047).
- **`event_types`** removed from the DSL, `modules.NAME_KEYED_SECTIONS` and
  `release.VOCABULARY_SECTIONS`. It was reserved in P0, never populated, and an
  occurrence needs identity, display, claims, provenance and an object view —
  everything an object type already has (spec 10 §3.1).
- **`GEO_ADMIN_LEVELS` / `GEO_DERIVATIONS`** registered in
  `aegis/ontology/registries.py`, code-owned beside `SUBMISSION_CRITERIA` for
  the same reason: the validator and the renderer must implement each value, so
  a value that could be declared before it could be honoured would be a promise
  nothing keeps (H-13). Exported to the workspace by the generator.

## Why the roles are predicates and the geometry is one claim

**Roles.** One predicate per role rather than a `role` column on a participation
table. An undeclared role is then an undeclared predicate, rejected by the claim
validator that has existed since P1; a role that only fits one kind of
occurrence says so in its subject list; and each participation carries its own
source, grading, time and handling code because it *is* a claim, so two sources
naming different participants disagree visibly instead of merging into a list
(ADR-046).

**Geometry.** H-21 requires geometry, uncertainty, administrative granularity
and derivation to be modelled *separately*. It does not require them to be
*asserted* separately, and they must not be: an accuracy radius without its
geometry means nothing, and four independent claims could disagree in ways that
have no interpretation. One claim, four fields, one source, one grading
(ADR-048).

The geometry type is derived from the geometry itself and is never asserted —
it is not a fifth axis, it is a fact about the value.

## Compatibility

**`major`, and the reason is one line: `location.precision` is removed.**

Everything else in this bump is additive — four object types, two interfaces,
two shared properties, two categories, eleven predicates, one action, one
optional predicate field. No name is renamed, no property is retyped, no
handling code moves, and no existing predicate changes its subject or object.

Removal is major under spec 01 §4 **regardless of row counts**. The precedent is
`1.0.0`, which removed `merged_into` and recorded "No rows existed: nothing ever
wrote it" while still taking the major bump and shipping the migration. The
alternative — keeping a dead property that means the wrong thing, so the bump
can be called minor — is how a schema accumulates fields nobody dares delete.

`location` also gains `geometry` and `notes`, and `implements: [place]`. Both
property additions are additive; `implements` is a new declaration on an
existing type and removes nothing.

`event_types` disappearing from the composed artifact is not a vocabulary
removal: the section was empty in every released version, so no key is lost.

## Migration

**`migrations/versions/0011_ontology_v2_vocabulary_check.py`** — and it is a
*check*, not a rewrite, because there is nothing to rewrite.

`location.precision` was a property. Properties are claim-derived (spec 09
§6.4): no column stores one, and no predicate carried this one, so no row in any
table references it. A migration that "migrated precision" would have nothing to
read and nothing to write.

What the migration does instead is prove that assumption on **every** database
it runs against, rather than only on the one it was written on. It reads the
distinct `claim.predicate` and `entity.entity_type` values actually recorded and
fails the upgrade, naming them, if any is absent from the 2.0.0 registry. If a
deployment somewhere did record vocabulary this bump removes, the upgrade stops
instead of silently orphaning it — which is the failure ADR-013 says is
unrecoverable, because claims are immutable and cannot be reinterpreted later.

**What a claim stamped `1.7.0` means afterwards:** exactly what it meant before.
Its predicate and entity types all still exist in 2.0.0, and the composition
version it stamps resolves to `ontology/history/2.0.0/` — the module sources
archived unchanged by this bump — plus `composed-1.7.0.json` for the resolved
form.
