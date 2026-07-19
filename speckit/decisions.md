# Architecture Decision Records

Format: Context → Decision → Consequences → Revisit when.
Status is **Accepted** unless noted. Amend by appending a superseding ADR, never by
editing history.

---

## ADR-001: Claims are the core primitive; edges become projections

**Context.** The prototype stores relationships as `TemporalEdge` — an edge *is* a
fact with one confidence tag. GOAL.md Rule 2 and §41.1 require claims with provenance,
grading, time, and mutual contradiction. Both ChatGPT's and Claude's designs agree on
this point.

**Decision.** Introduce a `claim` table as the only canonical relationship/attribute
store. The multiplex edge shape (`TemporalEdge`) survives only as a *projection* built
from recorded claims, so the existing UI, clustering, and Neo4j export keep working.

**Consequences.** One migration (curated dataset → claims); extraction passes change
their output type; contradiction/corroboration/retraction become possible; slight read
overhead paid once per projection rebuild, not per query.

**Revisit when.** Never — constitutional (Article I).

---

## ADR-002: PostgreSQL-first; graph database is an optional projection

**Context.** GOAL.md §11.5 recommends Neo4j Enterprise first. Claude's counterpoint:
Palantir-style systems are columnar + indexed joins underneath; recursive CTEs cover
1–3-hop expansion; graph DBs only pay off when traversal dominates. We are one analyst
with tens of thousands of claims at most for years.

**Decision.** PostgreSQL 16 is the system of record and the traversal engine
(recursive CTEs over an `edge_projection` materialized view). Keep the existing
`neo4j_export.py` as an optional projection for analysts who want Cypher.

**Consequences.** One database to operate, back up, and secure; ACID writes with
row-level authorization filters in the same engine; no graph-DB licence or cluster.
Deep traversal (> ~4 hops) and graph algorithms run in Python (igraph/leidenalg —
already in the stack) over projected subgraphs.

**Revisit when.** Benchmarked bounded expansion p95 > 2 s on realistic data
(GOAL.md §34 target) or traversal becomes the dominant access pattern.

---

## ADR-003: The ontology is a declarative, versioned YAML artifact

**Context.** Claude: "Ontology first… Everything else generates from this. Get this
wrong and nothing else saves you." GOAL.md's NIEM discussion (§1.4) points the same
way. The prototype hard-codes types in `models.py`.

**Decision.** `ontology/aegis.yaml` declares object types, properties (+ sensitivity),
predicates (+ category, replacing the fixed `LayerType`), event types, grading schemes,
handling codes, and actions. A loader/validator/codegen module derives Pydantic
validators, DDL enum values, FGA object types, and UI descriptors.

**Consequences.** Adding a domain type is a data change; the four current layers become
predicate categories (extensible — e.g. `communication` can be added without code);
ontology changes are reviewed like code and semantically versioned.

**Revisit when.** Never — constitutional (Article XI). DSL details may evolve.

---

## ADR-004: OpenFGA for ReBAC + roles now; Keycloak for identity

**Context.** RBAC is a stated hard requirement. GOAL.md §23.2 wants RBAC+ABAC+ReBAC;
Claude: "OpenFGA or Cedar, decided early. Retrofitting ABAC is agony." Candidates:
Casbin (embedded, weak ReBAC ergonomics), Cedar (policy-as-code, relationship modeling
awkward), OpenFGA (Zanzibar-style, native case-assignment/handler-of modeling, Python
SDK, single light container), SpiceDB (similar, heavier).

**Decision.** Keycloak (docker) is the OIDC identity provider; OpenFGA (docker) stores
the authorization model (`infra/fga/model.fga`) and relationship tuples. Case
membership, compartments, and handler-of are FGA relations. Handling-code clearance is
an attribute check enforced as SQL row filters (ABAC-lite). All behind a `PolicyPort`
so the engine is swappable.

**Consequences.** Two more containers in compose; authorization is real from Phase 1;
multi-user later is tuple writes, not a rewrite.

**Revisit when.** Policy needs exceed relationships + clearance (e.g. purpose-based
rules with rich conditions) → add OPA in front, keep FGA for relationships.

---

## ADR-005: Splink for entity resolution; identity clusters, never slug identity

**Context.** The prototype uses `slugify(name)` as identity — same spelling merges,
different spelling splits. GOAL.md §10 calls wrong merges the most dangerous failure;
Claude: "Splink… don't hand-roll fuzzy matching." Sinhala/Tamil/English transliteration
makes name-only matching worse.

**Decision.** Names in source records become **mentions**. Deterministic rules (NIC,
passport+country, registration+jurisdiction) and Splink (DuckDB backend; features:
normalized name, aliases, transliteration keys, affiliations, co-occurrence) produce
scored candidate pairs with explanations. Membership of mentions in an
`identity_cluster` is versioned; merges/splits are analyst actions recorded in audit.

**Consequences.** ER becomes a reviewable process; the migration keeps current slugs
as initial one-mention clusters, so nothing breaks on day one.

**Revisit when.** Never for reversibility (Article V); the matching model itself is
expected to evolve.

---

## ADR-006: One modular Python/FastAPI application (ports & adapters)

**Context.** GOAL.md §36 recommends Kotlin/Spring for the core, §37 warns against
premature microservices. Existing code, ingestion stack, and the analyst's skills are
Python; FastAPI already serves the UI.

**Decision.** A single `aegis` Python package with domain/actions/queries/adapters
layering (GOAL.md §37 internal layering). No domain import of SQLAlchemy/FGA/MinIO
types. Extraction (`pipeline/`) remains a separate producer feeding the review queue.

**Consequences.** One deployable, fast iteration, no cross-language contract overhead.
CPU-heavy analytics (Leiden, Splink) stay in-process or as CLI jobs — acceptable at
this scale.

**Revisit when.** A second maintainer/team, or a service needs independent scaling or
a different security boundary (GOAL.md §37 extraction criteria).

---

## ADR-007: Evidence vault = content-addressed object store + hash ledger (no blockchain)

**Context.** GOAL.md §5.1/§20 requires immutable originals, derivative lineage, custody
events; NIST (cited there) says a tamper-evident ledger beats blockchain for evidence
units.

**Decision.** MinIO (S3 API, versioned bucket; local-FS adapter for dev) keyed by
`sha256/<first2>/<hash>`; `evidence_item`, `derivative`, and `custody_event` tables in
Postgres; the append-only hash-chained `audit_log` doubles as the integrity ledger for
registration/transfer events.

**Consequences.** `Files/` and `output/ingest/` migrate into the vault with provenance
envelopes; re-upload of the same bytes is a no-op (idempotency by content hash).

