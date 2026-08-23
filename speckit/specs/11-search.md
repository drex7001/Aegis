# Spec 11 — Search

Status: **final** (authored 2026-08-23 by T66, the blocking re-validation that
opens Phase 6) · Charter:
`../phases/phase-06-search-object-sets-analytics.md` · Constitutional basis:
Articles VI, X, XIII, XIV · GOAL.md §12 · Findings closed here: B-17 (search
half), H-22, M-11, M-13 · ADR-050…ADR-053

Its governing sentence:

> **Search is a read. It is not a second authorization system, a second
> relevance model, or a second index — and a result you may not see must be
> absent from the scan, not removed from the answer.**

Phase 6 therefore adds **one** search route, **one** normalization pipeline
applied identically at write and query time, and **one** searchable-text
projection for the document text Postgres does not currently hold. The
companion spec for sets, analytics and findings is `12-object-sets-analytics.md`.

---

## 0. What re-validation changed

`tasks/phase-06.md` was pre-authored 2026-07-17, before Phase 3, 4 and 5
existed, and amended 2026-07-18 by ADR-033 without the task text being
rewritten. T66 walked both against the as-built system. Divergences affecting
search are below; those affecting sets and analytics are in spec 12 §0.

| # | The plan said | As built / as required | Disposition |
|---|---|---|---|
| S1 | T67: "authorization **re-check before hydration** (ADR-012)" | That is the pre-amendment wording B-17 rejects, and the as-built system already does better: `aegis/search/entities.py` composes `claim_filters` into a **subquery** that constrains candidate generation (T23c, P2). The plan asks P6 to build something weaker than what shipped in P2 | Task text corrected. §4 states the rule as an **invariant with a test**, not a review habit. No ADR — nothing is being decided, a stale sentence is being fixed |
| S2 | M-11: "avoid parallel endpoints"; the plan adds "global search" beside the existing `GET /v1/search/entities` | Adding a grouped route beside the entity route *is* the parallel-endpoint outcome M-11 names: two ranking models, two pagination implementations, two places to get the leak surface right | **ADR-050** — one route, `GET /v1/search`. `GET /v1/search/entities` is **removed** in the same change and declared with `BREAKING API CHANGE` (spec 06 §7.3). §1 |
| S3 | Charter: search spans "entities, claims, **documents**" | Document text is **not in Postgres**. `derivative.storage_uri` points at the object store and `source_record` holds a hash and a URI. There is nothing to index and no handling code to filter by on a blob | **ADR-051** — a `document_text_projection`, rebuilt from the vault, carrying the record's handling code and case scope. Article XIII applies: it is a cache, and `aegis projections rebuild` reproduces it. §2.3 |
| S4 | H-22: "one **versioned** index/query pipeline applied identically at write and query time" | `norm_key`, `latin_key` and `phonetic_key` exist and are applied at both ends — but **nothing records which version of them produced a stored key**. Changing `collapse_separators` silently desynchronises every stored key from every query key, and the failure mode is missing results, which nothing alerts on | **ADR-052** — `NORMALIZATION_VERSION`, stamped on every stored key row, with a CLI/CI check that stored keys were produced by the running version. §3.4 |
| S5 | T68: "precision/recall computed in CI"; H-22: "targets defined at phase start" | Targets are defined here, in §8, as **numbers per script and resource type**, and they live in code (`aegis/search/targets.py`) so the gate reads the same constants the spec quotes | §8, §9. No ADR — this is the charter being obeyed rather than amended |
| S6 | P5 carryover: "`?asOf=` on **search**" | Geo closed it at T59 and graph at T62; search never had it. A saved object set that filters on a search term (spec 12) makes the historical question real | §6. Closed in T67, not carried further |
| S7 | T67 AC: "the **narrower** of two users gets **strictly fewer** results" | M-13: a narrower user legitimately gets the *same* results when everything matching is `open`. "Strictly fewer" is only true when a restricted matching row is seeded | AC corrected to **subset always, strict subset on a seeded restricted hit**. §11 |

Two things the plan assumed and reality confirms, recorded so nobody re-checks
them: `pg_trgm` is installed (migration `0002`) and `ix_entity_label_trgm` is a
GIN trigram index that already exists; and `claim.excerpt` is an ordinary
Postgres column, so claim-text search needs no projection at all.

