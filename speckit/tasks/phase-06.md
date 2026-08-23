# Phase 6 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them; narrower dependencies are noted in the task text. Reference specs in
parentheses. Numbering continues from Phase 5 (T65).

> **Status: ACTIVE, opened 2026-08-23 by T66.** Phases 2–5 closed (strict
> sequence, ADR-025). T66 re-validated this plan against the P3–P5-as-built
> system and against the 2026-07-18 charter amendment (ADR-033); its **fourteen
> divergences** are recorded in `../specs/11-search.md` §0 (S1–S7) and
> `../specs/12-object-sets-analytics.md` §0 (O1–O7), and in ADR-050…ADR-057.
> The task text below has been corrected where it diverged. **Specs 11 and 12
> are authoritative where this file and they disagree.** Charter:
> `../phases/phase-06-search-object-sets-analytics.md` · specs:
> `../specs/11-search.md` (final), `../specs/12-object-sets-analytics.md`
> (final), `../specs/06-api.md` §2.1, §2.6, §2.9.
>
> The five corrections that change what gets built:
>
> 1. **One search route** (ADR-050). `GET /v1/search` supersedes
>    `GET /v1/search/entities`, which is removed with `BREAKING API CHANGE`.
>    M-11 asks for one endpoint with an additive backend; two routes would be
>    two rankings, two paginations, and two copies of B-17's leak surface.
> 2. **Authorization in candidate generation is already how search works**
>    (T23c, P2). The pre-authored "re-check before hydration" is the wording
>    B-17 rejects; it is now an invariant with a structural test, not a habit.
> 3. **Object sets are pinned to an ontology version by default** (ADR-054).
>    T69's AC said the opposite. A set that silently widens when a domain module
>    lands changes the meaning of findings people already acted on.
> 4. **Reproducibility is manifest equality** (ADR-055), not "same inputs".
>    Neither a set nor a projection is immutable, and `clustering.py`'s
>    Leiden→Louvain fallback is labelled on the result but carries no library
>    version and belongs to no run record. This also closes P5's `is_stale`
>    carryover without changing what `is_stale` means.
> 5. **Watchlists are evaluated explicitly, never on write** (ADR-056). The
>    side-effect outbox spec 08 §6.5 declares is still executed by nothing, and
>    building it for one feature would ship a second inert mechanism.
>
> **Weighted paths are out** (ADR-030, spec 12 §0 O4): the projection carries a
> support summary, not an aggregate weight, so there is no weight to traverse.

## Milestone A — Search

**T66. ⛓ Specs 11 + 12 and the caveat catalog** (charter §Specs) — **DONE
2026-08-23.** Re-validated this plan against the P3–P5-as-built system;
authored `../specs/11-search.md` (index strategy, the versioned normalization
pipeline, transliteration keys, result grouping, candidate-generation
authorization per ADR-012, numeric precision/recall targets) and
`../specs/12-object-sets-analytics.md` (the filter-tree grammar over types
*and* interfaces, the `AnalyticFinding` schema and run manifest, and the
**caveat catalog** — the Article IX warning text per metric); added
search/sets/findings/watchlist routes to `../specs/06-api.md` §2.1, §2.6, §2.9;
appended ADR-050…ADR-057.
AC: **met.** Both specs exist. The caveat catalog is code
(`aegis/analytics/caveats.py`), covers every metric §9.1 says records a
finding, and `tests/contract/test_caveat_catalog.py` proves completeness in
both directions, that spec 12 §9.3 quotes it verbatim, and that no metric name
or label uses leadership language or a superlative — with a non-vacuity check,
because a word list that catches nothing proves nothing. Targets are numbers in
`aegis/search/targets.py`, quoted by spec 11 §8 and compared by
`tests/contract/test_search_targets.py`. Divergences are ADR'd.

