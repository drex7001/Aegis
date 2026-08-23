# Spec 12 — Object sets, analytics & findings

Status: **final** (authored 2026-08-23 by T66, the blocking re-validation that
opens Phase 6) · Charter:
`../phases/phase-06-search-object-sets-analytics.md` · Constitutional basis:
Articles I, VI, VII, IX, X, XIII, XIV · GOAL.md §13, §32, §7.8 · Findings
closed here: B-17 (set half), H-23, H-24, M-16 · ADR-054…ADR-057

Its governing sentence:

> **A set is a question, a finding is an answer with its working shown, and
> neither is ever a claim.**

Phase 6 therefore adds three tables that are **not** the claim store —
`object_set`, `analytic_run`, `analytic_finding` — plus a watchlist built on
sets whose detections arrive as typed suggestions in the queue that already
exists.

---

## 0. What re-validation changed

Divergences affecting sets, analytics and findings. Those affecting search are
in `11-search.md` §0.

| # | The plan said | As built / as required | Disposition |
|---|---|---|---|
| O1 | T69 AC: "a set filtering on an interface **picks up a new member type** after an ontology minor bump without edits" | This is the pre-amendment behaviour B-17 rejects and the amended charter reverses: *"pinned to the ontology version by default with an explicit track-future-members opt-in"*. Left as written, a saved watchlist silently widens its own scope when a new domain module lands | **ADR-054**. AC inverted: a pinned set does **not** pick up the new member; a set that opted in does, **and the change is notified**. §4 |
| O2 | T72 AC: "re-running with the same inputs reproduces the finding" | H-23 is right that neither an object set nor a projection is an immutable input. There is also a specific hole. `aegis/analytics/clustering.py` falls back from Leiden to NetworkX Louvain when igraph is unavailable — it does better than I first read it as doing, stamping each returned cell with `algorithm: "louvain-fallback"` — but that label is (a) a name with **no library version**, (b) attached to a summary **no caller is obliged to persist**, and (c) attached to no run record at all, because there is none. So "the same inputs" can still produce a different partition from a different algorithm and leave nothing durable behind | **ADR-055** — an immutable **run manifest** with an evaluated-input digest. Reproducibility is defined as *same manifest → same finding digest*, and the implementation that ran is part of the manifest. §8.2 |
| O3 | P5 carryover: "`is_stale` cannot report claim-staleness … matters when a finding has to name the projection it was computed over" | Confirmed and closed **without changing what `is_stale` means**. A manifest does not ask "is this projection fresh?" — an unanswerable question at the moment of a run — it records *which* projection was read: `built_at_revision_id`, `builder_version`, `aggregation_method_version`, and a digest of the rows actually consumed | **ADR-055**. §8.2. The carryover closes here; `is_stale` keeps its meaning and its docstring |
| O4 | T72: "shortest/**weighted** paths" | ADR-030 removed the aggregate weight from `edge_projection` on purpose: an edge carries a support summary, and averaging grading into one number is the thing that ADR forbids. There is no weight to shortest-path over | No new ADR — ADR-030 already decided it. Weighted paths are **out**; path length is hop count. A future weighted metric must declare its weight function *in the manifest* and derive it from the support summary in the open. §9.2 |
| O5 | T72 lists "k-hop neighborhoods, shortest paths" as analytics; `POST /v1/graph/expand` and `/v1/graph/paths` already do both (T22) | Building them again under `/v1/analytics/` would be two implementations of one traversal with two authorization stories | **ADR-057** — `/v1/graph/*` **answers a question** and records nothing; `/v1/analytics/*` **records an answer**. The traversal code is shared; the difference is whether a finding is written. §9.1 |
| O6 | T75: "an exact identifier landing in canon **fires** the watching set's alert" | On-write firing needs the side-effect outbox, which spec 08 §6.5 declares and **nothing executes** — P5 carried it forward untouched. Building it here to power one feature would ship a second inert mechanism | **ADR-056** — evaluation is **explicit or scheduled** (`aegis watchlists evaluate`), never a hidden write-path hook. Each run records what it saw, so a missed window is visible. §11.3 |
| O7 | T74: "finding → review → **assessed** claim" | The vocabulary is `assessed` (`ASSERTION_TYPES` in `aegis/actions/service.py`), not `assessment`, and `analytic_confidence` is already refused on any claim whose assertion type is not `assessed`. The plan's wording would not have validated | Wording corrected; no design change. §10 |