---

## 1. One route (M-11, ADR-050)

```
GET /v1/search?q=&types=&asOf=&asOfRevision=&cursor=&limit=
```

`GET /v1/search/entities` is removed. It was P2's first implementation of this
route under a narrower name; P6 is the additive backend expansion M-11 asks
for, and the honest expression of "additive backend, same endpoint" is that the
endpoint stops naming one of its backends.

- `types` selects **result groups** by ontology object type (`person`,
  `organization`, `location`, `arrest`, …) and by the two non-object groups
  `claim` and `document`. Omitted means every group the caller may read.
- Groups follow the ontology (Article XIV): the route enumerates
  `ontology.object_types`, never a hard-coded list, so a new domain module's
  types are searchable the day they are declared.
- Every group is ranked by the same score on the same 0–1 scale (§3.3), and
  every hit reports `matched`, as P2's route already did — a phonetic lead
  must not read as a name match.

**The break is declared, not absorbed.** `aegis api check-contract` reports
`searchEntities: operation removed or renamed`; the PR carries
`BREAKING API CHANGE` and this section is the reason it points at. The only
client is the workspace, which regenerates from the contract in the same
commit (`make openapi`).

---

## 2. What is searchable, and where its text lives

### 2.1 Entities — unchanged

Labels, `aliases` claims, and the mention keys resolved to the entity through
active `identity_membership` (ADR-035). This is P2's implementation and it is
kept: §0 S1 is a correction to the *plan*, not to the code.

### 2.2 Claims — `claim.excerpt` and literal values

Both columns are in Postgres and both are already governed by `claim_filters`,
so claim search is the case where the invariant costs nothing: the same filter
list that authorizes a claim read authorizes its candidacy.

A claim hit renders as **the claim**, never as a free-floating snippet:
subject, predicate, object, grading, source. A snippet without its grading is
the thing Article III exists to prevent.

### 2.3 Documents — a projection, because the text is not here (ADR-051)

| Column | Meaning |
|---|---|
| `record_id` | the `source_record` this text came from |
| `derivative_id` | the extraction that produced it, or `NULL` for text landed directly |
| `content_hash` | the hash of the **text**, so a rebuild is verifiable |
| `text` | the extracted text, `tsvector`-indexed |
| `handling_code` | **copied from the record**, so the row filters like the record |
| *(no `case_id`)* | **`source_record` carries no case scope.** Records live in the general pool and are filtered by handling code alone (spec 06 §2.3). Deriving a scope by aggregating a record's claims would over-restrict (take the max) or leak (take NULL) for any record cited by more than one case, so the column does not exist rather than existing and always being NULL |
| `normalization_version` | §3.4 |
| `built_at` | Article XIII stamp |

Rules:

1. It is a **cache**. `aegis projections rebuild` truncates and reproduces it
   from the vault. Nothing writes to it except the builder.
2. `handling_code` is **copied, never defaulted**. A row whose source record's
   handling code changed since the build would be stale in the *unsafe*
   direction, so the builder is the only writer and the rebuild is what
   corrects it — the same rule the geometry projection follows.
3. Text is stored once per (record, derivative). A re-extraction is a new
   derivative and therefore a new row; the old row goes when its derivative
   does.
4. **No text from a document above the caller's clearance is ever rendered** —
   not as a snippet, not as a highlight, not as a count.

---

## 3. The normalization pipeline, versioned (H-22, ADR-052)

### 3.1 The stages, in order

Corrected against the code on 2026-08-23. The first draft of this section
described a pipeline that does not exist — it said stage 1 was NFKC and that
diacritics are never stripped, and `norm_key` does neither. A spec that
misdescribes a shipped function is worse than no spec, so what follows is what
the code does, and the one change T67 makes to it is marked.

