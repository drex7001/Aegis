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
— **DONE 2026-08-23.**
— FGA `object_set` type (viewer/editor); composition (union / intersect /
difference); evaluation applies the **caller's** row filters in candidate
generation, under **one snapshot and one authorization context** per request
(M-16); the definition is protected data — a `property` node above clearance
reads back `withheld: true` with an unchanged shape.
AC: **met.** The composition identity is tested as an identity — union,
intersection and difference each equal the corresponding operation over their
operands' evaluated memberships **for that same caller**, each with a control
asserting the operands actually overlap so the equality is not vacuous. A
narrower caller sees a subset, strictly so once a restricted member matches,
and the same-answer case is a test rather than an omission (M-13). A set
evaluated by a junior returns the junior's view, never its owner's — including
through composition of somebody else's set. `difference` over a definition the
caller cannot read is refused **at save**, and the default refuses rather than
permits, because a security rule nobody remembers to opt into is not a rule.

**T70 found an authorization hole in T69.** `{"kind": "type", "object_type":
"person"}` compiled to a bare type comparison with no claim join, so an object
set returned every person in the database — including those reachable only
through claims above the caller's clearance. An entity carries no handling code
of its own; claims do, and `aegis/search/entities.py` had encoded that since
T23c. `visible_entity_ids` now lives in `aegis/authz/filters` with one
definition and two callers, `compile_set` composes it once for every node
rather than per node, and `tests/contract/test_object_set_invariants.py`
asserts both packages compose it.

**M-16's snapshot is obtained by construction, not by isolation level.** The
first implementation issued `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ`
and could not — PostgreSQL accepts it only as a transaction's first statement.
`compile_set` produces one `SELECT` with every operand as a subquery, and a
single statement sees a single snapshot at any isolation level, so there is no
moment between operands for the corpus to change in.
`test_composition_is_a_single_statement` pins it and says what to do if it ever
fails. Spec 12 §6 records both.

FGA gains an `object_set` type with a third relation: `evaluator` is weaker
than `viewer`, so a colleague can be given the answer without being given the
question (spec 12 §5.2). The creator is made an `editor` at save, so a set
cannot exist that nobody — including its author — can edit.

**T71. Set builder in the workspace** (needs T70; SDK regen) — **DONE
2026-08-23.** Set and finding
types regenerate into the TypeScript client; workspace set builder (build,
compose, save, share) and results panel. Closes the P4 claims-picker carryover:
a hypothesis link picker is an object set with `type: claim`.
AC: **met.** A set is built, saved, evaluated and shared entirely from the
workspace through the generated client. The builder's menus are fed from the
*generated* ontology descriptors, so a second domain's vocabulary appears with
no change to the workspace (Article XIV) and there is deliberately **no
free-text condition box** — that would be a second grammar, and the one in
spec 12 §2 is the one that gets validated. The browser test asserts a declared
type is offered and an undeclared one is not.

T71 also adds the routes, which T69 and T70 built the service layer for. The
property they exist to hold is that **an unshared set is absent, never
forbidden**: every check is 404-on-failure, the list omits rather than marks,
and a missing set and an unshared one return byte-identical responses. The
stub FGA answers `False` for anything ungranted, so "the route never asked"
and "the route asked and was refused" are distinguishable — and one test
asserts the *relation* asked for, because a route that skipped its check would
pass every other case.

**The two grants are visible in the routes, not only in the model.**
Evaluating asks for `evaluator`; reading the definition asks for `viewer`. A
colleague granted only the first gets the answer and still gets 404 from the
definition, which is the disclosure boundary spec 12 §5.2 draws.

The results panel labels members "as you can see them" and shows the
evaluation digest. Two people sharing one set correctly see different members,
and a screen that implied otherwise would teach a model this system does not
have. No total, in the panel or the API.

## Milestone C — Analytics

**T72. ⛓ Analytics service + findings** (specs/12 §8–§9; needs T69) — **DONE
2026-08-23.** K-hop
neighbourhoods, shortest paths, Leiden communities (reusing
`aegis/analytics/clustering.py`), betweenness, degree, shared-identifier
detection; each run takes a projection or an object set as input, writes an
**immutable run manifest first** (ADR-055) and returns `AnalyticFinding` rows
carrying method, parameters, inputs and the catalog caveat **copied into the
row**. **Findings are a distinct table with a distinct lifecycle — never
claims** (Article IX). `/v1/graph/*` keeps answering questions without
recording anything (ADR-057). **No weighted paths** (ADR-030).
AC: **met.** Every finding carries its catalog caveat, read from the row
rather than the renderer — and a `CHECK` constraint refuses a blank one, so a
future code path cannot route around Article IX. `caveat_for()` raises before
any work is done, so a metric with no caveat cannot run at all.