**T67. ⛓ Global search** (specs/11; supersedes T25) — one route,
`GET /v1/search`: Postgres FTS + trigram + transliteration keys across
entities, `claim.excerpt` and the `document_text_projection` (ADR-051);
grouped results enumerated from `ontology.object_types`; the versioned
normalization pipeline (ADR-052) applied identically at write and query time;
**authorization in candidate generation** (ADR-012, B-17), never
generate-then-filter; identifiers matched exactly (ADR-053); `asOf` /
`asOfRevision` (closing the P5 carryover); purpose capture when a sensitive
hit is opened. Removes `GET /v1/search/entities` with `BREAKING API CHANGE`.
AC: a hit the caller's filters exclude is absent — not redacted, absent; two
users get **subset** results for the same query, and a **strict** subset once a
restricted matching row is seeded (M-13, spec 11 §0 S7); a restricted row
leaves no pagination gap; no response carries a total, approximate total or
hidden count in any group, and an empty group is omitted; opening a sensitive
hit without a purpose is `422`, and with one the purpose is in `audit_log`;
result groups follow the ontology's types; an identifier near-miss returns
nothing; `aegis search check-index` fails on a key at an older
`NORMALIZATION_VERSION`.

**T68. Golden multilingual set + CI gate** (specs/11 §8–§10; needs T67) — the
fictional Sinhala/Tamil/English golden set (name variants, transliterations,
known-distinct same-name people, transliteration near-misses that are different
names, NFC/NFD pairs, format characters, identifier queries, and at least one
restricted matching row) with precision, recall and latency computed in CI on
every run; failure is the documented OpenSearch trigger (ADR-012), never a
silent regression.
AC: CI publishes the metrics; every target in `aegis/search/targets.py` is met;
a seeded regression fixture fails the gate; stripping diacritics **lowers** the
score, which is the fixture that keeps spec 11 §3.1 honest; the trigger
condition is written next to the numbers it watches, and remediation lands
inside this phase if it fires (H-22).

## Milestone B — Object sets

**T69. ⛓ Object-set model + grammar** (specs/12 §2–§4; needs T66) —
filter-tree definitions over ontology types *and interfaces* (type, predicate,
property, time, case scope, search, composition); stored as a **validated
AST**, never SQL; saved and versioned; **sets store queries, never results**,
enforced by there being nowhere to put them; complexity limits and cycle
detection at **save**, not at run time.
AC: a stored definition contains no result rows (schema makes it impossible)
and no SQL text; the AST compiler is total over the grammar and undefined
outside it; depth, node count, composition depth and cycles are refused with a
`422` naming the offending path; **a set filtering on an interface does _not_
pick up a new member type after a minor bump** (ADR-054 — the pre-authored AC
inverted), a set with `track_interface_members` does, and both receive a
notice; edits create a new immutable version.

**T70. Sharing + evaluation under caller filters** (specs/12 §5–§7; needs T69)
— FGA `object_set` type (viewer/editor); composition (union / intersect /
difference); evaluation applies the **caller's** row filters in candidate
generation, under **one snapshot and one authorization context** per request
(M-16); the definition is protected data — a `property` node above clearance
reads back `withheld: true` with an unchanged shape.
AC: the same shared set evaluates as a subset for a narrower-clearance user,
and a strict subset with a seeded restricted member (charter exit №4, second
half); composed sets equal set algebra over their evaluated operands for that
caller (property-based); an unshared set is **absent** from every list; a
`difference` over a definition the caller cannot read is refused at save; a set
never evaluates with its owner's clearance except the watchlist sweep, which is
asserted explicitly.

**T71. Set builder in the workspace** (needs T70; SDK regen) — set and finding
types regenerate into the TypeScript client; workspace set builder (build,
compose, save, share) and results panel. Closes the P4 claims-picker carryover:
a hypothesis link picker is an object set with `type: claim`.
AC: a set is built, composed, and shared entirely from the workspace through
typed SDK calls; the builder offers only grammar the spec defines; no
hand-written domain types appear in the workspace.

## Milestone C — Analytics