| # | Stage | What actually happens | Why |
|---|---|---|---|
| 1 | Decompose | NFKD (`norm_key`); NFKC (`script_key`, Splink only) | `norm_key` needs marks *separable* so stage 2 can act on them; `script_key` compares Sinhala to Sinhala and must not separate them |
| 2 | **Fold Latin diacritics** | a combining mark is dropped **only when the character it follows is ASCII** — `José` → `jose` | Latin diacritics in this corpus are transliteration noise, and folding keeps `norm_key` identical to the prototype's `slugify` on ASCII, so keys written by the Phase-1 migration still match |
| 3 | **Preserve non-Latin marks** | `Mn`/`Mc` following a non-ASCII base are kept | In Sinhala and Tamil these are **vowel signs that carry meaning**. This is the half of H-22 that matters |
| 4 | Case fold | lowercase | — |
| 5 | Collapse separators | every run of non-letter, non-mark, non-digit characters becomes one `_` | `\w` excludes `Mn`/`Mc`, so a naive `[^\w]+` replaces every Sinhala and Tamil vowel sign with an underscore — mangling exactly the scripts the key exists to preserve |
| 6 | **Ignore format characters** (T67) | `Cf` — ZWJ, ZWNJ, bidi marks — is **removed**, not treated as a separator | Today a zero-width joiner inside a Sinhala word becomes `_` and **splits the token**, so the same name pasted from two web pages produces two keys. This is the one behavioural change T67 makes, and it is why `NORMALIZATION_VERSION` exists (§3.4) |
| 7 | Empty result | `u_<sha256(text)[:16]>` rather than a shared literal | The prototype returned the string `"unknown"`, so every unkeyable mention collided; a digest blocks with itself and nothing else |

**Sinhala and Tamil diacritics are never stripped.** H-22 is explicit, and so
is stage 3: wholesale removal collapses distinct names rather than normalizing
equivalent encodings. Any proposal to strip them must arrive with labelled
evidence from the golden set (§9) showing recall gained exceeds precision lost,
and must be recorded as an ADR.

**Latin diacritics are folded, deliberately**, and the two rules are not in
tension: stage 2 folds a mark whose base is ASCII, stage 3 keeps one whose base
is not. Saying "diacritics are not stripped" without that distinction would
describe neither the code nor what H-22 asks for.

### 3.2 Applied identically at write and query time

The same function, from the same module, at both ends.
`tests/contract/test_search_invariants.py` asserts it structurally rather than
by inspection: only `pipeline.py` may call `norm_key`, `latin_key` or
`phonetic_key`, and there is a non-vacuity check that `pipeline.py` actually
does — a rule nobody satisfies would pass a rule nobody breaks.

**Where the boundary is, and what sits outside it.** `search_keys` is the entry
point for anything that **writes or reads a stored key**: the mention writer
(`aegis/er/mentions.py`), the document projection builder, and every search
query. Three other places compute keys and are deliberately *not* routed
through it:

| Outside | Why | The risk, stated |
|---|---|---|
| `aegis/er/features.py` | Splink comparison values, computed in memory from `raw_text` for one scoring run. They are never stored and never queried against | A name carrying a format character produces a feature that differs from the stored key. Narrow today — the golden set has none — and it moves ER's numeric gate, so it is a change with its own evidence requirement, not a tidy-up |
| `aegis/er/evaluation.py` | The ER golden-set harness, deliberately database-free (spec 05) | Same |
| `resolve_norm_key` (`aegis/er/ledger.py`) | Compares a **producer-supplied node id** against `mention.norm_key`. The producer computes its own slug; the two already "agree for ASCII names" and no more, which `mentions.py` has said since T17 | A producer id containing a format character stops resolving. Narrow — producers emit slugs — but it is the one place the boundary can bite, and it is written down rather than discovered |

Routing ER through the pipeline is the obviously tidier end state. It is not
done here because it changes what Splink blocks on, which moves a gate with
numeric thresholds (spec 05 §6) — and moving a quality gate inside a task about
a different subsystem is how a green number stops meaning anything.

### 3.3 Three keys, three different claims

| Key | Matches | Strength |
|---|---|---|
| `norm_key` | script preserved — Sinhala to Sinhala, Latin to Latin | strongest; a real name match |
| `latin_key` | romanization to romanization — a Latin query reaching a Sinhala name | strong, and lossy in a direction that **manufactures agreement**, so it never outranks a `norm_key` hit at equal similarity |
| `phonetic_key` | metaphone equality | weakest; pinned at a fixed `PHONETIC_SCORE = 0.5` because metaphone collapses genuinely different names |