Findings and claims are separate tables, proved at the **schema**: different
columns, no foreign key from `claim` back to a finding (`promoted_claim_id`
points one way only, because a claim reachable *as* a finding would be one
lifecycle wearing two names), and a sweep asserting no module in
`aegis/analytics/` constructs a `Claim` — with a non-vacuity check, since a
sweep over nothing passes.

**Reproducibility is manifest equality** and is tested in both directions: a
different clearance or a projection whose rows moved produces a different key;
who ran it, when and why do not. The clearance case is the one that matters —
`authorization_digest` is *in* the manifest, so a finding computed under a
narrower clearance **is a different finding** and cannot be compared with one
that is not (Article VI).

**P5's `is_stale` carryover closes here.** The manifest records *which*
projection was read — `built_at_revision_id`, builder version, aggregation
method — plus an `edge_digest` over the rows actually consumed, which catches
what the stamps cannot: a projection rebuilt at the same identity revision with
different rows. `is_stale` keeps its meaning and its docstring.

`implementation` records the library **and its version**, so a Leiden run and a
Louvain fallback are different manifests. `seed` is NULL for an unseeded run
rather than 0, which would later read as a determinism it never had.

`handling_code` is derived from the contributing claims, never chosen: a
finding built from a `sensitive` link is `sensitive`, and a narrower caller
gets an empty list rather than a redacted row.

**`k_hop` and `shortest_path` raise rather than half-work.** They are in
`METRICS` because spec 12 §9.1 lists them, but the traversal lives in
`/v1/graph/*` and a second copy wired to record findings is T73's business —
the error names the spec section rather than leaving a stub somebody has to
remember.

**T73. Findings panel** (needs T71, T72) — **DONE 2026-08-24.** Findings
rendered in the workspace; the caveat comes from the finding record and always
renders; no metric has a caveat-free rendering path.
AC: **met.** The browser test is parameterised over every metric, because a
caveat asserted for one proves nothing about the next one somebody adds — and a
**count** assertion pairs with it: findings rendered and caveats rendered must
be equal, so a metric that skipped one fails the moment the counts diverge. The
caveat comes from `finding.caveat_text`, renders without any interaction, and
sits behind no toggle: a caveat somebody has to open is a caveat nobody reads.

**The route serves labels and never caveat text**, and a contract test asserts
`AnalyticMetricOut` is exactly `{metric, label}`. That is the subtle half of
spec 12 §9.3: if the workspace could *fetch* a caveat there would be a render
path that fetches one, and therefore one that can fail to. The text lives on
the row or nowhere.

Metric labels ride on `/v1/ontology/vocabulary` — the precedent
`assertion_types` set (platform vocabulary, code-owned, Article XIV) — because
a hand-written label map in TypeScript is exactly where "most connected"
becomes "most important". `degree` is labelled **Recorded connections**: a
superlative does the same work as "leader" with none of the vocabulary. The
rendered page is swept for leadership language, exempting words that appear
*inside* a caveat, since a caveat's job is to name the wrong reading and deny
it.

A finding opens its manifest, including `authorization_digest`: two analysts
running one metric under different clearances correctly get different findings,
and without that on screen it reads as the system contradicting itself.

**The browser flakiness was diagnosed rather than tolerated.** Three runs had
failed 2–4 map-heavy journeys while every one passed in isolation, and T71
recorded it as a local sensitivity. The cause is worker count: Playwright
defaults to half the cores, so a 16-core machine runs 8 workers and several
MapLibre journeys compete for one software renderer, while a 2–4 core CI runner
uses 1–2 and never sees it. Measured at 151 tests: 8 workers fail, **4 workers
pass all 151**. `workers: 4` is now in the config, below what CI already uses,
so it costs CI nothing. `retries` stays 0 — a retry would have made those runs
green while hiding the reason.

## Milestone D — Promotion & watchlists

**T74. Finding → claim promotion** (specs/12 §10; needs T72) — **DONE
2026-08-24.** The audited action: finding → **typed suggestion**
(`finding_promotion`) → review → claim with `assertion_type = 'assessed'` (not
"assessment" — spec 12 §0 O7), written with the **reviewer** as actor
(ADR-031 §2); the finding stays linked as the claim's analytic basis through
`promoted_claim_id`, never an invented source record (H-23).
AC: **met.** Promotion writes a suggestion and never a claim; the produced
claim's assertion type is `assessed`; the finding is not consumed — it remains,
immutable, and gains a pointer to what it became the basis of; promoting twice
is refused (409, not 422 — the request is well formed and the *state* refuses
it) and the finding still exists. A rejection leaves the finding exactly as it
was: not "promoted and then unpromoted", never promoted.

