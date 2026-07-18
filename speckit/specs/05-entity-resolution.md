# Spec 05 — Entity Resolution

Status: active (rewritten 2026-07-18 by P2 **T17a** under ADR-028 — identity
decision ledger, revision chain, persisted candidates, versioned negative
constraints; ADR-027 — nothing algorithmic writes canon; ADR-029 — projections
resolve through the active revision). Schema DDL lives in specs/02 §2; this
file owns the semantics. Where this text conflicts with those ADRs, the ADRs
win. · Constitutional basis: Articles V, VII, VIII, XIII · GOAL.md §10 ·
ADR-005, ADR-027, ADR-028, ADR-029

Wrong merges are the most dangerous failure mode in the platform. Everything here is
reversible, explained, and audited. Timestamps alone cannot prove exact reversal —
a **decision ledger** can, and that is what this spec specifies.

## 1. Model

```
source_record ──▶ mention (raw_text, norm_key, offsets, script)
                     │
                     │ identity_membership — keyed to the revision that
                     │ opened it and to the revision that closed it
                     ▼
                  entity (canonical id — stable forever, never reused)
                     ▲
                     │ resolved through
              entity_canonical_map (rebuildable projection — Article XIII)

  er_candidate ──▶ identity_decision ──▶ identity_revision
   (machine,          (human actor,        (parent → new;
    persisted)         note required)       one per decision)
```

- `slugify()` survives as `mention.norm_key` — a blocking and lookup key only,
  never identity (Article V).
- An entity is **never deleted** on merge. Its memberships close at a revision
  and its id is retained forever. Merge lineage is **ledger metadata**, not a
  claim (ADR-028 §5): the `merged_into` predicate is retired from the ontology
  in the T17 migration, because inventing a source record for administrative
  metadata violates Article I.
- Nothing algorithmic writes any of this. Rules and Splink produce
  `er_candidate` rows; only a human-executed `adjudicate_identity` action
  writes a decision (ADR-027, Article VII).

## 2. Revisions and the ledger

**Every adjudication creates exactly one `identity_decision` and exactly one new
`identity_revision`.** Revisions form a single append-only chain over the whole
store; `revision 0` is the migration baseline (§7). A membership row names the
revision that opened it and, once closed, the revision that closed it — so the
membership set at any revision is reconstructible by selecting rows opened at or
before it and not yet closed at it. This is what makes reversal *provable*
rather than merely likely.

**Invariant (enforced by the database, not by code):** at most one active
membership per mention, as a partial unique index (specs/02 §2). A mention
belongs to exactly one entity at a time, or to none while unresolved.

**Optimistic concurrency (ADR-028 §4).** A decision carries the
`parent_revision_id` it was computed against. The check is *scoped*, not
global: the decision is rejected if any entity in its input scope has had a
membership opened or closed at a revision later than `parent_revision_id`.
A global head check would make every unrelated concurrent adjudication
conflict; a scoped check rejects exactly the decisions whose evidence has gone
stale. A rejected decision is **re-presented** to the analyst with the
intervening decisions shown — never silently retried and never merged blind.

**Decision kinds.** `confirm` · `reject` · `merge` · `split` · `unresolved`.
Each carries actor (always a human — Article VII), an evidence note (required),
input references (candidate id and/or explicit mention set), the parent and
resulting revision, and transaction time.

## 3. Stages (GOAL.md §10.1, scaled)

### 3.1 Deterministic rules — pre-verified **candidates**, never auto-decide (ADR-027)

**Implemented** in `aegis/er/rules.py` (T18); settings versioned in
`aegis/er/settings.py`.

- **Exact registry identifiers.** The engine names no identifier: it iterates
  the predicates the ontology declares `identifier: true`, so a new domain adds
  identifiers by declaring them rather than by editing the rule engine
  (Article XIV). The claim's `jurisdiction` carries the issuer and
  `valid_from`/`valid_to` the validity window. A conflicting issuer or a
  disjoint validity window **suppresses** the candidate rather than raising it,
  because identifiers contain errors, fraud, duplicates and reuse (H-07) — and
  a pre-verified band that admits reissued identifiers launders wrong merges
  through a batch-confirm button.
