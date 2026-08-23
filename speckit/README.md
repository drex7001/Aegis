# Aegis Spec Kit

This directory is the **specification kit** for building **Aegis** — the
ontology-driven intelligence platform described in [`../GOAL.md`](../GOAL.md), whose
first application domain is criminal-network analysis. GOAL.md is the *north star*
(enterprise end-state); this kit is the *buildable path* for a small team. The
pre-Aegis prototype (quarantined under `legacy/`, ADR-024) is scaffolding to be **replaced, not
extended** (ADR-023).

## Reading order

| # | File | What it answers |
|---|------|-----------------|
| 1 | [`constitution.md`](constitution.md) | Non-negotiable principles. Never violated, in any phase. |
| 2 | [`spec.md`](spec.md) | What we are building, for whom, and what we are **not** building. |
| 3 | [`plan.md`](plan.md) | Technical plan: architecture, stack choices, upgrade paths. |
| 4 | [`decisions.md`](decisions.md) | ADR log — every load-bearing decision with rationale and revisit triggers. |
| 5 | [`roadmap.md`](roadmap.md) | Phased roadmap v2.1 (milestones I–VI, P0–P9, ★ MVP gate at P2, pilot deployment gate) with hard gate semantics (ADR-025) and exit criteria. |
| 6 | [`phases/`](phases/) | One charter per phase (P0–P9): objectives, deliverables, dependencies, exit criteria, risks, task sketch. P0–P1 are retrospective records; P4–P9 charters carry 2026-07 amendments their re-validation tasks disposition. |
| 7 | [`tasks/`](tasks/) | Per-phase T-level task lists, numbering global across phases: [`phase-01`](tasks/phase-01.md) (T1–T16 + closure addendum T16a–T16d — DONE) · [`phase-02`](tasks/phase-02.md) (T17–T28 — **DONE, ★ MVP gate passed**) · [`phase-03`](tasks/phase-03.md) (T29–T40 — **DONE**, all five gate criteria checked) · [`phase-04`](tasks/phase-04.md) (T41–T53 — **DONE**, all five gate criteria checked) · [`phase-05`](tasks/phase-05.md) (T54–T65 — **DONE**, all five gate criteria checked) · [`phase-06`](tasks/phase-06.md) (T66–T77 — **ACTIVE**, re-validated by T66) · pre-authored: [`phase-07`](tasks/phase-07.md) (T78–T89), [`phase-08`](tasks/phase-08.md) (T90–T101), [`phase-09`](tasks/phase-09.md) (T102–T113). |
| 8 | [`reviews/`](reviews/) | Phase exit reviews ([`phase-01`](reviews/phase-01-exit-review.md), verdict revised 2026-07-18; [`phase-02`](reviews/phase-02-exit-review.md), ★ MVP gate passed 2026-07-20) and the [Phase 5 migration dispositions](reviews/phase-05-migration-dispositions.md), and the [external-review disposition](reviews/2026-07-18-external-review-disposition.md) (B-01…B-19 accepted/narrowed/rejected, with homes). |

## Detailed specs

| File | Scope |
|------|-------|
| [`specs/01-ontology.md`](specs/01-ontology.md) | The declarative ontology DSL — object types, predicates, actions, grading schemes. |
| [`specs/02-data-model.md`](specs/02-data-model.md) | Claim store schema (PostgreSQL DDL), time model, migration from current models. |
| [`specs/03-security.md`](specs/03-security.md) | RBAC + ReBAC design (Keycloak + OpenFGA), handling codes, audit, enforcement points. |
| [`specs/04-ingestion.md`](specs/04-ingestion.md) | Ingestion pipeline evolution: landing, idempotency, quarantine, suggested claims. |
| [`specs/05-entity-resolution.md`](specs/05-entity-resolution.md) | Splink-based ER, versioned identity clusters, adjudication. |
| [`specs/06-api.md`](specs/06-api.md) | API v1 surface, authorization annotations, as-of queries. |
| [`specs/07-ui.md`](specs/07-ui.md) | The investigation workspace — one durable React + TS app from Phase 2 (ADR-032); amended by T41 (ADR-043, ADR-045). |
| [`specs/08-ontology-v2.md`](specs/08-ontology-v2.md) | Ontology v2 — **final** (Phase 3, narrowed by ADR-033, amended by ADR-037…042): module composition, interfaces, shared properties, actions v2 schema, change management, contracts. §0 records what T29's re-validation changed; §11 holds the machinery deferred to its first consumer. |
| [`specs/09-investigation-domain.md`](specs/09-investigation-domain.md) | Investigation domain & the object-view contract — **final** (Phase 4, T41): cases, hypotheses, tasks/leads as storage/actions/authorization written before any screen (H-17); the generic object view's descriptor contract and its leak-free case list (H-18); the narrowed as-of promise (B-11). §0 records what re-validation changed. |
| [`specs/10-events-geospatial.md`](specs/10-events-geospatial.md) | Events, geospatial & time — **final** (Phase 5, T54; ADR-046…049): events as entities and participation as claims (B-13); the event-vs-edge rule with its migration candidate list (M-17); geometry's four axes, WGS84-only, validated at the write (H-21); map privacy as a recorded coarser claim rather than a runtime blur (M-18); no external tile or geocoding service (M-19). §0 records what re-validation changed. |
| [`specs/11-search.md`](specs/11-search.md) | Search — **final** (Phase 6, T66; ADR-050…053): one route over entities, claims and documents (M-11); the versioned normalization pipeline applied identically at write and query time, with no wholesale diacritic stripping (H-22); authorization in candidate generation and the six leak surfaces B-17 names, each with a mechanism; numeric precision/recall/latency targets and the OpenSearch trigger written beside them. §0 records what re-validation changed. |
| [`specs/12-object-sets-analytics.md`](specs/12-object-sets-analytics.md) | Object sets, analytics & findings — **final** (Phase 6, T66; ADR-054…057): sets as validated ASTs that store queries and never results, pinned to an ontology version by default (B-17); one snapshot and one authorization context per evaluation (M-16); the immutable analytic run manifest that makes reproducibility checkable (H-23); the caveat catalog as code (Article IX); watchlist detections as typed alert suggestions (H-24). §0 records what re-validation changed. |

## The ontology artifact

[`../ontology/aegis.yaml`](../ontology/aegis.yaml) is the **declarative ontology** —
the single artifact from which schemas, validation, API surface, authorization object
types, and UI screens are progressively generated. Per ADR-003, code never defines a
domain type the ontology doesn't declare.

## How this kit relates to GOAL.md

GOAL.md describes the full platform (Kafka, Flink, Neo4j Enterprise, Kubernetes,
multi-agency federation). We adopt its **principles completely** and its
**infrastructure incrementally**. Where GOAL.md and the scaled plan diverge
(e.g. Neo4j-first vs Postgres-first), `decisions.md` records the choice, the reason,
and the objective trigger for upgrading to the GOAL.md end-state component.
Python/FastAPI is the reference implementation through production (ADR-020), and
GOAL.md §7.8–7.10 records the Foundry-informed ontology architecture this kit
implements phase by phase (ADR-021).
