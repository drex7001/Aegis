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

## ADR-036: Entity detail carries claim relations, and resolves through the canonical map

**Context.** T23c requires the provenance panel to render "conflicting property
claims side by side" with a visible `contradicts` badge (Article VIII). Two
dates of birth are a *property* disagreement, so they belong to one entity, not
to an edge — `GET /v1/entities/{id}/why-connected/{other}` answers the edge
question and has no node equivalent.

`GET /v1/entities/{id}` already returned "claims grouped by predicate", which
is the grouping the side-by-side rendering needs. What it did not return was
any relation between those claims: a caller could see two dates but not that
the store records them as contradicting. Discovering that meant one
`GET /v1/claims/{id}/provenance` request per claim.

Reading the route also surfaced a second problem. It filtered on
`Claim.subject_id == entity_id` with no canonical-map resolution, while
`why_connected` resolves explicitly and documents why. After a merge, claims
written against the absorbed id still name that id, so the surviving entity's
detail view silently dropped them.

**Decision.** Both are fixed in the existing route rather than a new one.

`EntityDetail.claims_by_predicate` becomes `dict[str, list[ClaimProvenanceOut]]`
— the same unit the why-connected panel renders, so a claim arrives with its
grading dimensions apart, its source and record, and **both** relation
directions. A new `entity_provenance()` query resolves through
`EntityCanonicalMap` exactly as `why_connected` does, and the response reports
`resolved_entity_id` and `truncated`.

No new route: spec 06 declares none for this, its row's description ("claims
grouped by predicate") stays true, and a parallel `/entities/{id}/provenance`
would leave two routes answering "what is claimed here?" differently. The
shared `ClaimProvenance → ClaimProvenanceOut` mapper moves to
`aegis/api/mappers.py` so the two panels cannot drift.

**Consequences.**

- The N+1 the why-connected route exists to avoid on edges is now avoided on
  nodes too. The relations are computed while the caller already holds the
  rows.
- A merge can no longer hide evidence from an entity's own view (Article V).
  This was a live defect, not a hypothetical: any adjudicated merge produced
  it.
- The response is heavier than a bare claim list. That is the cost of the panel
  being able to *name* a disagreement rather than leaving a reader to notice
  two values differ, which is the whole of Article VIII in the UI.
- `ClaimOut` remains the unit for the write routes; only the detail read
  changed.

**Revisit when.** Field-level sensitivity (T24a) lands. Filtering individual
claim *fields* rather than whole claims may make the grouped shape the wrong
place to apply the mask, and the panel would need to say which fields were
withheld rather than silently rendering a thinner card.

---

## ADR-037: The ontology is a composition — platform module + domain modules, unprefixed names, composition version on claims

**Context.** Article XIV says the core is domain-neutral and domains arrive as
ontology modules. Through Phase 2 that had no mechanism behind it (B-07):
`ontology/aegis.yaml` is one flat file mixing governance vocabulary (handling
codes, grading, source types, platform actions) with criminal-network
vocabulary (person, organization, 30-odd predicates). "Domains are modules" was
a claim no test could fail.

Three as-built constraints bound any design. `claim.predicate` and
`claim.ontology_version` are TEXT columns on immutable rows (ADR-013), so
neither names nor version semantics may be rewritten. Twelve modules under
`aegis/` consume the loader's registry surface, so the composed result must be
substitutable for today's `Ontology`. And `aegis ontology validate` runs
offline in CI with no database.

**Decision.** `ontology/aegis.yaml` becomes a **composition manifest** over
module files, and stays the single artifact Article XI names. Spec 08 §2 is the
format.

1. **Two modules to start.** `platform` owns handling codes, grading (scales
   and external schemes), source types, and all platform actions with their
   parameters. `criminal_network` owns the object types, predicates, and
   categories. Their union is today's file section-for-section, so T30 is a
   pure reorganization whose proof is that the normalized composed registry is
   unchanged.
2. **Names stay globally unique and unprefixed** in the registry, on the wire,
   and in `claim.predicate`. `namespace` is metadata for errors, release
   records, and client grouping. A cross-module collision is a validation
   error, never silent shadowing.
3. **Imports carry PEP 440 version specifiers**, parsed with
   `packaging.specifiers` (Article XII). A module may reference only names it
   owns or imports; a reference without a declared import is a validation error
   naming both modules and the path.
4. **Type ownership is derived from declaration**, not listed in the manifest.
   The composed registry records `owner_module` per name.
5. **`ontology_version` is the composition version.** Per-module versions live
   in the release metadata (spec 08 §7.2). Existing stamped values keep their
   meaning; the modularization bump is minor (1.2.0 to 1.3.0).
6. **`enabled: false`** omits a module's vocabulary from the registry. It is an
   authoring-time control: it deletes and hides nothing, and the API refuses to
   start when a disabled module's vocabulary appears in recorded claims.

**Alternative rejected — lexical namespacing** (`criminal_network:member_of`).
It is the textbook answer and it is wrong here: every recorded claim stores a
bare predicate string, so prefixing would either rewrite immutable rows or add
a translation layer to every read and write path. Article XI's guarantee is
that exactly one artifact declares a name; global uniqueness delivers that
directly, and collision-as-error delivers it loudly.

**Consequences.** The Article XIV test becomes executable: T31's `border-cargo`
fixture loads against the same core and round-trips claims, and the test fails
if any file under `aegis/` needs a domain edit. Two domains that genuinely want
the same word must resolve it through a proposal rather than a prefix — a real
constraint, accepted because the alternative costs immutability. The loader
gains module resolution, but the registry its twelve consumers see does not
change shape.

**Revisit when.** A third domain wants a name a shipped domain already owns, or
a module must be distributed separately from this repository (spec 08 §11.4's
trigger).

---

## ADR-038: Ontology codegen is built per consumer — spec 01 §5's three targets never existed

**Context.** Spec 01 §5 and the spec 08 draft both list three committed codegen
targets — `aegis/ontology/_generated/models.py`, `infra/fga/_generated.fga`,
`aegis/api/_generated/ui_meta.json` — produced by `aegis ontology generate` and
"used by" Phase 1 code. T29's walk of the as-built system found that **none of
them exists**. The CLI exposes `aegis ontology validate` and nothing else;
`infra/fga/model.fga` is hand-written and its only types are `user`, `case`,
`compartment`, and `evidence_item` — no domain object type appears in the
authorization model at all; the workspace gets its vocabulary from
`GET /v1/ontology/vocabulary`, a route added at T23b precisely because no
generated descriptor existed.

This mattered for planning, not just honesty: T33 was chartered as "codegen v2
for existing targets", which would in fact have been building three generators
from scratch — one of which (FGA stubs) would emit an empty file.

