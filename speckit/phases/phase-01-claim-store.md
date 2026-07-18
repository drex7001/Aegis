# Phase 1 Charter — Claim store, evidence vault, RBAC, audit

Status: **COMPLETE with closure addendum** (T1–T16 delivered; T16a–T16d open —
ADR-033; retrospective record — this phase predates the charter format; kept so
`phases/` covers the whole P0–P9 pipeline) ·
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

## Closure addendum (2026-07-18 — ADR-033)

The 2026-07 external review found that the original exit review deferred
load-bearing governance items without owners, and that one criterion rested on
the ADR-019 public-route exception (since superseded by ADR-026). The verdict
is revised to *complete with closure addendum*. Open items — they block P2's
implementation milestones, not its design tasks:

- **T16a** interim exposure containment on the legacy `/api/*` surface
  (loopback default + limits; full retirement lands with P2 T22).
- **T16b** FGA revocation inline best-effort delete + documented staleness
  bound (ADR-014's specified behavior, deferred at T12).
- **T16c** dependency lockfile + CI pinning.
- **T16d** documentation honesty pass (statuses, README claims, legacy-only
  runbooks quarantined with warnings).

Field-level sensitivity filtering — the other deferred item — is feature work
and is a **hard P2 gate criterion**, not an addendum task.

## Record

Tasks: `../tasks/phase-01.md` (T1–T16 + addendum T16a–T16d) · Exit review:
`../reviews/phase-01-exit-review.md` (verdict revised 2026-07-18) ·
Divergences: ADR-017…ADR-019 (ADR-019 superseded by ADR-026).