One thing the plan assumed and reality confirms: the typed suggestion envelope
(ADR-031) takes both new kinds — `finding_promotion` and `watchlist_hit` — as
one enum value and one dispatch branch each, exactly as `event_draft` did in
P5. Neither needs a second review queue.

---

## 1. What an object set is

> A **named, versioned, shareable filter tree over objects**, stored as a
> validated AST, evaluated under the **caller's** authorization at read time.

It is the consumption-layer primitive adopted from Foundry (charter §Objective)
and it is the working unit for analytics, watchlists and bulk operations.

**It is not** a saved result, a materialized view, a permission grant, or a
second place where domain vocabulary is written. It holds no rows, grants no
access, and names only vocabulary the ontology declares.

---

## 2. The filter grammar (B-17)

### 2.1 Node types

An AST node is one of:

| Node | Fields | Meaning |
|---|---|---|
| `type` | `object_type` \| `interface` | membership in an ontology object type or interface |
| `predicate` | `predicate`, `direction`, optional `target` | the object has a claim with this predicate, as subject or object |
| `property` | `property`, `op`, `value` | a claim-derived property comparison |
| `time` | `field`, `from`, `to` | event-time or validity overlap, reusing `aegis/queries/window.py` |
| `case` | `case_id` | recorded in this case's scope |
| `search` | `q` | the spec 11 pipeline, same normalization, same candidate-generation rule |
| `set` | `set_id`, `version` | composition — §7 |
| `and` / `or` / `not` | `children` | boolean composition |

Every leaf names ontology vocabulary and is validated against the composed
registry at save time (Article XI). A predicate the ontology does not declare
is a `422` with the failing path, exactly as a claim write is.

### 2.2 Complexity limits

Declared as constants in `aegis/sets/limits.py`, so the numbers in this table
and the numbers enforced are the same numbers.

| Limit | Value | Why |
|---|---|---|
| AST depth | 8 | deeper is unreadable, and an unreadable set cannot be reviewed before sharing |
| total nodes | 64 | — |
| `set` references (direct) | 8 | — |
| composition depth | 3 | a set of sets of sets is a query language, not a filter |
| composition cycles | **rejected at save** | detected by walking the reference graph; a cycle is a `422`, not a runtime timeout |
| evaluated cardinality | 50 000 objects | over this the evaluation returns `truncated: true` and refuses to feed an analytic run — a metric over a truncated set is a metric about the truncation |
| statement timeout | 10 000 ms | one setting, per evaluation |

### 2.3 Never raw SQL

The AST compiles to parameterized SQLAlchemy. No node carries SQL text, no
node carries a column name, and nothing in the grammar can express a value that
is not a bound parameter. A schema-level test asserts the stored definition
contains no SQL — the T69 AC — by round-tripping every node type and asserting
the compiler is total over the grammar and undefined outside it.

---

## 3. Storage: sets store queries, never results

`object_set`:

| Column | Note |
|---|---|
| `set_id`, `name`, `description` | — |
| `case_id` | nullable; a case-scoped set is invisible outside the case |
| `owner` | the actor who created it |
| `created_at`, `created_by` | — |

`object_set_version`:

| Column | Note |
|---|---|
| `set_id`, `version` | monotonic per set |
| `ast` | JSONB, validated |
| `ontology_version` | the composition version pinned at save (§4) |
| `track_interface_members` | boolean, default **false** |
| `as_of`, `as_of_revision` | nullable pins (§4.4) |
| `created_at`, `created_by`, `note` | an edit is a new version with a reason |

