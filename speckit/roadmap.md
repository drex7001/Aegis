# Aegis Roadmap

Phases are gated by **exit criteria**, not dates. Effort estimates assume one
hands-on developer part-time; treat them as relative sizes. GOAL.md phase numbers
(§40) are cross-referenced. Nothing in a later phase may violate the constitution to
ship earlier.

```
P0 governance ▸ P1 claim store + RBAC ▸ P2 identity & provenance
▸ P3 investigation workspace ▸ P4 geo & events ▸ P5 search & analytics
▸ P6 sharing & governance hardening ▸ P7 scale-out options
```

---

## Phase 0 — Governance before code  *(GOAL.md Phase 0 — this spec kit)*

**Goal.** Decide the rules before schemas exist.

**Deliverables**
- [x] This spec kit (constitution, spec, plan, ADRs, roadmap, detailed specs).
- [x] Starter ontology `ontology/aegis.yaml` (object types, predicates, grading,
      handling codes, actions).
- [ ] Confirm grading normalization tables (specs/02 §5) against the sources you
      actually use.
- [ ] Decide handling-code ladder for an OSINT-only deployment
      (proposed: `open < restricted < sensitive`).

**Exit criteria.** Kit reviewed; ontology validates; you can state, for any feature
idea, which constitutional article governs it.

---

## Phase 1 — Claim store, evidence vault, RBAC, audit  *(GOAL.md Phase 1 · effort: L)*

**Goal.** The prototype's data lives in a governed Postgres claim store; every access
is authenticated, authorized, and audited; the existing UI keeps working, now fed from
a projection.

**Deliverables**
1. `infra/docker-compose.yml`: postgres+postgis, minio, keycloak, openfga + bootstrap.
2. Ontology loader/validator (`aegis.ontology`) + CI check.
3. Alembic schema: `source`, `source_record`, `entity`, `claim`, `claim_relation`,
   `review_queue`, `case_file`, `case_member`, `evidence_item`, `derivative`,
   `custody_event`, `audit_log` (specs/02).
4. Evidence vault adapter; migrate `Files/` + `output/ingest/` with provenance
   envelopes and content hashes.
5. **Legacy migration**: `real_dataset.py` SOURCES → `source` rows; curated
   nodes/edges → entities + recorded claims (mapping in specs/02 §6). LLM/structural
   passes rewired to emit `suggested` claims.
6. AuthN/AuthZ: Keycloak realm, FGA model + tuples, FastAPI dependencies, row filters.
7. Hash-chained audit writer + `aegis audit verify`.
8. Projection builder: claims → `edge_projection` matview + legacy
   `output/real_graph.json` (byte-compatible shape) + optional Cypher.
9. API v1 core routes (specs/06): claims, entities, sources, review queue, graph
   projection, audit (auditor role).

**Exit criteria**
- `aegis projections rebuild` reproduces the current graph (snapshot test green).
- Anonymous request → 401; analyst without case membership → 403; every decision in
  `audit_log`; chain verifies.
- A suggested claim from the Gemini pass can be accepted in the API and appears in the
  rebuilt projection; rejected ones never do.
- Postgres restore + projection rebuild from backup works (tested once).

---

## Phase 2 — Identity resolution & provenance UX  *(GOAL.md Phase 2 · effort: L)*

**Goal.** Slugs stop being identity; every connection explains itself.

**Deliverables**
1. `mention` extraction from source records; legacy slugs become one-mention clusters.
2. Deterministic ER rules (NIC, exact registry identifiers) + Splink pipeline with
   transliteration-aware features (specs/05); candidate pairs with score breakdowns.
3. Adjudication action + queue UI (accept/reject/split/merge, evidence note required);
   versioned `identity_cluster` history.
4. "Why connected?" API + UI panel: claims, sources, contradictions behind any edge.
5. Contradiction/corroboration recording (`claim_relation`) surfaced in the detail
   panel.
6. Review-queue UI for suggested claims (Phase 1 exposed only the API).

**Exit criteria**
- Merging then splitting two identities restores the exact prior state (history test).
- Every rendered edge opens a provenance panel listing ≥ 1 source record.
- A seeded transliteration variant pair (e.g. Sinhala/English spellings) is found by
  Splink, adjudicated, and merges cleanly.

---

## Phase 3 — Investigation workspace  *(GOAL.md Phase 2/§18 · effort: M)*

**Goal.** Work happens inside access-scoped cases, with hypotheses instead of vibes.

**Deliverables**
1. Case CRUD + FGA-scoped membership; claims/evidence linkable to cases.
2. Hypotheses with supporting/contradicting claim links + missing-info notes
   (GOAL.md §18).
