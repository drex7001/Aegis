# Phase 1 Charter — Claim store, evidence vault, RBAC, audit

Status: **COMPLETE** (T1–T16; retrospective record — this phase predates the
charter format; kept so `phases/` covers the whole P0–P9 pipeline) ·
Constitutional basis: Articles I, IV, VI, VII, X, XI, XIII · GOAL.md §40 M-I

## Objective

The governed foundation: claims (not edges) as the knowledge primitive in
PostgreSQL, immutable content-addressed evidence, authentication/authorization
and hash-chained audit from the first commit, extraction rewired to a review
queue, and the legacy UI fed from a rebuildable projection.

## Delivered (T1–T16)

- Compose stack + bootstrap: PostgreSQL/PostGIS, MinIO, Keycloak, OpenFGA.
- Governed claim store (claims, entities, mentions, sources, cases) with
  Alembic migrations; ontology-validated vocabularies (ADR-013).
- Content-addressed evidence vault with hash ledger and derivative tracking.
- Keycloak OIDC + OpenFGA ReBAC (tuples projected from Postgres via
  `authz_outbox`, ADR-014) + handling-code row filters; deny-by-default route
  lint (public routes explicit, ADR-019).
- Hash-chained, append-only audit with chain verification (ADR-015).
- Legacy migration (`aegis migrate-legacy`, ADR-016) — slugs became one-mention
  clusters; extraction passes emit suggested claims to the review queue.
- Projection builder (`aegis projections rebuild`) reproducing the
  legacy-shaped graph JSON from claims; legacy explorer served by `aegis serve`.
- API v1, `aegis` CLI, backup/restore drill (T15).

## Exit criteria — met

All four exit boxes checked; see the full walkthrough in
`../reviews/phase-01-exit-review.md`.

## Record

Tasks: `../tasks/phase-01.md` (T1–T16) · Exit review:
`../reviews/phase-01-exit-review.md` · Divergences: ADR-017…ADR-019.