**There is no results column and no results table.** The T69 AC ("a stored
definition contains no result rows — schema makes it impossible") is met by
there being nowhere to put them, which is the only way that AC can be met
durably.

Editing a set writes a **new version**. Versions are immutable, so a finding
that names `(set_id, version)` names something that cannot change under it.

---

## 4. Versioning and ontology pinning (ADR-054)

### 4.1 Pinned by default

`ontology_version` is the composition version current at save. Interface
expansion is resolved **at pin time and frozen into the stored AST** as the
explicit member list it expanded to, so the set means the same thing after a
module adds a type.

### 4.2 Opting in to future members

`track_interface_members: true` re-expands interfaces at every evaluation
against the live composition. It is an explicit, per-version choice, recorded
in the version row and visible wherever the set is displayed.

### 4.3 Change notification

When a composition bump adds a member to an interface a tracking set uses, the
set's owner and every principal it is shared with get a notification carrying
the set, the interface, the new member type, and the composition versions on
both sides. Notification is a row, not an email: `object_set_notice`, listed by
the set's own route.

A **pinned** set gets the same notice, worded as an opportunity rather than a
change — its evaluation did not move.

### 4.4 As-of pins

A version may pin `as_of` and/or `as_of_revision`. A pinned set answers the
same question forever, which is what makes it a legitimate analytic input.
An unpinned set answers today's question, which is what makes it a legitimate
watchlist.

---

## 5. Sharing, and the definition as protected data

### 5.1 The FGA type

`object_set` with relations `viewer` and `editor`, granted directly or derived
from a case's membership when `case_id` is set. An unshared set is **absent**
from every list — not 403, absent — for the same reason a non-member gets 404
from a case (spec 06 §2.5).

### 5.2 The definition is protected

B-17: *"a shared set definition can reveal hidden identifiers even if results
are filtered."* A set filtering on `has_nic = '...'` discloses that identifier
to everyone it is shared with, regardless of what the evaluation returns.

Therefore:

1. A set definition is read under the **same field-sensitivity rules as a
   claim**. A `property` node naming a property above the viewer's clearance is
   returned as `{property: "...", op: "...", value: null, withheld: true}` —
   the shape stays, the value does not.
2. A viewer who cannot read the definition can still **evaluate** the set. The
   two are different permissions on purpose: "run the analyst's saved query"
   and "read what the analyst was looking for" are different disclosures.
3. Sharing a set is an audited action naming what was shared with whom.

---

## 6. Evaluation: one snapshot, one authorization context (M-16)

> An evaluation request opens **one** repeatable-read transaction, resolves
> **one** authorization context, and evaluates every node — including every
> composed subset — inside it.

- One snapshot: union, intersection and difference cannot see the corpus change
  between their operands, which is the cardinality/timing channel M-16 names.
- One authorization context: `claim_filters` is built once per request from one
  `UserContext`, and every subquery composes that same list — including subsets
  owned by other people. **A set never evaluates with its owner's clearance.**
- Applied in candidate generation, per spec 11 §4. The rule is one rule; sets
  do not get their own.

The evaluation returns object ids plus the labels and types the caller may
read, `truncated`, and the **evaluation digest** (§8.2). No total.

---

## 7. Composition

`union`, `intersect`, `difference` over evaluated members, under §6's single
snapshot and single authorization context.

The stated identity — the T70 AC — is:

> For a given caller and snapshot, the evaluated membership of a composed set
> equals the corresponding set operation over the evaluated memberships of its
> operands **for that same caller**.

Which is the property that makes composition safe: `difference` cannot be used
to probe, because both operands were already narrowed by the same filters. A
row the caller cannot see is in neither operand, so it is in no result and
changes no cardinality.

`difference` is still the sharpest tool here, so it carries one extra rule: a
composed set whose top-level node is `not` or `difference` over a set the
caller **cannot read the definition of** (§5.2) is refused at save. Otherwise
"everything in Ayesha's set that is not in mine" is a definition-disclosure
oracle run one element at a time.

---

## 8. Analytic runs and findings (H-23)

### 8.1 Three tables, one lifecycle each

| Table | Holds | Lifecycle |
|---|---|---|
| `analytic_run` | the manifest — what was run, over what, by whom | immutable once written |
| `analytic_finding` | one result of a run, with its caveat | immutable; may be **promoted** (§10) or superseded by a later run, never edited |
| `claim` | assertions | Article I; unchanged |

**A finding is not a claim and cannot become one by editing.** The schema test
the charter asks for asserts three things, not one: different tables, no
foreign key that would let a finding be read as a claim, and no write path that
turns a finding row into a claim row (§10 makes a *new* claim, and the finding
survives).

### 8.2 The run manifest (ADR-055)

Immutable, written before the algorithm runs, and complete enough that
"reproduce this" is a mechanical instruction:

| Field | Why H-23 requires it |
|---|---|
| `method`, `method_version` | which algorithm, at which revision of our implementation |
| `implementation` | **which library actually ran** — `leidenalg`, `networkx-louvain` — plus its version, closing O2's silent fallback |
| `parameters`, `seed` | a seeded run is reproducible; an unseeded one is recorded as unseeded rather than pretending |
| `input_kind` | `object_set` or `projection` |
| `object_set_id`, `object_set_version` | the immutable definition (§3) |
| `evaluation_digest` | SHA-256 over the **sorted evaluated member ids** — the input digest H-23 asks for, and the thing that makes "the same inputs" checkable rather than hoped |
| `projection_built_at_revision_id`, `projection_builder_version`, `projection_aggregation_method_version` | *which* projection was read (O3). Not whether it was fresh — that is `is_stale`'s question and it answers a different one |
| `edge_digest` | SHA-256 over the sorted edge rows consumed, so a projection rebuilt between two runs is visible as a different digest |
| `ontology_version`, `identity_revision_id` | what the vocabulary and identity meant |
| `code_version`, `settings_digest` | the release and the configuration |
| `actor`, `purpose`, `authorization_digest` | who ran it, why, and **under which clearance and case membership** — a finding computed under a narrower clearance is a different finding, and saying so is Article VI |
| `caveat_version` | which wording of the caveat this finding carries |
| `started_at`, `finished_at` | — |

**Reproducibility, defined.** Two runs whose manifests agree on every field
above except `actor`, timestamps and `purpose` must produce the same finding
digest. That is testable; "rerunning reproduces the finding" was not.

### 8.3 The finding

| Field | Note |
|---|---|
| `finding_id`, `run_id` | — |
| `finding_type` | the metric (§9) |
| `subjects` | the entity ids the finding is about |
| `value` | JSONB, shaped by the metric |
| `caveat_text`, `caveat_version` | **copied into the row**, not looked up at render time (§9.3) |
| `finding_digest` | SHA-256 over `(finding_type, subjects, value)` |
| `promoted_claim_id` | nullable; set by §10, never cleared |
| `handling_code` | the **maximum** handling code of any claim that contributed — a finding over restricted evidence is restricted |

`handling_code` is derived, not chosen. A finding computed from sensitive
claims and stored as `open` would be the leak that all of §6 exists to prevent,
arriving one level up.

---

## 9. The metric catalog and the caveat catalog (Article IX)

### 9.1 Where each metric lives (ADR-057)

| Metric | Route | Records a finding |
|---|---|---|
| k-hop neighbourhood | `POST /v1/graph/expand` | no — it is a read |
| shortest paths | `POST /v1/graph/paths` | no — it is a read |
| k-hop neighbourhood, **as an analytic** | `POST /v1/analytics/k_hop` | yes |
| shortest paths, **as an analytic** | `POST /v1/analytics/shortest_path` | yes |
| community detection (Leiden) | `POST /v1/analytics/community` | yes |
| betweenness centrality | `POST /v1/analytics/betweenness` | yes |
| degree centrality | `POST /v1/analytics/degree` | yes |
| shared identifier | `POST /v1/analytics/shared_identifier` | yes |

The traversal code is shared — one implementation, one authorization story. The
distinction is whether the answer is **recorded**, and recording is what
demands a manifest, a caveat and an actor.

### 9.2 Graph and weight interpretation (H-23)

Stated once, for every metric:

- The graph is `edge_projection` filtered by the caller's `claim_filters`, with
  entity ids resolved through the active canonical map, unless the manifest
  pins an identity revision.
- It is **undirected** for community, betweenness and degree; direction is a
  property of a predicate, not of a co-occurrence, and treating a directed
  claim as flow is an inference the data does not support.
- It is **unweighted** for path length: hop count only (O4, ADR-030).
- Community detection is the one metric that takes weights, and it takes them
  from the caller — `aegis/analytics/clustering.py` says so and makes no claim
  about what a weight means. The manifest records the weight source, and a run
  whose weights came from the display score says exactly that.
- Multiplex: when more than one predicate category is present, community
  detection optimises across layers jointly rather than flattening. The layer
  set is a manifest parameter.

### 9.3 The caveat catalog

Code-owned, in `aegis/analytics/caveats.py`, versioned, and **copied into every
finding row** — which is what "structural, never UI decoration" means. There is
no rendering path that fetches a caveat, so there is no rendering path that can
fail to.

| Metric | Caveat |
|---|---|
| `k_hop` | Everything reachable within the given number of hops through claims **you** are permitted to read. A different clearance produces a different neighbourhood. This describes the readable record, not the world. |
| `shortest_path` | The shortest route through recorded claims — not the shortest real relationship. A path exists because records exist, and a missing path means missing records, not absence of connection. A path is not a chain of instruction, causation, or responsibility. |
| `community` | A partition computed from edge weights the caller supplied. A cell is a question to investigate, not a finding about membership, affiliation, or shared purpose. Two people in one cell may never have met. |
| `betweenness` | How often an entity lies on a shortest **recorded** path between others. It measures the shape of what has been written down, not the flow of anything real. A high score is a reason to ask why the records connect through this entity — it is not an answer. |
| `degree` | A count of recorded connections. An entity scores highly when it is frequently **reported**, which reflects the reporting. This is not a measure of influence, seniority, control, or responsibility, and the highest score in a graph is not evidence of any of them. |
| `shared_identifier` | Two records carry the same exact identifier. Identifiers are transcribed by people and reused by institutions. This is a strong lead and never an identity decision — only a human adjudication merges identities (Articles V and VII). |

**The leadership rule.** No metric name, no metric label and no rendered
analytics string may describe a centrality score as leadership, seniority,
command, control, or importance. `FORBIDDEN_LANGUAGE` is the word list and
`tests/contract/test_caveat_catalog.py` applies it to the catalog's names and
labels and to the generated UI descriptors — the wording *is* the governance
here, and a template is not a place governance should live.

**Caveat text is exempt from that word list, and held to a stronger rule.** A
caveat's job is to name the wrong reading and deny it, so a word list over
caveats would forbid the sentence *"this is not a measure of seniority"* —
weakening every caveat in the name of enforcing them. Instead every caveat must
contain an explicit denial (`DENIAL_MARKERS`). The bar is low because the
failure it catches is not subtle: a caveat rewritten into a method note is
accurate, useless, and denies nothing.

Bumping a caveat's wording bumps `caveat_version`. Old findings keep the
wording they were issued with; a finding is a record of what was said at the
time, and silently improving the disclaimer on a finding somebody acted on is
not an improvement.

---

## 10. Finding → claim promotion

The audited action `promote_finding`:

1. Requires a human actor with the `analyst` role and a **rationale**
   (`required_text_is_substantive`).
2. Writes a **typed suggestion** of kind `finding_promotion` into the review
   queue — never a claim. Article VII is not relaxed because the producer is
   deterministic.
3. On acceptance, `record_claim` runs with the **reviewer** as actor
   (ADR-031 §2), producing a claim with `assertion_type = 'assessed'` (O7) and
   an `analytic_confidence` the reviewer sets.
4. The claim's `record_id` is the finding's **source record chain**, never an
   invented one (H-23). A finding computed over claims from many records
   promotes against the record the reviewer names as the basis, and the finding
   itself is linked through `analytic_finding.promoted_claim_id` and a
   `claim_relation` of kind `analytic_basis`.
5. **The finding is not consumed.** It remains, immutable, linked. Promoting
   twice is refused — one finding, one assessed claim — but the finding
   continues to exist as the basis of the one that was made.

An assessed claim promoted from a finding is a claim like any other from that
moment: retractable, contradictable, graded, and displayed beside anything that
disagrees with it (Article VIII).

---

## 11. Watchlists (H-24)

### 11.1 What a watchlist is

An object set plus a rule: `watchlist(set_id, set_version, rule, rule_version)`.
The set says *what to watch*; the rule says *what counts as a detection*.

Exact identifiers only. Fuzzy matching is deliberately absent (charter risk
table) and its absence is asserted, not assumed (§12).

### 11.2 A detection is a typed alert suggestion

`suggestion_kind = 'watchlist_hit'`, into the queue that already exists, with:

| Field | Why |
|---|---|
| `watchlist_id`, `rule`, `rule_version` | which rule fired, at which version |
| `inputs` | the claim and entity ids that triggered it |
| `dedupe_key` | `(watchlist_id, rule_version, matched_value, entity_id)` — the same identifier landing twice does not produce two alerts |
| `exactness` | `exact` only, today; the field exists so a future fuzzy rule cannot arrive without declaring itself |
| `authority_ref` | the collection-policy/legal-basis seam (B-08), nullable now, enforced P7 |
| `handling_code` | the maximum of the contributing claims, as §8.3 |

Triage is `new → reviewing → closed`, minimal per GOAL.md §32, with **every
transition audited** and a required reason on `closed`. There is no transition
graph beyond "closed requires a reason" — the same decision spec 09 made for
investigation tasks, for the same reason: a workflow nobody agreed to is a
workflow people route around.

### 11.3 Evaluation is explicit (ADR-056)

`aegis watchlists evaluate [--watchlist ID]` runs the rules and records an
`analytic_run` for the sweep — so a window that was never evaluated is visible
as a gap in the runs, rather than as silence.

- It is **not** a write-path hook. The side-effect outbox spec 08 §6.5 declares
  is not executed by anything, and giving one feature a private hook would make
  the second one harder, not easier.
- Each run records `evaluated_through` (the recorded-at watermark), so the next
  run starts where the last finished and a re-run is idempotent by dedupe key.
- Detections are evaluated under the **watchlist owner's** authorization
  context, which is recorded in the manifest, because an alert nobody may read
  is not an alert. This is the one place a saved artifact runs with its owner's
  clearance rather than the caller's, and it is stated here rather than
  discovered later.

---

## 12. Test obligations

| Obligation | Layer |
|---|---|
| A stored set definition contains no result rows and no SQL text | contract (schema + grammar round-trip) |
| The AST compiler is total over the grammar and rejects everything else | unit |
| Depth, node count, composition depth and cycles are refused at **save**, not at run time | unit + integration |
| A pinned set does **not** gain a new interface member after a minor bump; a tracking set does, and both get a notice | integration |
| Evaluation composes the **caller's** `claim_filters`, never the owner's (except §11.3, asserted explicitly) | contract (structural) + integration |
| A shared set evaluates as a subset for a narrower caller, and a **strict** subset with a seeded restricted member | integration |
| Composed sets equal set algebra over evaluated operands for that caller | property-based |
| A `difference` over a definition the caller cannot read is refused at save | integration |
| A `property` node above clearance reads back `withheld: true` with a null value, and the shape is unchanged | integration |
| Two runs with equal manifests produce equal finding digests | integration |
| The manifest records the implementation that ran, and a forced fallback produces a **different** manifest | unit |
| Findings and claims are separate tables with separate lifecycles; no write path converts one to the other | contract |
| Every metric in the catalog has caveat text; every finding row carries it; no rendering path omits it | contract + ui e2e |
| No metric name, label or rendered string contains leadership language; every caveat contains an explicit denial | contract, word list |
| A finding's `handling_code` is the maximum of its contributing claims | integration |
| Promotion requires an actor and a rationale, produces an `assessed` claim, and survives in audit with the basis attached | integration |
| Promoting the same finding twice is refused; the finding still exists | integration |
| An exact identifier fires; a near-miss does **not** (asserted, not assumed) | integration |
| The same identifier landing twice produces one alert | integration |
| Every triage transition is audited; `closed` without a reason is `422` | integration |
| A watchlist run records its watermark, and a re-run is idempotent | integration |

---

## 13. Non-goals, and what is carried

**Non-goals, this phase:** GNN link prediction and ML anomaly detection
(GOAL.md §13.4 — no explainability story); financial-flow models (no financial
feeds exist); streaming alerts (Kafka trigger); cross-case global dashboards;
fuzzy watchlist matching; bulk *write* operations over a set — a set drives
reads and analytics, and a bulk claim write over a set is an unreviewed
machine write wearing a UI (Article VII).

**Carried:**

| Item | Target | Why not now |
|---|---|---|
| Side-effect outbox execution (spec 08 §11.2) | The first feature that genuinely needs on-write dispatch | ADR-056: watchlists do not, and a mechanism built for a feature that does not need it is a mechanism nobody tests |
| Compartment-aware set sharing | P7 | Compartments do not exist yet; the FGA `object_set` type is declared so P7 adds a relation rather than a model |
| Notification delivery beyond a row | P7 or later | §4.3 records the notice; delivering it is a channel decision, not a governance one |
| Claims picker for hypothesis links (P4 carryover) | Closed here | A hypothesis link picker is an object set with `type: claim` — the picker is the set builder, which is why it waited |