- Ontology v1.1.0 declares `has_nic` (person), `registered_as` (vehicle) and
  `reachable_on` (phone number). **Passport is not declared**: the ontology has
  no passport property, and inventing domain vocabulary without a competency
  question belongs in the P3 proposal process (specs/08 §7), not in a rule
  engine. Passport matching arrives when the property does.
- Same `norm_key` **within one document** — a candidate, ranked below
  identifier matches and never in the pre-verified band: one document can name
  two different people who share a common name.
- **Cross-document name similarity is deliberately absent here.** It is Splink's
  job (§3.2), where it arrives with a score and a per-feature waterfall instead
  of a bare assertion that two slugs matched.

Rule output is a **pre-verified candidate**: ranked top-of-queue, evidence
attached, batch-confirmable in one human action. `producer` on the candidate is
`rule:<name>`; `decided_by` on the resulting decision is always the human who
confirmed it. Cross-document same-`norm_key` never enters the pre-verified band.

### 3.2 Probabilistic (Splink, DuckDB backend)

**Implemented** in `aegis/er/splink_job.py` with the feature frame in
`aegis/er/features.py` and the keys in `aegis/er/translit.py` (T19).

**Weights are declared, not trained.** Splink can estimate m and u from the
data, but EM on a corpus this size converges to whatever the corpus happens to
contain, and the result would be neither reproducible across runs nor
explainable to a reviewer. Every level therefore carries an explicit starting
probability versioned in `aegis/er/settings.py`; the T26 harness moves them,
with the eval diff in the same PR (§6).

Features (comparison levels):

- Name/alias similarity on **transliteration keys**: a romanized Latin key +
  a raw-script key (Sinhala/Tamil preserved — GOAL.md §10.3); Jaro-Winkler
  levels at 0.92 and 0.85, with raw-script exact match ranked above Latin
  exact match because it never passed through a romanizer.
  **PyICU is not a dependency**: it would give a better romanizer, but it is a
  heavyweight C binding whose wheels are unreliable on the platforms this runs
  on. `unidecode` + `jellyfish` metaphone are used instead, and §6's harness —
  not the name of the library — is what decides whether the romanizer is good
  enough. Keeping the raw-script key alongside the Latin one is what stops a
  lossy romanization from manufacturing agreement invisibly.
- Alias cross-match (any alias of A against any name or alias of B).
- Affiliation overlap (shared organizations).
- Graph context: shared associates, computed from a **versioned projection
  snapshot whose id is recorded on the run** (H-07) — a feature, never a merge
  reason by itself. Without the recorded snapshot, a score is not reproducible.
- Date-of-birth agreement or conflict when present; conflict is strong negative
  evidence.

Blocking rules: same metaphone-on-Latin-key, same 4-character Latin-key prefix,
shared affiliation. The phonetic block is what makes the seeded transliteration
pair comparable *at all* — `Nimal Perera` and the romanized `නිමල් පෙරේරා`
differ too much for a prefix block to catch, but both reduce to `NML PRR`.

Date of birth is compared but is **not** an identifier rule: agreement is weak
evidence (many people share a birthday) while a conflict between two stated
dates is strong negative evidence, so it earns its own comparison level rather
than a deterministic rule. Ontology v1.2.0 adds `born_on` to carry it; the
declared `person.date_of_birth` property had no predicate that could.

Every candidate above threshold is **persisted** to `er_candidate` with its
producer, settings version, graph-snapshot id, and the full per-feature
waterfall — Splink's own explanation, stored verbatim (GOAL.md §10.4). Scores
that exist only in a log cannot be audited or evaluated.

### 3.3 Negative constraints