**Decision.** Do not restore the three targets wholesale. Each codegen target is
built by the phase whose first consumer needs it, and spec 08 §8 becomes the
authoritative table; spec 01 §5 keeps the original table marked as intent, with
this correction.

Phase 3 builds three: the composed registry + release metadata (consumer: the
change-management gates), ontology constants for the workspace client
(consumer: the workspace, replacing ad-hoc vocabulary reads), and Pydantic
action request models (consumer: actions v2 parameter enforcement). UI
descriptors move to P4 with the generic screens that read them, FGA stubs to P7
when a domain type first acquires an FGA relation, and the Python SDK stays at
P8 per ADR-033.

**Consequences.** T33 is rewritten from "extend existing generators" to "build
`aegis ontology generate` with exactly the P3 targets"; the honest scope is
larger per generator and smaller in count. The commit-and-check-for-drift
discipline in spec 01 §5 is unchanged and now applies to generators that exist.
Documentation that asserted P1 deliverables which were never built is corrected
in both specs rather than quietly dropped — the same treatment T16d gave the
Phase 1 runbooks.

**Revisit when.** A phase finds it needs a deferred target earlier than its
listed consumer, or a generator's output stops having exactly one consumer.

---

## ADR-039: The generated TypeScript client stays in `ui/`; the error envelope joins the contract

**Context.** Phase 3 was chartered to generate a TypeScript client into
`sdk/ts/` and migrate `ui/` off its "P2-era generated client" (T37/T38). The
as-built system already does most of this: `ui/src/api/schema.d.ts` is generated
by `openapi-typescript` from the committed `ui/openapi.json`, consumed through
`openapi-fetch`, with a workspace CI job that regenerates and fails on diff and
a contract test that fails when the document drifts from the live routes. There
is no hand-rolled client to migrate away from. `sdk/ts/` contains a README.

What is genuinely missing is smaller and sharper. The client has no
ontology-derived constants, so predicates and handling codes reach the UI only
as opaque strings or through a runtime fetch. And the RFC 7807 error envelope,
though real at runtime since P1, is **absent from the OpenAPI document**: all 37
operations declare only their success codes plus FastAPI's default 422. That
absence is why `ui/src/api/client.ts` hand-writes `ProblemDetail` and
`StaleRevisionProblem` — the two hand-written response types whose removal is
T38's acceptance criterion.

**Decision.** Generation stays where its consumer is.

1. The generated surface remains under `ui/src/api/`. T37 adds a generated
   `ontology.ts` (predicates, object types, interfaces, categories, handling
   codes, source types, owner module per name) beside the existing
   `schema.d.ts`, under the same drift gate.
2. `sdk/ts/` as a versioned, published package waits for its first consumer
   outside this repository (spec 08 §11.4). Packaging with one in-repo consumer
   is cost without benefit and adds a build boundary the workspace must cross.
3. T36 adds the error envelope to the OpenAPI document as a component schema
   with its two documented extensions — the 422 validation path and the typed
   409 stale-revision body — and documents per-route error responses. Spec 06
   §7 is the specification.
4. T38 becomes "consume the generated constants and generated error types",
   which is what makes its "no hand-written request/response types remain"
   criterion achievable at all.

**Consequences.** T37/T38 shrink and become real; the charter's exit criterion
("a new predicate reaches the TS client with zero hand-written domain code") is
met through `ontology.ts` rather than a package move. The `openapi-fetch`
runtime is retained rather than swapped for a class-based generator — it is
already adopted, already gated, and already type-checks the whole workspace
(Article XII). The typed 409 stops being a shape the UI knows by convention.

**Revisit when.** A consumer outside this repository needs the client (the P8
producer tooling is the likely first), or the OpenAPI generator stops being
able to express a response the workspace must type.

---

## ADR-040: Action declarations become the write-side gate — parameters, criteria, and audited denials

**Context.** Spec 08's draft said `submission_criteria` failures are "audited
denials, not silent 403s", and the Phase 3 charter makes a criterion denial an
exit criterion. Reading `aegis/actions/service.py` shows two gaps that make
that unachievable as written.

First, the ontology's `roles` list is not enforced at the write for almost any
action. `_require_action(name)` is called without an `ActionContext` by every
action except `adjudicate_identity`, and `ActionContext.roles` defaults to
empty, which the method treats as "not supplied" and skips. Role enforcement is
real, but it lives at the API layer; the ontology declaration is documentation
for twelve of thirteen actions.

Second, the actions layer **cannot record a denial**. `ActionService._audit`
passes `decision="allow"` unconditionally, and `_require_action` raises
`ActionValidationError` before any audit row is written. The API layer does
write `authz.deny` rows (`aegis/api/deps.py`), so the shape exists — it is not
reachable from where criteria are evaluated.

**Decision.** T34 makes the declarations load-bearing rather than descriptive.

1. **`parameters` are the action's public request contract** — what an API or
   SDK caller may send — generated into a request model that rejects undeclared
   parameters. They are not the service function's Python keyword surface:
   mention anchors and resolution hints that acceptance dispatch supplies
   internally are not caller input. Platform actions declare their parameters
   in the platform module, so a domain module can never widen the claim
   envelope.
2. **The closed parameter type list** (spec 08 §6.2) is sized against the real
   Phase 2 request bodies — `record_claim` alone has 19 fields — not the
   draft's four-line illustration. `json` is admitted only with a registered
   code-side schema id, so it cannot become an escape hatch around ADR-031's
   closed suggestion-kind list.
3. **`submission_criteria` are named registry predicates**, and the validator
   rejects a name with no registered implementation — a criterion can never be
   declared before it can be enforced. P3 registers exactly three, each making
   an existing policy declarative: `actor_holds_action_role`,
   `actor_is_case_member`, `second_approver_present`. P7's `target_not_sealed`
   and `within_legal_authority` are named in the spec but declared by the phase
   that implements them.
4. **Every action call passes its `ActionContext`**, closing the roles gap, and
   **the actions layer writes `decision="deny"` audit rows** naming the actor,
   action, failed criterion, and target.

**Consequences.** Enforcement moves from one layer to two, deliberately: the
API gate stays (it must, for routes that never reach an action), and the write
gains its own. Any caller of the action functions — CLI, migration, tests,
future SDK — is now subject to the ontology's declaration rather than only HTTP
callers. Migrating thirteen actions to declared parameters is real work T34
owns, and the Phase 1 call sites that pass no context must be updated in the
same change or they will start failing the role check; that is the point.
Denial auditing changes the audit volume under normal use, since a rejected
write now appends a row where it previously only raised.

**Revisit when.** A criterion needs state the actions layer cannot see inside
its transaction (P7 sealing and legal authority are the candidates), or the
generated request models and the hand-written API schemas disagree about a
field's optionality often enough to argue for generating the route bodies too.

---

## ADR-041: Interfaces are implemented by the object type, not listed on the interface