**T72. ⛓ Analytics service + findings** (specs/12 §8–§9; needs T69) — k-hop
neighbourhoods, shortest paths, Leiden communities (reusing
`aegis/analytics/clustering.py`), betweenness, degree, shared-identifier
detection; each run takes a projection or an object set as input, writes an
**immutable run manifest first** (ADR-055) and returns `AnalyticFinding` rows
carrying method, parameters, inputs and the catalog caveat **copied into the
row**. **Findings are a distinct table with a distinct lifecycle — never
claims** (Article IX). `/v1/graph/*` keeps answering questions without
recording anything (ADR-057). **No weighted paths** (ADR-030).
AC: every finding carries its catalog caveat and its exact inputs; a
schema-level test proves findings and claims are separate tables with separate
lifecycles and no write path converting one to the other (charter exit №2);
**equal manifests produce equal finding digests** (ADR-055 — the pre-authored
"same inputs reproduces the finding" made precise); a forced Leiden→Louvain
fallback produces a **different** manifest rather than a silent difference; a
finding's handling code is the maximum of its contributing claims.

**T73. Findings panel** (needs T71, T72) — findings rendered in the workspace;
the caveat comes from the finding record and always renders; no metric has a
caveat-free rendering path.
AC: a UI test asserts caveat presence for every metric type (charter exit №2);
centrality never renders with leadership language or a superlative; a finding
links back to its inputs, its parameters and its manifest.

## Milestone D — Promotion & watchlists

**T74. Finding → claim promotion** (specs/12 §10; needs T72) — the audited
action: finding → **typed suggestion** (`finding_promotion`) → review → claim
with `assertion_type = 'assessed'` (not "assessment" — spec 12 §0 O7), written
with the **reviewer** as actor (ADR-031 §2); the finding stays linked as the
claim's analytic basis through `promoted_claim_id` and a `claim_relation` of
kind `analytic_basis`, never an invented source record (H-23).
AC: promotion requires an actor and a substantive rationale, and survives in
audit with the analytic basis attached (charter exit №3); the produced claim's
assertion type is `assessed`; the finding is not consumed — it remains, linked;
promoting the same finding twice is refused and the finding still exists.

**T75. Watchlists + alert triage** (specs/12 §11; needs T69) —
exact-identifier watchlists built on object sets; a detection is a **typed
alert suggestion** (`watchlist_hit`) with rule, rule version, inputs, dedupe
key, exactness and authority ref (H-24); triage `new / reviewing / closed`,
minimal per GOAL.md §32; fuzzy matching deliberately absent. **Evaluation is
`aegis watchlists evaluate`, never a write-path hook** (ADR-056), recording an
`analytic_run` and an `evaluated_through` watermark.
AC: an exact identifier landing in canon produces an alert **suggestion** on
the next sweep; a fuzzy near-miss does not fire (asserted, not assumed); the
same identifier landing twice produces one alert; all triage transitions are
audited and `closed` without a reason is `422`; a re-run over an overlapping
window is idempotent; an unevaluated window is visible as a gap in the runs.

**T76. End-to-end proof** (charter exit №4; needs T70, T72, T75) — the owning
task for the headline criterion, scripted: create a set → share it case-scoped
→ drive an analytic run and a watchlist from it → a second user with narrower
clearance sees a correctly narrower evaluation of the *same* set.
AC: the full chain passes as a repeatable test including the two-user
assertion, seeded so the narrower evaluation is a **strict** subset; the script
joins the demo runbook.

**T77. Phase exit review** — walk the charter's exit criteria; update speckit
docs where reality diverged; append ADRs; write
`../reviews/phase-06-exit-review.md`; tag `phase-6-search-analytics` per the
git workflow.
AC: every gate criterion checked (non-deferrable, ADR-025); non-blocking
deliverables carried over with owner + target phase recorded; the OpenSearch
trigger's measured numbers recorded whether or not it fired.

## Explicit non-goals for Phase 6

OpenSearch (fires only on the ADR-012 trigger the golden set now measures),
GNN link prediction and ML anomaly detection (no explainability story — GOAL.md
§13.4), financial-flow models (no financial feeds exist), streaming alerts
(Kafka trigger), cross-case global dashboards, fuzzy watchlist matching,
weighted paths (ADR-030), embeddings or semantic search, and bulk *write*
operations over a set — a set drives reads and analytics, and a bulk claim
write over a set is an unreviewed machine write wearing a UI (Article VII).