A `reject` decision writes a **versioned negative constraint** over the pair.
Candidate generation consults constraints before emission: a constrained pair is
not re-emitted while the constraint holds. A constraint is scoped to the
evidence that produced it, so a genuinely new evidence *type* (a newly landed
identifier, not a re-run of the same model) may supersede it with a new
constraint version — the history of both is kept (Article VIII).

### 3.4 Human adjudication

Candidates surface in the review **inbox**, which is a UI composition over
`review_queue` and `er_candidate` (ADR-031 §3) — identity candidates live in
their own table because they are high-volume with their own lifecycle, and are
**not** written into `review_queue` with `producer='splink'`.

Adjudication is mandatory (no batch path) for: cross-document merges, any
entity carrying `sensitivity`-elevated properties, any entity participating in
≥ 10 recorded claims (impact threshold), and any protected-person flag (the P7
informant compartment). `adjudicate_identity` declares
`dual_control_for: [protected_person]` in the ontology; the action layer must
enforce that declaration — today `_require_action` checks only that the action
is declared and audited, which is a gap T20 closes.

## 4. Adjudication actions

**Implemented** in `aegis/er/adjudication.py` with the transaction and audit in
`ActionService.adjudicate_identity` (T20). All four are modes of the single
ontology action `adjudicate_identity`.

| Action | Effect |
|---|---|
| `confirm_match` | ledger decision + new revision: close B-memberships → open A-memberships at the new revision; merge lineage recorded as **ledger metadata** (ADR-028 — not a claim); note required |
| `reject_match` | records a versioned negative constraint (§3.3); the pair is not re-suggested while it holds |
| `split_entity` | ledger decision + new revision: selected mentions move to a new or restored entity; unanchored claims on the split entity route to **re-adjudication** (ADR-029 §4); note required. A split that moves *every* mention is refused — that is a rename, and it would leave the original entity empty while changing nothing knowable |
| `mark_unresolved` | keeps the pair visible in an "unresolved identities" list (Article VIII) — an explicit decision, not an absence of one |

Each is a **single transaction** writing decision + revision + membership
changes + audit row, with the scoped optimistic-concurrency check of §2. Identity
changes are FGA-neutral: they do not change access (case scoping does).

## 5. `entity_canonical_map` — a projection, not a source of truth

A rebuildable map from `entity_id` to its current canonical `entity_id`,
derived by replaying merge lineage from the ledger in revision order (Article
XIII — losing it loses nothing). Projections and queries resolve entity-valued
claim arguments through it (ADR-029 §3); as-of queries may pin an explicit
revision instead of the active one.

- **Cycles.** Lineage is append-only and each merge points the non-surviving
  entity at the survivor, so a cycle can only mean a corrupt ledger. The builder
  **fails the rebuild and names the decisions involved** — it never breaks the
  cycle by picking a winner.
- **Tombstones.** An entity with no active memberships and no lineage target is
  tombstoned: it resolves to itself, is excluded from projections, and is
  retained forever. Ids are never reused.
- A split re-derives the map from the ledger; it never rewrites a claim row.

## 6. Thresholds and evaluation (numeric — H-08)

Thresholds are **recorded here, not in code comments**, and are enforced in CI
by the T26 harness against the fictional golden set (`data/sample/mvp/`). The
values below are the **starting floor**, ratified at the first passing run; they
are tuned only with an eval diff in the same PR (GOAL.md §38 model governance,
scaled).

| Gate | Floor | Measured over |
|---|---|---|
| Pairwise precision, pre-verified rule band | ≥ 0.95 | golden set, rules only |
| Pairwise recall, seeded transliteration set | ≥ 0.70 | seeded Sinhala/English variant pairs |
| Splink candidate emission threshold | match probability ≥ 0.80 | per pair, above blocking — **live** in `aegis/er/settings.py` since T19 |
| Review load | ≤ 50 candidates per 1,000 mentions | full pipeline run |

Golden set composition: known transliteration pairs (e.g.
"Mohamed"/"Mohammed"/"முகமது" variants), known **distinct** same-name people as
hard negatives, common names, and records with missing fields. Fictional data
only — no real-person identifiers ever enter CI fixtures.

