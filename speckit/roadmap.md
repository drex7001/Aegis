# Aegis Roadmap

This roadmap builds an **ontology-driven intelligence platform**; criminal-
network analysis is its first application domain, not its identity (ADR-023).
The legacy prototype is replaced along the way, never extended.

Phases are gated by **exit criteria**, not dates. Effort estimates assume one
hands-on developer part-time; treat them as relative sizes. Nothing in a later
phase may violate the constitution to ship earlier.

This is **roadmap v2** (ADR-022): phases are grouped into architectural
milestones, renumbered P0–P9, and a **★ MVP gate** closes Phase 2 — Aegis must
be a usable, demonstrable product there before any later phase starts. Each
remaining phase has a full charter in `phases/`; this file is the spine.
GOAL.md §40 now defers to this file.

```
Milestone I    Governed foundation      P0 governance ▸ P1 claim store + RBAC        [DONE]
Milestone II   MVP                      P2 identity, provenance & analyst console    ★ MVP
Milestone III  Ontology platform        P3 ontology v2 ▸ P4 workspace & object views
Milestone IV   Intelligence domain      P5 events, geo & time ▸ P6 search, object sets & analytics
Milestone V    Trust boundaries & AI    P7 sharing & governance ▸ P8 controlled AI & reasoning
Milestone VI   Production               P9 production readiness & scale-out
```

Reasoning capability arrives in three deliberate steps: **mechanism** (P3
functions/derivations) → **deterministic analytics** (P6 explainable findings)
→ **assisted reasoning** (P8, suggest-only per Article VII).

### Numbering map (v1 → v2)

| v1 phase | v2 phase |
|---|---|
| P0 governance | P0 (unchanged) |
| P1 claim store + RBAC | P1 (unchanged) |
| P2 identity & provenance | **P2 MVP** (enlarged: + review-queue UI polish, basic search, demo runbook) |
| — | **P3 ontology v2** (new — Foundry-informed semantic/kinetic completion, ADR-021) |
| P3 investigation workspace | P4 (+ object views) |
| P4 geo & events | P5 |
| P5 search & analytics | P6 (+ object sets) |
| P6 sharing & governance hardening | P7 |
| P7 scale-out trigger table | P9 (+ mandatory production baseline); controlled-AI row promoted to **P8** |

---

## Milestone I — Governed foundation *(complete)*

### Phase 0 — Governance before code *(GOAL.md §40 M-I · this spec kit)*

**Goal.** Decide the rules before schemas exist.

**Deliverables**
- [x] This spec kit (constitution, spec, plan, ADRs, roadmap, detailed specs).
- [x] Starter ontology `ontology/aegis.yaml` (object types, predicates, grading,
      handling codes, actions).
- [x] Grading normalization tables confirmed against the sources actually used —
      exercised by the Phase 1 legacy migration (ConfidenceTag → credibility/
      verification map, ADR-011/ADR-016).
- [x] Handling-code ladder for an OSINT-only deployment decided and shipped in
      ontology 0.3.0: `open < restricted < sensitive`.

**Exit criteria.** Met — kit reviewed; ontology validates in CI; every feature
idea can be traced to a governing article.

### Phase 1 — Claim store, evidence vault, RBAC, audit *(effort: L · COMPLETE)*

Delivered T1–T16: governed Postgres claim store, content-addressed evidence
vault, Keycloak OIDC + OpenFGA ReBAC + row filters, hash-chained audit,
extraction rewired to a review queue, projection builder feeding the legacy UI,
API v1, backup/restore drill. See `tasks/phase-01.md` and
`reviews/phase-01-exit-review.md`; divergences recorded as ADR-017…019. All
four exit boxes checked. Charter (retrospective): `phases/phase-01-claim-store.md`
(P0: `phases/phase-00-governance.md`).

---

## Milestone II — MVP

### Phase 2 — Identity, provenance & analyst console *(GOAL.md §40 M-II · effort: L · ★ MVP gate)*

**Goal.** Slugs stop being identity; every connection explains itself; and the
platform becomes **usable end-to-end by an analyst** — land a source →
extraction suggests claims → review/adjudicate → governed graph with
provenance. Charter: `phases/phase-02-mvp-identity-provenance.md` · tasks:
`tasks/phase-02.md`.