**The `claim_relation` half of this task's own description was wrong**, and
building it is what showed that. `claim_relation` has `from_claim` and
`to_claim`, both foreign keys to `claim`, and its `relation` is constrained to
`corroborates`/`contradicts` — the claim-to-claim epistemic relations Article
VIII is about. A finding is not a claim, so it fits in neither column, and
widening the constraint would have made "this claim relates to that claim" mean
two different things. The link already existed and is one-directional on
purpose: `analytic_finding.promoted_claim_id`. Spec 12 §10 and this entry are
corrected rather than the schema.

**The rationale is part of the idempotency key**, which is a governance choice
rather than a detail. The default key digests the payload, so two promotions of
one finding with the same subject and predicate collided however differently
they were argued — and a promotion rejected once could never be re-proposed on
better reasoning. Including the rationale makes the rule the one worth having:
**the same argument, already rejected, cannot be resubmitted; a new argument
can.** A reviewer who said no to one case is not saying no to every future case
anybody might make from the same finding.

**A suggestion kind lives in three places, and two is a bug.** The dispatch
branch (`SUGGESTION_KINDS`), the database check, and the ontology's
`submit_suggestion` enum must agree — the code-owned list is what can be
*accepted*, the enum is the public contract for what may be *sent* (ADR-031 §1).
T74 built the first two and not the third, so the kind existed and no caller was
permitted to name it. `test_every_kind_declares_its_target_action` went red on
exactly that, in both directions, which is the test doing its job rather than a
drift somebody noticed later. The vocabulary went through the workflow it should
have gone through first: **proposal 009**, platform `1.5.0` → `1.6.0`,
composition `2.1.0` → `2.2.0`, both additive, `check-release` and
`generate --check` green.

The kind is admitted by `ck_review_queue_kind` through migration `0017`, and
that it needed a migration at all is the point: the set of things a machine may
propose is enforced by the **database**, not by a dictionary in Python. Adding
the kind in code and finding out at insert time — which is exactly how this was
found — is the constraint working. The downgrade refuses while any promotion
row exists, per the rule migration `0013` set.

**T75. Watchlists + alert triage** (specs/12 §11; needs T69) — **DONE
2026-08-24.**
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

AC: **met.** An exact identifier landing in canon produces an alert on the next
sweep; a fuzzy near-miss does not fire (asserted, not assumed — every fixture
sends one and requires silence); the same identifier landing twice produces one
alert; all triage transitions are audited and `closed` without a reason is
refused by the **service and the database**; a re-run over an overlapping window
is idempotent (proved by rewinding the watermark, so it tests the dedupe key
rather than the window arithmetic); an unevaluated window is a null watermark on
the watchlist, read from the runs.

**A detection is not a review-queue suggestion, and spec 12 §11.2 said it was.**
Building it found five of six things an alert needs that `review_queue` cannot
give: `target_action` is `NOT NULL` and an alert dispatches to nothing; the
accepted-result CHECK wants exactly one typed result and an alert produces none;
the status vocabulary is different; queue visibility keys on the **source
record's** handling code while an alert's sensitivity comes from the **claims**
that fired it — and a `sensitive` claim can sit in an `open` record, so reusing
the queue would have keyed alert visibility on the wrong thing in the direction
that discloses. Only the dedupe key fit. ADR-060 records the decision; the spec
is corrected, and Article VII is untouched because an alert reaches no canonical
table — it points at a claim that arrived through the ordinary path.

**Two bugs the tests found rather than the reader.** The sweep took its window
boundary from the Python clock while `claim.recorded_at` is a server default, so
on any skew a claim recorded moments ago fell outside a window that should
contain it — a flaky sweep, which is worse than a slow one because it looks like
the rule not matching. It now uses the database's clock. And `owner_clearance`
was first written onto `ObjectSet` rather than `Watchlist`, because the patch
anchored on the first `owner:` column in the file; `object_set` inserts started
failing immediately, which is the NOT NULL constraint doing its job.

**The owner-clearance snapshot is a stated limitation, not a silent one.** There
is no user table to look a clearance up from — Keycloak holds it — so an offline
sweep has to carry the number. It is taken from the creator's own token and can
never exceed it, but it does not follow them down: an owner later narrowed keeps
a watchlist firing at the clearance it was created with, until it is recreated.
Written into the model, spec 12 §11.3 and the route docstring.

**The first sweep reports where the watched values already are**, including on
the set's own members, because its window is all of time. That is the honest
answer to "where does this value appear"; starting silent would hide everything
already in the corpus at the moment somebody starts watching. Recorded as its
own test so the behaviour is a decision rather than an artefact.

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