**Two floors, because they are two different comparisons (T68).** A same-script
comparison holds at `SIMILARITY_FLOOR = 0.35`; a comparison where the query's
script and the mention's script **differ** holds at `CROSS_SCRIPT_FLOOR = 0.10`.

The reason is measured, not assumed. `unidecode` romanizes an abugida by
dropping inherent vowels, so `නිමල් වීරසිංහ` stores as `niml_viirsinh` while an
analyst types `nimal_weerasinghe`. Those are two different romanization
systems, and their trigram similarity sits below what a same-script floor
expects — §8 records what that costs and what relaxing it recovers.

The relaxation is **symmetric and script-aware**: it applies when the two
scripts differ, in either direction, and never when they agree. Scoping it to
"the mention is non-Latin" was tried first and immediately cost precision in
the Tamil bucket, because a Tamil query against a Tamil name is a same-script
comparison where a weak match really is noise.

A hit found only under the relaxed floor reports `matched: "transliterated"`
and renders as a **lead**, beside `phonetic`, rather than as a name match.

`script_key` exists (`aegis/er/translit.py`) and is used by Splink features. It
is **not** stored on `mention` and search does not use it; recorded here so the
next reader does not go looking.

### 3.4 Versioning

`NORMALIZATION_VERSION` is a code-owned string in `aegis/search/pipeline.py`.
Every table storing a derived key carries the version that produced it
(`mention.normalization_version`,
`document_text_projection.normalization_version`).

- The query path stamps its keys with the running version and **only compares
  against rows carrying that version**.
- `aegis search check-index` reports rows at an older version and exits
  non-zero; CI runs it, so a pipeline change that would silently lose recall
  fails the build instead of losing results in production.
- Bumping the version is a **reindex**, not a migration of meaning: old rows
  are rebuilt, never reinterpreted. Nothing in the claim store depends on a
  key, so no claim is affected — which is exactly why keys may be rebuilt and
  claims may not.

---

## 4. Authorization in candidate generation (B-17)

### 4.1 The invariant

> Every candidate-generating query is constrained by the caller's row filters
> **inside the query that chooses candidates**. No search path may generate
> and then filter.

An entity carries no handling code of its own; claims do. So an entity is
reachable only through a claim the caller may read, expressed as a subquery
(`_visible_entity_ids`) rather than a materialized id list — the point being
that the database applies it while choosing candidates.

### 4.2 The leak surfaces, and where each is closed

B-17 lists six. Each gets a mechanism, not a promise:

| Surface | Closed by |
|---|---|
| **Ranking** | Restricted rows never enter the scan, so they cannot displace a permitted row from a page |
| **Counts** | The response carries **no total** for any group (spec 06 §4 default 4). "More results" is `next_cursor` being present, derived from fetching `limit + 1` |
| **Pagination gaps** | Keyset cursors over `(score, label, id)`, carrying **no authority** — every page rebuilds the filters. A restricted row leaves no gap because it was never in the sequence |
| **Timing** | The filters are part of the plan, so a restricted corpus is not scanned and then discarded. Constant time is not claimed — it is not achievable here — but response time is not proportional to the restricted set either |
| **Snippets** | §2.3 rule 4: a snippet can only be generated from a row that already passed the filters, because no other row is present |
| **Resource consumption** | `q` ≤ 200 chars, `limit` ≤ 50 per group, per-branch fetch capped, one statement timeout per request (§5.3) |

### 4.3 What this does *not* claim

It does not claim a caller can infer nothing. A caller who knows a name and
gets no hit learns the corpus holds no **readable** row for it — the same thing
every filtered read on this system tells them, and the honest boundary spec 03
already draws. What it does claim is that no restricted row's content,
existence, position or count reaches the response.

---

## 5. Grouping, counts, pagination

### 5.1 Grouping

The response is groups, each with `group`, `label` (from the ontology) and
`hits`. Empty groups are **omitted**, never returned with an empty list — a
present group with no hits is a count of zero, which §4.2 just refused to give.

**Groups are how a page is displayed, never how it is fetched.** Corrected
during T67: the first draft of §5.3 said "limit ≤ 50 *per group*", which implies
a limit and therefore a cursor per group — and several independent cursors are
the pagination-gap surface §4.2 says is closed. A caller advancing them
separately would see gaps exactly where restricted rows were removed.

