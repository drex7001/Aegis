# 009 — `finding_promotion`: a computation may be *proposed* as an assertion

- **Bump**: `2.1.0` → `2.2.0` (`minor`)
- **Modules**: `platform` `1.5.0` → `1.6.0`
- **Task / ADR**: T74 · ADR-031 (unchanged, extended by one kind) · ADR-057 · spec 12 §10

## Motivation

A betweenness run says a person sits on more recorded paths than anybody else in
the set. That is a **finding**: a machine's reading of what has been written
down, true of the corpus rather than of the world. An analyst who wants to say
*"this person brokers between the two harbour groups"* is asserting something
else — about the world, in their own name, and answerable as such.

Article IX is the line between those two sentences, and today there is no way to
cross it. The finding sits in `analytic_finding` with its manifest and its
caveat; the assertion, if anybody wants to make it, has to be typed by hand into
an unrelated claim that records no connection to the computation it came from.
Both failures are bad in the same direction: the working is lost, so the reader
cannot tell an assessment from an observation.

What is missing is the **review path** — a promotion that a person proposes, a
reviewer accepts or rejects, and that writes nothing canonical in between.
Article VII is not weakened by adding this; it is the reason the kind is needed.
Without it, promoting a finding would mean writing a claim directly from a
computation, which is the one thing no producer may do.

## Competency questions (GOAL.md §7.9)

1. Which analytic findings have been *proposed* as assertions but not yet
   decided?
2. Who proposed this assertion, on what reasoning, from which run — and who
   accepted it?
3. What does canon look like if I reject this promotion? (Unchanged, because
   nothing was written. The finding is not "promoted and then unpromoted" — it
   was never promoted.)
4. Given a claim that reads as an assessment, what computation is it based on,
   at what method version, over which edges?

## Diff

```yaml
# platform 1.5.0 → 1.6.0
actions:
  submit_suggestion:
    parameters:
      suggestion_kind:
        {type: enum,
         values: [claim_draft, identity_candidate, claim_relation, event_draft,
                  finding_promotion],
         default: claim_draft}
```

One enum value. Everything else the task needs is code and schema, not
vocabulary:

- `SUGGESTION_KINDS["finding_promotion"] = "record_claim"` in the actions layer,
  where every kind's dispatch target is declared;
- the widened `ck_review_queue_kind` (migration `0017`);
- `aegis/analytics/promotion.py`, the promotion itself.

No new **result** column, and that is the tell that this kind is well-formed: an
accepted promotion produces exactly one claim, which is one typed result, which
is what `ck_review_queue_accepted_result` already requires.

## Why the kind is code-owned and the enum is declared

Both, for the reason ADR-031 §1 gave and proposal 008 restated: `suggestion_kind`
is a **closed, code-owned list** because each kind is a dispatch branch, and the
enum here is the *public request contract* — what a producer may send. A kind
declared before its branch existed would be a suggestion nobody could accept; a
branch without the declaration would be a kind no caller is permitted to name.

T74 met the second failure the hard way. The dispatch branch and the database
check were built and the enum was not, so the kind existed and no caller could
have named it — caught by `test_every_kind_declares_its_target_action`, which
asserts the two lists agree in both directions. The test working is the reason
this proposal exists rather than a drift nobody noticed.

## Compatibility

**`minor`.** One enum value added to one parameter. No kind removed, no default
changed, no action or role touched. Every suggestion already in a queue keeps its
kind, its target action and its meaning, and a producer that has never heard of
`finding_promotion` is unaffected.

## Migration

Not applicable to recorded data: nothing is removed or retyped, and no existing
row changes.

Migration `0017` is a **schema** change — it widens `ck_review_queue_kind` to
admit the kind, and nothing else. Its downgrade refuses while any promotion row
exists, per the rule migration `0013` set: narrowing a vocabulary that rows
already use would leave suggestions the constraint says cannot exist.
