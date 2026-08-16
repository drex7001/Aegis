# NNN — <short title>

- **Bump**: `<from>` → `<to>` (`major` | `minor` | `patch`)
- **Modules**: `<module>` `<from>` → `<to>`
- **Task / ADR**: `<T-number>`, `<ADR-number>` if one was needed

## Motivation

What the ontology cannot currently express, and what goes wrong because of it.
Write the *problem*, not the change — if the motivation only makes sense once
the diff is read, the change probably belongs somewhere else.

## Competency questions (GOAL.md §7.9)

The questions this change makes answerable, phrased the way an analyst would
ask them. A change that answers no new question is a rename.

1. …
2. …

## Diff

```yaml
# the YAML as it changes, module by module
```

## Compatibility

Why the declared class is right. For `minor`/`patch`, name what was *not*
removed, renamed or retyped — the CI diff checks this, and this section is
where a reader learns whether the check was trusted or reasoned about.

## Migration

Required for `major`. The script, what it touches, and what a claim recorded
under the previous version means afterwards (ADR-013 — claims are immutable, so
"reinterpret" is not an option).

Not applicable for additive changes; say so explicitly rather than leaving the
heading empty.