**Revisit when.** Agency deployment demands S3 Object Lock/WORM or HSM-backed signing.

---

## ADR-008: Bitemporal-lite time model on claims

**Context.** GOAL.md §7.7 wants five time axes. Full bitemporal SQL machinery is heavy;
but "what did we know on date X" is a core product promise.

**Decision.** Every claim carries: `event_time_earliest/latest` (uncertainty interval),
`valid_from/valid_to`, `recorded_at` (knowledge/system time collapsed — one agency, so
they coincide), `retracted_at`. As-of queries filter on `recorded_at`/`retracted_at`;
temporal snapshots on `valid_*`. Authorization time is deferred until legal-authority
objects exist (Phase 6).

**Consequences.** The existing UI time slider maps to `valid_*` unchanged; as-of
audit questions become answerable without full bitemporal tables.

**Revisit when.** Multi-agency ingestion separates "they knew" from "we learned"
(then split knowledge time from system time).

---

## ADR-009: LLM extraction output is a suggested claim in a review queue

**Context.** The Gemini semantic pass currently writes edges directly into the merged
graph (pruned but unreviewed). GOAL.md §26 and Article VII forbid AI-created facts.

**Decision.** `semantic_pass.py` (and future AI assists) emit rows with queue status
`suggested`, carrying model id/version, prompt hash, and excerpt. A human accepts
(possibly editing grading/assertion type), or rejects with reason. `--semantic` builds
for exploration render suggested claims *visually distinct* and excluded from canonical
projections.

**Consequences.** The audit story for every AI-derived link is complete; extraction
quality becomes measurable (acceptance rate per model/prompt version — feeds GOAL.md
§38 model governance later).

**Revisit when.** Never — constitutional (Article VII).

---

## ADR-010: Docker Compose deployment until the federation phase

**Context.** GOAL.md §33 assumes Kubernetes, service mesh, GitOps. One host, one
analyst today.

**Decision.** `infra/docker-compose.yml` runs postgres+postgis, minio, keycloak,
openfga; the API runs via uvicorn (dev) or a container (prod-ish). Backups =
`pg_dump` + MinIO mirror, scripted and tested.

**Consequences.** Minutes to stand up; the compose file documents the target topology
that later maps 1:1 onto Kubernetes manifests.

**Revisit when.** Second host, second agency cell, or availability targets that a
single node can't meet.

---

## ADR-011: Original grading preserved + normalized; display weight derived

**Context.** GOAL.md §1.2 (don't collapse to `confidence = 82%`; don't hard-code one
national scheme). The prototype's `EXTRACTED/INFERRED/AMBIGUOUS → 1.0/0.7/0.4` is a
good derived-weight discipline but conflates source, credibility, and verification.

**Decision.** Claims store `reliability` (of source, on the source), `credibility`
(of the information), `verification_status`, and optional `analytic_confidence` —
each with `scheme + original + normalized`. The legacy tags map via a fixed table
(see specs/02). UI/clustering weight remains a *pure function* of normalized values,
never stored as truth.

**Consequences.** 5×5×5 / 3×5×2 / Admiralty inputs can be ingested faithfully;
the "weight cannot be gamed" property of the prototype is preserved and strengthened.

**Revisit when.** Never — constitutional (Article III). Mapping tables may grow.

---

## ADR-012: Search on Postgres first (FTS + pg_trgm), OpenSearch later

**Context.** GOAL.md §11.6 assumes OpenSearch. Corpus today: dozens of documents,
thousands of claims. Sinhala/Tamil need script-aware normalization more than they need
a search cluster.

