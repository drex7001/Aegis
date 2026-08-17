# 004 — `controls`: a party controlling an organization

- **Bump**: `1.5.0` → `1.6.0` (`minor`)
- **Modules**: `criminal_network` `1.1.0` → `1.2.0`
- **Task / ADR**: T39

The first proposal written **before** its change merges. `001`–`003` were
backfilled by T35 for bumps that had already landed; from here the workflow
runs forwards.

## Motivation

Control is not membership and not ownership of a thing. A person who directs a
haulage company they are not listed as an officer of, or a company that directs
a subsidiary through an arrangement no registry records, is the shape that
matters in enterprise analysis — and there is currently no way to record it.

The nearest existing predicates all say something else. `member_of` says a
person belongs to an organization, not that they direct it.
`founded` is historical and does not survive a handover. `affiliated_with` is
deliberately vague. `successor_leader_of` names a role inside an organization,
which is a different claim from directing it from outside.

The subject is a **party**, not a person: front companies are controlled by
companies at least as often as by named individuals, and forcing an analyst to
choose the wrong subject type would push that structure out of the graph
entirely.

## Competency questions (GOAL.md §7.9)

1. Which organizations does this person or company control, as distinct from
   belonging to or having founded?
2. Who controls this organization, when the registry names someone else?
3. Does control pass through a chain — a party controlling an organization that
   controls another?
4. Which control claims are contested, and by which sources?

## Diff

```yaml
# ontology/modules/criminal-network.yaml
predicates:
  controls: {subject: [party], object: [organization], category: financial}
```

`subject: [party]` is the first use of an interface as a predicate endpoint in
the shipped ontology (spec 08 §4). It expands at load time to `person` and
`organization` — the concrete types a claim records — so nothing downstream
sees an interface, and adding a third `party` implementor would widen this
predicate without touching it.

## Compatibility

`minor`. One name added; nothing removed, renamed or retyped. The interface it
targets already exists and already has implementors, so the expansion is
non-empty (a predicate targeting an unimplemented interface is a validation
error, spec 08 §9 rule 14).

**Not a status.** Article II forbids inherent derogatory status, and control is
neutral: a party controls a lawful company exactly as it controls an unlawful
one. The doubt lives in the claim's grading, not in the predicate's name
(ADR-016).

**Not an inference.** Article IX — control is a claim a source makes, not
something computed from co-occurrence. Nothing derives `controls`, and the
`computed` flag is deliberately absent.

## Migration

Not applicable. Nothing existing changes meaning, and no rows are touched.
