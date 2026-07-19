# Phase 2 Charter — MVP: Identity, provenance & analyst workspace ★

Status: **COMPLETE 2026-07-20 — ★ MVP GATE PASSED** · Exit review:
`../reviews/phase-02-exit-review.md` · Constitutional basis: Articles I, III,
V, VI, VII, VIII ·
GOAL.md §10, §12 (minimal), §18 ("Why connected?"), §40 M-II ·
ADR-005, ADR-022, **ADR-025…ADR-033** (2026-07 recomposition) ·
Tasks: `../tasks/phase-02.md` · Effort: **XL**

## Objective

Three things close this phase, and all must hold at once:

1. **Slugs stop being identity.** Entity identity becomes a versioned decision
   ledger over source mentions (ADR-028), resolved deterministically and
   probabilistically into *candidates*, adjudicated by humans (ADR-027), and
   reversible without loss — including through intervening edits and concurrent
   decisions (Article V).
2. **Claims survive identity change.** Entity-valued claim arguments carry
   mention evidence and resolve through the active identity revision, so a
   merge collapses the graph and a split restores it without rewriting a
   single claim (ADR-029); projections aggregate honestly (ADR-030).
3. **Aegis becomes a usable product — the MVP gate.** An analyst (not the
   developer) runs the entire loop from **one durable UI** (ADR-032): land a
   source → extraction suggests → review and adjudicate → explore the governed
   graph where every edge explains itself.

Everything in this phase serves one of those outcomes; anything that serves
none is out of scope (see non-goals).

## Prerequisites

- Phase 1 closure addendum T16a–T16d — **satisfied 2026-07-18** (PRs #11–#14).
  It gated Milestones B–D; Milestone A ran in parallel and is now complete
  (T17a–T17d, PRs #17–#20).

## Architecture layers touched

- **Semantic:** identity model (mention → decision ledger → entity) becomes
  real; claim arguments gain mention anchors + identity-revision stamps.
- **Kinetic:** adjudication actions over the ledger with optimistic
  concurrency; typed-suggestion acceptance dispatches through declared actions
  (ADR-031).
- **Consumption:** the durable React + TypeScript workspace shell — source
  landing, review queue, adjudication, graph + provenance, search.
- **Governance:** field-level sensitivity filtering on reads; cursor
  pagination; route-by-route authorization matrix; no anonymous route
  survives this phase (ADR-026).

## Deliverables

**A — Design pack (blocking; specs rewritten before code):**
1. Identity decision ledger schema (spec 05 + spec 02 §2 rewrite — ADR-028).
2. Claim-argument attribution + identity-revision-aware projection semantics
   (spec 02 §3/§7 rewrite — ADR-029/030).
3. Typed suggestion envelope + per-kind dispatch (spec 02 queue rewrite —
   ADR-031).
4. Route authorization matrix + governance schema seams (spec 06 update —
   B-14, B-08).

**B — Identity core:**
5. Mention extraction from source records; legacy slugs verified as
   one-mention clusters.
6. Deterministic ER as **pre-verified candidates** (never auto-merge —
   ADR-027) + Splink pipeline (DuckDB) with transliteration-aware features
   and versioned settings + graph-context snapshot.
7. Adjudication actions (`confirm/reject/split/unresolved`) writing ledger
   decisions + revisions; negative constraints; concurrency control.

**C — Workspace & governed UI loop (ADR-032):**
8. React + TS + Vite shell: Keycloak OIDC (PKCE, `oidc-client-ts`),
   OpenAPI-generated client, CSP/security headers.
9. Screens (function over polish): source landing/extraction status (B-04),
   review queue (typed suggestions), identity adjudication (score waterfall),
   graph view (Cytoscape-in-React) + "why connected?" provenance panel,
   entity search.
10. **Legacy explorer + anonymous `/api/*` deleted** when the graph view
    lands (ADR-026); the deny-by-default lint loses its exemption branch.
11. Projection rebuild v2: identity-revision resolution, honest aggregation,
    core no longer imports `legacy.pipeline` (H-36).

**D — Quality & close-out:**
12. Field-level sensitivity filtering; cursor pagination; authz-matrix tests.
13. ER evaluation harness with **numeric** precision/recall thresholds and a
    review-load bound, in CI.
14. MVP demo: fictional deterministic fixture drives the blocking gate;
    real-corpus walkthrough as authorized manual smoke (H-09);
    `docs/MVP_DEMO.md`.

## Exit criteria — the MVP gate (non-deferrable, ADR-025)

- [x] Merge → intervening claim edits → split restores mention-attributable
      state exactly; a concurrent adjudication against a stale revision is
      rejected and re-presented (ledger history tests).
- [x] Every rendered edge opens a provenance panel listing ≥ 1 source record
      with reliability/credibility/verification shown independently; seeded
      contradictions render side by side.
- [x] A seeded transliteration variant pair (Sinhala/English) scores above the
      recorded numeric threshold, is adjudicated in the UI, and the graph
      reflects the merge; the seeded distinct same-name pair stays unmerged.
- [x] A field with `sensitivity: restricted` is absent from responses to a
      low-clearance caller on every shipped route; the route lint passes with
      **no** public exemption.
- [x] **The full ingest → suggest → review → accept → projection loop runs on
      the fictional fixture, driven entirely from the UI by someone who didn't
      build it, following `docs/MVP_DEMO.md`.**

## Risks

| Risk | Mitigation |
|---|---|
| XL scope for a solo developer | Design pack is small and front-loaded; screens are function-over-polish; anything cosmetic moves to P4; non-goals enforced in review |
| Splink quality on Sinhala transliteration is poor | Deterministic candidates carry the demo; numeric thresholds make quality visible; failure feeds the ADR-012 evidence base — the *fictional-fixture* gate does not depend on Splink quality on real data |
| React toolchain drag (build, CI, e2e) | Vite defaults; one minimal e2e (the demo loop) — not a test pyramid; OpenAPI client is generated, not hand-written |
| Wrong merge contaminates the graph | ADR-028 ledger + ADR-029 attribution make reversal provable; blocking tests incl. concurrency |
| Typed-envelope migration breaks Phase-1 suggestions | T17c includes a data migration for existing queue rows; Phase-1 accept/reject tests keep running |

## Specs to author or update

- `specs/05-entity-resolution.md` — rewritten by T17a (ledger, candidates,
  negative constraints, thresholds).
- `specs/02-data-model.md` — §2/§3/§7/queue rewritten by T17a–T17c.
- `specs/06-api.md` — authz matrix authoritative table (T17d); search,
  identity, provenance routes; pagination convention implemented.
- `specs/07-ui.md` — rewritten for the single durable workspace (ADR-032).

## Explicit non-goals

Object views/cases/hypotheses/timeline (P4 — the shell ships without them),
ontology modules/interfaces/TS-SDK-from-ontology (P3 — P2 uses the
OpenAPI-generated client), PostGIS and events (P5), OpenSearch and full
multilingual FTS (P6), object sets and watchlists (P6), compartments and
disclosure (P7), any new LLM capability (P8), UI polish beyond function.

## Task breakdown

See `../tasks/phase-02.md` (T17–T28 with lettered subtasks, Milestones A–D) —
rewritten 2026-07-18 with this charter (ADR-033).
