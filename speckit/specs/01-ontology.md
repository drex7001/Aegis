# Spec 01 — Ontology DSL

Status: draft for Phase 1 · Owner: analyst · Constitutional basis: Article XI

## 1. Purpose

`ontology/aegis.yaml` is the single declarative artifact defining the domain. It is to
Aegis what Palantir's Ontology is to Foundry: object types, properties, link
predicates, actions — shared by pipeline, API, authorization, and UI. Code consumes
the ontology through `aegis.ontology`; nothing re-declares domain types by hand.

## 2. Top-level structure

```yaml
version: <semver>          # bump on any change; breaking rules below
namespace: aegis.lk
handling_codes: [...]      # ordered, low → high
grading: {...}             # schemes + normalization maps
source_types: [...]        # closed list for source.source_type
categories: {...}          # predicate categories (generalizes LayerType)
object_types: {...}
predicates: {...}
event_types: {...}         # Phase 4
actions: {...}
```

## 3. Sections

### 3.1 `handling_codes`
Ordered list; index = clearance level required. Phase 1:
`[open, restricted, sensitive]`. Compartments are *not* handling codes — they are FGA
relations (specs/03).

### 3.2 `grading`
Declares the internal normalized scales and maps external schemes onto them
(GOAL.md §1.2 — preserve original, normalize internally):

```yaml
grading:
  reliability:            # of the source
    normalized: [reliable, generally_reliable, unknown, unreliable]
  credibility:            # of the information
    normalized: [confirmed, probably_true, possibly_true, doubtful, improbable, cannot_judge]
  verification: [unverified, partially_corroborated, corroborated, record_confirmed, refuted]
  analytic_confidence: [low, moderate, high]
  schemes:
    admiralty:                  # example external scheme, extensible
      A: {reliability: reliable}
      B: {reliability: generally_reliable}
      F: {reliability: unknown}
```

`schemes` holds external grading vocabularies that sources will **keep using**.
Migration-era vocabularies (e.g. the prototype's `EXTRACTED/INFERRED/AMBIGUOUS`
ConfidenceTag) are not ontology schemes — they live in the migration adapter
(specs/02 §6, ADR-016) and are consumed once.

### 3.3 `categories`
Groups predicates for display and filtering. Each category may declare UI hints:

```yaml
categories:
  ideological:        {color: "#7c4dff"}
  financial:          {color: "#00897b"}
  prison_co_location: {color: "#ef6c00"}
  transnational:      {color: "#3949ab"}
  kinship:            {color: "#6d4c41"}
  # extensible without code: communication, logistics, ...
```

### 3.4 `object_types`
```yaml
object_types:
  person:
    label: Person
    properties:
      name:          {type: text, required: true}
      aliases:       {type: text, many: true}
      nic:           {type: identifier, sensitivity: restricted}
      date_of_birth: {type: date, conflicts: preserve}   # two DOBs may coexist (Rule 5)
    display: {title: name, subtitle: aliases}
```
- `type` ∈ text | identifier | date | timestamp | int | decimal | geo (Phase 4) | ref.
- `sensitivity` names a handling code — property-level minimum, enforced in row/field
  filters.
- `conflicts: preserve` marks properties where contradictory claims are expected and
  must both survive (Article VIII).
- **Properties are stored as claims** (predicate `has_<prop>` auto-derived); the
  ontology entry defines validation + display, not a column.

### 3.5 `predicates`
```yaml
predicates:
  transferred_funds_to:
    subject: [person, organization]
    object:  [person, organization]
    category: financial
    symmetric: false
  co_located_with:
    subject: [person]
    object:  [person]
    category: prison_co_location
    symmetric: true
    computed: true        # produced by rules (remand-window overlap), still claim-backed
  known_as:
    subject: [person, organization]
    object: literal       # object_value, not an entity ref
```
Validator enforces: subject/object types exist; symmetric predicates are stored in
canonical order (lower entity id first) to dedupe.

### 3.6 `actions`
Write-back functions with validation and audit — the part of an ontology "people
miss" (Claude's note). Declares who may run it and what it must validate; the
implementation lives in `aegis/actions/`.

```yaml
actions:
  record_claim:        {roles: [analyst, investigator], audit: true}
  review_suggestion:   {roles: [analyst], audit: true}
  adjudicate_identity: {roles: [analyst], audit: true, dual_control_for: [protected_person]}
  register_evidence:   {roles: [analyst, investigator], audit: true}
  transfer_custody:    {roles: [evidence_officer, analyst], audit: true}
  seal_record:         {roles: [supervisor], audit: true}     # Phase 6
```
`audit: true` is currently mandatory for all actions; the key exists so the validator
can *reject* any action declared without it.

## 4. Versioning rules

- **Patch**: display hints, docs.
- **Minor**: additive — new types, predicates, grading schemes, categories.
- **Major**: renames/removals/retyping. Requires a data migration script shipped in
  the same change, and the previous ontology version kept in `ontology/history/`.
- Claims store the ontology version current at `recorded_at`; the loader must be able
  to interpret all historical versions (or a migration must have upgraded the rows).

## 5. Codegen targets (`aegis ontology generate`)

| Target | Output | Used by |
|---|---|---|
| Pydantic validators | `aegis/ontology/_generated/models.py` | actions, API bodies |
| FGA object-type stubs | `infra/fga/_generated.fga` fragment | authz model review |
| UI descriptors | `aegis/api/_generated/ui_meta.json` | generic entity screens (Phase 3) |

Generated files are committed; CI fails if regeneration produces a diff (ontology and
code drifted).

DB constraints are deliberately **not** a codegen target (ADR-013): vocabulary columns
stay TEXT and are validated at write time by the actions layer against this registry.
Ontology changes never trigger DDL, and claims recorded under earlier ontology versions
remain valid rows.

## 6. Validation rules (loader)

1. Unique names across object_types/predicates/actions.
2. Every predicate subject/object type declared (or `literal`).
3. Every `category`, `sensitivity`, grading value referenced exists.
4. Handling codes strictly ordered, unique.
5. Every action declares `roles` and `audit: true`.
6. Scheme maps target only declared normalized values.
7. Version present and ≥ previous committed version (CI compares).
