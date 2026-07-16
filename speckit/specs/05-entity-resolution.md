# Spec 05 — Entity Resolution

Status: draft for Phase 2 · Constitutional basis: Article V · GOAL.md §10 · ADR-005

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

### 2.1 Deterministic rules (auto-decide, audited as `rule:<name>`)
- NIC exact match (when lawfully present — note current dataset omits NICs for real
  people, so this mostly serves fictional/test data and future authorized data).
- Exact registry identifiers: vehicle registration + jurisdiction, passport + country.
- Same `norm_key` **within one document** (the current implicit rule, now scoped:
  cross-document same-slug is a *candidate*, not an auto-merge — this is the key
  behavior change vs the prototype).

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
(Phase 6 informant compartment).

## 3. Adjudication actions

| Action | Effect |
|---|---|
| `confirm_match` | close B-memberships → open A-memberships; `merged_into` claim on B; note required |
| `reject_match` | records a *negative constraint* (pair never re-suggested unless new evidence type appears) |
| `split_entity` | selected mentions move to a new (or restored) entity; note required |
| `mark_unresolved` | keeps pair visible in an "unresolved identities" list (Article VIII) |

All are single transactions writing membership history + audit + FGA-neutral (identity
changes don't change access; case scoping does).

## 4. Consequences downstream

- Projections rebuild after adjudication (claim subjects/objects reference entities,
  so merges re-aggregate edges automatically).
- Analytics jobs record the identity-cluster version they ran against; findings from
  stale versions are flagged.
- The UI shows a "identity decided by / when / why" line on every entity page.

## 5. Evaluation

- Seeded test set: known transliteration pairs (e.g. "Mohamed"/"Mohammed"/"முகமது"
  variants), known distinct same-name people. Track precision/recall per release of
  the Splink model; model settings versioned in git (`aegis/er/settings.py`).
- Never ship a threshold change without rerunning the evaluation (mini model
  governance — GOAL.md §38, scaled).
