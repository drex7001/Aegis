# 003 — Action parameters, submission criteria, side-effect declarations

- **Bump**: `1.4.0` → `1.5.0` (`minor`)
- **Modules**: `platform` `1.1.0` → `1.2.0`
- **Task / ADR**: T34, ADR-040

> Backfilled by T35, the last of the three retrospective proposals. The change
> landed at T34; every bump from `1.5.0` onwards is proposed before it merges.

## Motivation

The ontology declared `roles` for thirteen actions and the actions layer
enforced them for one. Every call except `adjudicate_identity` passed no
`ActionContext`, and an empty role set was read as "not supplied", so twelve
declarations were documentation. Worse, the layer could not record a refusal at
all: `ActionService._audit` wrote `decision="allow"` unconditionally and
`_require_action` raised before any row existed.

Separately, nothing described what a caller may *send* to an action. The claim
envelope lived in a hand-written `ClaimIn` beside the route, which meant a
domain module could not be prevented from widening it — because nothing said
what it was.

## Competency questions (GOAL.md §7.9)

1. What may a caller send to `record_claim`, and what happens to an undeclared
   field?
2. Which checks run before a write, and where is each one implemented?
3. When a write is refused, who refused it, why, and is that reviewable?
4. Can a domain module widen the claim envelope? (No — `record_claim` is
   declared in `platform`.)
5. What does this action do after it commits? (Declared; nothing runs it yet.)

## Diff

```yaml
# ontology/modules/platform.yaml
actions:
  record_claim:
    roles: [analyst, investigator]
    audit: true
    parameters:            # all 27 claim-envelope fields (spec 02)
      predicate: {type: predicate, required: true}
      record_id: {type: ref, to: source_record, required: true}
      assertion_type: {type: assertion_type, default: reported}
      handling_code: {type: handling_code, default: open}
      # ...
    submission_criteria: [actor_holds_action_role, actor_is_case_member]
    side_effects:
      - refresh_projection: edge_projection
  # ...twelve more, each with parameters and at least one criterion
```

## Compatibility

`minor`. No action, role, or `dual_control_for` rule changed; the parameters
describe a request contract that already existed in Python, and the criteria
restate policy already enforced — two of them at the API layer, one already in
`_require_action`.

The composition bumps because a module did (spec 08 §7.4). That is not
bookkeeping: a claim recorded before this change and one recorded after were
written under different action contracts, and stamping both `1.4.0` would make
them indistinguishable.

`side_effects` are declared and **stored, not executed** (spec 08 §6.5). A test
asserts nothing in `aegis/actions/` reads them, so a `notify:` here cannot
quietly start sending anything.

## Migration

Not applicable to recorded data. It is a behaviour change for *callers*: every
action call now passes its `ActionContext`, and API routes supply the actor's
roles, so a request that was refused at the route and would have succeeded if
called directly is now refused in both places. System callers — the migration
adapter, the CLI, the fixture loader, the projection rebuilder — hold no roles
and are unaffected by design.
