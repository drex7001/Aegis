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
GET /v1/search?q=&types=&as_of=&as_of_revision=&cursor=&limit=
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
| `case_id` | copied from the record's recording scope; `NULL` for the general pool |
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

| Stage | What it does | Why it is not something else |
|---|---|---|
| 1. Unicode normalization | NFKC | Gives canonically equivalent sequences one form. NFKD would decompose the Sinhala and Tamil vowel signs this corpus depends on |
| 2. Format-character removal | strips `Cf` (zero-width joiner/non-joiner, bidi marks) | Invisible, inconsistently present in pasted web text, and not letters |
| 3. Separator collapse | `collapse_separators` — anything that is not a letter, mark or digit becomes one space | Keeps `Mn`/`Mc` marks, which `\w` drops. A naive `[^\w]+` mangles exactly the two scripts the corpus needs |
| 4. Case folding | lowercase | — |
| 5. Key generation | `norm_key` (script preserved), `latin_key` (romanized), `phonetic_key` (metaphone) | Three keys, three different claims about similarity. §3.3 |

**Diacritics are not stripped.** H-22 is explicit and so is this spec:
wholesale diacritic removal collapses distinct Sinhala and Tamil names rather
than normalizing equivalent encodings. Any future proposal to strip must arrive
with labelled evidence from the golden set (§9) showing recall gained exceeds
precision lost, and must be recorded as an ADR.

### 3.2 Applied identically at write and query time

The same function, from the same module, at both ends. A test asserts this
structurally rather than by inspection: the query path and the index builder
must call the same named entry point, and
`tests/contract/test_normalization_pipeline.py` fails if either grows its own.

### 3.3 Three keys, three different claims

| Key | Matches | Strength |
|---|---|---|
| `norm_key` | script preserved — Sinhala to Sinhala, Latin to Latin | strongest; a real name match |
| `latin_key` | romanization to romanization — a Latin query reaching a Sinhala name | strong, and lossy in a direction that **manufactures agreement**, so it never outranks a `norm_key` hit at equal similarity |
| `phonetic_key` | metaphone equality | weakest; pinned at a fixed `PHONETIC_SCORE = 0.5` because metaphone collapses genuinely different names |

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

The response is groups, each with `type`, `label` (from the ontology) and
`hits`. Empty groups are **omitted**, never returned with an empty list — a
present group with no hits is a count of zero, which §4.2 just refused to give.

### 5.2 No totals

No `total`, no `approximate_total`, no `hidden_count`, in any group or at the
top level. This is asserted against the OpenAPI document, so a future field
cannot reintroduce one quietly.

### 5.3 Limits

| Limit | Value | Reason |
|---|---|---|
| `q` | ≤ 200 chars | already `MAX_QUERY` |
| `limit` | ≤ 50 per group | already the entity route's clamp |
| groups per response | ≤ 12 | a response is a page, not a corpus dump |
| statement timeout | 3 000 ms | per request, so a pathological trigram query fails as `503` rather than holding a connection |

Ordering is `(score desc, label asc, id asc)` — total and stable, so a cursor
means something.

---

## 6. `as_of` and `as_of_revision` (P5 carryover, closed)

Search accepts both, with exactly the semantics ADR-029 and spec 06 §3 already
define, because `claim_filters` implements them and search composes
`claim_filters`.

- `as_of` restricts candidacy to claims recorded at or before that instant, so
  a search "as of last March" cannot surface an entity known only through a
  claim recorded in June.
- `as_of_revision` resolves identity through that revision, so a merge made
  last week does not retroactively unify two hits in a historical view.
- The two are independent and may be combined.
- A saved object set that pins an as-of evaluates at that as-of (spec 12 §4.4).

---

## 7. Purpose capture on sensitive hits

Opening a hit whose handling code is above `open` records `purpose` in the
audit row (Article X). Capture is at **open**, not at search: requiring a
purpose to type a name trains users to supply a meaningless one, and the audit
value is in knowing why a specific restricted record was read.

The purpose travels as a request field on the detail read, is validated by the
existing `required_text_is_substantive` criterion, and is written to
`audit_log` with the record identifier. A missing purpose on a sensitive open
is a `422`, never a silent default.

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
| Stripping diacritics from the golden set **lowers** the score — the regression fixture that keeps §3.1 honest | unit |
| An identifier near-miss returns nothing | unit + integration |
| Golden-set precision, recall and latency meet §8 | integration, in CI |
| Result groups enumerate `ontology.object_types`, not a literal list | contract |
| `as_of` excludes an entity known only through a later claim | integration |

---

## 12. Non-goals, and what is carried

**Non-goals, this phase:** OpenSearch unless §10 fires; embeddings or semantic
search (no explainability story — GOAL.md §13.4); query spelling correction;
saved searches (an object set is the durable artifact — spec 12); search over
`audit_log` (that is the P7 audit console, ADR-045); cross-case dashboards.

**Carried:**

| Item | Target | Why not now |
|---|---|---|
| Highlighted snippets with span offsets | P8 | The extraction spans P8 produces are what make an offset meaningful; a highlight computed by re-matching the query would be a second normalization pipeline (§3) |
| Search over evidence-item text | P7 | Evidence is custody-governed and its read path is `can_view` on the item, not `claim_filters`. Folding it into one route would put two authorization models behind one query, which is §0 S2's whole objection |