**Deliverables**
1. `mention` extraction from source records; legacy slugs become one-mention
   clusters.
2. Deterministic ER rules + Splink pipeline with transliteration-aware features
   (specs/05); candidate pairs with score breakdowns.
3. Adjudication action + queue UI (accept/reject/split/merge, evidence note
   required); versioned identity-cluster history.
4. "Why connected?" API + UI panel: claims, sources, contradictions behind any
   edge.
5. Contradiction/corroboration recording surfaced in the detail panel.
6. Review-queue UI for suggested claims (Phase 1 exposed only the API).
7. Basic entity search (`pg_trgm` over names/aliases/mentions) in API + UI —
   pulled forward from old P5, minimal scope.
8. MVP demo runbook (`docs/MVP_DEMO.md`): scripted full-loop walkthrough on the
   real OSINT corpus.

**Exit criteria — the MVP gate**
- Merging then splitting two identities restores the exact prior state
  (history test).
- Every rendered edge opens a provenance panel listing ≥ 1 source record.
- A seeded transliteration variant pair (Sinhala/English spellings) is found by
  Splink, adjudicated, and merges cleanly.
- **The full ingest → suggest → review → accept → projection loop runs live in
  one sitting, driven from the UI by someone who didn't build it.**

---

## Milestone III — Ontology platform

### Phase 3 — Ontology v2: semantic & kinetic completion *(GOAL.md §7.8–7.10 · effort: M · new, ADR-021)*

**Goal.** `aegis.yaml` grows from vocabulary file into a full ontology-platform
artifact — the Foundry-class layer the rest of the product is built on.
Charter: `phases/phase-03-ontology-v2.md` · spec: `specs/08-ontology-v2.md` ·
tasks: `tasks/phase-03.md` (T29–T40, pre-authored).

**Deliverables (summary)** — DSL v2: **interfaces** + **shared property
types**; **functions registry** (declared derivations; prison co-location
becomes the first computed predicate); **actions v2** (parameters, submission
criteria, side effects); **ontology change management** (proposal → review →
semver + migration, `ontology/history/`); **generated SDKs** (typed Python +
TypeScript clients alongside existing Pydantic/FGA/UI-meta codegen).

**Exit criteria.** A new predicate added to an interface flows to API
validation, FGA stubs, and both SDKs with zero hand-written domain code; a
computed predicate regenerates deterministically; CI fails on codegen drift.

### Phase 4 — Investigation workspace & object views *(GOAL.md §18, §29–30 · effort: M/L)*

**Goal.** Work happens inside access-scoped cases in a real product UI, with
hypotheses instead of vibes. Charter:
`phases/phase-04-workspace-object-views.md` · tasks: `tasks/phase-04.md`
(T41–T53, pre-authored).

**Deliverables (summary)** — React + TypeScript workspace **built on the
generated SDK** (ontology-driven screens); **object views** (entity-360:
claim-derived properties, links, timeline, sources, cases); case UI +
FGA-scoped membership; hypotheses with supporting/contradicting links; tasks/
leads; timeline + as-of mode end-to-end; legacy explorer replaced and deleted
(scope set by analyst needs, not legacy parity — ADR-023).

**Exit criteria.** Authz matrix holds in the UI (non-member sees nothing via
any endpoint); a hypothesis page shows both sides (Article VIII); "what was
recorded before date X?" returns a defensible as-of answer; adding an entity
type via ontology alone yields a working object view.

---

## Milestone IV — Intelligence domain

### Phase 5 — Events, geospatial & time *(GOAL.md §7.3, §16, §17 · effort: M)*

**Goal.** Places and events become first-class, with honest precision.
Charter: `phases/phase-05-events-geo-time.md`.

**Deliverables (summary)** — event object types (meeting, arrest, travel,
observation) with participants, replacing binary edges where > 2 parties or
uncertainty matter; PostGIS geometry + explicit `precision` on locations;
MapLibre map synced with timeline + graph selection; movement/travel ingestion
path.

**Exit criteria.** The same incident renders consistently on map, timeline,
and graph from one claim set; precision is visually distinct; an event with
3+ participants round-trips through API and UI.

### Phase 6 — Search, object sets & governed analytics *(GOAL.md §12, §13, §32 · effort: M)*

**Goal.** Find anything you're allowed to find; save and share what you found;
compute metrics that explain themselves. Charter:
`phases/phase-06-search-object-sets-analytics.md`.

