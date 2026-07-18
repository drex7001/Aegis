# Aegis Roadmap

This roadmap builds an **ontology-driven intelligence platform**; criminal-
network analysis is its first application domain, not its identity (ADR-023).
The legacy prototype is replaced along the way, never extended.

This is **roadmap v2.1** (ADR-022 structure, ADR-033 content): phases are
grouped into architectural milestones, numbered P0–P9, with a **★ MVP gate**
closing Phase 2. Each phase has a charter in `phases/`; this file is the spine.
GOAL.md §40 defers to this file. Content changes from v2 follow the 2026-07
external-review disposition (`reviews/2026-07-18-external-review-disposition.md`).

## Gate semantics (ADR-025 — binding)

- A phase's charter lists **gate criteria** (its "Exit criteria" checkboxes)
  and **deliverables**. Gate criteria are **non-deferrable**: if one cannot be
  met, the phase stays open, or a superseding ADR amends the charter *before*
  the exit review. Deliverables may carry over with an owner, a target phase,
  and a recorded dependency impact.
- Phases run **strictly in sequence**. Where work may genuinely begin before a
  prior gate closes, the charter names the exact prerequisite task ("may start
  after P4 T43"); the word "soft" is banned.
- Effort estimates assume one hands-on developer part-time; treat them as
  relative sizes. Nothing in a later phase may violate the constitution to
  ship earlier.

```
Milestone I    Governed foundation      P0 governance ▸ P1 claim store + RBAC     [COMPLETE — closure addendum open]
Milestone II   MVP                      P2 identity, provenance & workspace       ★ MVP
Milestone III  Ontology platform        P3 modules & contracts ▸ P4 workspace v2 & object views
Milestone IV   Intelligence domain      P5 events, geo & time ▸ P6 search, object sets & analytics
Milestone V    Trust boundaries & AI    P7 sharing & governance ▸ P8 controlled AI & reasoning
Milestone VI   Production               P9 production certification & scale-out

Deployment gate (phase-independent): ▸ PILOT GATE — minimum operating baseline
before any non-localhost binding or second real user (see §Pilot gate).
```

Reasoning capability arrives in three deliberate steps: **mechanism**
(derived-record functions, first consumer phase) → **deterministic analytics**
(P6 explainable findings) → **assisted reasoning** (P8, suggest-only per
Article VII).

### Numbering map (v1 → v2)

| v1 phase | v2 phase |
|---|---|
| P0 governance | P0 (unchanged) |
| P1 claim store + RBAC | P1 (unchanged) |
| P2 identity & provenance | **P2 MVP** (recomposed: + durable React workspace shell, UI ingest loop, typed suggestions, identity ledger — ADR-028…033) |
| — | **P3 modules & contracts** (module composition, interfaces, TS client — ADR-021 narrowed by ADR-033) |
| P3 investigation workspace | P4 (+ object views) |
| P4 geo & events | P5 |
| P5 search & analytics | P6 (+ object sets) |
| P6 sharing & governance hardening | P7 |
| P7 scale-out trigger table | P9 (certification + triggers); controlled-AI row promoted to **P8** |

---

## Milestone I — Governed foundation *(complete; closure addendum open)*

### Phase 0 — Governance before code *(GOAL.md §40 M-I · this spec kit)*

**Goal.** Decide the rules before schemas exist.

**Deliverables**
- [x] This spec kit (constitution, spec, plan, ADRs, roadmap, detailed specs).
- [x] Starter ontology `ontology/aegis.yaml` (object types, predicates, grading,
      handling codes, actions).
- [x] Grading normalization tables confirmed against the sources actually used —
      exercised by the Phase 1 legacy migration (ADR-011/ADR-016).
- [x] Handling-code ladder for an OSINT-only deployment decided and shipped:
      `open < restricted < sensitive`.

**Exit criteria.** Met — kit reviewed; ontology validates in CI. *(2026-07
review note: the governance conflicts later found — public routes, machine
writes, deferral language — were resolved by ADR-025…027 rather than reopening
P0; the constitution-conformance check is now part of every phase's exit
review.)*

### Phase 1 — Claim store, evidence vault, RBAC, audit *(effort: L · COMPLETE with closure addendum)*

Delivered T1–T16: governed Postgres claim store, content-addressed evidence
vault, Keycloak OIDC + OpenFGA ReBAC + row filters, hash-chained audit,
extraction rewired to a review queue, projection builder, API v1,
backup/restore drill. See `tasks/phase-01.md` and
`reviews/phase-01-exit-review.md` (verdict revised 2026-07-18).

**Phase 1 exit criteria (as defined, all met):**
- [x] `aegis projections rebuild` reproduces the migrated graph (snapshot test).
- [x] Anonymous `/v1/*` request → 401; non-member analyst → 403; every decision
      audited; hash chain verifies.
- [x] A suggested claim can be accepted via API into the projection; rejected
      ones never appear.
- [x] Postgres + vault restore drill executed successfully once.

**Closure addendum (T16a–T16d — blocks P2 implementation milestones, not P2
design tasks):**
- [ ] T16a: interim exposure containment — loopback-default bind + response
      limits on the legacy `/api/*` surface (full retirement lands with P2 T22,
      ADR-026).
- [ ] T16b: FGA revocation inline best-effort delete + documented staleness
      bound (finishes ADR-014's specified behavior).
- [ ] T16c: dependency lockfile + CI pinning (supply-chain minimum, H-33).
- [ ] T16d: documentation honesty pass — statuses, README claims, legacy-only
      runbooks moved under `legacy/` with warnings (B-15/M-01/M-25).

---

## Milestone II — MVP

### Phase 2 — Identity, provenance & analyst workspace *(GOAL.md §40 M-II · effort: XL · ★ MVP gate)*

**Goal.** Slugs stop being identity; every connection explains itself; and the
platform becomes **usable end-to-end by an analyst in one durable UI** — land a
source → extraction suggests → review/adjudicate → governed graph with
provenance. Charter: `phases/phase-02-mvp-identity-provenance.md` · tasks:
`tasks/phase-02.md`.

**Deliverables (summary)**
1. **Design pack first** (blocking): identity decision ledger (ADR-028), claim
   arguments with mention anchors + identity-revision resolution (ADR-029),
   typed suggestion envelope (ADR-031), honest projection semantics (ADR-030)
   — specs 02/05 rewritten before implementation.
2. **Identity core**: mention extraction; deterministic rules as pre-verified
   candidates (never auto-merge, ADR-027); Splink pipeline with
   transliteration-aware features; adjudication actions over the ledger.
3. **Workspace shell (durable, ADR-032)**: React + TypeScript + Vite,
   Keycloak OIDC (PKCE), OpenAPI-generated client; screens: source
   landing/extraction status (B-04), review queue, identity adjudication,
   graph view with provenance panel, entity search. Legacy explorer +
   anonymous `/api/*` deleted when the graph view lands (ADR-026).
4. **Governance in-phase**: field-level sensitivity filtering on reads,
   cursor pagination, route-by-route authorization matrix, governance schema
   seams (collection-policy ref, retention class — nullable, enforced P7).
5. **Quality gates**: ER evaluation harness with numeric precision/recall
   thresholds and review-load bound; fictional deterministic demo fixture.

**Exit criteria — the MVP gate (non-deferrable, ADR-025)**
- Merge → intervening edits → split restores mention-attributable state
  exactly (ledger history test incl. concurrent-decision case).
- Every rendered edge opens a provenance panel listing ≥ 1 source record with
  all three grading dimensions; contradictions render side by side.
- A seeded transliteration variant pair is found by Splink above the recorded
  numeric threshold, adjudicated in the UI, and the graph reflects the merge.
- Field-sensitivity filtering and no-anonymous-route hold on every shipped
  route (authz matrix green; lint has no public exemption).
- **The full ingest → suggest → review → accept → projection loop runs on the
  fictional fixture, driven entirely from the UI by someone who didn't build
  it, following `docs/MVP_DEMO.md`.** (Real-corpus walkthrough runs as an
  authorized manual smoke test, not the blocking gate — H-09.)

---

## Milestone III — Ontology platform

### Phase 3 — Ontology modules & contracts *(GOAL.md §7.8–7.10 · effort: M · ADR-021 narrowed by ADR-033)*

**Goal.** Make "domains are ontology modules" true, and give the workspace a
typed contract. Charter: `phases/phase-03-ontology-v2.md` · spec:
`specs/08-ontology-v2.md` · tasks: `tasks/phase-03.md` (re-validated at start).

**Deliverables (summary)** — **module composition** (platform module + domain
module manifests, namespaces, imports/versions, enable/disable; a tiny second
fictional domain in CI proving zero core-code change — B-07); interfaces +
shared property types; ontology change management (proposals, history, CI
gates); stable OpenAPI operation IDs + generated TypeScript client consumed by
the P2-born workspace. **Moved out** (each lands with its first consumer):
functions execution machinery (first consumer: P5/P6 derived records),
generalized side-effect outbox, Python SDK (first consumer: P8 producers).

**Exit criteria.** A new predicate added via a domain module + proposal flows
to API validation and the TS client with zero hand-written domain code; the
second-domain fixture loads with no core change; CI fails on codegen drift and
on a bump without proposal + history.

### Phase 4 — Investigation workspace v2 & object views *(GOAL.md §18, §29–30 · effort: M/L)*

**Goal.** Work happens inside access-scoped cases; the P2 workspace grows
object views, hypotheses, and time — it is **not** a new UI. Charter:
`phases/phase-04-workspace-object-views.md` · tasks: `tasks/phase-04.md`.

**Deliverables (summary)** — investigation-domain spec authored first (cases /
hypotheses / tasks / leads model + routes — H-17); object views (entity-360:
claim-derived properties, links, timeline, sources, cases — every value opens
its provenance); case UI + FGA-scoped membership with no case-existence leaks;
hypotheses with supporting/contradicting links; ontology-driven generic
screens from UI descriptors + TS client.

**Exit criteria.** Authz matrix holds in the UI (non-member sees nothing via
any endpoint, no existence leak); a hypothesis page shows both sides
(Article VIII); "what was recorded before X?" returns the defined
claim-recording snapshot stamped with identity revision + ontology version
(narrowed as-of, B-11); adding an entity type via ontology alone yields a
working object view.

---

## Milestone IV — Intelligence domain

### Phase 5 — Events, geospatial & time *(GOAL.md §7.3, §16, §17 · effort: M)*

**Goal.** Places and events become first-class, with honest precision —
**claims-first**: asserted geometry, precision, participation, and time are
typed claims; PostGIS tables are projections (B-13). Charter:
`phases/phase-05-events-geo-time.md` · tasks: `tasks/phase-05.md`.

**Deliverables (summary)** — event object types with role-typed participants
(claim-backed); location geometry + separated precision/uncertainty/admin-level
model; MapLibre map synced with timeline + graph; movement/travel ingestion via
suggestions; map privacy (authorized generalization) in the same phase (M-18).

**Exit criteria.** The same incident renders consistently on map, timeline,
and graph from one claim set; precision is visually distinct; an event with 3+
participants round-trips; no canonical mutable geometry column exists (spot
check: geometry projections rebuild from claims).

### Phase 6 — Search, object sets & governed analytics *(GOAL.md §12, §13, §32 · effort: M)*

**Goal.** Find anything you're allowed to find; save and share what you found;
compute metrics that explain themselves. Charter:
`phases/phase-06-search-object-sets-analytics.md` · tasks: `tasks/phase-06.md`.

**Deliverables (summary)** — global search with **authorization applied in
candidate generation, not only hydration** (B-17); golden
Sinhala/Tamil/English test set with numeric targets defined at phase start;
object sets as validated ASTs with complexity limits, versioned definitions,
ontology-version pinning by default; analytics service returning
`AnalyticFinding` with immutable run manifests (inputs digest, identity
revision, code versions — H-23); finding→claim promotion via review;
watchlists as typed alert suggestions with triage lifecycle (H-24).

**Exit criteria.** Golden search-set targets met; no metric renders without
its caveat; a narrower-clearance user's evaluation of a shared set is a strict
subset when restricted rows are seeded; promoting a finding requires an actor
and survives in audit with its basis attached.

---

## Milestone V — Trust boundaries & AI

### Phase 7 — Sharing & governance hardening *(GOAL.md §21–24, §27 · effort: L)*

**Goal.** Ready for a second user you don't fully trust, and for output that
leaves the system. Charter: `phases/phase-07-sharing-governance.md` · tasks:
`tasks/phase-07.md`.

**Deliverables (summary)** — compartments with a canonical Postgres assignment
model projected to FGA (H-26); sealed/expunged handling with a policy
precedence matrix; disclosure/export packages on a standard container (BagIt
profile + signing — H-28) with recipient grants and redaction log; break-glass
with request-time expiry enforcement; **enforcement** of the P2 governance
seams: legal-authority objects, purpose vocabulary in policy, retention
classes with governed disposition (B-08); response-mode policy (omit vs marked
redaction vs counts — H-25).

**Exit criteria.** An export never exceeds the recipient's grant, redaction
log attached; a sealed record disappears from every non-auditor read surface
and survives for the auditor; a compartment outsider never sees compartment
rows via any surface; break-glass requires reason, expires at request time,
and is reviewable as one query.

### Phase 8 — Controlled AI & assisted reasoning *(GOAL.md §26 · effort: M)*

**Goal.** AI accelerates analysts without ever becoming a source of fact.
Charter: `phases/phase-08-controlled-ai.md` · tasks: `tasks/phase-08.md`.

**Deliverables (summary)** — **AI data-egress policy first** (approved
providers/models, prohibited data classes, endpoint allowlist, minimization —
B-18); producers run with credentials that can write only typed suggestions/
derivatives; extraction v2 (ontology-grounded, span-anchored); translation as
derivatives; source-grounded summarization with claim *and* source-span
citations validated against the authorized retrieval set (H-29); hypothesis
assistance; multilingual held-out evaluation with absolute minimums (H-30);
reproducibility = immutable inputs/config/model IDs + cached outputs, not
regeneration.

**Exit criteria.** Every AI output type lands as a typed suggestion or
derivative with source references; a runtime-permission test (not only a code
scan) proves zero direct canonical writes; assistant citations resolve and are
within the authorized set; promotion of any model config has a recorded eval.

---

## Milestone VI — Production

### Phase 9 — Production certification & scale-out *(GOAL.md §33–35 · effort: ongoing)*

Charter: `phases/phase-09-production.md` · tasks: `tasks/phase-09.md`.
The **pilot gate** below is a prerequisite and is *not* this phase: P9
certifies a production deployment tier (observability, SLOs, automated DR
covering the full recovery boundary, pen-test, performance baselines,
runbooks) and evaluates the trigger table against measured numbers.

**Deployment tiers (H-32).** dev (localhost compose) → **pilot** (hardened
single host, pilot gate passed, known availability limits documented) →
**production/agency** (P9 certified; HA/KMS/WORM-replication per GOAL.md
targets — single-host compose is never called this).

**Trigger-gated options** — only when the ADR revisit conditions fire, never
by ambition. Triggers are evaluated **continuously at the phase that observes
the evidence** (H-31); P9's review is the backstop:

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

**Exit criteria.** Baseline items all done; every trigger row evaluated
against measured numbers — fired triggers have a chartered work package
(delivery is chartered separately, not implied); a cold-start deploy from the
runbook succeeds.

---

## Pilot gate — minimum operating baseline (ADR-033 §4)

A **deployment gate, not a phase**: all items must hold before Aegis binds to
a non-localhost interface or serves a second real user, whichever comes first.
Items may be completed any time; none may be waived.

- [ ] TLS on every non-loopback listener.
- [ ] Secrets out of `.env` (compose secrets or equivalent); no secret ever in
      git or docs.
- [ ] Request/body size limits, rate limiting, and security headers on the API
      and UI.
- [ ] Dependency lockfile enforced in CI (T16c) + dependency/container
      scanning.
- [ ] Encrypted, verified backups covering **all non-reconstructible state**
      (Postgres, vault object versions, Keycloak users/config, FGA store
      identity) with a tested restore (B-16 minimum).
- [ ] MinIO Object Lock / legal hold on evidence buckets (documented dev-mode
      exception) + periodic signed audit-checkpoint export to an independently
      protected location (B-09 minimum).
- [ ] Health endpoints + structured logs reviewed; audit-append throughput
      benchmarked under concurrent audited reads (H-37 pre-check).

---

## GOAL.md → roadmap coverage (H-35)

| GOAL.md capability | Status |
|---|---|
| Claims, grading, provenance, evidence, audit, review queue | **Scheduled** P1–P2 |
| Reversible identity, ER, multilingual matching | **Scheduled** P2 |
| Ontology modules, interfaces, typed clients | **Scheduled** P3 |
| Investigation workspace, object views, hypotheses, as-of (narrowed) | **Scheduled** P4 |
| Events, geospatial, timeline, map privacy | **Scheduled** P5 |
| Search, object sets, analytics, watchlists/alert triage | **Scheduled** P6 |
| Compartments, sealing, disclosure packages, break-glass, legal authority, retention enforcement | **Scheduled** P7 |
| Controlled AI (extraction v2, translation, summarization, hypothesis assist) | **Scheduled** P8 |
| Observability, DR automation, pen-test, performance, deployment tiers | **Pilot gate + P9** |
| Communications-metadata & financial-event modules | **Trigger-gated** (no such feed exists; event model must not preclude them — P5 non-goal note) |
| Federation, originator control across agencies, sovereign cells | **Trigger-gated** (second agency) |
| Intelligence-report lifecycle, collection requirements/plans, collaboration (comments/review requests), correction/challenge workflow, privileged-material workflow | **North-star only — not scheduled.** Explicitly out of scope until a real second analyst/agency exists; revisit at the P7 and P9 exit reviews |
| Person-level predictive policing, universal risk scores, autonomous accusation | **Never** (GOAL.md §2, §25 prohibitions) |

---

## Standing risks

| Risk | Mitigation |
|---|---|
| Speckit rots as code diverges | Exit-criteria checklists reviewed at each phase close; ADR append-only discipline; statuses corrected at every review (M-01) |
| MVP scope creep | Anything not needed for the P2 demo loop moves to P3+; the charter's non-goals list is enforced in review |
| Gate erosion ("just this once") | ADR-025: gate criteria cannot be deferred; charter amendments require a superseding ADR before the exit review |
| RBAC friction tempts bypass ("it's just me") | Article VI gate on every governed `/v1/*` route; the legacy `/api/*` exception is loopback-contained and deleted at P2 T22 (ADR-026) |
| Wrong merge contaminates analysis | Article V reversibility + ADR-028 ledger + P2 history tests incl. concurrency |
| Machine output creeps into canon | Article VII + ADR-027: no auto-accept/auto-merge/machine-claim path exists; P8 runtime-permission test |
| Scope creep toward GOAL.md's full stack | Every infra addition needs an ADR trigger already met |
| Solo-dev burnout on the XL Phase 2 | Design pack (T17a–d) is deliberately small and unblocks review; UI screens are function-over-polish; anything cosmetic is P4 |
