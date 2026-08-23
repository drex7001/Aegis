# Phase 6 Charter — Search, object sets & governed analytics

Status: **ACTIVE — opened 2026-08-23** (amended 2026-07-18, ADR-033) · tasks:
`../tasks/phase-06.md` (T66–T77), **re-validated by T66 on 2026-08-23**, whose
fourteen divergences are recorded in `../specs/11-search.md` §0 and
`../specs/12-object-sets-analytics.md` §0 and in ADR-050…ADR-057. The 2026-07
review findings tagged P6 are dispositioned there: **B-17** (spec 11 §4, spec 12
§2/§5), **H-22** (spec 11 §3, §8–§10), **H-23** (spec 12 §8.2), **H-24**
(spec 12 §11), **M-11** (ADR-050), **M-13** (spec 11 §0 S7), **M-16** (spec 12
§6) · Constitutional basis: Articles VI, IX, XIII ·
GOAL.md §12, §13, §32, §7.8 (object sets) · ADR-012

## Objective

Find anything you're allowed to find; **save and share what you found**; compute
metrics that explain themselves. This phase adds the missing consumption-layer
primitive adopted from Foundry — the **object set**: a saved, composable,
access-controlled query over objects/interfaces that becomes the working unit
for analytics, watchlists, and bulk operations.

## Architecture layers touched

- **Consumption:** global search; object sets (definition, storage, sharing,
  composition); analytics results as first-class `AnalyticFinding` records.
- **Governance:** authorization applied **in candidate generation** (ADR-012 as
  amended by B-17 — "re-check before hydration" is the wording B-17 rejects,
  and P2's search already does better; spec 11 §4); finding→claim promotion as
  an audited action; every metric ships its caveat.
- **Semantic:** object-set filter grammar targets ontology types *and
  interfaces* (P3), so sets survive ontology growth.

## Deliverables

1. **Global search**: Postgres FTS + trigram + transliteration keys across
   entities, claims, documents; grouped results; **authorization constraints
   applied in candidate generation, not only before hydration** (B-17 —
   post-filtering leaks through ranking/counts/pagination/timing); leak-free
   count/pagination semantics; purpose capture on sensitive hits; one
   versioned normalization pipeline applied identically at write and query
   time (H-22 — no wholesale diacritic stripping without labeled evidence).
2. **Golden multilingual test set**: Sinhala/Tamil/English name variants with
   **numeric targets defined at phase start** (per script: precision@k,
   recall, latency); gates search quality in CI; failure fires the OpenSearch
   trigger **inside this phase, before its gate** (ADR-012, H-22).
3. **Object sets**: filter-tree definitions stored as **validated ASTs**
   (never raw SQL) over ontology types/interfaces; complexity limits (depth,
   nodes, runtime, composition cycles); saved and **versioned, pinned to the
   ontology version by default** with an explicit "track future interface
   members" opt-in + change notification (B-17); FGA `object_set` type for
   sharing; set definitions treated as protected data; composable
   (union/intersect/difference) **evaluated under one snapshot + one
   authorization context per request** (M-16); a shared set never leaks what
   the viewer can't see (Article VI).
4. **Analytics service**: k-hop neighborhoods, shortest paths — **not weighted;
   ADR-030 removed the aggregate weight on purpose, so there is none to
   traverse (spec 12 §0 O4)** — Leiden
   communities, brokerage/betweenness, shared-identifier detection — each run
   records an **immutable run manifest** (input digest/snapshot, projection
   version, identity revision, ontology version, code + settings versions,
   parameters, seed, actor/purpose — H-23) and returns an `AnalyticFinding`
   with method, inputs, and caveat text (Article IX). Findings are a distinct
   table, never claims.
5. **Finding promotion**: finding → review → assessed claim, human-actored and
   audited; the finding stays linked as the claim's analytic basis (never an
   invented source record — H-23).
6. **Watchlists**: exact-identifier watchlists built on object sets; a
   detection is a **typed alert suggestion** (rule + version, inputs, dedupe
   key, confidence/exactness) with triage lifecycle (new/reviewing/closed) —
   Article VII applies to alerts too (H-24); evaluation ownership decided
   in-spec — **explicit/scheduled, never a write-path hook** (ADR-056), because
   the side-effect outbox spec 08 §6.5 declares is still executed by nothing.

## Dependencies

- P3: interfaces (filter grammar), client regen for set/finding types.
- P4: workspace UI (search bar, set builder, findings panel).
- P5 gate closed (strict sequence, ADR-025). Search/set *design* work may
  start after P5 T54 (ontology event shapes fixed); events must be searchable
  and set-filterable at this phase's gate.

## Exit criteria

- [x] Golden search-set precision/recall targets met in CI.
- [x] No metric renders without its caveat text; findings and claims are
      different tables with different lifecycles (Article IX test).
- [x] Promoting a finding requires an actor and survives in audit with its
      analytic basis attached.
- [x] An object set is created, shared case-scoped, and drives both an
      analytic run and a watchlist; a second user with narrower clearance sees
      a correctly narrower evaluation of the *same* set.

## Risks

| Risk | Mitigation |
|---|---|
| Multilingual search quality insufficient in Postgres | Golden set makes it measurable; OpenSearch trigger fires on evidence, not vibes |
| Metrics read as guilt ("most connected = leader") | Article IX caveats are structural: the text is code (`aegis/analytics/caveats.py`), copied into every finding row, and `tests/contract/test_caveat_catalog.py` refuses leadership language and superlatives in any metric name or label — with a non-vacuity check, since a word list that catches nothing proves nothing |
| Object sets become a second authorization system | Sets store *queries*, never results; evaluation always applies the caller's filters at read time |
| Watchlist scope creep toward §32's full alert engine | Exact identifiers only; anything fuzzy waits for a real need |

## Specs to author or update

- [x] `specs/11-search.md` and `specs/12-object-sets-analytics.md` — authored
  at phase start by T66 (filter grammar, finding schema, caveat catalog).
  Both **final**.
- [x] `specs/06-api.md` — search (§2.1), analytics and findings (§2.6), sets,
  watchlists and alerts (§2.9).

## Explicit non-goals

OpenSearch (trigger-gated), GNN link prediction and ML anomaly detection
(GOAL.md §13.4 — stays out until an explainability story exists), financial-flow
models (no financial feeds yet), streaming alerts (Kafka trigger), cross-case
global dashboards.

## Task sketch (expanded into `../tasks/phase-06.md`, T66–T77)

- **A — Search:** indexes, transliteration keys, grouped results, authz
  re-check, golden set + CI gate.
- **B — Object sets:** grammar, storage, FGA type, composition, evaluation
  under caller filters.
- **C — Analytics:** service + finding schema, caveat catalog, workspace panel.
- **D — Promotion & watchlists:** promote action, watchlist evaluation, triage
  statuses.