**Deliverables (summary)** — global search (FTS + trigram + transliteration,
authorization re-check before hydration, golden Sinhala/Tamil/English test
set); **object sets** — saved, composable, access-controlled queries (GOAL.md
§7.8) feeding analytics, watchlists, and bulk actions; analytics service
(k-hop, paths, Leiden, brokerage, shared identifiers) returning
`AnalyticFinding` with method + caveats (Article IX); finding→claim promotion;
watchlists with alert triage.

**Exit criteria.** Golden search-set precision/recall targets met; no metric
renders without its warning; promoting a finding requires an actor and
survives in audit; an object set is created, shared case-scoped, and drives
both an analytic run and a watchlist.

---

## Milestone V — Trust boundaries & AI

### Phase 7 — Sharing & governance hardening *(GOAL.md §21–24, §27 · effort: L)*

**Goal.** Ready for a second user you don't fully trust, and for output that
leaves the system. Charter: `phases/phase-07-sharing-governance.md`.

**Deliverables (summary)** — compartments (FGA) incl. informant-pattern
separation; sealed/expunged judicial-state handling with projection exclusion;
disclosure/export packages (manifest, redaction preview, hash manifest,
recipient record); break-glass flow + insider-threat audit queries;
legal-authority objects on sensitive collections.

**Exit criteria.** An export never contains handling levels above the
recipient's grant, with redaction log attached; a sealed record disappears
from all projections but remains for the auditor role.

### Phase 8 — Controlled AI & assisted reasoning *(GOAL.md §26 · effort: M)*

**Goal.** AI accelerates analysts without ever becoming a source of fact —
promoted from the old trigger table to a real phase. Charter:
`phases/phase-08-controlled-ai.md`.

**Deliverables (summary)** — extraction v2 (schema-aware, ontology-grounded
prompts via the generated SDK); Sinhala/Tamil ↔ English translation stored as
derivatives (Article IV); source-grounded summarization; hypothesis assistance
(suggests supporting/contradicting claims); contradiction-detection
suggestions — **all through the review queue** (Article VII).

**Exit criteria.** Every AI output type lands as a suggestion with source
references; a test proves zero direct canonical writes from any AI code path;
assistant answers cite claim IDs.

---

## Milestone VI — Production

### Phase 9 — Production readiness & scale-out *(GOAL.md §33–35 · effort: ongoing)*

Charter: `phases/phase-09-production.md`.

**Mandatory baseline** — OpenTelemetry observability + dashboards; SLOs and
alerting; security hardening pass (secrets, TLS, dependency scanning); backup
automation + scheduled restore drills; pen-test checklist; load/performance
benchmarks on a realistic corpus; operational runbooks.

**Trigger-gated options** — only when the ADR revisit conditions fire, never
by ambition:

| Upgrade | Trigger (from decisions.md) |
|---|---|
| Neo4j as primary traversal | ADR-002: CTE p95 > 2 s, traversal-dominant |
| OpenSearch | ADR-012: golden-set failure or corpus scale |
| Dagster orchestration | plan §2: ≥ 3 scheduled pipelines |
| Iceberg/Trino event lake | plan §2: DuckDB single-node limits |
| Kubernetes + GitOps | ADR-010: multi-host / agency cell |
| Temporal workflows | plan §2: multi-day human approval chains |
| Kafka streaming | plan §2: a real continuous feed exists |
| Federation / sovereign cells | A real second agency (GOAL.md §33.1) |

**Exit criteria.** Baseline items all done; every trigger row either fired and
delivered, or its trigger documented as unmet at review time.

---

## Standing risks

| Risk | Mitigation |
|---|---|
| Speckit rots as code diverges | Exit-criteria checklists reviewed at each phase close; ADR append-only discipline |
| MVP scope creep | Anything not needed for the P2 demo loop moves to P3+; the charter's non-goals list is enforced in review |
| RBAC friction tempts bypass ("it's just me") | Article VI test: authz dependency required on every route from the first commit |
| Wrong merge contaminates analysis | Article V reversibility + Phase 2 history test |
| LLM output creeps into canon | Article VII: single write path via adjudication action; P8 zero-direct-write test |
| Scope creep toward GOAL.md's full stack | Every infra addition needs an ADR trigger already met |
