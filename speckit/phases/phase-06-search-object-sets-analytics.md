# Phase 6 Charter — Search, object sets & governed analytics

Status: charter · tasks pre-authored: `../tasks/phase-06.md` (T66–T77;
re-validated by T66 at phase start) · Constitutional basis: Articles VI, IX,
XIII · GOAL.md §12, §13, §32, §7.8 (object sets) · ADR-012

## Objective

Find anything you're allowed to find; **save and share what you found**; compute
metrics that explain themselves. This phase adds the missing consumption-layer
primitive adopted from Foundry — the **object set**: a saved, composable,
access-controlled query over objects/interfaces that becomes the working unit
for analytics, watchlists, and bulk operations.

## Architecture layers touched

- **Consumption:** global search; object sets (definition, storage, sharing,
  composition); analytics results as first-class `AnalyticFinding` records.
- **Governance:** authorization re-check before result hydration (ADR-012);
  finding→claim promotion as an audited action; every metric ships its caveat.
- **Semantic:** object-set filter grammar targets ontology types *and
  interfaces* (P3), so sets survive ontology growth.

## Deliverables

1. **Global search**: Postgres FTS + trigram + transliteration keys across
   entities, claims, documents; grouped results; authorization re-check before
   hydration; purpose capture on sensitive hits.
2. **Golden multilingual test set**: Sinhala/Tamil/English name variants with
   precision/recall targets gating search quality in CI; failure is the
   documented OpenSearch trigger (ADR-012), not a silent regression.
3. **Object sets**: filter-tree definitions over ontology types/interfaces
   (type, predicate, property, time, case scope); saved and versioned; FGA
   `object_set` type for view/edit sharing; composable (union/intersect/
   difference); evaluated with the caller's row filters at read time — a
   shared set never leaks what the viewer can't see (Article VI).
4. **Analytics service**: k-hop neighborhoods, shortest/weighted paths, Leiden
   communities (exists in projections), brokerage/betweenness, shared-identifier
   detection — each run against a projection or object set, returning an
   `AnalyticFinding` with method, parameters, inputs, and caveat text
   (Article IX). Findings are a distinct table, never claims.
5. **Finding promotion**: finding → review → assessed claim, human-actored and
   audited; the finding stays linked as the claim's analytic basis.
6. **Watchlists**: exact-identifier watchlists built on object sets; alert
   triage statuses (new/reviewing/closed) — minimal per GOAL.md §32.

## Dependencies

- P3: interfaces (filter grammar), SDK regen for set/finding types.
- P4: workspace UI (search bar, set builder, findings panel).
- P5: events searchable and set-filterable (soft — sets ship typed against
  whatever the ontology holds).

## Exit criteria

- [ ] Golden search-set precision/recall targets met in CI.
- [ ] No metric renders without its caveat text; findings and claims are
      different tables with different lifecycles (Article IX test).
- [ ] Promoting a finding requires an actor and survives in audit with its
      analytic basis attached.
- [ ] An object set is created, shared case-scoped, and drives both an
      analytic run and a watchlist; a second user with narrower clearance sees
      a correctly narrower evaluation of the *same* set.

## Risks

| Risk | Mitigation |
|---|---|
| Multilingual search quality insufficient in Postgres | Golden set makes it measurable; OpenSearch trigger fires on evidence, not vibes |
| Metrics read as guilt ("most connected = leader") | Article IX caveats are structural (in the finding record), not UI decoration; wording reviewed once with the analyst persona |
| Object sets become a second authorization system | Sets store *queries*, never results; evaluation always applies the caller's filters at read time |
| Watchlist scope creep toward §32's full alert engine | Exact identifiers only; anything fuzzy waits for a real need |

## Specs to author or update

- `specs/11-search.md` and `specs/12-object-sets-analytics.md` — author at
  phase start (filter grammar, finding schema, caveat catalog).
- `specs/06-api.md` — search, sets, findings, watchlist routes.

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