3. Tasks/leads (lightweight status columns — no workflow engine, per plan §2).
4. React + TypeScript shell (ontology-driven entity pages, graph view embedded);
   legacy explorer stays until parity.
5. Timeline view over claim/event times with uncertainty rendering; as-of mode
   (`?asOf=`) end-to-end.

**Exit criteria**
- A non-member of a case cannot see its claims via any endpoint (authz matrix test).
- A hypothesis page shows both supporting and contradicting claims (Article VIII).
- "What was recorded before date X?" returns a defensible as-of answer.

---

## Phase 4 — Geospatial & event intelligence  *(GOAL.md Phase 3 · effort: M)*

**Goal.** Places and events become first-class, with honest precision.

**Deliverables**
1. `location` entities with PostGIS geometry + explicit `precision` (exact / centroid /
   area / city / country — GOAL.md §16.4).
2. Event objects (meeting, arrest, travel, observation) with participants — replacing
   binary edges where >2 parties or uncertainty matter (GOAL.md §7.3).
3. MapLibre map view synced with timeline + graph selection.
4. Movement/travel ingestion path (border/press reports → events with sources).

**Exit criteria**
- The same incident renders consistently on map, timeline, and graph from one claim
  set; precision is visually distinct.
- An event with 3+ participants round-trips through API and UI.

---

## Phase 5 — Search & governed analytics  *(GOAL.md Phase 5 · effort: M)*

**Goal.** Find anything you're allowed to find; compute metrics that explain
themselves.

**Deliverables**
1. Global search: FTS + trigram + transliteration keys across entities, claims,
   documents; grouped results; authorization re-check before hydration (ADR-012).
2. Golden multilingual test set (Sinhala/Tamil/English names) gating search quality.
3. Analytics service: k-hop, paths, Leiden communities (exists), brokerage, shared
   identifiers — each returning an `AnalyticFinding` with method, inputs, and caveat
   text (Article IX).
4. Finding-promotion flow: finding → review → assessed claim.
5. Basic watchlists (exact identifiers) with alert triage statuses (GOAL.md §32,
   minimal).

**Exit criteria**
- Golden search set precision/recall targets met.
- No metric renders without its warning; promoting a finding requires an actor and
  survives in audit.

---

## Phase 6 — Sharing & governance hardening  *(GOAL.md Phase 4 + §21–24 · effort: L)*

**Goal.** Ready for a second user you don't fully trust, and for output that leaves
the system.

**Deliverables**
1. Compartments (FGA) incl. informant-pattern separation (pseudonym objects,
   handler-only reads — GOAL.md §21) if/when such data exists.
2. Sealed/expunged handling: judicial-state model, projection exclusion.
3. Disclosure/export packages: manifest, included/redacted field preview, hash
   manifest, recipient record (GOAL.md §27 exchange packages, scaled).
4. Break-glass flow + insider-threat audit queries (bulk reads, off-case access).
5. Legal-authority objects attached to sensitive collections (GOAL.md Rule 4, scaled
   to OSINT: collection-policy references).

**Exit criteria**
- An export never contains handling levels above the recipient's grant; redaction log
  attached.
- A sealed record disappears from all projections but remains for the auditor role.

---

## Phase 7 — Scale-out options  *(GOAL.md Phases 4–6 · effort: as-needed)*

Triggered only by the ADR revisit conditions, not by ambition:

| Upgrade | Trigger (from decisions.md) |
|---|---|
| Neo4j as primary traversal | ADR-002: CTE p95 > 2 s, traversal-dominant |
| OpenSearch | ADR-012: golden-set failure or corpus scale |
| Dagster orchestration | plan §2: ≥ 3 scheduled pipelines |
| Iceberg/Trino event lake | plan §2: DuckDB single-node limits |
| Kubernetes + GitOps | ADR-010: multi-host / agency cell |
| Temporal workflows | plan §2: multi-day human approval chains |
| Federation / sovereign cells | A real second agency (GOAL.md §33.1) |
| Controlled AI assistants beyond extraction | GOAL.md Phase 6 flow (§26) — summarization, contradiction detection, always via review queue |

---

## Standing risks

| Risk | Mitigation |
|---|---|
| Speckit rots as code diverges | Exit-criteria checklists reviewed at each phase close; ADR append-only discipline |
| RBAC friction tempts bypass ("it's just me") | Article VI test: authz dependency required on every route from the first commit |
| Wrong merge contaminates analysis | Article V reversibility + Phase 2 history test |
| LLM output creeps into canon | Article VII: single write path via adjudication action |
| Scope creep toward GOAL.md's full stack | Every infra addition needs an ADR trigger already met |
