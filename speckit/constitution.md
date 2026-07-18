# Aegis Constitution

## Mission

Aegis is an **ontology-driven intelligence platform**: a sovereign, governed
environment in which every analytical domain — criminal-network analysis,
financial crime, border and customs intelligence, and others to come — is an
application of one shared core. The ontology is the product; the domains are
its consumers. Comparable in concept to Palantir's platforms, but open-stack,
auditable, and designed for Sri Lanka's legal, linguistic (Sinhala / Tamil /
English), and institutional context.

## Long-term vision

A single platform where the semantic layer (object types, properties, links,
interfaces), the kinetic layer (actions, functions), and the governance layer
(grading, handling, authorization, audit) are declared once in the ontology and
power every domain's ingestion, resolution, analysis, and UI. Adding a new
analytical domain means adding an ontology module — not building a new system.
**Criminal-network analysis is the first such domain**, not the platform's
identity.

The legacy implementation that preceded Aegis (the static pipeline and
Cytoscape explorer) is scaffolding: it is **replaced, never extended**. New
capability is designed from the ontology outward, without inheriting legacy
shapes or constraints (ADR-023).

## Articles

Non-negotiable principles. Every phase, every feature, every schema change is checked
against these articles. They condense GOAL.md §3 (design rules) and §41 (product
decisions) into testable rules. If a proposed change violates an article, the change is
wrong — not the article — unless the article itself is amended here, with a recorded
reason.

## Article I — Claims, not facts

The atomic knowledge unit is a **claim**: subject, predicate, object, source,
assertion type, grading, time, handling. Entities are stable identifiers that claims
attach to — they carry no asserted properties of their own beyond a display label
rebuilt from claims. Two sources may contradict each other without either being
deleted. (GOAL.md Rule 2, §7.4)

**Test:** no table or API accepts a relationship or attribute without a source record
reference.

## Article II — No inherent derogatory status

The ontology never encodes accusation as identity — in any domain. There is no
`Criminal` entity type, no `Terrorist` or `Fraudster` type, no global risk score, and no
permanent derogatory label. Roles (suspect, witness, victim, informant) are case-scoped,
time-bounded claims. Judicial states (charged, convicted, acquitted, sealed) are explicit
and current. (GOAL.md Rule 1, §22, §25)

**Test:** grep the ontology — no object type or unqualified property implies guilt.

## Article III — Source and information graded separately

Source reliability and information credibility are separate fields, preserved in their
original scheme plus a normalized internal form. A single collapsed confidence number is
never stored — display scores are *derived* and their components always inspectable.
(GOAL.md §1.2; already enforced in spirit by `weight`-derivation in `pipeline/models.py`)

**Test:** every claim exposes `reliability`, `credibility`, `verification_status`
independently; UI detail panels show all three.

## Article IV — Evidence is not intelligence

Original evidence is immutable, content-addressed, and hash-ledgered. Derivatives
(transcripts, translations, extracts) record parent, tool, version, parameters, hash.
Intelligence (reports, claims, assessments) never silently becomes evidence.
(GOAL.md §1.5, §5.1, §20)

**Test:** no code path mutates an object in the evidence store; every derivative row has
a parent reference.

## Article V — Reversible identity

Entity merges are never destructive. Identity is a versioned cluster of source mentions;
analysts can confirm, reject, split, and merge with recorded evidence. Name slugs are
*mention keys*, never identity. (GOAL.md §10)

**Test:** any merge can be undone by a cluster edit; no `UPDATE ... SET entity_id` that
loses the prior mapping.

## Article VI — Authorization at query time

Every read and write is authorized against role + relationship (case assignment,
handler-of) + handling code, **in the backend**, before data leaves the store. There is
no unrestricted global graph view and **no anonymous route**: "open" is a data
classification, not an authorization decision — an authenticated actor, a decision, and
an audit row exist for every access. Authorization applies at row *and* field level:
a property whose sensitivity exceeds the caller's clearance is absent from the
response. The policy engine is a first-class dependency from Phase 1 — retrofitting
access control is forbidden by this constitution. If a public demonstration is ever
needed, it is a statically generated fictional artifact outside the governed API
(ADR-026). (GOAL.md Rule 6, §23)

