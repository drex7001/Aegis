# Phase 6 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them; narrower dependencies are noted in the task text. Reference specs in
parentheses. Numbering continues from Phase 5 (T65).

> **Status: PRE-AUTHORED, NOT ACTIVE.** Phases 2–5 must close first (strict
> sequence, ADR-025; design work may start after P5 T54 per the charter).
> Authored 2026-07-17 ahead of phase start; **the charter was amended
> 2026-07-18 (ADR-033): authorization in candidate generation not only
> hydration (B-17), AST-only set storage with complexity limits and
> ontology-version pinning, one-snapshot set evaluation (M-16), immutable
> analytic run manifests (H-23), typed alert suggestions (H-24), numeric
> search targets defined at phase start (H-22)**. T66 re-validates this plan
> against the amended charter and dispositions the findings tagged P6 before
> any other task starts. Charter:
> `../phases/phase-06-search-object-sets-analytics.md` · specs:
> `../specs/11-search.md` and `../specs/12-object-sets-analytics.md` (authored
> by T66).

## Milestone A — Search

**T66. ⛓ Specs 11 + 12 and the caveat catalog** (charter §Specs) — re-validate
this plan against the P3–P5-as-built system; author `specs/11-search.md`
(index strategy, transliteration keys, result grouping, the authz re-check
flow per ADR-012, numeric precision/recall targets) and
`specs/12-object-sets-analytics.md` (the filter-tree grammar over types *and
interfaces*, the `AnalyticFinding` schema, and the **caveat catalog** — the
Article IX warning text per metric, written once with the analyst persona so
caveats are structural, never UI decoration); add search/sets/findings/
watchlist routes to specs/06.
AC: both specs exist; the caveat catalog covers every planned metric and
"most connected" is never worded as leadership; precision/recall targets are
numbers, not adjectives; divergences from this plan are ADR'd.

**T67. ⛓ Global search** (specs/11; extends T25) — Postgres FTS + trigram +
transliteration keys across entities, claims, and documents; grouped results;
**authorization re-check before hydration** (ADR-012); purpose capture when a
sensitive hit is opened.
AC: a hit the caller's filters exclude is absent — not redacted, absent; the
narrower of two users gets strictly fewer results for the same query; opening
a sensitive hit records purpose in audit; result groups follow the ontology's
types.

**T68. Golden multilingual set + CI gate** (specs/11; needs T67) — the
Sinhala/Tamil/English golden set (name variants, transliterations, known
distinct same-name people) with precision/recall computed in CI on every run;
failure is the documented OpenSearch trigger (ADR-012), never a silent
regression.
AC: CI publishes the metrics; targets met (charter exit №1); a seeded
regression fixture fails the gate; the trigger condition is written next to
the numbers it watches.

## Milestone B — Object sets

**T69. ⛓ Object-set model + grammar** (specs/12; needs T66) — filter-tree
definitions over ontology types/interfaces (type, predicate, property, time,
case scope); saved and versioned; **sets store queries, never results** (the
risk-table rule, enforced by schema).
AC: a stored definition contains no result rows (schema makes it impossible);
a set filtering on an interface picks up a new member type after an ontology
minor bump without edits; edits version the definition.

**T70. Sharing + evaluation under caller filters** (needs T69) — FGA
`object_set` type (view/edit grants); composition (union / intersect /
difference); evaluation always applies the **caller's** row filters at read
time.
AC: the same shared set evaluates strictly narrower for a narrower-clearance
user (charter exit №4, second half); composed sets equal set algebra over
their evaluated members for that caller; an unshared set is invisible in
every list.

**T71. Set builder in the workspace** (needs T70; SDK regen) — set and
finding types regenerate into both SDKs; workspace set builder (build,
compose, save, share) and results panel.
AC: a set is built, composed, and shared entirely from the workspace through
typed SDK calls; the builder offers only grammar the spec defines; no
hand-written domain types appear.

## Milestone C — Analytics

**T72. ⛓ Analytics service + findings** (specs/12; needs T69) — k-hop
neighborhoods, shortest/weighted paths, Leiden communities (reusing the
projection implementation), brokerage/betweenness, shared-identifier
detection; each run takes a projection or an object set as input and returns
an `AnalyticFinding` — method, parameters, inputs (set version / projection
snapshot), caveat text from the catalog. **Findings are a distinct table with
a distinct lifecycle — never claims** (Article IX).
AC: every metric's finding carries its catalog caveat and its exact inputs; a
schema-level test proves findings and claims are separate tables with
separate lifecycles (charter exit №2); re-running with the same inputs
reproduces the finding.

**T73. Findings panel** (needs T71, T72) — findings rendered in the
workspace; the caveat comes from the finding record and always renders; no
metric has a caveat-free rendering path.
AC: a UI test asserts caveat presence for every metric type (charter exit
№2); centrality never renders with leadership language; a finding links back
to its inputs and parameters.

## Milestone D — Promotion & watchlists

**T74. Finding → claim promotion** (needs T72) — the audited action: finding
→ review → **assessed** claim (assertion type `assessment`), human-actored;
the finding stays linked as the claim's analytic basis.
AC: promotion requires an actor and survives in audit with the analytic basis
attached (charter exit №3); the produced claim's assertion type is
`assessment`; the finding is not consumed — it remains, linked.

**T75. Watchlists + alert triage** (needs T69) — exact-identifier watchlists
built on object sets; alert statuses new / reviewing / closed — minimal per
GOAL.md §32; fuzzy matching deliberately absent (risk table).
AC: an exact identifier landing in canon fires the watching set's alert; all
triage transitions are audited; a fuzzy near-miss does not fire (asserted).

**T76. End-to-end proof** (charter exit №4; needs T70, T72, T75) — the owning
task for the headline criterion, scripted: create a set → share it
case-scoped → drive an analytic run and a watchlist from it → a second user
with narrower clearance sees a correctly narrower evaluation of the *same*
set.
AC: the full chain passes as a repeatable test including the two-user
assertion; the script joins the demo runbook.

**T77. Phase exit review** — walk the charter's exit criteria; update speckit
docs where reality diverged; append ADRs; write
`../reviews/phase-06-exit-review.md`; tag `phase-6-search-analytics` per the
git workflow.
AC: every gate criterion checked (non-deferrable, ADR-025); non-blocking
deliverables carried over with owner + target phase recorded.

## Explicit non-goals for Phase 6

OpenSearch (fires only on the ADR-012 trigger the golden set now measures),
GNN link prediction and ML anomaly detection (no explainability story — GOAL.md
§13.4), financial-flow models (no financial feeds exist), streaming alerts
(Kafka trigger), cross-case global dashboards, fuzzy watchlist matching.
