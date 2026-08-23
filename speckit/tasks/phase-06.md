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

**T67. ⛓ Global search** (specs/11; supersedes T25) — **DONE 2026-08-23.** One route,
`GET /v1/search`: Postgres FTS + trigram + transliteration keys across
entities, `claim.excerpt` and the `document_text_projection` (ADR-051);
grouped results enumerated from `ontology.object_types`; the versioned
normalization pipeline (ADR-052) applied identically at write and query time;
**authorization in candidate generation** (ADR-012, B-17), never
generate-then-filter; identifiers matched exactly (ADR-053); `asOf` /
`asOfRevision` (closing the P5 carryover); purpose capture when a sensitive
hit is opened. Removes `GET /v1/search/entities` with `BREAKING API CHANGE`.
AC: **met.** A hit the caller's filters exclude is absent — not redacted,
absent; two users get **subset** results, and a **strict** subset once a
restricted matching row is seeded (M-13, spec 11 §0 S7); paging both users
yields the narrower's set as a **subsequence**, so a restricted row leaves no
gap; a borrowed cursor widens nothing; no response carries a total in any
group, asserted over the response *and* over the OpenAPI document; an empty
group is omitted; opening a restricted record without a purpose is `422` and
with one the purpose is in `audit_log`; result groups are enumerated from
`ontology.object_types`; an identifier near-miss returns nothing, with a
non-vacuity check that the near-miss scores >0.8 on trigram; a row at an older
`NORMALIZATION_VERSION` is excluded from the scan and `aegis search
check-index` exits non-zero on it.

Three things implementation changed, each written back into spec 11:

1. **§3.1 described a pipeline that does not exist.** It said stage 1 was NFKC
   and that diacritics are never stripped; `norm_key` does NFKD and *does* fold
   Latin diacritics, deliberately, so P1-migration keys still match. The rule is
   **fold when the base is ASCII, preserve when it is not** — which is what
   H-22 actually asks for. Rewritten against the code.
2. **One cursor, not one per group.** §5.3 said "limit ≤ 50 per group", which
   implies a cursor per group — and independent cursors are the pagination-gap
   surface §4.2 claims to close. One ranked sequence, one cursor; groups are a
   display of the page.
3. **The group cap was a latent silent-drop bug.** It truncated *after* the
   page was cut and after `next_cursor` was computed. Eleven groups against a
   cap of twelve: two more object types and it would have dropped hits nobody
   could ever reach. Removed, with `tests/unit/test_search_grouping.py`
   asserting grouping is a partition.

Two defects found and fixed on the way: a **zero-width joiner inside a name
split the token**, so the same Sinhala name pasted from two pages produced two
keys that never blocked together (migration `0014` recomputes rather than
merely stamps); and the results overlay styling lived on the result *list*, so
splitting results into one list per group made **every group its own floating
panel**, stacked — the top group's rows were unclickable. Only a test that
clicks could see it, and one did.

**T68. Golden multilingual set + CI gate** (specs/11 §8–§10; needs T67) — **DONE
2026-08-23.** The
fictional Sinhala/Tamil/English golden set (name variants, transliterations,
known-distinct same-name people, transliteration near-misses that are different
names, NFC/NFD pairs, format characters, identifier queries, and at least one
restricted matching row) with precision, recall and latency computed in CI on
every run; failure is the documented OpenSearch trigger (ADR-012), never a
silent regression.
AC: **met.** CI publishes `output/search-evaluation.json` on success *and*
failure — evidence that vanishes when a gate fails is evidence nobody reads.
Every target in `aegis/search/targets.py` is met (spec 11 §8.1). The seeded
regression stamps mention rows at an older pipeline version — a regression an
operator could actually cause — and the test asserts the *healthy* run passed
first, because an earlier draft passed while the harness found nothing at all.
Diacritic behaviour is covered at the unit layer, where both halves of the rule
are asserted together (§0 S4, `test_search_pipeline.py`).

The first run **failed** cross-script at 0.375 against a 0.60 floor, which is
the ADR-012 trigger condition. It did not fire: the condition says *after a
documented tuning attempt*, one was made, and it worked. Cross-script is now
0.750 — passing, and still the weakest surface by a wide margin, with two of
eight names unreachable. Spec 11 §10.1 records the measurement table, and
`test_search_quality.py` asserts cross-script stays below same-script so an
improvement cannot regress it unnoticed.

Two defects fell out of the first measurement, which is what a first
measurement is for: **T67's document rank floor** discarded true positives
above an already-correct `@@` match (document retrieval 0.333 → 1.000), and
**one similarity floor was serving two different comparisons** — relaxing it
for *differing scripts*, symmetrically, is what recovered cross-script.

## Milestone B — Object sets

**T69. ⛓ Object-set model + grammar** (specs/12 §2–§4; needs T66) — **DONE
2026-08-23.**
filter-tree definitions over ontology types *and interfaces* (type, predicate,
property, time, case scope, search, composition); stored as a **validated
AST**, never SQL; saved and versioned; **sets store queries, never results**,
enforced by there being nowhere to put them; complexity limits and cycle
detection at **save**, not at run time.
AC: **met.** A stored definition contains no result rows because
`object_set_version` has nowhere to put them — the only durable way to meet
that criterion, since a column with a comment saying not to use it is still a
column. No node carries SQL because the grammar has **no free-text field** that
reaches a query: every string either names ontology vocabulary, is an opaque
id, or is `search.q`, which goes through the spec 11 pipeline to a bound
parameter. Asserted over the grammar's own field types, with a non-vacuity
check that the grammar actually has nodes.

The compiler raises `CompileError` on anything it cannot compile, including an
unexpanded interface — because a compiler that treated an unknown node as "no
constraint" would evaluate a **wider** set than the one saved, and the
definition would still read correctly. Depth, node count, set references,
composition depth, self-reference and dangling references are all refused **at
save**, each naming its path; a cycle caught at evaluation would be a request
that times out differently every time while the definition sits in the database
being shared.

**The inverted criterion holds** (ADR-054): with a fictional `port`
implementing `place`, the pinned set does *not* gain it, the tracking set
does, and **both owners are notified** — a pinned set could have widened, and
finding that out is as useful as finding out that it did. The notice carries a
uniqueness constraint so a second sweep cannot multiply what an owner sees.

Edits append; nothing updates a version, because a finding names
`(set_id, version)` and must name something that cannot change under it.

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
