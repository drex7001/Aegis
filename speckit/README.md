# Aegis Spec Kit

This directory is the **specification kit** for evolving the current prototype
(`pipeline/`, `app/`) into **Aegis** — the governed intelligence platform described in
[`../GOAL.md`](../GOAL.md). GOAL.md is the *north star* (enterprise end-state); this kit
is the *buildable path* for a small team starting from the code that exists today.

## Reading order

| # | File | What it answers |
|---|------|-----------------|
| 1 | [`constitution.md`](constitution.md) | Non-negotiable principles. Never violated, in any phase. |
| 2 | [`spec.md`](spec.md) | What we are building, for whom, and what we are **not** building. |
| 3 | [`plan.md`](plan.md) | Technical plan: architecture, stack choices, upgrade paths. |
| 4 | [`decisions.md`](decisions.md) | ADR log — every load-bearing decision with rationale and revisit triggers. |
| 5 | [`roadmap.md`](roadmap.md) | Phased roadmap with exit criteria, mapped to the current repo. |
| 6 | [`tasks-phase-1.md`](tasks-phase-1.md) | Concrete, ordered task list for the next phase. |

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