**Test:** every API route has an explicit authorization dependency — no exemption
marker exists; field-sensitivity filtering has a blocking test; direct DB access in
handlers without the policy filter fails code review.

## Article VII — Machines suggest, humans decide

Algorithmic output of every kind — LLM extraction, deterministic rules, ER candidates,
link prediction, alerts — enters a **review queue** as typed suggestions with
explanations. Nothing algorithmic writes to the canonical claim store, identity
clusters, or evidence: there is no auto-accept mode, no auto-merge rule, and no
machine-written claim class (ADR-027). Deterministic derivations of accepted claims
are **rebuildable derived records** (projections/findings, Article XIII), typed and
displayed as derived — never canonical claims. Exact-identifier identity matches are
pre-verified *candidates* a human confirms (batch confirmation is fine; the actor is
always human). An AI model is a source of *analytic suggestions*, never of observed
fact. (GOAL.md §7.6, §26)

**Test:** the only writer to canonical tables from any algorithmic code path is a
human-executed adjudication action recorded in audit; `decided_by` on identity
decisions is always a human actor.

## Article VIII — Disagreement is preserved

Conflicting claims, retractions, and exculpatory information stay visible. Conflict
resolution produces an *assessment* claim referencing what it weighs — it never deletes
or hides the losing side. (GOAL.md Rule 5)

**Test:** retraction sets `retracted_at`; nothing hard-deletes a recorded claim.

## Article IX — Association is not guilt

Network metrics ship with interpretation warnings. "Most connected" is never rendered as
"leader". Analytic findings (`possible_association`) are a distinct type from asserted
relationships. (GOAL.md §1.6, §13.2)

**Test:** every metric endpoint/UI panel includes its caveat text; findings and claims
are different tables.

## Article X — Everything is audited

Every read of sensitive data, every write, every export, every policy decision produces
an append-only, hash-chained audit event with actor, purpose, case, resource, decision.
Auditors are a role that administrators cannot silently bypass. (GOAL.md §39)

**Test:** audit rows are insert-only (no UPDATE/DELETE grants); chain verification job
passes.

## Article XI — The ontology is the single source of domain truth

Object types, properties, predicates, event types, grading schemes, handling codes, and
actions are declared in `ontology/aegis.yaml` (versioned). Pydantic models, DB
constraints, API routes, authorization object types, and UI screens derive from it.
Hand-written domain types that bypass the ontology are defects.

**Test:** CI validates the ontology; adding an entity type requires only an ontology
change plus a migration, not new bespoke screens.

## Article XII — Adopt before build

Use proven open source for every non-domain concern: identity (Keycloak), authorization
(OpenFGA), record linkage (Splink), storage (PostgreSQL/PostGIS/MinIO), search (Postgres
FTS → OpenSearch), orchestration (Dagster when needed). We hand-build only the domain
core: ontology, claim store, adjudication, projections.

**Test:** any "let's implement our own X" proposal needs an ADR explaining why the
shelf tool fails.

## Article XIII — Projections are caches

The claim store (PostgreSQL) is the source of truth. Graph views, search indexes,
Neo4j exports, and the UI's graph JSON are rebuildable projections. Losing every
projection loses nothing. (GOAL.md §8.3, §28)

**Test:** `rebuild-projections` command regenerates all derived stores from canonical
tables alone.

## Article XIV — The core is domain-neutral

Platform services (claim store, identity resolution, evidence vault, review queue,
actions, projections, search, authorization, audit) contain no hard-coded domain
concepts. A domain — criminal networks, financial crime, border intelligence — enters
the platform as an **ontology module** (object types, predicates, event types, actions,
functions) plus migrations, and every domain rides the same core. One-time migration
adapters (ADR-016) and code scheduled for deletion are the only exemptions. (ADR-023)

**Test:** adding a second domain requires an ontology change and migrations, not changes
to core services; domain nouns in core code outside ontology-derived artifacts fail
review.
