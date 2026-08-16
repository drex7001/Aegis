# 002 — Shared properties and interfaces

- **Bump**: `1.3.0` → `1.4.0` (`minor`)
- **Modules**: `platform` `1.0.0` → `1.1.0`, `criminal_network` `1.0.0` → `1.1.0`
- **Task / ADR**: T32, ADR-041

> Backfilled by T35 alongside proposal 001. The change landed at T32.

## Motivation

Three properties were declared inline in three places and had to agree by
inspection. `aliases` was `{type: text, many: true}` on both `person` and
`organization`; `nic` and `phone_number.number` were both restricted
identifiers written out separately. Nothing stopped a fourth from arriving at a
*lower* clearance, and nothing said that `person` and `organization` are the
same kind of thing for the purposes of a predicate.

## Competency questions (GOAL.md §7.9)

1. What must be true of every entity a `party` predicate can point at?
2. Where is the one definition of "a state-issued registry identifier", and
   what clearance does it carry everywhere?
3. Which object types carry a registry identifier at all?
4. Can a domain module implement a platform interface without editing the
   platform module? (Yes — ADR-041.)

## Diff

```yaml
# ontology/modules/platform.yaml
shared_properties:
  alias:                 {type: text, many: true, label: Alias}
  registered_identifier: {type: identifier, sensitivity: restricted}
  notes:                 {type: text, label: Notes}

interfaces:
  party:        {label: Party,        properties: [alias]}
  identifiable: {label: Identifiable, properties: [registered_identifier]}
```

```yaml
# ontology/modules/criminal-network.yaml
object_types:
  person:
    implements: [party, identifiable]
    properties:
      aliases: {shared: alias}
      nic:     {shared: registered_identifier}
      notes:   {shared: notes}
  organization:
    implements: [party]
    properties: {aliases: {shared: alias}, notes: {shared: notes}}
  phone_number:
    implements: [identifiable]
    properties: {number: {shared: registered_identifier, required: true}}
```

## Compatibility

`minor`. `party` and `identifiable` are new names; the properties that became
`shared:` references resolve to exactly the type, cardinality and sensitivity
they already carried, and the loader rejects a reference that tries to override
either (spec 08 §9 rule 13).

**One boundary was deliberately not moved.** `vehicle.registration` is a
registry identifier and does *not* adopt `registered_identifier`: the shared
property is `restricted` and the inline one has been `open` since v0.1.0, so
adopting it would raise the clearance needed to read rows already recorded.
That is a handling-policy change and needs its own proposal — putting it here
would have made an additive bump quietly reclassify data.

## Migration

Not applicable. No property changed type or sensitivity, so no recorded value
is read differently.
