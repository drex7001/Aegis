# Phase 5 — the event-vs-edge migration list, dispositioned (T63)

Date: 2026-08-23 · Task: T63 · Rule: `../specs/10-events-geospatial.md` §2.1 ·
Candidate list: §2.4

Spec 10 §2.4 enumerated **every** predicate in `criminal-network.yaml` against
the event-vs-edge rule and recorded a recommendation for each. T63's job is to
decide them once, with the sources in view, and to say so — the risk-table
discipline the charter asks for.

Nothing on this list is revisited later in the phase. A predicate decided "keep"
here stays a predicate until a future phase declares the event type it would
need.

## The one migration

**`co_arrested_with` → `arrest` events. Migrated.**

It is the single predicate in the shipped ontology that names an occurrence.
"The 4 February arrest in Dubai" is a thing two sources can independently
describe, disagree about, and be corrected on; learning of a third arrestee
extends it rather than changing what the recorded pairs meant. All three of
§2.1's tests hold.

**What the corpus actually contains.** Two claims, and they are two *different*
arrests:

| Report | When | Where | Who |
|---|---|---|---|
| Ada Derana — Madush arrested in Dubai | 2019-02-04 | Dubai, UAE | two people |
| News First — Harak Kata extradited from Madagascar | 2023-03-15 | Madagascar | two people |

The projection snapshot said two edges and the store agrees. Neither is a chain:
each report names two people, so the migration produces two events of two
arrestees each rather than collapsing anything.

**How the transformation is bounded.** `aegis migrate arrests-to-events`, dry by
default — a one-time transformation over a real corpus should have to be asked
for twice, once to see it and once to mean it.

- Grouping is by `(record, event time, location text)`: same report, same day,
  same place. Conservative on purpose. Merging two occurrences that were not the
  same one is an identity decision a machine must not make (Article VII), and
  splitting one that was is a mistake a reviewer fixes by attaching the second
  event's claims to the first with `record_event`.
- Every envelope field travels — record, assertion type, excerpt, all three
  grading dimensions, event time, handling code, case. The test enumerates them
  rather than spot-checking, so a field added to the claim model later fails
  until someone decides whether it travels. `restricted` travels too: the
  migration cannot declassify an incident by moving it.
- The original is **retracted, never deleted**, with a reason naming the event
  it became. An auditor still reads it, and the record says why it stopped being
  the current answer.
- `location_text` travels as **text**. Resolving a source's words to a
  `location` entity is an analyst act with its own grading (spec 02 §9.3);
  doing it here would manufacture geography the report never asserted.
- Every write is audited under the operator, one row per write — not one summary
  row saying a migration happened (Article X).

## Flagged, not migrated: five predicates that name occurrences

These meet §2.1 and are **kept as predicates for Phase 5**, because the event
type each would need is not among the four this phase declares. Inventing a
fifth type to hold them is scope the charter did not fund, and inventing it
*badly* — one `incident` type absorbing five different kinds of occurrence — is
worse than waiting.

| Predicate | Event type it would need | Why it waits |
|---|---|---|
| `masterminded_attack_with` | `attack` | An attack is an occurrence with its own identity, casualties, place and time. It deserves a type designed for it, not an `arrest` with the label changed |
| `co_attacker_with` | `attack` | Same occurrence, same type — and the pair would migrate together or not at all |
| `ordered_killing_of` | `directive` or `incident` | Two occurrences are tangled here: the order and the killing. Which one the claim is about is a modelling question, and answering it wrong is worse than leaving the pair |
| `killed_family_of` | `incident` | Same |
| `tipped_off_police_on` | `directive` | Same |

Recorded here so a future phase inherits a decision rather than re-deriving one.
The rule that applies to them is unchanged; only the vocabulary is missing.

## Kept: everything else

Every remaining predicate fails §2.1, and the reasons are in three groups.

**Explicitly out of scope.** `communicated_with` names an occurrence, and
communications-metadata events are a stated non-goal (GOAL.md §14–15, charter
§Non-goals). The event model must merely not preclude them, and it does not —
§3.2's structural rules mean a future module adds them by declaring types and
predicates, with no core change.

**A course of conduct, not an occurrence.**
`provided_military_training_to`, `trafficked_narcotics_with`,
`helped_establish_operations_of`, `financed_and_supplied_materiel_to`. Each
describes a pattern over time. "Which training?" has no single answer, which is
the test failing.

**Standing relations, computed predicates, and properties.**
`member_of`, `founded`, `pledged_allegiance_to`, `splinter_affiliate_of`,
`successor_leader_of`, `affiliated_with`, `allied_with`, `partnered_with`,
`close_associate_of`, `rival_of`, `controls`, `foreign_contact_of`,
`sibling_of`, `spouse_of`, `conspired_with`, `conspired_against`,
`co_located_in_prison_with`, `known_as`, `has_nic`, `born_on`, `registered_as`,
`reachable_on`, `assessed_as_criminal_organization`.

`sibling_of` names no occurrence and "when did the sibling-ness happen?" is a
category error. `member_of` is a status that began at a moment, which is not the
same as being one. `co_located_in_prison_with` is computed from two remand
windows — there is no occurrence to point at, only an overlap. The identifier
and property predicates are not relations at all.

## What changed in the corpus

Two claims retracted, two events created, eight claims written (two summaries,
four arrestees, and the two events' own summary claims). The projection
snapshot baseline moves accordingly; the diff is two `co_arrested_with` edges
leaving and the migrated events' participation edges arriving, which is the
shape §2.3 predicts — an event is drawn as a node with its participants
attached rather than as `k(k−1)/2` derived pairs.

## Standing decision

**No automatic pairwise derivation, now or later** (§2.3). An arrest with `k`
participants would derive `k(k−1)/2` edges, and a reader counting connections
would count a single sourced occurrence as ten. That is the "authoritative
rumour engine" arriving through a rendering choice, and the event *is* the
rendering. Revisit only when a P6 analytic genuinely needs co-participation
adjacency — computed inside the analytic, named in the finding's basis, and
still not a claim.