**Decision.** tsvector FTS + `pg_trgm` fuzzy + stored transliteration keys (ICU) on
names/aliases/documents. `SearchPort` abstraction; results return ids that re-enter the
authorization filter before hydration (GOAL.md §11.6's rule, kept).

**Consequences.** No extra cluster; multilingual quality tracked by a small golden
test set of Sinhala/Tamil/English name queries.

**Revisit when.** Golden set precision/recall fails, or corpus growth makes Postgres
FTS latency unacceptable.

---

## ADR-013: Ontology vocabularies are enforced in the application layer, never as DDL

**Context.** ADR-003 listed "DDL enum values" among codegen targets, and T4 originally
CHECK-constrained vocabulary columns from ontology-generated sets. External review
(2026-07) flagged the coupling: every predicate/type addition would demand an Alembic
migration, and altering constraints on a live database for routine domain updates is
operational risk. There is also a deeper correctness problem: claims are immutable and
stamped with `ontology_version` (specs/01 §4); a DB constraint can only encode the
*current* ontology, so rows recorded under earlier versions would violate it after any
rename/removal.

**Decision.** Vocabulary columns (`predicate`, `entity_type`, `source_type`, grading
values, `handling_code`, …) are plain TEXT. The actions layer validates every write
against the loaded ontology registry (the T3 loader) and stamps `ontology_version`.
DB CHECK constraints remain only for *code-owned* structural invariants: object_id XOR
object_value, no self-claims, time sanity, `claim_relation.relation` values,
queue/record status state machines.

**Consequences.** Ontology evolution = YAML change + review, zero DDL. Historical
claims stay valid under the version that admitted them. The DB no longer rejects
vocabulary garbage on its own — so every write path must go through the actions layer;
direct-SQL writes are already forbidden (specs/03 §4) and the app DB role's grants
enforce it. The `aegis/store/_generated/enums.py` codegen target is dropped (the
registry itself is the validator). Partially supersedes ADR-003's codegen list.

**Revisit when.** A second writing application appears that cannot share the Python
actions layer — then consider DB reference tables synced from the ontology (FK to
lookup rows: data changes, still not DDL).

---

## ADR-014: OpenFGA tuples are a projection of Postgres, synced via transactional outbox

**Context.** `assign_case_member` mutates Postgres and must push a tuple to OpenFGA.
Committing Postgres and then calling FGA over the network is a classic dual-write: an
FGA failure after commit leaves membership without permissions — or, on revocation,
permissions without membership. Specs/03 originally hand-waved "one transaction +
outbox-style retry"; external review (2026-07) correctly demanded the real pattern.

**Decision.** Postgres is the sole source of truth for authorization-relevant
relationships (`case_member`, evidence↔case, custodian). FGA tuples are a **derived
projection** of those rows — Article XIII applies to authorization state too. Mutating
actions write the row change *and* an `authz_outbox` row (specs/02 §4) in the same
transaction; a dispatcher drains the outbox into FGA writes/deletes with idempotent
retries. `aegis authz rebuild` re-derives the full tuple set from Postgres for
recovery and audit comparison. Revocations additionally attempt a best-effort
synchronous FGA delete in the request path to shrink the exposure window; the outbox
remains the guarantee.

**Consequences.** No split-brain: FGA lagging a grant fails closed (user briefly lacks
access — safe); FGA lagging a revocation is bounded by the inline delete attempt plus
dispatcher latency. Costs one table and one small dispatcher loop (in-process task in
the API; `aegis authz sync` runs it manually in dev) — no new infrastructure.

**Revisit when.** Outbox drain latency breaches what revocation windows tolerate →
move the dispatcher to a dedicated worker process (same table, same semantics).

---

## ADR-015: Audit hash chain stays synchronous; asynchronous chaining rejected

**Context.** External review (2026-07) noted that hash-chaining
(`entry_hash = H(prev_hash ‖ entry)`) serializes concurrent writers on the chain head
and recommended offloading hashing to an async worker or batch Merkle process.

**Decision.** Keep chaining synchronous inside the action's transaction. The proposed
fix trades away exactly the property the chain exists for: rows waiting on a background
hasher are an unhashed tamper window, and the worker is new infrastructure with its own
failure modes. Aegis's write profile is human-rate actions plus single-writer batch
jobs; serialized appends comfortably cover it (throughput ceiling ≈ 1/commit-latency —
hundreds of audited actions per second on local disk, orders of magnitude above need).

**Consequences.** Audit integrity holds at the moment of commit with no
eventual-consistency caveat — the right posture for an evidence-handling system.
Concurrent audited actions serialize on the audit insert; at this scale that is
unmeasurable.

**Revisit when.** Measured contention — audited-action p95 degraded by chain-head
waits under real multi-user load. Escape hatch, in order: batch one transaction's
audit rows into one chain entry; then per-shard chains with periodic Merkle anchoring
(an anchor row chains the shard heads). Never unhashed rows.

---

## ADR-016: The ontology is legacy-free; migration adapters own all legacy vocabulary

**Context.** v0.1.0 of `ontology/aegis.yaml` carried prototype residue: a
`legacy-confidence-tag` grading scheme consumed only by the T8 migration, lineage
comments ("legacy FIN"), and predicates that hard-coded dataset narrative into
vocabulary — place names (`helped_establish_in_dubai`), compound relations
(`sibling_co_attacker_of` = kinship + joint attack), and credibility prefixes
(`suspected_successor_leader_of`). User direction (2026-07): put things in their
proper place; no legacy maintenance in the domain artifact.

**Decision.** The ontology (v0.2.0) declares only timeless domain vocabulary, under
three rules: **no place names** (location lives on the claim), **no compound
relations** (record multiple claims), **no credibility words** in predicate names
(grading carries the doubt — Article III). All legacy mappings — the
ConfidenceTag→grading map and the verb-remap table (specs/02 §6) — live in
`aegis/migration/legacy.py`, consumed once by T8 and validated against the ontology
registry at run time.

**Consequences.** Compound legacy edges split into multiple claims, which the claims
model expresses properly (`sibling_of` + `co_attacker_with` from one source record);
"suspected_" prefixes become credibility caps; T8's reconciliation changes from 1:1
to table-driven (each edge → ≥ 1 claim, splits logged in the migration report).
Predicate count 32 → 30 while covering the same facts with reusable vocabulary.
Version bumped 0.1.0 → 0.2.0 with no data migration — no claims exist yet (T4
pending).

**Revisit when.** Never for the principle. The remap table grows only if more legacy
sources are migrated — and it grows in the migration module, not the ontology.

---

## ADR-017: Predicate objects may be entity-or-literal; ontology → 0.3.0

**Context.** The legacy `affiliations` field (specs/02 §6) resolves to an organization
entity "when it exists, else literal". The v0.2.0 ontology could express only a pure
entity object or a pure `literal` object, so `affiliated_with` could not carry both a
resolved org reference (`Madush → NTJ`) and an unresolved label (`"Madush drug
network"`) under one predicate. The T8 migration and the T9 extraction rewire both
need the fallback.

**Decision.** A predicate's `object` may be a list of object types that also contains
the string `literal` (e.g. `affiliated_with: {object: [organization, literal]}`),
meaning the object may be an entity of those types *or* a JSON literal. The loader
exposes `allows_entity` / `allows_literal` / `entity_object_types`; the actions layer
validates whichever form a claim supplies. `object: [literal]` alone is rejected as
redundant (use the string form `object: literal`). Ontology bumped 0.2.0 → 0.3.0
(additive/minor — one predicate widened, no rename).

**Consequences.** One predicate spans the resolved and unresolved cases, so the
projection round-trips affiliations back to the legacy `affiliations` node field
whether they matched an org or not. `claim` still enforces the object XOR at the DB
level (exactly one of `object_id` / `object_value`); the ontology only widens what the
actions layer accepts.

**Revisit when.** A predicate needs *typed* literals (Phase 4 value objects) — then
literals gain their own value-type declaration rather than the bare `literal` marker.

---

## ADR-018: Identity tables (`mention`, `identity_membership`) land with T8, not T4

**Context.** Spec 02 §2 defines `mention` + `identity_membership` for versioned,
reversible identity (Article V). T4's table list (the core claim store) omitted them,
and T4's schema-inspection test asserts exactly the T4 table set. The legacy migration
(T8) is the first code that needs them — one mention + one membership per legacy node,
`decided_by='rule:legacy-slug'`.

**Decision.** Ship `mention` and `identity_membership` in migration `0005` as part of
T8a, immediately before the migration that populates them, rather than back-dating
them into the T4 baseline. Full ER (Splink, adjudication) remains Phase 2 (specs/05);
Phase 1 only creates the one-mention-per-node clusters the projection reads.

**Consequences.** T4's schema test is unchanged (still asserts the core set); the
identity tables have their own migration and are exercised by the T8/T10 integration
tests. These tables carry FK columns but no ORM `relationship()`, so inserts that
reference a freshly-created parent must flush the parent first (the migration does).

**Revisit when.** Phase 2 — adjudication actions add merge/split, which supersede
memberships (`valid_to`) rather than deleting them.

---

## ADR-019: The legacy `/api/*` projection surface is public and open-only

**Context.** T13/T14 require the existing single-page UI to "work unchanged" against
the governed API. That UI fetches `/api/graph`, `/api/stats`, `/api/cells`,
`/api/query/{name}` with **no bearer token**. Spec 03 §4's deny-by-default rule says
every route without an `authorize` dependency fails CI.

**Decision.** The unversioned `/api/*` projection routes are explicitly marked
`public_route` and serve **only** the open-handling, case-less projection — the public
OSINT floor. The graph emitter (`aegis.projections.graph.build_graph`) defaults to
`open_only=True`: anything above `open`, case-scoped, or retracted never enters
`output/real_graph.json`, so there is nothing for a token-less caller to leak. The
deny-by-default lint (`find_ungated_routes`) accepts a route only if it is gated
(`authorize`/`current_user`) *or* marked `public_route`; the governed `/v1/*` routes
are all gated. The corrected kinship categorization (`sibling_of`, `spouse_of` →
`kinship`) surfaces as a new `KINSHIP` layer in the legacy `LayerType` enum and the UI
filter/colours.

**Consequences.** The public surface can never widen past `open` without changing the
emitter default (a visible, reviewable one-line change). Agency deployments that want
no anonymous graph at all drop the `public_route` markers and put the UI behind the
bearer flow — the data path is identical. `app/server.py` is retired to a deprecated
offline-demo tool (kept until Phase 3).

**Revisit when.** A deployment needs authenticated, clearance-scoped graph reads in the
UI — then the UI adopts the bearer flow and `/api/graph` gains the `authorize()` gate
plus row filters, and the `public_route` marker is removed.

---

## ADR-020: Python/FastAPI is the reference implementation — the Kotlin/Spring end-state is withdrawn

**Context.** GOAL.md §36 originally recommended a Kotlin/Spring core with Python
confined to analytics. Phase 1 delivered the entire governed platform (claim store,
actions, authz, audit, projections, API) in Python 3.12 + FastAPI, built and operated
by one hands-on developer. plan.md §2 already treated the JVM rewrite as trigger-gated
("second backend team, or JVM-grade throughput need") — a trigger with no plausible
path to firing in this deployment.

**Decision.** Python 3.12 + FastAPI is the *reference implementation* of the Aegis
core through production, not a stepping stone. GOAL.md §36 is amended accordingly
(reference-implementation vs trigger-gated-upgrade table). Scale pressure is answered
by the per-concern triggers (Neo4j, OpenSearch, Kubernetes, Kafka, …) in plan.md §2
and roadmap Phase 9 — never by a wholesale rewrite.

**Consequences.** All remaining phases (P2–P9) build on the existing codebase; the
generated SDKs (ADR-021) target Python and TypeScript. Removing the rewrite option
makes long-lived Python choices (SQLAlchemy models, actions layer) worth continued
investment in quality rather than treated as disposable.

**Revisit when.** A second backend team exists, or a measured throughput requirement
exceeds what horizontal FastAPI workers + Postgres can serve.

---

## ADR-021: Foundry-informed ontology v2 — interfaces, functions, actions v2, generated SDKs

**Context.** Study of Palantir Foundry's Ontology (semantic/kinetic layers, action
types with parameters/submission criteria/side effects, functions, interfaces, shared
property types, Object Storage v2, object sets/views, OSDK, proposals workflow)
against the Aegis ontology DSL (spec 01) shows Aegis already matches Foundry on
ontology-as-single-source (Article XI), audited actions, projections-as-caches
(Article XIII), and review-queue writeback discipline — but lacks: interfaces/shared
properties, a real functions layer (only a `computed: true` flag), action
parameters/criteria/side-effects, object sets, object views, typed client SDKs, and an
ontology change-management workflow.

