# Spec 05 — Entity Resolution

Status: draft for Phase 2 — **being rewritten by T17a under ADR-027/ADR-028**
(identity decision ledger, persisted candidates, negative constraints, no
auto-decide; `merged_into` becomes ledger metadata, not a claim). Until the
rewrite lands, where this text conflicts with ADR-027/028 the ADRs win. ·
Constitutional basis: Articles V, VII · GOAL.md §10 · ADR-005, ADR-027, ADR-028

Wrong merges are the most dangerous failure mode in the platform. Everything here is
reversible, explained, and audited.

## 1. Model

```
source_record ──▶ mention (raw_text, norm_key)
                     │  identity_membership (versioned, decided_by, evidence note)
                     ▼
                  entity (canonical id — stable forever, never reused)
```

- `slugify()` survives as `mention.norm_key` — a blocking/lookup key only.
- An entity is never deleted on merge; it receives a `merged_into` claim and its
  memberships close (specs/02 §2). Splits reopen them. Full history reconstructible.

## 2. Stages (GOAL.md §10.1, scaled)

### 2.1 Deterministic rules (pre-verified **candidates** — never auto-decide, ADR-027)
- NIC exact match (when lawfully present — note current dataset omits NICs for real
  people, so this mostly serves fictional/test data and future authorized data).
- Exact registry identifiers: vehicle registration + jurisdiction, passport + country
  — with issuer/validity conflict checks (identifiers contain errors, fraud,
  duplicates, and reuse — H-07).
- Same `norm_key` **within one document** — also a candidate (ranked below
  identifier matches).

Rule output is a **pre-verified candidate**: top-of-queue, evidence attached,
batch-confirmable in one human action. `decided_by` on the resulting decision
is always the human; `rule:<name>` survives as the candidate's producer.

### 2.2 Probabilistic (Splink, DuckDB backend)
Features (comparison levels):
- Name/alias similarity on **transliteration keys**: ICU-normalized Latin key +
  raw-script key (Sinhala/Tamil preserved — GOAL.md §10.3); Jaro-Winkler +
  token-set levels.
- Alias cross-match (any alias of A vs any name/alias of B).
- Affiliation overlap (shared organizations).
- Graph context: shared associates via `edge_projection` (contextual matching,
  GOAL.md §10.1) — computed as a feature, not a merge reason by itself.
- Date-of-birth agreement/conflict when present (conflict is strong negative
  evidence).

Blocking rules: same norm_key prefix, same metaphone-on-latin-key, shared affiliation.

### 2.3 Human adjudication
Every probabilistic candidate above threshold enters `review_queue`
(`producer='splink'`, `producer_meta` = per-feature match weights — the GOAL.md §10.4
explanation, verbatim from Splink's waterfall output). Mandatory human decision for:
cross-document merges, any entity with `sensitivity`-elevated properties, any entity
participating in ≥ N recorded claims (impact threshold), protected-person flag
(Phase 7 informant compartment).

## 3. Adjudication actions

| Action | Effect |
|---|---|
| `confirm_match` | ledger decision + new revision: close B-memberships → open A-memberships; merge lineage recorded as **ledger metadata** (ADR-028 — not a claim); note required |
| `reject_match` | records a versioned *negative constraint* (pair never re-suggested unless new evidence type appears) |
| `split_entity` | ledger decision + new revision: selected mentions move to a new (or restored) entity; unanchored claims on the split entity route to re-adjudication (ADR-029); note required |
| `mark_unresolved` | keeps pair visible in an "unresolved identities" list (Article VIII) |

All are single transactions writing a ledger decision + revision + audit, with
optimistic concurrency on the parent revision (ADR-028); FGA-neutral (identity
changes don't change access; case scoping does).

## 4. Consequences downstream

- Projections resolve entity-valued claim arguments **through the active
  identity revision** via the rebuildable `entity_canonical_map` (ADR-029) —
  merges collapse edges and splits restore mention-attributable edges without
  rewriting any claim row.
- Analytics jobs record the identity revision they ran against; findings from
  stale revisions are flagged.
- The UI shows a "identity decided by / when / why" line on every entity page.

## 5. Evaluation

- Seeded test set: known transliteration pairs (e.g. "Mohamed"/"Mohammed"/"முகமது"
  variants), known distinct same-name people. Track precision/recall per release of
  the Splink model; model settings versioned in git (`aegis/er/settings.py`).
- Never ship a threshold change without rerunning the evaluation (mini model
  governance — GOAL.md §38, scaled).
