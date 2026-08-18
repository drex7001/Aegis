# 006 — the investigation's operational plane: cases, hypotheses, tasks

- **Bump**: `1.6.1` → `1.7.0` (`minor`)
- **Modules**: `platform` `1.2.1` → `1.3.0`
- **Task / ADR**: T43 / ADR-044, spec 09 §2–§5

Nine actions and one submission criterion. Additive throughout: no existing
action, role, parameter or dual-control rule moved, and no object type,
predicate or category is touched — a domain module sees none of this.

## Motivation

Phase 4 moves work inside access-scoped cases, and H-17 found that the model
underneath had never been specified: hypotheses and tasks had no storage, no
actions and no authorization, and "link a claim to a case" appeared in a charter
without saying what linking meant. Spec 09 §2–§5 defines all of it; this
proposal is the ontology half.

Everything here is **platform** vocabulary, not domain vocabulary. A
`border-cargo` deployment gets the same cases, the same hypotheses and the same
tasks — they are how an investigation is organized, not what it is about — so
they belong in the platform module beside `open_case`, which has been there
since v0.1.0 (Article XIV).

## What is added

| Action | Why it is not something that already exists |
|---|---|
| `close_case` | A case had no way to end. `status` accepted `closed` and nothing could write it |
| `link_case_reference` / `unlink_case_reference` | ADR-044: *referring* to a claim is not *re-scoping* it (below) |
| `open_hypothesis` / `revise_hypothesis` | A hypothesis is an assertion about our own reasoning. It has no source record, so it cannot be a claim (Article I requires one) |
| `link_hypothesis_claim` / `unlink_hypothesis_claim` | The evidence basis, with a stance. `link_claims` relates two claims to each other, which is a different relation |
| `open_task` / `update_task` | Tasks and leads. One action pair, no transition graph — plan §2's workflow-engine trigger stays untouched |

And one criterion, `required_text_is_substantive` (spec 09 §3.3).

## Competency questions (GOAL.md §7.9)

1. What does this investigation currently believe, and what would change its
   mind?
2. Which recorded claims support this hypothesis, and which contradict it —
   including a claim an analyst linked under both?
3. What did this hypothesis say before it was revised, and who revised it?
4. What is left to do on this case, who owns it, and what has stalled?
5. Which claims, entities and evidence items does this investigation refer to —
   as distinct from which ones were *recorded into* it?

Question 5 is the one that needed a decision rather than a table.

## The decision behind the reference actions (ADR-044)

`claim.case_id` is an **access predicate**: `aegis/authz/filters.py` admits a
claim when it is null or the reader is a member of that case. So "link a claim
to a case", read as assigning `case_id`, would widen or narrow who can read a
recorded claim — a governance event with no audit story, performed by an
ordinary analyst, on an append-only row.

So there are two concepts. `case_id` is the immutable **recording scope**, set
once and never reassigned. A **case reference** is a link that grants nothing:
reference lists are built from targets the caller can already read, so a
reference to something invisible is simply absent. Because the operation is
powerless, its authorization is cheap — an ordinary case-scoped write rather
than a privileged one.

## The fourth submission criterion

GOAL.md §18 requires a hypothesis to state what would change it. `required: true`
rejects an **absent** field; it does not reject `""` or `"   "`, because both
are strings — so the rule with the strongest reason to exist was the one with no
mechanism behind it.

`required_text_is_substantive` reads the action's own declaration and refuses
any `{type: text, required: true}` parameter that is only whitespace. Declared
per action, so no Phase 1–3 write changes behaviour, and self-extending: an
action that later gains a required text parameter is covered without editing the
predicate. The refusal is an audited denial (spec 08 §6.4), and
`hypothesis_revision` carries the same rule as a CHECK constraint, because a
governance rule enforced in exactly one layer is a governance rule with a
bypass.

## Diff

```yaml
# ontology/modules/platform.yaml — actions:
close_case:              {case_id, reason}
link_case_reference:     {case_id, target_type, target_id, note}
unlink_case_reference:   {case_id, target_type, target_id, reason}
open_hypothesis:         {case_id, statement, missing_info, hypothesis_id, handling_code}
revise_hypothesis:       {hypothesis_id, note, statement, status, missing_info}
link_hypothesis_claim:   {hypothesis_id, claim_id, stance, note}
unlink_hypothesis_claim: {hypothesis_id, claim_id, stance, reason}
open_task:               {case_id, title, kind, detail, owner, due_date, hypothesis_id, task_id}
update_task:             {task_id, status, owner, due_date, detail, note}
```

`REF_TARGETS` gains `hypothesis` and `investigation_task`, and
`SUBMISSION_CRITERIA` gains `required_text_is_substantive` — all three are
code-owned allowlists the ontology may only select from (spec 08 §6.3), so the
declaration above could not have been written before the implementation existed.

## Compatibility

`minor`. The composed-artifact diff reports nine additive changes and zero
breaking ones. Nothing is removed, renamed or retyped, and no recorded row is
reinterpreted: a claim stamped `1.6.1` was recorded under a claim envelope this
proposal does not touch.

## Migration

Schema migration `0010_investigation_model` creates the five tables the actions
write. It is additive — no existing table is altered, and `downgrade()` drops
them in reverse dependency order.

No data migration: there is nothing to convert, because none of this existed.

## Ethics

Hypotheses are the one place in Aegis where a person writes down what they
suspect, so three properties are structural rather than advisory:

- A hypothesis is **never** a claim and is **never** projected. It carries no
  grading and no source record, and no graph renders it — a suspicion must not
  be able to become an edge by accident (Article IX, spec 09 §9).
- Both sides are stored and both sides render. `stance` admits the same claim as
  supporting *and* contradicting, and the API returns both arrays always, empty
  or not (Article VIII).
- The missing-information note is required and must say something, which is the
  mechanical form of "what would change your mind".

Fictional fixtures only: no hypothesis about a real person is written in this
repository (`data/real/README.md`).
