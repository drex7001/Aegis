# 005 — display labels where humanization reads wrong

- **Bump**: `1.6.0` → `1.6.1` (`patch`)
- **Modules**: `platform` `1.2.0` → `1.2.1`, `criminal_network` `1.2.0` → `1.2.1`
- **Task / ADR**: T42 / ADR-043

The first `patch` bump. Spec 01 §4 classes display hints as a patch, and this
is exactly that: three labels, no name added, removed or retyped. Every claim
stamped `1.6.0` means precisely what it meant.

## Motivation

ADR-043 makes the generated TypeScript module the object-view descriptor, and
a generic screen needs a human label for every property and predicate. Declaring
a label for all 5 object types, 27 properties and 34 predicates would be 66
strings to keep in step with names they mostly repeat, so the generator
humanizes the name by default — `date_of_birth` → "Date of birth",
`affiliated_with` → "Affiliated with".

Four names read wrongly, and each one wrongly for a different reason:

| Name | Before | Declared | Why |
|---|---|---|---|
| `person.nic` | "Nic" | **NIC** | An initialism. Sentence-casing an acronym produces a word that is not the acronym |
| `phone_number.number` | "Registered identifier" | **Number** | It resolves `shared: registered_identifier`, whose own label is right for the shape and wrong for this use of it |
| `has_nic` | "Has nic" | **Has NIC** | Same initialism, in a predicate |
| `shared_properties.alias` | "Alias" | **Aliases** | The definition is `many: true`; "Alias" over a list of three is wrong everywhere it appears, so the fix belongs on the shared definition rather than on each reference |

The middle row is the interesting one, and it is why the label resolves in the
opposite direction from every other shared-property field. `type`, `many` and
`sensitivity` are **shared-wins**: a domain module must not be able to weaken a
platform definition, and that is the governance property the whole shared-property
mechanism exists to hold. A label weakens nothing, so the *reference* wins —
which is what lets one `registered_identifier` be a NIC on a person and a number
on a phone without either being wrong.

## Competency questions

Not applicable — no vocabulary changed. The equivalent question for a display
change is: *does any recorded row read differently after this?* No. Labels are
consumed only by generated client constants; no query, filter, projection or
authorization decision reads them.

## Diff

```yaml
# ontology/modules/criminal-network.yaml
object_types:
  person:
    properties:
      nic: {shared: registered_identifier, label: NIC}
  phone_number:
    properties:
      number: {shared: registered_identifier, required: true, label: Number}

predicates:
  has_nic: {subject: [person], object: literal, identifier: true, label: Has NIC}
```

`PropertySpec` and `PredicateSpec` gain an optional `label`. Both fields already
existed on `SharedPropertySpec` and `CategorySpec`; until now the shared one was
declared and read by nothing.

## Compatibility

`patch`. The composed-artifact diff reports zero additive and zero breaking
changes: `aegis ontology check-release` compares vocabulary names, property
types, sensitivities, handling codes and source types, and a label is none of
those. The bump exists so the artifact chain records that the descriptors the
workspace compiles against changed — a bundle built before this proposal renders
"Nic" and should be able to notice it is stale (spec 09 §6.3).

## Migration

None. No row is read, rewritten or reinterpreted: labels are consumed only by
the generated client constants, and no query, filter, projection or
authorization decision reads them. `ontology/history/composed-1.6.0.json` stays
where it is — a `patch` keeps the chain, it does not archive a superseded
vocabulary, because no vocabulary was superseded.

The one visible effect is on a workspace bundle built before this change: it
renders "Nic" and "Alias" until it is rebuilt. That is what the bundle/server
version banner (spec 09 §6.3) exists to surface, and this is the first bump it
would report.

## Ethics

`person.nic` is omitted for real people by the rubric in `data/real/README.md`
and appears only in fictional fixtures. Labelling the field changes nothing
about that: this proposal makes the name render correctly where it is already
allowed to appear, and grants no new place for it to appear.