**Context.** Spec 08 §4, as finalized by T29, gave each interface an explicit
`members:` list — `party: {members: [person, organization]}`. That reads well
in a single file and it is what the Foundry-informed draft described.

Implementing it against the module composition (ADR-037) made it unworkable in
the first case that matters. `party`'s members are `person` and `organization`,
which the **criminal-network** module declares. Its properties (`alias`) and
its role as governance vocabulary put the interface in the **platform** module.
A `members:` list therefore requires platform to name domain types, so platform
would have to import criminal_network — inverting the dependency the whole
composition rests on, and making the platform module unloadable without that
one domain.

Every workaround was worse. Putting `party` in the domain module means the next
domain redeclares it, and two `party` interfaces collide by ADR-037's global
uniqueness rule. Exempting interfaces from import validation means a module can
silently name types it does not depend on. Splitting into `party` (platform,
abstract) and `criminal_network_party` (domain, concrete) doubles the vocabulary
to describe one idea.

**Decision.** Flip the direction. An interface declares only what it
**requires**:

```yaml
# platform module
interfaces:
  party:
    properties: [alias]        # every implementor carries this shared property
```

and the object type declares what it **implements**:

```yaml
# criminal-network module
object_types:
  person:
    implements: [party, identifiable]
```

`Ontology.implementors(name)` derives the member list. Spec 08 §4's
"`members` is explicit (no structural inference)" survives unchanged in spirit
— membership is still declared, never inferred from shape — but it is declared
by the type that has to satisfy it.

Consequences of the flip, all deliberate:

- A domain module can implement a platform interface with no platform edit.
  `tests/fixtures/ontology/border-cargo.yaml` does exactly this, and that
  assertion is the executable form of this ADR.
- An interface with no implementor is a valid state (a platform interface no
  enabled domain implements). A **predicate targeting** an unimplemented
  interface is not: it could never be satisfied, so it is a validation error.
- Interfaces do not extend interfaces in P3, so spec 08 §9 rule 14's "no
  cycles" clause is vacuous. It stays as a guard for the phase that adds
  inheritance, if one ever does.
- Adding a member is still a minor bump; it is now a minor bump of the
  *domain* module rather than the platform module, which is the more accurate
  attribution.

**Consequences.** Both v2 semantic features resolve **in place at load time**:
a `shared:` reference becomes the full property (type, cardinality,
sensitivity) with `shared` retained for codegen, and a predicate's interface
endpoints expand to concrete implementors with `subject_interfaces` /
`object_interfaces` retained. No consumer learns the v2 syntax exists —
`aegis/authz/filters.py` still reads `properties['nic'].sensitivity` and gets
`restricted`; `aegis/actions/service.py` still tests `entity_type in
predicate.subject` and gets concrete types. That is what kept all 258
integration tests green through the change, and it is the same substitutability
rule ADR-037 imposed on the composed registry.

One boundary was deliberately not moved: `vehicle.registration` is a registry
identifier that does **not** adopt the shared `registered_identifier`, because
the shared property is `restricted` and the inline one has been `open` since
v0.1.0. Adopting it would raise the clearance needed to read rows already
recorded. That is a handling-policy change and belongs in a proposal, not in a
refactor that claims to be additive.

**Revisit when.** Interfaces need to extend other interfaces, or a domain needs
to declare that a type it does not own implements an interface (an "external
implementation" — which this design deliberately makes impossible, since the
implements list lives with the type).

---

## ADR-042: The API contract diffs against a git ref; the ontology diffs against a committed artifact

**Context.** Spec 06 §7.3, written at T29, said the API contract-diff check
compares "against the previously committed document" and then called it "the
API-side analogue of the ontology compatibility diff… comparison against a
committed artifact, not git archaeology". Those two sentences contradict each
other, and implementing T36 forced the question.

The ontology's rule (H-16) exists for a specific reason: `claim.ontology_version`
stamps every recorded claim, claims are immutable (ADR-013), and a version must
stay interpretable forever. That makes the previous ontology a **first-class
artifact** — `ontology/history/composed-<version>.json`, chained by content hash
— so the check works on a bare checkout with no remote, and an edited archive is
detected rather than silently diffed against.

Nothing stores an API version. `info.version` has been `1.0.0` through all of
Phase 2 and no row, claim, or client records it. There is no historical question
to answer, only a merge-time one: *does this branch break the contract on the
branch it is merging into?* Making that non-git would mean bumping an API
version and archiving a copy on every route change — ceremony with no consumer,
imposed to satisfy a sentence rather than a need.

**Decision.** The two checks compare differently, on purpose.

- **Ontology** (`aegis ontology check-release`): against
  `ontology/history/composed-<previous>.json`, named by `release.json` and
  verified by `previous_content_hash`. No git. The chain is the point.
- **API** (`aegis api check-contract`): against `git show <ref>:ui/openapi.json`,
  defaulting to `origin/master`. The document is a committed artifact; the
  *baseline selection* is a git ref, which is what "the contract we are merging
  into" means. An unreachable ref reports "nothing to compare against" rather
  than passing silently.

