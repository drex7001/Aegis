# Aegis — Product Specification (scaled)

## 1. Mission

An **ontology-driven intelligence platform** whose first application domain is
lawful, open-source criminal-network analysis — starting with Sri Lankan OSINT
(drug networks, historical underworld, Easter-attack network). The domain rides
a domain-neutral core (Article XIV); the same core grows into the
multi-domain, multi-analyst, multi-agency platform GOAL.md describes.

The defining property is **honesty under governance**: every relationship shown is a
claim with a source, a grading, a time window, and an access decision behind it.

## 2. Users and personas

| Persona | Phase introduced | Needs |
|---|---|---|
| **Analyst** (initially: Ayodhya, solo) | 1 | Ingest documents/media, record claims, explore graph/timeline, review AI suggestions, adjudicate identities |
| **Reviewer / supervisor** | 4 | Approve assessments, adjudicate high-impact merges, manage cases |
| **Auditor** | 1 (role exists from day one) | Read audit trail, verify hash chains, no edit rights |
| **Administrator** | 1 | Manage users/roles/ontology versions — *without* automatic access to intelligence content |
| **External partner** | 7 | Receives disclosure/export packages only; never direct DB access |

Even while a single person plays all roles, the roles exist and are enforced — that is
what makes the later multi-user phases a configuration change instead of a rewrite.

## 3. What Aegis is (capability map)

Tiered per roadmap v2: **MVP** = P0–P2 (★ gate closes P2), **Core** = P3–P6,
**Scale** = P7–P9 (see `roadmap.md`; phase numbers here are v2).

### Knowledge (MVP)
- Claim store: graded, sourced, time-bounded claims (GOAL.md §7.4).
- Entities as identifier containers; identity as a versioned decision ledger
  with reversible merges (ADR-028) and mention-anchored claim arguments
  (ADR-029).
- Contradiction / corroboration links between claims.
- Projections: identity-revision-aware graph + Cypher export, rebuilt from
  claims with honest aggregation (ADR-030).
- One durable React workspace: ingest → review → adjudicate → explore
  (ADR-032).

### Evidence (MVP)
- Content-addressed vault for raw source files (`Files/` → MinIO/object store).
- Hash ledger + provenance envelope per received item.
- Derivative tracking (PDF text, Whisper transcripts already exist — formalized).
- Chain-of-custody events (Core tier for physical-evidence workflows).

### Ingestion (MVP, largely exists)
- PDF (opendataloader), Sinhala A/V (Whisper), pasted text, curated entry.
- Structural (regex) and semantic (LLM) extraction → **suggested claims**.
- Idempotent landing, quarantine on validation failure.

### Investigation (Core)
- Cases with membership-scoped access; hypotheses with supporting/contradicting claims;
  tasks; leads.
- Timeline view; "why connected?" provenance panel; as-of queries.

### Geospatial (Core)
- PostGIS-backed locations with explicit precision; MapLibre map synced to timeline.

### Analytics (Core)
- Deterministic first: k-hop expansion, paths, community detection (Leiden — exists),
  brokerage, shared-identifier discovery. Every metric carries an interpretation warning.
- Analytic findings are a separate type; promotion to claim requires review.

### Governance (MVP for RBAC/audit; Scale for the rest)
- RBAC + ReBAC from Phase 1 (Keycloak + OpenFGA). **This is a hard requirement.**
- Handling codes on every claim/record; append-only hash-chained audit.
- Later: compartments, sealed records, disclosure packages, originator control,
  break-glass, insider-threat queries.

### AI assistance (exists as extraction; governed from Phase 1)
- LLM extraction (Gemini via LangChain — exists) reframed as suggested-claim producer.
- Later: summarization, translation, contradiction detection, hypothesis assistance —
  all through the review queue, all source-cited.

## 4. What Aegis is not

Directly from GOAL.md §2, binding at every phase:

- Not an autonomous accusation system or probable-cause generator.
- Not a universal criminal-risk scorer; no person-level predictive policing.
- Not a system that treats association as guilt or promotes AI output into facts.
- Not (for the foreseeable phases) a real-time streaming platform, a classified-network
  system, or a biometric-matching system.

## 5. Current state → target mapping

| Today (repo) | Status | Becomes |
|---|---|---|
| `pipeline/models.py` `TemporalEdge` (edge-as-fact) | works, wrong primitive | Claim rows; `TemporalEdge` survives only as a projection shape |
| `slugify(name)` as node identity | dangerous at scale | Mention key; identity via versioned clusters (Splink + adjudication) |
| `ConfidenceTag` → derived weight | good instinct | Split into credibility grade + verification status; display weight stays derived |
| `real_dataset.py` curated facts in code | fine for bootstrap | Migration script → sources + claims in Postgres |
| `structural_pass.py`, `semantic_pass.py` | keep | Emit suggested claims instead of edges |
| `pipeline/ingest.py`, `transcribe.py`, `pdf_ingest.py` | keep | Front end of the governed landing zone (provenance envelope, idempotency key) |
| `output/real_graph.json` + Cytoscape UI | kept through Phase 1 | Replaced by the durable React workspace in Phase 2 (ADR-032); explorer + anonymous `/api/*` deleted at T22 (ADR-026) |
| `neo4j_export.py` | keep | Optional projection target (ADR-002) |
| `clustering.py` (Leiden) | keep | Analytics service; results become findings, not node attributes |
| No auth, no audit | gap | Keycloak + OpenFGA + audit log — Phase 1, before new features |

## 6. Success criteria (product level)

1. Any relationship on screen can be traced to its source record in ≤ 2 clicks
   ("why connected?" everywhere).
2. Rebuilding all projections from the claim store reproduces the working graph.
3. Every access is attributable: who, purpose, case, decision — queryable by an auditor.
4. A wrong identity merge is reversible in minutes with full history.
5. Adding a new object type (e.g. `vessel`) touches only the ontology + a migration.
6. The existing dataset (41 nodes / 57 edges / 3 networks) migrates losslessly, with
   its confidence semantics preserved under the richer grading model.