So every backend is asked for the same over-fetch, the results merge into **one**
ranked sequence, the page is cut, and only then is the page split into groups.
One total order over one keyset cursor has no gaps to leave, because a row the
filters excluded was never in the sequence.

### 5.2 No totals

No `total`, no `approximate_total`, no `hidden_count`, in any group or at the
top level. This is asserted against the OpenAPI document, so a future field
cannot reintroduce one quietly.

### 5.3 Limits

| Limit | Value | Reason |
|---|---|---|
| `q` | ≤ 200 chars | already `MAX_QUERY` |
| `limit` | ≤ 50 **per page**, across all groups | already the entity route's clamp; per-group would mean per-group cursors (§5.1) |
| groups per response | *(none)* | Corrected during T67. The draft capped it at 12 and truncated **after** the page was cut and after `next_cursor` was computed, so a page spanning more groups than the cap would drop hits the cursor had already passed — invisibly, on this page and the next. **Latent rather than live**: the composition declares 11 groups today, so two more object types would have made it real. A page of N hits cannot produce more than N groups, so the page limit is the only bound needed |
| statement timeout | 3 000 ms | per request, so a pathological trigram query fails as `503` rather than holding a connection |

Ordering is `(score desc, label asc, id asc)` — total and stable, so a cursor
means something.

---

## 6. `asOf` and `asOfRevision` (P5 carryover, closed)

Search accepts both, with exactly the semantics ADR-029 and spec 06 §3 already
define, because `claim_filters` implements them and search composes
`claim_filters`.

- `asOf` restricts candidacy to claims recorded at or before that instant, so
  a search "as of last March" cannot surface an entity known only through a
  claim recorded in June.
- `asOfRevision` resolves identity through that revision, so a merge made
  last week does not retroactively unify two hits in a historical view.
- The two are independent and may be combined, and the response carries the
  `stamp` spec 06 §3 requires of every as-of-capable read — **including when no
  snapshot was asked for**, so a caller can tell a current answer from a
  historical one without re-reading its own request.
- A saved object set that pins an as-of evaluates at that as-of (spec 12 §4.4).

---

## 7. Purpose capture on sensitive hits

Opening a hit whose handling code is above `open` records `purpose` in the
audit row (Article X). Capture is at **open**, not at search: requiring a
purpose to type a name trains users to supply a meaningless one, and the audit
value is in knowing why a specific restricted record was read.

The purpose travels as a `purpose` query parameter on the detail read and is
written to `audit_log` with the record identifier. A missing or blank purpose is
a **`422`, never a silent default** — 422 and not 403 because the caller is
permitted and the *request* is incomplete, and because a 403 here would say
something different about existence than the 404 a caller above their clearance
already gets.

**Which reads this applies to, and why not all of them.** T67 implements it on
`GET /v1/source-records/{id}` — the document open, which is the surface search
newly exposes. It is deliberately **not** applied to claim reads. Opening a
record is a discrete act with a moment; a claim is rendered as one row among
dozens on an object view, and requiring a purpose there would either block the
page or capture one meaningless purpose for forty claims. Extending capture to
claim-level reads is a governance decision that belongs with the audit console
and the response-mode policy (§12, ADR-045, H-25).

"Above `open`" is an **index, not a name**: any handling code ranking above the
first one the ontology declares. A deployment that renames its ladder keeps the
rule (Article XIV).

---

## 8. Numeric targets (H-22)

Defined at phase start, as the charter requires. They live in
`aegis/search/targets.py`; this table restates those constants and
`tests/contract/test_search_targets.py` fails if the two disagree.

**Per script, over the golden set (§9):**

| Script | precision@5 | recall@20 | Notes |
|---|---|---|---|
| Latin | ≥ 0.90 | ≥ 0.85 | the easy case; a miss here is a bug, not a limit |
| Sinhala | ≥ 0.80 | ≥ 0.70 | raw-script matching carries this; romanization is the fallback |
| Tamil | ≥ 0.80 | ≥ 0.70 | same |
| Cross-script (Latin query → Sinhala/Tamil name) | ≥ 0.70 | ≥ 0.60 | what `latin_key` exists for, and it is lossy |

**Per resource type:**