**Decision.** Adopt the Foundry layer architecture where it fits, in phases: DSL v2
(interfaces, shared properties, functions, actions v2, proposals, Python+TS SDK
codegen) in Phase 3 (spec 08); object views in Phase 4; object sets in Phase 6.
**Retain the deliberate divergence:** Aegis property values and links are *claims*
with source, grading, and time (Article I) — Foundry-style mutable property values
are rejected; any "current value" is a derived, inspectable projection over claims.
GOAL.md gains §7.8–7.10 (layer model, design principles, explicit Aegis↔Foundry
concept map).

**Consequences.** The P4 workspace is generated from the ontology + TS SDK rather
than hand-built per type; function outputs are attributed algorithmic sources
(suggestion-mode by default, Article VII); ontology changes acquire a proposal +
history discipline enforced in CI.

**Revisit when.** DSL v2 features accumulate without consumers (trim to spec 08's
exclusion list), or single-repo proposals stop scaling to the contributor count.

---

## ADR-022: Roadmap v2 — milestones, P0–P9 renumbering, MVP gate at Phase 2

**Context.** Phase 1 closed (see phase-1-exit-review.md). The v1 roadmap (P0–P7) had
no home for the ontology-v2 work (ADR-021), buried controlled AI in a trigger-table
row, and had no explicit "usable product" checkpoint. The user's direction: complete
roadmap to production, with a demonstrable MVP by the end of Phase 2.

**Decision.** Roadmap v2 groups phases into six architectural milestones and
renumbers: P2 identity/provenance (enlarged with review-queue UI, basic search, and a
demo runbook) closes with a **★ MVP gate** — the full ingest→suggest→review→accept→
projection loop demonstrable from the UI by a non-builder; new P3 = ontology v2;
old P3–P6 shift to P4–P7; controlled AI is promoted to a real Phase 8; P9 = production
baseline + the trigger table. Every remaining phase gets a charter in
`speckit/phases/`; T-level task files are written at each phase start (Phase 2's
exists: tasks-phase-2.md, T17–T28).

**Consequences.** Phase references in living documents (specs, plan, ontology
comments, GOAL.md) are updated to v2 numbering. **ADR-001…019 are append-only history
and keep their v1 phase references** — the mapping table at the top of roadmap.md is
the translation. GOAL.md §40 now defers to speckit/roadmap.md.

**Revisit when.** A phase's exit criteria prove wrong in practice — amend via a new
ADR and a charter update, never by renumbering again.

---

## ADR-023: Platform-first identity — ontology-driven platform; criminal-network analysis is a domain module; legacy is replaced, never extended

**Context.** The project began as (and its repository is still named) a
criminal-network-analysis tool, and its founding documents framed Aegis that way, with
the intelligence platform as the growth path. After the Foundry study (ADR-021) and
roadmap v2 (ADR-022), the user set the reverse framing as the product identity: build
an ontology-driven intelligence platform for our country's needs — Palantir-class in
concept, open-stack and auditable in construction — where criminal-network analysis is
one application domain among several (financial crime, border/customs, and others),
all powered by the same ontology core. The pre-Aegis prototype (`pipeline/`, `app/`
static explorer) is to be treated as scaffolding to replace, not a system to extend.