Breaking, for a caller: an operation removed or renamed (the same event from the
client's side — a method that stops existing), an operation moved to another
path or method, a documented response code dropped, a parameter removed or
becoming required, a request body becoming required. Additive: new operations,
newly documented responses, new optional parameters, a parameter becoming
optional. A break is accepted with `--allow-breaking` plus the phrase
`BREAKING API CHANGE` in the change itself, so the reason lands in the history
the break will later be explained from.

Spec 06 §7.3 is corrected to say this rather than to claim a symmetry that does
not hold.

**Consequences.** CI's fast-tests job fetches `origin/master` at depth 1 before
the check, because the default checkout is shallow and `git show` would
otherwise fail into the "nothing to compare" branch — a check that cannot fail
is worse than no check. `tests/contract/test_error_envelope.py` exercises the
diff on in-memory documents, so its behaviour is pinned without depending on
repository state.

The asymmetry is a real cost: two commands, two mental models, one of which
reads git. It is accepted because the alternative — versioning the API document
per route change — buys nothing that `origin/master` does not already give,
while adding a step every contributor would have to remember.

**Revisit when.** An API version becomes load-bearing — recorded on a row, a
token, or an export package — or a second client outside this repository pins a
contract version. Either turns the historical question real, and the ontology's
artifact-and-chain design becomes the right shape for the API too.

---

## ADR-043: UI descriptors are the generated TypeScript module, not a fetched `ui_meta.json`

**Context.** Spec 07 §3 has said since P0 that generic screens render from
`ui_meta.json`, "generated from the ontology". ADR-038 moved that target to
Phase 4 with the screens that read it, and the Phase 3 exit review carries it as
a carryover. T41's re-validation found the ground had moved underneath it.

Phase 3 shipped `ui/src/api/ontology.ts`: object types, interfaces, categories
and predicates, generated by `aegis ontology generate`, committed, and guarded
by `generate --check` in CI and by `tests/contract/test_workspace_types.py`. It
is imported as ordinary typed constants, so a screen that reads a predicate that
no longer exists fails `npm run typecheck`.

Building `ui_meta.json` beside it would mean two generators emitting the same
facts, two drift risks, and a runtime fetch whose contents no type-checker sees.
The gap is not that the descriptor is the wrong artifact — it is that the
artifact is **missing fields**: `display` (which property is the title), and
per-property label, type, `required`, `many`, `sensitivity`, `conflicts` and
`shared`. Without those a generic object view cannot draw a heading, let alone a
conflict badge.

**Decision.** The object-view descriptor contract is the generated TypeScript
module, extended (spec 09 §6.2). No `ui_meta.json` is built. `PredicateSpec` and
`PropertySpec` gain an optional `label`, and the generator humanizes the name
where none is declared — so a badly-humanizing name is fixed by declaring a
label in the ontology, through a proposal and a version bump, with no UI change.

The descriptor describes the **ontology**, never the screen: no layout, no
ordering, no widths, no icons, no tab assignments. That line is what keeps it
from becoming the custom schema ecosystem H-20 warns about.

**Consequences.** Article XI's "vocabulary is fetched, never hard-coded"
(spec 07 §2) is about *hand-written* vocabulary, and this ADR states it that
way: the sweep in `tests/contract/test_second_domain.py` — no file under
`ui/src` may name a domain term — is the enforceable form, and a generated file
is exempt because regenerating it is the only way to change it.

The one thing a compiled constant cannot know is that the server moved to a
different ontology version. That is why the mismatch banner (spec 09 §6.3) is
part of this decision rather than a nicety: `ONTOLOGY_VERSION` in the bundle is
compared against `GET /v1/ontology/vocabulary`, and a difference raises a
persistent, non-blocking banner. Non-blocking because the server remains
authoritative for every value that matters — a stale bundle renders correct data
with possibly outdated labels, and refusing to render would turn cosmetic drift
into an outage. This closes the P3 carryover of the same name.

Spec 07 §3 and spec 06 §2.7's "superseded in P4 by the generated `ui_meta.json`"
are corrected. `GET /v1/ontology/vocabulary` is **not** retired: it is the
runtime half of the version comparison, and it serves `assertion_types`, which
are platform epistemics and appear in no ontology module.

**Revisit when.** A consumer outside this repository needs the descriptors —
the same trigger ADR-039 set for `sdk/ts/`. A language-neutral JSON artifact is
the right shape then, generated from the same source, and this decision becomes
"the workspace reads the TypeScript projection of it".

---

## ADR-044: A claim's case is its immutable recording scope; case references are separate and grant nothing

**Context.** The Phase 4 charter's third deliverable says "claims and evidence
linkable to cases". T41 found the phrase admits two readings, and the as-built
system makes the difference a security decision rather than a modelling
preference.

`claim.case_id` exists and is set at record time by `record_claim`. It is also
an **access predicate**: `aegis/authz/filters.py` admits a claim when its
`case_id` is null or the reader is a member of that case. So "linking a claim to
a case" read as *assigning `case_id`* would either widen who can read a recorded
claim, or silently remove it from someone's view — a governance event with no
audit story, performed by an ordinary analyst, on an append-only row.

**Decision.** Two concepts, two tables.

- **Recording scope** — `claim.case_id`, set once when the claim is recorded,
  immutable thereafter, and the only case field `claim_filters` consults.
  Nothing in Phase 4 reassigns it. The same rule holds for
  `evidence_item.case_id`, whose FGA `can_view from case` derivation depends on
  it.
- **Case reference** — `case_reference (case_id, target_type, target_id, ...)`,
  spec 09 §2.3: *this investigation refers to that claim, entity or evidence
  item.* It confers **no** read access. Reference lists are built from targets
  the caller can already read, so a reference to something invisible is simply
  absent. Unlinking writes `detached_at`; it never deletes.

Because a reference grants nothing, linking is an ordinary case-scoped write
(`analyst`/`investigator` plus `actor_is_case_member`) rather than a privileged
one — the authorization is cheap precisely because the operation is powerless.

**Consequences.** The charter deliverable is met in the form that does not
weaken `claim_filters`, and the Phase 1 authorization matrix keeps holding
unchanged — which is the strongest evidence available that nothing widened.

A cost, stated plainly: an analyst who records a claim into the wrong case
cannot move it. The remedy is the one the claim model already has — retract with
a reason and record it again in the right scope, leaving both events in the
audit. That is more friction than an `UPDATE`, and it is the friction Article I
is made of.

Hypothesis-to-claim links (`hypothesis_claim`) follow the same shape and the
same rule: linking a claim as evidence for a hypothesis grants no access to it,
and the evidence basis renders through `claim_filters` like everything else.

**Revisit when.** A real workflow needs a claim to change scope — most likely
P7, where compartment assignment and sealing make re-scoping a governed
operation with an approver, an audit trail and a reason code. Then it is an
action with dual control, not a column write.

---

## ADR-045: The audit console lands in Phase 7, not Phase 4

**Context.** Spec 07 §6's view table lists "Audit console | 4 | auditor role
only". The Phase 4 charter lists seven deliverables and an audit console is not
among them, and the pre-authored task file T41–T53 contains no task for it. One
of the two documents was wrong, and M-01 — statuses that rot as code diverges —
is the standing risk that says which failure to avoid: leave it, and the phase
either ships an unplanned screen or closes with a spec quietly unmet.

`GET /v1/audit` and `POST /v1/audit/verify` already exist, are auditor-gated,
cursor-paginated, and audited themselves. The capability is not missing; only
its screen is.

**Decision.** The audit console moves to Phase 7. Spec 07 §6 is corrected.

The reason is the project's own precedent (ADR-038, ADR-039): a surface is built
with its first real consumer. An auditor console's first real reader appears at
P7, where sealing, break-glass and disclosure packages make "reviewable as one
query" a **gate criterion** — a console built now would be a list view with
nothing yet to adjudicate, and it would be rewritten when those arrive.

**Consequences.** Phase 4 neither builds nor is measured on an audit console,
and Phase 7's charter gains it as a deliverable rather than inheriting it as a
surprise. Auditors are not left without recourse in the meantime: the routes are
callable, and the auditor's substantive P4 capability — seeing retracted claims
that other roles cannot (`claim_filters`) — is unchanged and already tested.

**Revisit when.** An auditor is a real second user before P7, which the pilot
gate would have to clear first anyway.

---

## ADR-046: An event is an entity, participation is claims — Phase 5 adds no canonical event storage

**Context.** The pre-authored T56 said "migrations: event objects with
role-typed participant links … PostGIS `geometry` column + `precision` on
location entities". B-13 found the problem before a line was written: that model
puts asserted geometry, precision and participant roles in mutable columns
outside the claim store, which Article I says is where assertions live. ADR-033
amended the charter to a claims-first boundary in July; the task text was never
rewritten, so the first thing Phase 5 had to decide was which document it was
implementing.

**Decision.** Events are ordinary entities and everything asserted about them is
an ordinary claim.

- An **event** is a row in `entity` whose type implements the platform `event`
  interface — `meeting`, `arrest`, `travel`, `observation`.
- **Participation is a claim**, and the role **is the predicate**:
  `arrest --has_arrestee--> person`. One predicate per role.
- **Place is a claim** whose object is a `place` entity.
- **Time is the claim envelope** — `event_time_earliest` / `event_time_latest`,
  which have carried intervals with uncertainty since P1. No new time column and
  no time predicate exists.
- `record_event` creates the entity **and at least one claim in one
  transaction**, or nothing. An entity row carries no source; an event no claim
  asserts would be a fact with no provenance.

The core finds all of this **structurally**, never by name: an event entity is
one whose type implements `event`; a participation claim is one whose predicate
has every subject type implementing `event` and every object type implementing
`party`. Nothing under `aegis/` names `arrest` or `has_arrestee` (Article XIV).

**Consequences.** Provenance panels, three-dimension grading, contradiction
display, retraction, `?asOf=`/`?asOfRevision=`, case scoping, handling-code
filtering, the audit trail and the review queue all apply to events on the day
they ship, because none of them knows an event from a person. A parallel event
model would have had to re-earn every one.

The costs are real and accepted. Role vocabulary is predicate vocabulary, so a
new role is an ontology proposal rather than an enum edit — which is the
governance the project wants and the friction it implies. And two reports of one
occurrence make two events, because no entity-resolution path reaches an entity
with no mentions and automatic occurrence merging would be a machine making an
identity decision (Article VII, ADR-027). The reviewer's move is to attach the
second report's claims to the first event; `record_event` takes an `event_id`
for exactly that.

**Revisit when** a measured query genuinely cannot be served from `claim` plus
its indexes. The answer then is another *projection*, not a canonical table; a
canonical event table needs an Article I amendment first, which is the sentence
the Phase 5 charter already carries.

---

## ADR-047: A literal-object predicate declares the property it carries

**Context.** The ontology has two parallel vocabularies with no declared link
between them: `object_types.*.properties` (what a type has) and `predicates`
(what a claim says). `aegis/authz/filters.py::property_sensitivity` bridges them
by matching a predicate's *name* against a property's *name*, with a fallback
that guesses from the `identifier` flag. Spec 09 §6.4 recorded this as "a
documented heuristic, not a contract" and moved on, correctly, because nothing
in Phase 4 depended on it.

Phase 5 has two things that do. **M-18** requires map privacy to be enforced,
and `has_geometry` does not match a property named `geometry` under that
heuristic — so field-level sensitivity on geometry would silently not exist.
**Article XIV** requires the core to find geometry claims without a hardcoded
predicate name, and a name-matching heuristic is not a mechanism to build a
governance control on.

**Decision.** `PredicateSpec` gains an optional `property: <name>` — the
object-type property this literal-object predicate carries.

```yaml
has_geometry: {subject: [place], object: literal, property: geometry}
has_nic:      {subject: [person], object: literal, identifier: true, property: nic}
```

Loader rule 15 (continuing spec 08 §9): a declared `property` must exist on
**every** expanded subject type, and the predicate must allow a literal object.
`property_sensitivity` consults the declaration first and keeps the heuristic for
predicates that do not declare one, so nothing that works today stops working.
The core discovers geometry claims as "predicates whose declared property has
type `geo`" — the `geo` type slot P3 added to the DSL and nothing had yet used.

**Consequences.** Field-level sensitivity becomes a statement instead of a
coincidence, and it becomes so for the three existing identifier predicates at
the same time, which is worth doing while the mechanism is being built. Adding an
optional field is additive under spec 08 §7.3.

The heuristic is deliberately kept rather than removed. Removing it would make
every predicate that currently relies on it lose its sensitivity the moment this
lands, which is a governance regression shipped as a cleanup.

**Revisit when** every literal-object predicate in every shipped module declares
its property. Then the heuristic is dead code and deleting it is a no-op that a
test can prove.

---

## ADR-048: `location.precision` is removed and the composition goes to 2.0.0

**Context.** T55 said: add a **required** `precision` property on `location`,
with a **minor** bump, and "a location without `precision` fails validation".
Three things are wrong with that, and they compound.

H-21 rejects the ladder itself: `exact | centroid | area | city | country` mixes
epistemic precision, geometric representation and administrative granularity in
one string, so no consumer can reason about any of the three. Spec 01 §4 makes
optional→required a **major** change, which the amended charter states in its own
words. And the AC is unachievable at any version class: object-type properties
are claim-derived, no write path constructs an entity with a property set, and
`required` is enforced nowhere — so "fails validation" describes a mechanism that
does not exist.

**Decision.** `location.precision` is **removed**. The four axes H-21 asks for
arrive as **one claim with four fields** — `geometry` (RFC 7946, WGS84 only),
`accuracy_m`, `admin_level`, `derivation` — carried by a `has_geometry` predicate
whose declared property has type `geo`.

The composition bumps **1.7.0 → 2.0.0**. Removal is major regardless of row
counts; the precedent is v1.0.0's removal of `merged_into`, which also had no
rows. The major bump ships the history copy and a migration script that is a
documented no-op, because the removed property was never claimable.

The four fields travel in **one** claim rather than four, because they are one
assertion: an accuracy radius without its geometry means nothing, and four
independent claims could disagree in ways that have no interpretation. H-21 asks
that they be modelled separately, not asserted separately.

`admin_level` and `derivation` are **code-owned** vocabularies registered beside
`SUBMISSION_CRITERIA` and `PAYLOAD_SCHEMAS`, for the same reason those are: the
validator and the renderer must implement each value, so a value that could be
declared before it could be honoured would be a promise nothing keeps (H-13).

**Consequences.** A major bump is more ceremony than a phase's first ontology
change usually carries, and it is the ceremony the rules prescribe: the release
gate, the history copy and the migration all fire, and every claim stamped 1.7.0
keeps meaning exactly what it meant. Nothing has to be migrated, which is the
cheapest possible time to prove the major-bump path works end to end — the last
one ran a year of development ago.

The write-side validation rules (spec 10 §4.3) are where the honesty actually
lives: a Point may not claim an administrative area unless its derivation is a
stated centroid with a radius, so the renderer's "no bare pin" guarantee is
enforced twice — once by refusing the claim, once by having no branch that would
draw it.

**Revisit when** a source supplies a coordinate system other than WGS84 that
cannot be converted losslessly on ingest. That is a spec 10 §4.3 amendment, not a
schema change.

---

## ADR-049: The map is served as authorized GeoJSON, not vector tiles

**Context.** T59 said "PostGIS-backed tiles"; the charter said "evaluate MapLibre
Martin before hand-building" (H-21). Martin was evaluated.

**Decision.** Geometry is served as GeoJSON `FeatureCollection`s from ordinary
authorized routes (`GET /v1/geo/locations`, `GET /v1/geo/events`), filtered by
the same `claim_filters` as every other read, applied in candidate generation. No
tile server is built and none is adopted.

The reasoning is authorization, not effort. A vector tile is a cache keyed by
z/x/y and shared across viewers. Read authorization here is per claim — handling
code × clearance × case membership × as-of revision — so a correct tile cache
would have to be keyed by authorization context, which is a cache of one. What
remains is the failure mode: a mis-keyed tile serves sensitive geometry to the
wrong viewer, silently, and no test that checks a route's response would see it.
Martin's headline capability is auto-publishing PostGIS tables and functions,
which is the specific thing H-21 says must not happen to canonical tables.

Scale settles the rest: this corpus holds hundreds of locations, not millions of
features.

**Consequences.** The geo routes are ordinary routes. They inherit the authz
matrix, the no-anonymous-surface sweep, cursor pagination, the problem+json
envelope and the as-of stamp, and they are tested by the same machinery as
everything else. `next_cursor` rides as a foreign member of the
`FeatureCollection`, which RFC 7946 §6.1 permits.

Article XII is satisfied by adopting *nothing*: the smallest correct thing here
is the API surface that already exists.

**Revisit when** a bbox query returns more than 5 000 features or p95 exceeds
500 ms over the real corpus. Then Martin is evaluated again against a **private
per-authorization cache** — never a shared one — and the measurement is recorded
with the decision.


## ADR-050: One search route — `/v1/search` supersedes `/v1/search/entities`

**Context.** P2 shipped `GET /v1/search/entities` (T23c). The Phase 6 plan adds
"global search" across entities, claims and documents. M-11 warns that P2 and P6
search "overlap without a migration contract" and recommends one stable endpoint
with an additive backend, explicitly: *avoid parallel endpoints*.

**Decision.** There is one search route, `GET /v1/search`, with a `types`
parameter selecting result groups. `GET /v1/search/entities` is **removed** in
the same change, declared with `BREAKING API CHANGE` (spec 06 §7.3).

Adding a grouped route beside the entity route would produce exactly the outcome
M-11 names: two ranking models, two pagination implementations, and two places
where B-17's leak surfaces — ranking, counts, pagination gaps, timing, snippets,
consumption — have to be closed independently and can drift apart silently. The
honest expression of "same endpoint, additive backend" is that the endpoint stops
naming one of its backends.

**Consequences.** The workspace is the only client and regenerates from the
contract in the same commit (`make openapi`). `aegis api check-contract` reports
the removal; the marker is what makes it a decision rather than an accident. A
typeahead is the same route with `types=person,organization` and `limit=5`.

Groups enumerate `ontology.object_types` (Article XIV), so a new domain module's
types are searchable the day they are declared, with no route change.

**Revisit when** a second, non-workspace client exists. Then removal costs
someone else something, and the answer is a deprecation window rather than a
declared break.

---

## ADR-051: Searchable document text is a projection, not a column

**Context.** The charter says search spans "entities, claims, and documents".
Document text is not in PostgreSQL: `derivative.storage_uri` and
`source_record.storage_uri` point at the object store, and the database holds a
hash and a URI. There is nothing to index and, on a blob, no handling code to
filter by.

**Decision.** `document_text_projection` holds extracted text keyed by
(record, derivative), carrying `content_hash`, the record's `handling_code`, its
case scope, the normalization version, and a build stamp. It is a **projection**
under Article XIII: `aegis projections rebuild` truncates it and reproduces it
from the vault, and nothing but the builder writes to it.

The handling code is **copied from the record, never defaulted**. A default
would be a leak with a plausible-looking column beside it, and a row whose
record's handling code has since changed is stale in the unsafe direction — so
the builder is the only writer and a rebuild is the only correction.

**Consequences.** Search over documents is an ordinary filtered read: the same
candidate-generation rule applies (spec 11 §4), because the projection carries
the columns the filter needs. Storage grows by roughly the size of the extracted
text; this corpus is press reports and judgments, not a media archive.

Evidence-item text is deliberately **not** in this projection (spec 11 §12): its
read path is `can_view` on the item, not `claim_filters`, and putting two
authorization models behind one query is the thing this phase is trying not to
do.

**Revisit when** extraction produces text at a volume where a full rebuild is no
longer a routine operation. The answer then is incremental rebuild per record,
not a canonical text column.

---

## ADR-052: The normalization pipeline is versioned, and stored keys are stamped

**Context.** H-22 requires "one versioned index/query pipeline applied
identically at write and query time". `norm_key`, `latin_key` and `phonetic_key`
are applied at both ends today — but nothing records *which version* of them
produced a stored key. Changing `collapse_separators` desynchronises every
stored key from every query key, and the failure mode is **missing results**,
which nothing alerts on and no test would notice.

**Decision.** `NORMALIZATION_VERSION` is a code-owned string. Every table
storing a derived key carries the version that produced it. The query path
stamps its keys with the running version and compares only against rows carrying
that version. `aegis search check-index` exits non-zero on rows at an older
version, and CI runs it.

Bumping the version is a **reindex, not a reinterpretation**: rows are rebuilt.
This is safe precisely because nothing in the claim store depends on a key — the
asymmetry with `ontology_version` on a claim (ADR-013) is deliberate and worth
stating. A claim's meaning must survive forever, so its stamp is history. A key
is a cache, so its stamp is a build marker.

**Consequences.** A pipeline change becomes a two-step operation — bump, then
reindex — and the gate makes forgetting the second step a red build rather than
a quiet recall regression. Diacritic stripping is out of the pipeline entirely
(spec 11 §3.1) and any proposal to add it must arrive with labelled golden-set
evidence and its own ADR.

---

## ADR-053: Identifier queries match exactly, never fuzzily

**Context.** Search uses trigram similarity, which is the right tool for names.
An identifier — a NIC, a phone number, a registration number — is not a name. A
trigram near-match on an identifier returns a **different person** with a high
score and a name attached.

**Decision.** A query recognised as an identifier is matched by exact equality
after normalization, and never by similarity, phonetics, or prefix. The
precision target for identifier queries is 1.00 and a single fuzzy identifier hit
fails the quality gate rather than lowering a score.

Recall is knowingly traded away. A mistyped identifier returns nothing, and that
is the correct answer: the alternative is a confident wrong person, which
Article IX makes unacceptable at any recall.

**Consequences.** The identifier surface is the one place in search where a
false negative is preferred outright, and the gate is a pass/fail assertion
rather than a threshold, so it cannot be tuned away under pressure to improve a
number. Identifier *linkage* remains where it belongs — the ER pipeline, whose
output is a candidate for a human decision (Article VII), not a search result.

---

## ADR-054: An object set pins its ontology version, and interface expansion is frozen at pin time

**Context.** T69's pre-authored acceptance criterion says a set filtering on an
interface "picks up a new member type after an ontology minor bump without
edits". The charter was amended on 2026-07-18 (ADR-033, from B-17) to require
the opposite: *pinned to the ontology version by default, with an explicit
track-future-members opt-in and change notification*. The task text was never
rewritten.

**Decision.** Pinned by default. A set version records the composition version
current at save, and interface expansion is resolved at that moment and frozen
into the stored AST as an explicit member list. `track_interface_members: true`
is an explicit per-version opt-in that re-expands at every evaluation. Either
way, a composition bump that adds a member to an interface a set uses produces a
notice row for the owner and everyone it is shared with.

The reason is that a saved set is an **input to analytics and watchlists**. A
set that silently widens changes the meaning of a finding somebody already
acted on and of an alert rule nobody re-approved, and it does so at the moment a
*different* team lands a domain module. Ontology growth must not be a
scope-widening event.

**Consequences.** Sets survive ontology growth by not moving, which is the
opposite of the pre-authored AC and the same conclusion the amended charter
reached. The opt-in exists because "watch every kind of place, including ones we
have not modelled yet" is a legitimate thing to want — it is just not a default.

A pinned set gets the same notice as a tracking one, worded as an opportunity:
finding out that your set *could* have widened is as useful as finding out that
it did.

---

## ADR-055: An analytic run records an immutable manifest; reproducibility is manifest equality

**Context.** T72's criterion is "re-running with the same inputs reproduces the
finding". H-23 objects that neither an object set nor a projection is an
immutable input, and that method versions, identity revision, ontology,
authorization scope, seed and graph snapshot are not all required. Phase 5
carried forward a related gap: `is_stale` answers "was any row built at an older
identity revision", not "has this projection seen every claim" — so an operator
cannot detect that the graph is behind, and a finding could not say what it was
computed over.

**Decision.** Every analytic run writes an immutable manifest **before** the
algorithm runs, recording: method and method version; the **implementation that
actually ran** and its library version; parameters and seed; the object-set id
and version; an `evaluation_digest` over the sorted evaluated member ids; the
projection's `built_at_revision_id`, builder version and aggregation-method
version; an `edge_digest` over the edge rows consumed; ontology version;
identity revision; code version and settings digest; actor, purpose and an
authorization digest; caveat version; and timestamps.

**Reproducibility is defined as: equal manifests produce equal finding
digests**, ignoring actor, purpose and timestamps. That is a testable statement.
"Rerunning reproduces the finding" was not.

This closes the Phase 5 `is_stale` carryover **without changing what `is_stale`
means.** A manifest does not ask whether a projection was fresh — an
unanswerable question at the moment of a run — it records *which* projection was
read. Freshness is an operator's question about a cache; provenance is a
finding's question about its own inputs, and they are different questions.

It also closes a gap found during re-validation. `aegis/analytics/clustering.py`
falls back from Leiden to NetworkX Louvain when igraph is unavailable, and it
already stamps each returned cell with `algorithm: "louvain-fallback"` — more
than the first reading of it credited. What is missing is what makes that
durable: the label carries **no library version**, it rides on a summary **no
caller is obliged to persist**, and there is no run record for it to belong to.
Under the manifest the fallback is a required `implementation` field with its
version, so it is a different run rather than a differently-labelled result
somebody may have thrown away.

**Consequences.** A run is cheap to record and expensive to fake. A finding
whose manifest cannot be reconstructed is a finding nobody should promote, and
§10's promotion path can say so mechanically. The `authorization_digest` makes
Article VI legible in the record: a finding computed under a narrower clearance
is a different finding, and the manifest says which one it was.

---

## ADR-056: Watchlist evaluation is explicit or scheduled, never a write-path hook

**Context.** T75 says "an exact identifier landing in canon fires the watching
set's alert". Firing on write requires the generalized side-effect outbox that
spec 08 §6.5 declares and **nothing executes** — Phase 3 deferred it to its
first real consumer, Phase 5 needed neither, and it remains a Phase 6 carryover.

**Decision.** Watchlists are evaluated by an explicit command,
`aegis watchlists evaluate`, run on demand or on a schedule. Each sweep records
an `analytic_run` and an `evaluated_through` watermark, so the next run starts
where the last one finished and a window that was never evaluated is a visible
gap in the runs rather than silence.

Building the outbox to power one feature would ship a second inert mechanism:
one hook, one consumer, no second caller to prove the abstraction, and a
write-path dependency on machinery no test exercises under load. The outbox
lands with the first feature that genuinely needs on-write dispatch, which this
is not — a watchlist is a standing query, and running a standing query on a
schedule is the ordinary shape of the thing.

**Consequences.** Detection latency is the sweep interval, stated rather than
implied. Idempotence comes from the dedupe key
`(watchlist_id, rule_version, matched_value, entity_id)`, so a re-run over an
overlapping window produces no duplicate alerts.

Watchlist evaluation runs under the **watchlist owner's** authorization context,
recorded in the manifest — the one place a saved artifact evaluates with its
owner's clearance rather than the caller's. An alert nobody may read is not an
alert. It is stated here, in the decision record, rather than discovered later
in a query.

**Revisit when** a second feature needs on-write dispatch. Then the outbox has
two consumers, which is the point at which building it is engineering rather
than speculation.

---

## ADR-057: `/v1/graph/*` answers a question; `/v1/analytics/*` records an answer

**Context.** T72 lists k-hop neighbourhoods and shortest paths among the
analytics to build. `POST /v1/graph/expand` and `POST /v1/graph/paths` already
do both, shipped at T22, with a support-summary edge model, a budget, and an
authorization story that took a phase to get right.

**Decision.** The traversal implementation is shared. The routes differ in one
respect: whether the answer is **recorded**.

- `/v1/graph/expand` and `/v1/graph/paths` are interactive reads. They write
  nothing, need no manifest, and carry no caveat row.
- `/v1/analytics/{metric}` records an `analytic_run` and one or more
  `analytic_finding` rows, each carrying its manifest and its caveat, each
  promotable and auditable.

Recording is what demands the manifest, the caveat, the actor and the purpose,
because a recorded answer outlives the question and gets forwarded to people who
never saw the query. An interactive expansion does not, and making an analyst
mint a finding to look at a neighbourhood would make findings worthless by
volume.

**Consequences.** k-hop and shortest path appear in both places, deliberately.
Asking is free; committing to an answer is a governed act. Weighted paths are
**not** offered under either: ADR-030 removed the aggregate weight from
`edge_projection` on purpose, so there is no weight to traverse, and any future
weighted metric must declare its weight function in the manifest and derive it
from the support summary in the open.

---

## ADR-058: a finding points at the claim it became; nothing points back

**Context.** Spec 12 §10 said an accepted promotion linked the finding to the
claim in two ways: `analytic_finding.promoted_claim_id`, **and** a
`claim_relation` of kind `analytic_basis`. T74 tried to build the second and
found it unbuildable. `claim_relation` has `from_claim` and `to_claim`, both
foreign keys to `claim`, and its `relation` is constrained to `corroborates` /
`contradicts` — the claim-to-claim epistemic relations Article VIII is about.

A finding is not a claim. It has no `record_id`, no assertion type, no grading;
it is a computation over claims, and it is true of the corpus rather than of the
world. So it fits in neither column, and widening the constraint to admit it
would have made "this claim relates to that claim" mean two different things
depending on the row — the one property `claim_relation` exists to keep
unambiguous.

**Decision.** The link is `analytic_finding.promoted_claim_id`, and it is
one-directional on purpose. A finding records what it became; a claim records
nothing about having been a finding, beyond `assertion_type = 'assessed'` and
`collection_method = 'analytic'`, which is what a *reader* needs and all of it.

The spec is corrected, not the schema. `claim_relation` keeps one meaning.

**Consequences.** "Which computation is this claim based on?" is answered by a
lookup on `promoted_claim_id`, not by walking a relation — one indexed column
rather than a join through a table that would then hold two kinds of thing.

A claim reachable *as* a finding would be one lifecycle wearing two names, and
`tests/contract/test_findings_are_not_claims.py` asserts the separation at
the schema. Making the link symmetric would have quietly weakened that: the
whole point of Article IX's line is that an assessment can be recognised as one,
and a finding that is also addressable as a claim is an assessment that has
stopped announcing itself.

Promotion is refused if the finding already has a `promoted_claim_id`. One
finding, one assessed claim — two would read as two independent assessments of a
single computation, which is the double-counting the article guards against.

**Revisit when** something needs to record that a claim was *contradicted* by a
computation rather than derived from one. That is a genuinely different
relation, and it should arrive as its own typed thing rather than by loosening
this one.

---

## ADR-059: the rationale is part of a promotion's idempotency key

**Context.** `submit_suggestion` derives an idempotency key from
`(kind, producer, producer_version, payload)`, which is right for machine
producers: an extraction pass re-run over the same record should not queue the
same draft twice.

A finding promotion is not that. The producer is a person, the payload is the
claim they want to assert, and the reasoning — *why this computation is worth
asserting* — travels in `producer_meta`, outside the key. T74 hit the
consequence directly: after a promotion was **rejected**, an analyst with an
entirely different argument could not propose one, because the payload digest
was identical and the unique constraint refused it.

**Decision.** The rationale is part of the key. The rule this produces is the
one worth having: **the same argument, already rejected, cannot be resubmitted;
a new argument can.**

**Consequences.** A rejection is a decision about a proposal, not a permanent
verdict on a computation. A reviewer who says no to "central to the harbour
movements" is not thereby saying no to every future case anybody might make from
the same finding — which is what the collision would have meant, silently, and
which nobody chose.

Re-submitting an identical promotion still fails, loudly, at the constraint. If
the argument has not changed, neither has anything the reviewer already saw.

This does not generalise to machine producers. Their reasoning is their method
version, which is already in the key; a producer that varied its rationale run
to run would defeat idempotence rather than express disagreement.

---

## ADR-060: a watchlist alert is not a review-queue suggestion

**Context.** Spec 12 §11.2 and spec 06 §2.9 both say a detection is
`suggestion_kind = 'watchlist_hit'` "in the queue that already exists". H-24
asks for detections to be **typed alert suggestions** rather than facts, and the
review queue is where typed machine output goes.

T75 tried to build it there. Five of the six things an alert needs are things
the queue cannot give it:

1. `review_queue.target_action` is `NOT NULL`, and every kind maps to a dispatch
   branch. **An alert dispatches to nothing** — accepting one writes no claim,
   no entity, no relation. It would need a sentinel action that does nothing,
   which is a lie in a `NOT NULL` column.
2. `ck_review_queue_accepted_result` requires **exactly one typed result** on
   acceptance. An alert produces none. Admitting it means a fifth result column
   that is not a result, or a per-kind hole in the check that currently makes
   "acceptance wrote exactly one kind of thing" verifiable by the database.
3. The status vocabulary is `suggested / accepted / rejected / superseded /
   expired`. Triage is `new / reviewing / closed`. Two vocabularies in one
   column, or a second status column used by one kind.
4. Queue visibility is keyed on **`source_record.handling_code`**. An alert's
   sensitivity comes from the **claims** that triggered it, and a `sensitive`
   claim can sit in an `open` record. Reusing the queue would give alerts a
   visibility rule keyed on the wrong thing — quietly, and in the direction that
   discloses.
5. `watchlist_id`, `rule`, `rule_version`, `matched_value`, `entity_id`,
   `exactness`, `authority_ref` and a per-row handling code are eight fields
   used by exactly one kind.

The sixth fits well: the dedupe key is an idempotency key, and
`uq_review_queue_idempotency_key` would have enforced it.

**Decision.** `watchlist` and `watchlist_alert` are their own tables. The queue
keeps one meaning.

**This does not weaken Article VII**, and the reason matters. Article VII
governs machine output reaching **canonical tables**. An alert is not canonical
data: it asserts nothing about the world, and the claim it points at arrived
through the ordinary governed path already. It is a pointer at evidence,
produced by a rule the user wrote themselves.

What H-24 is really asking for is the queue's **discipline** — typed, deduped,
attributable to a rule and a version, triaged by a human, never acted on
automatically. That discipline is what `watchlist_alert` implements. The table
is different because the lifecycle is different, which is the same reasoning
ADR-058 used to keep a finding out of `claim_relation`.

**Consequences.** `GET /v1/alerts` filters on the alert's own `handling_rank`,
derived from the contributing claims exactly as a finding's is — one comparison
rather than a join back through the record. Dedupe is
`uq_watchlist_alert_dedupe` over `(watchlist_id, rule_version, matched_value,
entity_id)`, so a re-run over an overlapping window is idempotent by
construction rather than by the sweep remembering what it did.

`closed` requires a reason at the **database**, not in a handler:
`ck_watchlist_alert_closed_reason`. A workflow that can be routed around is not
a workflow, and spec 09 made the same call for investigation tasks.

**Revisit when** a second non-canonical machine output needs triage. Two of them
is an abstraction; one of them is this table.