| Type | precision@5 | recall@20 |
|---|---|---|
| entity | ≥ 0.85 | ≥ 0.80 |
| claim | ≥ 0.75 | ≥ 0.70 |
| document | ≥ 0.70 | ≥ 0.60 |

**Latency**, measured on the fictional corpus in CI, single connection:

| Percentile | Budget |
|---|---|
| p50 | ≤ 150 ms |
| p95 | ≤ 400 ms |
| hard timeout | 3 000 ms (§5.3) |

**Identifier false-positive policy.** An identifier query (NIC, phone,
registration number) is matched **exactly, never fuzzily**. A trigram
near-match on an identifier is a false positive with a person's name attached,
and Article IX makes that unacceptable at any recall. The precision target for
identifier queries is **1.00**, and the gate treats a single fuzzy identifier
hit as a failure rather than as a score.

**Authorized-result behaviour** is not a quality metric and is never traded
against one: every target above is computed **only over rows the evaluating
user may read**, and no target may be met by widening what is visible.

### 8.1 What the gate actually measured (T68)

First run against the committed golden set, 29 queries, on the fictional
corpus. Recorded because a target with no measurement beside it is a wish:

| Bucket | precision@5 | recall@20 | Floor | |
|---|---|---|---|---|
| latin | 1.000 | 1.000 | 0.90 / 0.85 | pass |
| sinhala | 1.000 | 1.000 | 0.80 / 0.70 | pass |
| tamil | 1.000 | 1.000 | 0.80 / 0.70 | pass |
| **cross-script** | **0.750** | **0.750** | 0.70 / 0.60 | pass |
| entity | 0.909 | 0.909 | 0.85 / 0.80 | pass |
| claim | 1.000 | 1.000 | 0.75 / 0.70 | pass |
| document | 1.000 | 1.000 | 0.70 / 0.60 | pass |
| latency | p50 7 ms | p95 12 ms | 150 / 400 ms | pass |

**Cross-script is the weakest surface by a wide margin, and the number is not
comfortable.** Two of eight fictional Sinhala and Tamil names are not reachable
from their English romanization at all. The gate passes; the limitation is
real, and `test_search_quality.py` asserts that cross-script stays *below*
same-script so an improvement cannot quietly regress it unnoticed.

The run also found two defects, which is what a first measurement is for:

1. **T67's document rank floor discarded true positives.** `plainto_tsquery`
   already requires every term, so `@@` had matched the right document and
   nothing else — and a floor of 0.02 then threw two of three away for being
   wordy. Correct matches ranked 0.005, 0.020 and 0.091, a twentyfold spread,
   so any single floor over it is arbitrary. `@@` now decides membership and
   `ts_rank_cd` decides order. Document retrieval went 0.333 → 1.000.
2. **One floor was being asked to serve two different comparisons.** §3.3.

---

## 9. The golden set

`data/sample/search/golden-set.json` — **fictional**, deterministic, and in the
same shape as the ER golden set (T26), which is the precedent this follows.

Contents, minimum:

- Name variants of one fictional person across all three scripts.
- **Known-distinct same-name people** — the case that punishes over-normalizing.
- Transliteration variants that are genuinely the same name.
- Transliteration near-misses that are genuinely *different* names — the pair
  that fails if diacritics are stripped.
- Mixed-script strings, initials, and strings carrying format characters.
- Canonically equivalent Unicode sequences (NFC and NFD input) that must score
  identically.
- Identifier queries, exact and near-miss.
- Claim-excerpt and document-text queries.
- At least one **restricted** matching row, so §11's strict-subset assertion is
  not vacuous (M-13).

Every expected result carries its script, its resource type, and whether it is
a true match — so precision and recall are computed, not asserted.

---

## 10. The OpenSearch trigger (ADR-012)

Written next to the numbers that watch it, as the AC requires.

> **Fires when** the golden set fails any §8 target after a documented tuning
> attempt, **or** p95 exceeds 400 ms on the real corpus, **or** the corpus
> passes 500 000 searchable rows.

If it fires, remediation lands **inside Phase 6, before its gate** (H-22), not
as a Phase 9 surprise. Firing is recorded in the exit review with the measured
numbers whether or not the response is to adopt OpenSearch — "we measured and
Postgres held" is a result worth keeping.

### 10.1 The trigger did not fire, and the tuning attempt is the reason