**Decision.** (1) The constitution gains a mission/vision preamble stating the
platform-first identity, and a new **Article XIV — the core is domain-neutral**:
platform services carry no hard-coded domain concepts; a domain enters as an ontology
module plus migrations (one-time migration adapters per ADR-016, and code scheduled
for deletion, exempt). (2) **Article II generalizes** from "no inherent criminality"
to "no inherent derogatory status" — same rule, stated for every domain; number, test,
and intent unchanged. (3) GOAL.md §1–2 and speckit framing docs are rewritten
platform-first; the domain list in GOAL.md §2.3 presents criminal-network analysis as
the first domain module. (4) **Legacy stance:** nothing new is built on or shaped by
the legacy explorer/pipeline; P2 keeps only throwaway panels on durable APIs, and P4
replaces and deletes the explorer with scope set by analyst needs, not feature parity.
The `/api/*` legacy-shaped projection surface (ADR-019) is reviewed for retirement at
the P4 gate.

**Consequences.** Charters and roadmap drop "parity" language in favour of
"replacement"; future domain proposals are ontology-module proposals, not new
subsystems; Article XIV becomes a review gate for core code (domain nouns outside
ontology-derived artifacts fail review). The repository name is historical and may be
revisited separately; no code changes are implied by this ADR. ADR-001…022 remain
append-only history in the original framing.

**Revisit when.** A second real domain module lands (validates Article XIV in
practice), or a domain need arises that genuinely cannot be expressed as an ontology
module plus migrations.

---

## ADR-024: Greenfield repository layout — legacy quarantined under `legacy/`, tree scaffolded to the roadmap

**Context.** After ADR-023 the *stance* was platform-first, but the *tree* still
presented the prototype as a peer of the platform: `pipeline/`, `app/`, `demo.py`,
`build_real_graph.py`, `cypher/`, a screenshot, and the extraction `requirements.txt`
sat at the root beside `aegis/` and `ontology/`, and the future homes the specs
already name (`sdk/`, `ui/`, `ontology/history/`, `aegis/functions/`) did not exist.
User direction (2026-07): design the layout greenfield from the roadmap and specs;
do not let legacy shape the structure.

**Decision.** The repository is reorganized around the platform, with every
roadmap-named component given its scaffolded home (see plan.md §3 for the full
tree). The prototype is quarantined under `legacy/` — one directory, one README
with a piecewise deletion schedule — and the data corpora move under `data/`.
Path translation (documents written before this ADR use the old paths):

| Old path | New path |
|---|---|
| `pipeline/` | `legacy/pipeline/` (imports: `legacy.pipeline.*`) |
| `app/` | `legacy/app/` (imports: `legacy.app.*`) |
| `build_real_graph.py`, `demo.py`, `cypher/` | `legacy/…` |
| `requirements.txt` (extraction extras) | `legacy/requirements.txt` |
| `ARCHITECTURE.md` (prototype tour) | `legacy/ARCHITECTURE.md` |
| `image.png` | `legacy/explorer-screenshot.png` |
| `real_data/` | `data/real/` |
| `sample_data/` | `data/sample/` |

New scaffolding, each bound to the phase that fills it: `ontology/proposals/` +
`ontology/history/` (P3 change management, spec 08 §7); `aegis/functions/` (P3),
`aegis/search/` + `aegis/analytics/` (P6), `aegis/sharing/` (P7), `aegis/assist/`
(P8) as docstring-placeholder packages; `sdk/python/` + `sdk/ts/` (P3, spec 08 §8);
`ui/` (P4, spec 07). Platform paths (`aegis/`, `ontology/aegis.yaml`, `infra/`,
`migrations/`, `tests/`) are unchanged, as are the speckit's prescribed file
locations (`aegis/er/settings.py`, `sdk/python/aegis_sdk/`, …).

**Consequences.** The root now reads as the architecture. Legacy keeps working
(extraction still feeds the review queue; the explorer is still served) — only its
import prefix changed. Runtime artifacts (`output/`, `backups/`, `Files/`) stay at
the root, gitignored. `pyproject.toml` still packages only `aegis`; `legacy` is
importable in dev/CI but never shipped. ADR-001…023 keep their original path
references — this table is the translation (ADR-022 precedent).

**Revisit when.** Phase 4 deletes `legacy/app/`; the last `legacy/pipeline/`
consumer is replaced (extraction v2, P8) — then `legacy/` disappears entirely and
this ADR's mapping becomes pure history. *(Amended by ADR-032: the explorer is
deleted in Phase 2, when the workspace shell's graph view lands.)*

---

## ADR-025: Phase gates are hard — criteria cannot be deferred

**Context.** The roadmap says phases are gated by exit criteria, yet every
phase's exit task accepted "all exit boxes checked **or explicitly deferred
with reason**", and several charters listed prior phases as "soft"
dependencies. External review (2026-07, B-06) correctly observed that a
criterion that may be deferred is not a gate: the MVP or a governance phase
could close while its defining property is absent, and every downstream
dependency claim becomes unreliable.

**Decision.** Two distinct concepts, used consistently:

- **Gate criterion** — the checkboxes in a phase charter's "Exit criteria".
  Non-deferrable. If one cannot be met, the phase stays open, or a superseding
  ADR amends the charter *before* the exit review — never in it.
- **Non-blocking deliverable** — everything else in a charter. May carry over
  with an owner, a target phase, and a note on dependency impact, recorded in
  the exit review.

