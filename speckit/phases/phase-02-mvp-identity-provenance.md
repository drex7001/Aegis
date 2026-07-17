# Phase 2 Charter — MVP: Identity, provenance & analyst console ★

Status: ACTIVE (next phase) · Constitutional basis: Articles I, III, V, VII, VIII ·
GOAL.md §10, §12 (minimal), §18 ("Why connected?"), §40 M-II · ADR-005, ADR-022 ·
Tasks: `../tasks-phase-2.md`

## Objective

Two things close this phase, and both must hold at once:

1. **Slugs stop being identity.** Entity identity becomes a versioned cluster of
   source mentions, resolved deterministically and probabilistically, adjudicated
   by humans, and reversible without loss (Article V).
2. **Aegis becomes a usable product — the MVP gate.** An analyst (not the
   developer) can run the entire loop from the UI: land a source → extraction
   suggests claims → review and adjudicate → explore the governed graph where
   every edge explains itself.

Everything in this phase serves one of those two outcomes; anything that serves
neither is out of scope (see non-goals).

## Architecture layers touched

- **Semantic:** identity model (mention → identity cluster → entity) becomes
  real; no ontology DSL changes beyond what adjudication needs.
- **Kinetic:** `adjudicate_identity` action implemented with dual-control hook;
  review/accept/reject actions get their first UI.
- **Consumption:** provenance panel, review-queue UI, basic entity search on the
  existing explorer (React workspace waits for P4).
- **Governance:** identity decisions audited with evidence notes; merge history
  queryable.

## Deliverables

1. **Mention extraction** from source records; legacy slugs become one-mention
   clusters (`decided_by='rule:legacy-slug'` rows already seeded by T8).
2. **Deterministic ER** on exact registry identifiers (specs/05 §2).
3. **Splink pipeline** (DuckDB backend) with transliteration-aware features for
   Sinhala/English name variants; candidate pairs persisted with score
   breakdowns (specs/05 §3).
4. **Adjudication action + queue UI**: confirm/reject/split/merge with a
   required evidence note; versioned identity-cluster history; merge→split
   restores prior state exactly.
5. **"Why connected?" API + panel**: for any edge, the claims, source records,
   gradings, and contradictions behind it.
6. **Contradiction/corroboration surfacing** (`claim_relation`) in the detail
   panel.
7. **Review-queue UI** for suggested claims — accept / edit-then-accept /
   reject, with producer metadata (model, prompt) visible.
8. **Basic entity search**: `pg_trgm` over names, aliases, and mention keys,
   authorization-filtered; search box in the explorer. (Pulled forward from old
   P5 in minimal form; full multilingual search stays in P6.)
9. **MVP demo runbook** `docs/MVP_DEMO.md`: a scripted, repeatable walkthrough
   of the full loop on the real OSINT corpus (Easter-attacks PDF or narcotics
   narrative → suggestions → review → graph).

## Dependencies

- Phase 1 complete: claim store, review-queue API, `mention` /
  `identity_membership` tables (migration 0005), evidence vault, authz row
  filters, projection builder.
- No new infrastructure services (Splink runs embedded on DuckDB — Article XII
  without new containers).

## Exit criteria — the MVP gate

- [ ] Merging then splitting two identities restores the exact prior state
      (history test).
- [ ] Every rendered edge opens a provenance panel listing ≥ 1 source record.
- [ ] A seeded transliteration variant pair (Sinhala/English spellings) is found
      by Splink, adjudicated, and merges cleanly; the graph reflects the merge.
- [ ] **The full ingest → suggest → review → accept → projection loop runs live
      in one sitting, driven from the UI by someone who didn't build it,
      following `docs/MVP_DEMO.md`.**

## Risks

| Risk | Mitigation |
|---|---|
| Splink quality on Sinhala transliteration is poor | Deterministic rules carry the demo; probabilistic threshold tuned on the seeded golden pairs; failure feeds the ADR-012 evidence base, not a blocker |
| UI effort sunk into the legacy explorer feels throwaway | It is throwaway by design — legacy is replaced, never extended (ADR-023). Panels stay minimal HTML/JS; their *APIs* (why-connected, review, search) are the durable artifact and carry unchanged into P4 |
| Wrong merge contaminates the graph | Article V reversibility test is a blocking task, not an afterthought |
| MVP scope creep | Non-goals list below is enforced in review; anything not needed for the demo loop moves to P3+ |

## Specs to author or update

- `specs/05-entity-resolution.md` — promote from draft to final as
  implementation lands; record threshold choices.
- `specs/06-api.md` — add why-connected, identity-adjudication, and search
  routes.
- `specs/07-ui.md` — stage-2 (explorer + panels) is this phase; confirm stage-3
  handoff points for P4.

## Explicit non-goals

React workspace (P4), ontology interfaces/functions/SDK (P3), PostGIS and
events (P5), OpenSearch and full multilingual search (P6), compartments and
disclosure (P7), watchlists (P6), any new LLM capability (P8).

## Task breakdown

See `../tasks-phase-2.md` (T17–T28, Milestones A–C) — authored with this
charter, since this phase is active.