The first run failed cross-script at **0.375** against a 0.60 floor. The
condition says *after a documented tuning attempt*, so one was made and is
documented here.

| Floor for a cross-script comparison | Names found (of 8) | False positives |
|---|---|---|
| 0.35 — the same-script floor | 3 | 0 |
| 0.20 | 3 | 0 |
| 0.15 | 4 | 0 |
| **0.10** | **6** | **0** |
| 0.05 | 8 | 1 |

0.10 doubled recall at no measurable precision cost. Cross-script went 0.375 →
0.750 and the gate passed.

**Two things this deliberately does not claim.** The number is fitted to eight
pairs, which is not many; whoever widens the golden set must re-measure rather
than inherit it. And OpenSearch would not have helped here — the keys are the
problem, not the engine indexing them. A different backend fed the same lossy
romanization returns the same answers, so the remediation for the residual gap
is a **better transliterator**, which is the decision `aegis/er/translit.py`
recorded as waiting on exactly this evidence.

---

## 11. Test obligations

| Obligation | Layer |
|---|---|
| Every candidate-generating query composes `claim_filters` | contract — structural, over the search module |
| A hit the caller's filters exclude is **absent**, not redacted | integration |
| Two users, one query: the narrower's results are a **subset**; with a seeded restricted match, a **strict** subset (M-13) | integration |
| No response carries a total, an approximate total, or a hidden count | contract, over the OpenAPI document |
| A restricted row leaves no pagination gap — paging the full set as both users yields the narrower's set as a subsequence | integration |
| Opening a sensitive hit without a purpose is `422`; with one, the purpose is in `audit_log` | integration |
| Query-time and write-time normalization call the same entry point | contract |
| A stored key at an older `NORMALIZATION_VERSION` fails `aegis search check-index` | integration |
| NFC and NFD spellings of one name score identically | unit |
| Stripping **Sinhala/Tamil** marks from the golden set **lowers** the score — the regression fixture that keeps §3.1 stage 3 honest | unit |
| A zero-width joiner inside a name produces the **same** key as the name without it (§3.1 stage 6) | unit |
| `José` and `Jose` produce the same `norm_key`, and a Sinhala vowel sign is **not** folded — the two halves of the diacritic rule, asserted together | unit |
| An identifier near-miss returns nothing | unit + integration |
| Golden-set precision, recall and latency meet §8 | integration, in CI |
| Result groups enumerate `ontology.object_types`, not a literal list | contract |
| `asOf` excludes an entity known only through a later claim | integration |
| The response carries `stamp` even when no snapshot was asked for (spec 06 §3) | contract |

---

## 12. Non-goals, and what is carried

**Non-goals, this phase:** OpenSearch unless §10 fires; embeddings or semantic
search (no explainability story — GOAL.md §13.4); query spelling correction;
saved searches (an object set is the durable artifact — spec 12); search over
`audit_log` (that is the P7 audit console, ADR-045); cross-case dashboards.

**Carried:**

| Item | Target | Why not now |
|---|---|---|
| A transliterator that survives an abugida | P8, or sooner if the real corpus demands it | §10.1 measured the gap: 2 of 8 fictional Sinhala/Tamil names are unreachable from their English romanization, because `unidecode` drops inherent vowels. `aegis/er/translit.py` recorded PyICU as waiting on exactly this evidence — it is now available, and the decision is a dependency question (heavyweight C binding, unreliable wheels) rather than an open one |
| Highlighted snippets with span offsets | P8 | The extraction spans P8 produces are what make an offset meaningful; a highlight computed by re-matching the query would be a second normalization pipeline (§3) |
| Routing ER feature computation through `search_keys` | With the next ER change that touches blocking | §3.2: it moves what Splink blocks on, and therefore a gate with numeric thresholds. Worth doing beside a change that already has to re-measure them, never as a tidy-up |
| Purpose capture on a restricted **claim** read | P7 | §7: a claim is rendered, not opened. The decision belongs with the audit console (ADR-045) and the response-mode policy (H-25), which is where "what does a withheld thing look like" is settled |
| Search over evidence-item text | P7 | Evidence is custody-governed and its read path is `can_view` on the item, not `claim_filters`. Folding it into one route would put two authorization models behind one query, which is §0 S2's whole objection |