The roadmap is strictly sequential. Where earlier-phase work may genuinely
start before a gate closes, the charter says so explicitly ("may start after
Px task Ty") — the word "soft" is retired.

**Consequences.** Every exit task's AC is rewritten; phase-01's "complete"
verdict is revised to "complete with closure addendum" (ADR-033) because two
of its deferred items were in fact load-bearing (field filtering, revocation
safety) and one criterion rested on an exception (ADR-019 public routes).

**Revisit when.** Real parallel workstreams emerge (second contributor) — then
introduce an explicit dependency DAG, not adjective-based softness.

---

## ADR-026: Anonymous projection routes are retired — every route is authorized (supersedes ADR-019)

**Context.** ADR-019 marked the legacy explorer's unversioned `/api/*`
projection routes `public_route`, serving an open-only projection with no
authentication. External review (2026-07, B-01) held this against Article VI
and Article X: "open" is a data classification, not an authorization decision;
an anonymous route records no actor, purpose, or decision; and a bulk graph
endpoint over a real-person corpus is a scraping/enumeration surface even when
every row is nominally public. The exception also poisoned the deny-by-default
lint with a permanent escape hatch. With ADR-032 (React shell in Phase 2) the
only consumer of the anonymous surface is scheduled for deletion anyway.

**Decision.** No production route is anonymous. Concretely:

1. The `public_route` marker and its lint exemption are removed when the P2
   workspace shell's graph view lands; `/api/*` and the legacy explorer are
   deleted in the same change (T22).
2. **Interim containment** (until that task): `aegis serve` binds to loopback
   by default and the `/api/*` routes gain response-size and rate limits.
   These are exposure controls, not authorization — the debt is visible, owned
   by T22, and time-boxed to Phase 2.
3. If a public demo is ever wanted, it is a **statically generated, fictional**
   artifact produced outside the governed API — never a live route over real
   data.

**Consequences.** Article VI's test is again universally true once T22 lands;
the deny-by-default lint loses its exception branch; agency deployments need
no configuration to be safe by default.

**Revisit when.** Never for the principle. A deliberate public-transparency
product would be its own system with its own ADR.

---

## ADR-027: Nothing algorithmic writes canon — auto-accept, auto-merge, and `system_claim` are removed

**Context.** Article VII says model output enters a review queue and nothing
algorithmic writes canonical claims or identity clusters. Three specs quietly
contradicted it: spec 04 §4 made deterministic structural passes "eligible for
auto-accept by config"; spec 05 §2.1/T18 auto-decided exact-identifier identity
merges; spec 08 §5 gave ontology functions a `system_claim` output mode
writing recorded claims directly (echoed in GOAL.md §7.8/§7.10). External
review (2026-07, B-02) called the contradiction correctly: an ADR cannot
override a constitutional article, and audited automation is still not human
adjudication. Identity is the worst case — one wrong deterministic merge
contaminates all downstream analysis, and registry identifiers do contain
errors, fraud, duplicates, and reuse (H-07).

**Decision.** Article VII is kept strict; the three escape hatches are
removed rather than constitutionalized:

1. **Extraction:** deterministic passes emit suggestions like every other
   producer. No auto-accept mode exists. (Spec 04 §4 amended.)
2. **Identity:** deterministic rules produce **pre-verified candidates** —
   top-of-queue, evidence attached, batch-confirmable in one human action —
   never merges. `decided_by` is always a human actor; `rule:<name>` survives
   only as the candidate's producer. (Spec 05 §2, T18 amended.)
3. **Functions:** output modes are `suggestion` (review queue) or **derived
   record** — rows in rebuildable projection/finding tables (Article XIII),
   typed and displayed as derived, never rows in `claim`. The `system_claim`
   mode is deleted. (Spec 08 §5, GOAL.md §7.8/§7.10 amended.)
4. Reproducibility of derived records is defined as *canonical-digest equality
   over inputs + config + output* — not byte-identical database rows (H-14).

**Consequences.** The constitution, specs, and tasks say the same thing again.
Deterministic derivations lose nothing: what is mathematically implied by
accepted claims is exactly what projections are for. Human throughput for
identifier matches is preserved via batch confirmation, and every merge has an
accountable human in `decided_by`.

**Revisit when.** A real, measured adjudication bottleneck on a specific
derivation class — then amend Article VII *first*, defining admissible class,
proof obligation, provenance, retraction, failure semantics, and approval
authority. A lint marker or config flag is never the mechanism.

---

## ADR-028: Identity is a decision ledger — revisions, persisted candidates, negative constraints (extends ADR-005, supersedes the ADR-018 minimal schema)

**Context.** Spec 02 modeled identity as `identity_membership` rows with
`valid_from`/`valid_to`, and T20 promised that merge-then-split restores the
exact prior state. External review (2026-07, B-03) showed timestamps alone
cannot prove that: nothing forbids two active memberships for one mention,
a split cannot know which rows formed the pre-merge state after intervening
edits or concurrent adjudications, candidate pairs and rejections aren't
persisted at all, and `merged_into`-as-a-claim invents a source record for
what is administrative metadata.

**Decision.** Phase 2 lands an **identity decision ledger** (design task T17a
rewrites spec 05/spec 02 §2 before implementation):

1. `identity_decision`: decision id, kind (confirm/reject/merge/split/
   unresolved), actor, evidence note, input references (candidate pair,
   mention set), **parent revision id**, resulting **revision id**, transaction
   time. Every adjudication creates a revision; revisions form a chain.
2. `identity_membership` rows are keyed to the revision that created/closed
   them; a database invariant (partial unique index) guarantees **at most one
   active membership per mention**.
3. `er_candidate` persists every candidate pair with producer, model/settings
   version, feature breakdown, and disposition; rejections create versioned
   **negative constraints** consulted by candidate generation.
4. Adjudication uses **optimistic concurrency** on the parent revision: a
   decision made against a stale revision is rejected and re-presented.
5. Merge lineage (`merged_into`) is **ledger metadata**, not a domain claim.
   A rebuildable `entity_canonical_map` projection is derived from the ledger
   for fast resolution (Article XIII), with defined cycle/tombstone behavior.
6. Reversal tests cover multi-merge chains, partial splits, concurrent
   decisions, and later mention additions — not only immediate merge→split.

**Consequences.** "Exact reversal" becomes provable instead of promised.
The Phase-1 tables stay as the migration substrate; migration `xxxx` in P2
upgrades them. Splink settings/versioning (ADR-005) now records the graph
snapshot used for contextual features so scores are reproducible.

**Revisit when.** Never for reversibility (Article V). The ledger schema may
evolve additively.

---

## ADR-029: Claim arguments carry mention evidence and resolve through identity revisions

**Context.** Claims store raw `subject_id`/`object_id` entity references, and
the edge projection groups those raw IDs. Identity decisions move *mentions*
between entities. External review (2026-07, B-19 — the most important finding)
showed the disconnect: after B merges into A, old claims still project edges
for B unless projections resolve a canonical representative; and a canonical
map alone cannot undo a mistaken merge, because when mentions are split out
again nothing records which entity-valued claims arose from which mentions.
Rewriting claims during adjudication would be race-prone and contradict
immutable history.

**Decision.** Adopt the hybrid claim-argument model (design task T17b rewrites
spec 02 §3 before implementation):

1. Entity-valued claim arguments gain **optional mention anchors**
   (`subject_mention_id` / `object_mention_id`) preserved from extraction;
   extracted/reported claims must carry them.
2. Every claim stamps the **identity revision** current at `recorded_at`.
3. Projections resolve entity arguments **through the active identity
   revision** (via the `entity_canonical_map` of ADR-028); as-of queries may
   pin an explicit revision — this is what makes the P4 as-of answer
   defensible.
4. Manual and assessment claims may be **unanchored** (no textual mention)
   under an explicit rule: on a split affecting their entity, unanchored
   claims route to **re-adjudication** rather than being silently reassigned.
5. Blocking tests: a merge collapses nodes/edges; a split restores
   mention-attributable edges without rewriting any claim row; ambiguous
   unanchored claims appear in the review queue.

Mention-only references (no entity IDs at all) were considered and rejected:
analyst-authored and assessment claims legitimately have no textual mention.

**Consequences.** Claims stay immutable through identity churn; the graph can
never disagree with the active identity decision; splits are cheap and safe.
Costs one join in projection rebuild — acceptable, projections are batch.

**Revisit when.** Never for the principle; the argument table shape may be
normalized (a `claim_argument` table) if >2-ary claims arrive with events (P5).

---

## ADR-030: Edge projections aggregate honestly — no fabricated time, no collapsed confidence

**Context.** The illustrative `edge_projection` took `min(valid_from)`,
`max(valid_to)` (open-ended if *any* claim is open), `max(credibility
weight)`, and `count(DISTINCT record_id)` labelled "independent records".
External review (2026-07, B-12): two disjoint intervals become one continuous
relationship; one weak open-ended report makes the whole edge permanent;
max() erases contradictions; distinct records are not independent sources.
That is precisely the "authoritative rumor engine" GOAL.md forbids.

**Decision.** Projection semantics (implemented with T21):

1. **Time:** interval *sets* are preserved — an edge either carries its
   interval list or is emitted as time-segmented rows; no min/max collapse.
2. **Confidence:** no scalar aggregate is stored as authoritative. The edge
   carries a **support summary**: per-claim grading references, contradiction
   count, corroboration count, and the aggregation method + version. Any
   display score is computed in the UI from the summary and is inspectable.
3. **Counting:** `record_count` (distinct records), never "independent
   sources"; source-derivation modeling is future work and until it exists no
   independence claim is rendered.
4. The projection build stamps identity revision + ontology version + builder
   version (with ADR-029), so any rendered edge is fully attributable.

**Consequences.** The graph may look *less* certain — that is the product
working as designed (Article III/VIII). Legacy weight semantics survive only
inside the legacy emitter until T22 deletes it.

**Revisit when.** Never for honesty; the summary shape may grow (source
lineage, grading dimensions) as P6 analytics need it.

---

## ADR-031: Suggestions are typed — one envelope, per-kind schemas, dispatch through declared actions

**Context.** `review_queue` holds an opaque JSON `payload` and a single
`result_claim` FK. Phase 2 puts claim suggestions *and* identity candidates
through it; Phase 8 adds claim relations, hypothesis links, summaries, and
contradiction candidates. External review (2026-07, B-05): these outcomes have
different validation, authorization, edit, and result semantics — an untyped
queue becomes a polymorphic state machine without referential integrity, and
acceptance cannot prove it invoked the right action.

**Decision.** A **typed suggestion envelope** (design task T17c rewrites
spec 02's queue section):

1. Envelope columns: `suggestion_kind` (closed, code-owned list),
   `schema_version`, `payload` validated against the kind's schema (generated
   from the target action's parameters), `target_action`, producer identity +
   version, source/input references, idempotency key, supersession/expiry,
   decision fields, and a **typed result reference** (claim id, decision id,
   relation key — per kind).
2. **Acceptance dispatches through the declared action** (`record_claim`,
   `adjudicate_identity`, `link_claims`, …) with the reviewer as actor — the
   queue never writes tables itself.
3. High-volume machine candidates with their own lifecycle (ER candidates,
   ADR-028's `er_candidate`) live in dedicated tables; the review **inbox** is
   a UI composition over queue + candidate sources, not one mega-table.

**Consequences.** Adding a suggestion kind = schema + action mapping, no queue
migration; Article VII's test ("the only writer is the adjudication action")
becomes mechanically checkable per kind.

**Revisit when.** Kinds proliferate past what a closed list serves — then a
registry pattern, still typed.

---

## ADR-032: One durable UI — React + TypeScript from Phase 2; no interim server-rendered stack (supersedes spec 07's staging; amends ADR-023 execution)

**Context.** The plan had three UI generations: legacy Cytoscape explorer
(P1), throwaway HTML/HTMX panels bolted onto it (P2), then a React + TS
workspace (P4). External review (2026-07, H-10) flagged the deliberate waste;
the MVP gate (B-04) independently requires a real authenticated UI loop
(ingest → extract → review → adjudicate → explore) that "two panels" cannot
carry; and the user directed a greenfield re-evaluation with React as the
candidate. Considered honestly: Jinja2 + HTMX is a legitimate lightweight
pattern for server-rendered CRUD, and React costs a build chain a solo
developer must carry. But the destination is *already* React + TS (ADR-021's
generated TS SDK, P4 ontology-driven screens), the workspace is an
interaction-heavy product (graph canvas, adjudication flows, provenance
drill-downs) where client state is the norm, and a second interim stack would
be built solely to be deleted — exactly what ADR-023 forbids.

**Decision.**

1. `ui/` starts in **Phase 2** as the single durable workspace: React 18 +
   TypeScript + Vite. It authenticates via Keycloak OIDC (PKCE) using a
   maintained client (`oidc-client-ts` / `react-oidc-context` — Article XII);
   tokens in memory, no localStorage; CSP and security headers served with it.
2. Until the P3 ontology SDK exists, the API client is **generated from the
   FastAPI OpenAPI document** (`openapi-typescript`-class generator — adopt
   before build). The P3 SDK extends/replaces the generated client without UI
   rewrite; stable operation IDs become an API convention now.
3. P2 ships function-over-polish screens: source landing/extraction status,
   review queue, identity adjudication, graph view (Cytoscape.js inside
   React), provenance panel, entity search. P4 grows the same app (object
   views, cases, hypotheses, timeline) — it no longer starts a UI.
4. The legacy explorer and its `/api/*` surface are **deleted when the shell's
   graph view lands** (T22, with ADR-026). No HTMX/Jinja investment happens.

**Consequences.** P2's effort grows (honest — the MVP gate was always this
big); total UI work across P2+P4 shrinks by one full throwaway generation.
The repo gains a Node toolchain in CI (type-check + build + minimal e2e).
Spec 07 is rewritten around one evolving app.

**Revisit when.** The workspace's interaction model turns out to be
form-dominated CRUD after all (then simplify inside React — not by adding a
second stack).

---

## ADR-033: Roadmap v2.1 — Phase 1 closure addendum, P2 MVP recomposition, P3 narrowed to module composition, pilot security gate

**Context.** The 2026-07 external review (disposition:
`reviews/2026-07-18-external-review-disposition.md`) plus ADR-025…032 change
what several phases must contain. Roadmap v2 (ADR-022) remains the structure;
this ADR records the content corrections.

**Decision.**

1. **Phase 1 verdict revised** to *complete with closure addendum*: the four
   functional exit boxes stand, but T16a–T16d (interim exposure containment,
   revocation inline delete + lag bound, dependency lockfile, runbook/status
   honesty) close the items the original review wrongly deferred without an
   owner. The addendum blocks P2's implementation milestones (not its design
   tasks).
2. **Phase 2 recomposed** (charter + tasks rewritten): a blocking **design
   pack** (T17a–T17d: identity ledger, claim arguments, typed envelope,
   projection semantics — specs rewritten before code); identity core
   implementation; the **durable React shell + full UI loop** (ADR-032)
   including source landing/extraction UI (B-04); field-level sensitivity
   filters and cursor pagination in-phase; a route-by-route authz matrix;
   numeric ER thresholds; the blocking MVP demo on a **fictional deterministic
   fixture** with the real-corpus walkthrough as a manual smoke test (H-09).
   Effort: XL.
3. **Phase 3 narrowed**: headline becomes **ontology module composition**
   (platform module + domain modules, namespaces, imports, a tiny second
   fictional domain proving zero core change — B-07) plus interfaces/shared
   properties, change management, and the OpenAPI-generated TS client P4
   needs. Functions execution machinery, side-effect outbox generalization,
   and the Python SDK move out of P3 (each lands with its first consumer).
4. **Pilot gate** added to the roadmap between phases and deployment reality:
   before any non-localhost binding or second real user — TLS, secrets
   hygiene, request/body limits + security headers, encrypted verified
   backups covering all non-reconstructible state, MinIO Object Lock on
   evidence buckets, signed audit-checkpoint export, dependency scanning.
   This is a deployment gate, not a phase: it can be satisfied any time, and
   P9 remains full production certification.
5. **Traceability**: roadmap gains a GOAL→roadmap coverage appendix classifying
   every major GOAL.md capability as scheduled / trigger-gated / out of scope,
   so unowned promises are visible (H-35).

**Consequences.** Pre-authored task files for P4–P9 stay valid as drafts;
each phase's re-validation task (T41/T54/T66/T78/T90/T102) now explicitly
dispositions the 2026-07 review findings tagged to its phase in the charters.

**Revisit when.** Phase 2's exit review — measured against the recomposed
charter, under ADR-025 gate semantics.

---

## ADR-034: Ingestion runs inside the request, bounded by two limits; the job model waits for the connector path

**Context.** T23a had to decide whether landing, the derivative stage and
extraction run synchronously or as tracked jobs (the task says "sync or job
status — decided here"). A job queue is the reflex answer for anything that
touches a file, and it is not free: it buys a status model, a worker
deployment, a retry policy, and a permanent new failure mode — work that is
neither done nor failed — in exchange for latency an operator only feels once
the work outlasts a request. Phase 2 has no worker; the scheduled-connector
trigger that would need one is plan §2, still unbuilt.

The real hazard in the synchronous shape is not slowness, it is
unboundedness: landing must buffer a body to hash it, so an unbounded upload
is memory exhaustion, and an unbounded document is a request that never
returns.

**Decision.**

1. Landing, the derivative stage and extraction all run **inside the
   request**, in one transaction, and return what happened.
2. Two configured bounds, with two different meanings — collapsing them into
   one number was the mistake worth avoiding:
   - `AEGIS_INGEST_OVERSIZE_BYTES` (default 25 MiB) is **governance**. Past
     it, the artifact still lands and is **quarantined** as spec 04 §3's
     "oversized anomaly". The bytes are kept and their *use* is withheld;
     deciding an artifact is too big to exist is not the pipeline's call.
   - `AEGIS_INGEST_MAX_BYTES` (default 100 MiB) is **transport**. Past it the
     request is refused `413` and nothing is stored, because we will not
     buffer it. This is a limit on us, not a judgement about the evidence.
3. Quarantine reasons **accumulate**: an artifact that is both a version
   conflict and oversized reports both, so fixing one and re-landing does not
   reveal the next one.
4. The derivative stage is keyed by *(parent record, kind, tool, tool version,
   params)* — `params` included, so changing how pages are joined produces a
   new derivative instead of silently reusing text we would no longer produce.

**Consequences.** No worker, no job table, no stuck-job state in P2. A
document large enough to outlast a request is a quarantine, not a timeout.
Extraction latency is the operator's to see, which is honest while the corpus
is small and will stop being acceptable as it grows.

**Revisit when.** The scheduled-connector / watch-folder path lands (plan §2)
— a poll has no request to hold open, so that is where a job model first earns
its complexity, and it should be introduced there rather than retrofitted
here.

---

## ADR-035: Transliteration keys are stored on `mention`, and search reads them

**Context.** T23c requires `GET /v1/search/entities` to satisfy "a
transliterated query variant finds the seeded entity", where the seeded set is
spec 05 §6's Sinhala/English variant pairs. Spec 06 §2.1 describes the search
surface as "`pg_trgm` over names/aliases/mention **norm_keys**".

Those two cannot both hold. `norm_key` deliberately **preserves non-Latin
script** (`aegis/er/normalize.py`): in Sinhala and Tamil the combining marks
are vowel signs that carry meaning, so folding them would merge names that are
not the same name. A Sinhala mention therefore has a Sinhala `norm_key`, and no
key derivable from a Latin query is ever Sinhala. Searching `norm_key` alone
can match romanized-to-romanized, and never Latin-to-Sinhala.

The cross-script keys already exist — `latin_key`, `script_key`,
`phonetic_key` in `aegis/er/translit.py` — but they are computed per run inside
`aegis/er/features.py` and never stored, so no query can reach them.

**Decision.** Persist `latin_key` and `phonetic_key` on `mention`, written at
mention creation, backfilled by migration `0009`, and indexed (GIN/trigram on
`latin_key`, btree on `phonetic_key`). `GET /v1/search/entities` matches a
query's own keys against them in SQL, alongside `Entity.label` and alias
claims.

`script_key` is **not** stored: it is `norm_key` for the cases that matter, and
a third near-duplicate column earns nothing.

**Consequences.**

- Cross-script search works in one SQL statement, which is what keeps
  authorization *in candidate generation* rather than in hydration (spec 06
  §2.1, ADR-012, B-17). A Python post-filter over a candidate set would have
  made the result count leak what a caller may not read.
- ER gains a single stored definition of the keys instead of recomputing them
  on every run; `features.py` reads the columns.
- The keys are derived data, so a change to `translit.py` requires a backfill.
  They are not identity and never were (Article V) — losing them costs a
  reindex, not a fact.
- Spec 06 §2.1's "mention norm_keys" is widened to "mention keys" to match.

**Revisit when.** ADR-012's trigger fires and search moves to a dedicated
engine, which would own its own analysis chain and make these columns a
denormalization rather than the index.
