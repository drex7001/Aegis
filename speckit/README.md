# Aegis Spec Kit

This directory is the **specification kit** for building **Aegis** — the
ontology-driven intelligence platform described in [`../GOAL.md`](../GOAL.md), whose
first application domain is criminal-network analysis. GOAL.md is the *north star*
(enterprise end-state); this kit is the *buildable path* for a small team. The
pre-Aegis prototype (`pipeline/`, `app/`) is scaffolding to be **replaced, not
extended** (ADR-023).

## Reading order

| # | File | What it answers |
|---|------|-----------------|
| 1 | [`constitution.md`](constitution.md) | Non-negotiable principles. Never violated, in any phase. |
| 2 | [`spec.md`](spec.md) | What we are building, for whom, and what we are **not** building. |
| 3 | [`plan.md`](plan.md) | Technical plan: architecture, stack choices, upgrade paths. |
| 4 | [`decisions.md`](decisions.md) | ADR log — every load-bearing decision with rationale and revisit triggers. |
| 5 | [`roadmap.md`](roadmap.md) | Phased roadmap v2 (milestones I–VI, P0–P9, ★ MVP gate at P2) with exit criteria. |
| 6 | [`phases/`](phases/) | One charter per remaining phase (P2–P9): objectives, deliverables, dependencies, exit criteria, risks, task sketch. |
| 7 | [`tasks-phase-1.md`](tasks-phase-1.md) | Phase 1 task list (T1–T16, COMPLETE) + [`phase-1-exit-review.md`](phase-1-exit-review.md). |
| 8 | [`tasks-phase-2.md`](tasks-phase-2.md) | Phase 2 task list (T17–T28) — the active phase, closing with the MVP gate. |

## Detailed specs

| File | Scope |
|------|-------|
| [`specs/01-ontology.md`](specs/01-ontology.md) | The declarative ontology DSL — object types, predicates, actions, grading schemes. |
| [`specs/02-data-model.md`](specs/02-data-model.md) | Claim store schema (PostgreSQL DDL), time model, migration from current models. |
| [`specs/03-security.md`](specs/03-security.md) | RBAC + ReBAC design (Keycloak + OpenFGA), handling codes, audit, enforcement points. |
| [`specs/04-ingestion.md`](specs/04-ingestion.md) | Ingestion pipeline evolution: landing, idempotency, quarantine, suggested claims. |
| [`specs/05-entity-resolution.md`](specs/05-entity-resolution.md) | Splink-based ER, versioned identity clusters, adjudication. |
| [`specs/06-api.md`](specs/06-api.md) | API v1 surface, authorization annotations, as-of queries. |
| [`specs/07-ui.md`](specs/07-ui.md) | UI evolution: projection explorer → investigation workspace. |
| [`specs/08-ontology-v2.md`](specs/08-ontology-v2.md) | Ontology DSL v2 (Phase 3): interfaces, shared properties, functions, actions v2, change management, generated SDKs (ADR-021). |

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