Splink settings are versioned in `aegis/er/settings.py` and every run records
its settings version and graph-snapshot id. A threshold or settings change
without a rerun of the evaluation in the same PR is a defect.

## 7. Migration from Phase 1

**Implemented** by `migrations/versions/0007_identity_ledger.py` (T17).
Phase 1 already shipped `mention` and `identity_membership` (migration
`0005_identity_tables.py`); they were the migration substrate, not a blocker.
The T17 Alembic series:

1. Creates `identity_revision` and inserts **revision 0** as the migration
   baseline, actor `system:migration`, note naming this spec.
2. Creates `identity_decision`, `er_candidate`, the negative-constraint table,
   and `entity_canonical_map`.
3. Adds the revision keys to `identity_membership` and backfills every existing
   row as opened at revision 0, closed nowhere — the legacy one-mention clusters
   are thereby **verified as revision 0 of the ledger**, exactly as ADR-005
   promised, with no decision invented for them.
4. Adds the partial unique index enforcing one active membership per mention.
   Any pre-existing violation fails the migration loudly rather than being
   silently de-duplicated.
5. Drops `identity_membership.decided_by`'s `rule:<name>` usage: the producer
   moves to `er_candidate.producer` and `decided_by` becomes a human actor
   reference (ADR-027).
6. Retires the `merged_into` predicate from the ontology. This is a **removal**,
   so specs/01 §4 makes it a *major* change: ontology `0.4.0 → 1.0.0`, the
   prior file archived as `ontology/history/aegis-0.4.0.yaml`, and the data
   migration shipped in the same change. (An earlier draft of this section
   called it minor; that was wrong, and the T17 PR corrected it.) No rows
   existed, since nothing ever wrote the predicate.

The migration is idempotent on re-run and reversible (`downgrade` restores the
Phase-1 shape, losing only ledger rows that the Phase-1 shape cannot express —
stated explicitly in the migration docstring).

## 8. Reversal test plan (ADR-028 §6 — blocking)

The gate criterion is exact reversal, so the tests enumerate more than
merge→split:

| Case | Assertion |
|---|---|
| Multi-merge chain | A←B, then (A+B)←C, then split C out: A+B state is restored exactly, C's mentions return to C |
| Partial split | Only some mentions of a merged entity move out; the remainder keep their memberships and their claim attribution unchanged |
| Intervening edits | Merge → record and retract claims on the merged entity → split: mention-attributable state is restored exactly **with zero claim-row rewrites** |
| Concurrent decision | A decision against a stale parent revision within the same entity scope is rejected and re-presented with the intervening decisions; an unrelated concurrent decision is **not** rejected |
| Late mention | A mention landing after a merge attaches at the current revision and is not retroactively attributed to a pre-merge revision |
| Unanchored claim on split | A manual/assessment claim with no mention anchor routes to re-adjudication, not to a silently chosen side (ADR-029 §4) |
| Canonical-map rebuild | `entity_canonical_map` dropped and rebuilt from the ledger alone reproduces byte-identical resolution (Article XIII) |

Tests live in `tests/integration/` (ledger behavior against real PostgreSQL, so
the partial unique index and transaction semantics are exercised) and
`tests/unit/` (revision arithmetic, cycle detection), tagged
`@pytest.mark.requirement("Article-V", "ADR-028", "T17a")`.

## 9. Consequences downstream

- Projections resolve entity-valued claim arguments **through the active
  identity revision** via `entity_canonical_map` (ADR-029) — merges collapse
  edges and splits restore mention-attributable edges without rewriting any
  claim row. Specified in specs/02 §7.
- Analytics jobs record the identity revision they ran against; findings from a
  stale revision are flagged rather than silently recomputed.
- The UI shows an "identity decided by / when / why" line on every entity page,
  and the full score waterfall on every candidate (specs/07 §6).
