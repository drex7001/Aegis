# 008 — `event_draft`: a producer may propose an occurrence

- **Bump**: `2.0.0` → `2.1.0` (`minor`)
- **Modules**: `platform` `1.4.0` → `1.5.0`
- **Task / ADR**: T58 · ADR-031 (unchanged, extended by one kind) · spec 04, spec 10

## Motivation

A press report says three men flew to Chennai on 4 April. Today an extraction
producer can propose the *claims* that would describe that — but there is no
occurrence for them to be claims about, so each one has to name a pair, and the
journey itself is not represented at all. That is exactly the shape spec 10 §2.1
says should be an event.

`record_event` exists (proposal 007) and a human can call it. What is missing is
the **review path**: a producer that proposes an occurrence, a reviewer who
accepts or rejects it, and nothing reaching a canonical table in between.

Article VII is not weakened by adding this — it is the reason the kind is needed.
Without it a travel producer would have exactly two options, and both are worse:
emit pairwise claim drafts that misrepresent the journey, or write the event
directly, which no producer may do.

## Competency questions (GOAL.md §7.9)

1. What travel has been *proposed* from press reporting but not yet accepted?
2. Which producer proposed this occurrence, at what version, from which source
   record — and who accepted it?
3. What does the graph look like if I reject this journey? (Nothing changes,
   because nothing was written.)
4. Which suggestions in the queue are occurrences rather than single claims, so
   a reviewer can see what they are being asked to admit?

## Diff

```yaml
# platform 1.4.0 → 1.5.0
actions:
  submit_suggestion:
    parameters:
      suggestion_kind:
        {type: enum,
         values: [claim_draft, identity_candidate, claim_relation, event_draft],
         default: claim_draft}
```

One enum value. Everything else this task needs is code and schema, not
vocabulary:

- `SUGGESTION_KINDS["event_draft"] = "record_event"` in the actions layer, where
  every kind's dispatch target is declared;
- `review_queue.result_entity_id`, and the widened `ck_review_queue_kind` and
  accepted-result checks (migration 0013);
- `aegis/ingestion/travel.py`, the producer itself.

## Why the kind is code-owned and the enum is declared

Both, and the tension is old (ADR-031 §1). `suggestion_kind` is a **closed,
code-owned list** because each kind is a dispatch branch: a kind that could be
declared before a branch existed would be a suggestion nobody could accept. The
enum in this file is the *public request contract* — what a producer may send —
and it must agree with the code, which
`tests/contract/test_actions_v2.py` already asserts in both directions.

So the value lands here **and** in `SUGGESTION_KINDS`, in one commit, and neither
can drift from the other without a test going red.

## Compatibility

**`minor`.** One enum value added to one parameter. No kind removed, no default
changed, no action or role touched. Every suggestion already in a queue keeps its
kind, its target action and its meaning, and a producer that has never heard of
`event_draft` is unaffected.

The `check-release` diff would call this additive on its own; the class is
declared `minor` because that is what it is, not because the gate insisted.

## Migration

Not applicable to recorded data: nothing is removed or retyped, and no existing
row changes.

Migration `0013` is a **schema** change rather than a data one — it widens the
`ck_review_queue_kind` check to admit the new kind, adds `result_entity_id`, and
extends the accepted-result check so exactly one typed result is still required
across four columns instead of three. The invariant is unchanged; the arity is
not.

`result_entity_id` exists because an accepted `event_draft` produces an
**entity** and several claims. Recording the entity is the honest answer to
"what did accepting this suggestion create" — the claims are reachable from it,
and picking one of them as *the* result would be arbitrary.
