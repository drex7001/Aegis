# Spec 06 — API v1

Status: implemented in Phase 1 (v1 reference) — **rewritten 2026-07-18 by P2
T17d as the authoritative route-by-route authorization matrix (B-14). Every
route P2 ships has a row naming its role gate, FGA relation, filters, purpose
requirement, limits, and the tests that prove it. T24b turns this table into an
executable suite; T24a implements field-sensitivity filtering; T24c implements
cursor pagination. Stable operation IDs land in P3 (T36). Where this text
conflicts with ADR-026/029/030/031, the ADRs win.** · Constitutional basis:
Articles VI, X, XIII · ADR-012, ADR-026, ADR-029, ADR-030, ADR-031

FastAPI, `/v1/*`, OIDC bearer auth. Errors: RFC 7807 problem+json. Writes are
actions (validate → write → audit in one transaction).

**This file is authoritative for authorization.** A route that ships without a
row here is a defect, and the deny-by-default lint
(`find_ungated_routes`, `aegis/api/deps.py:131`) fails CI for a route with no
gate. After P2 T22 there is **no `public_route` exemption** — the marker and its
lint branch are deleted (ADR-026).

## 1. Defaults that apply to every route

Stated once so the matrix stays readable. A matrix cell says only what *differs*.

1. **Authenticated.** No anonymous route survives P2 (ADR-026, Article VI).
   The legacy `/api/*` surface is deleted by T22; until then it is
   loopback-bound with response and rate limits (T16a) — an exposure control,
   not an authorization decision.
2. **Row filters, always appended** (`aegis/authz/filters.py`, specs/03 §4):
   `handling_rank(row) <= user.clearance`; case scoping (member cases ∪
   case-less rows); `retracted_at IS NULL` unless auditor; sealed exclusions
   (P7).
3. **Field filters** (T24a): any property whose ontology `sensitivity` exceeds
   the caller's clearance is **absent** from the response — not masked, not
   counted, not hinted. The P7 marked-redaction mode is a different, later
   policy.
4. **No existence leaks.** Unauthorized and nonexistent both return **404** on
   single-resource reads; the pattern is `fga_check_or_404`
   (`aegis/api/deps.py:160`). Collection routes return the authorized subset
   with no "n hidden" affordance.
5. **Audited.** Every decision, allow and deny, writes an audit row with actor,
   purpose, resource, and decision (Article X). Denials record the failed check.
6. **Limits.** Default body limit 10 MiB (ingest: 100 MiB), default page size
   50, max 200. Rate limits per authenticated subject, not per IP.
7. **Purpose.** Required (`?purpose=`) wherever the matrix says **P**: reads of
   `handling >= restricted`, all audit queries, and all exports (GOAL.md §12.4).

Legend in the matrix: **R** role gate · **F** FGA relation · **P** purpose
required · **cursor** paginated per §4.

## 2. The matrix

### 2.1 Knowledge

| Route | R | F | Notes / filters | Limits | Tests |
|---|---|---|---|---|---|
| `POST /v1/claims` | analyst, investigator | case `can_edit` if case-scoped | body validated against ontology; anchors required for observed/reported (specs/02 §3.1) | body 1 MiB | `test_actions.py`, matrix suite |
| `POST /v1/claims/{id}/retract` | analyst, supervisor | case `can_edit` | reason required; soft (Article VIII) | — | `test_actions.py` |
| `POST /v1/claims/{id}/relations` | analyst | case `can_edit` | corroborates/contradicts | — | `test_actions.py` |
| `GET /v1/claims/{id}` | — | case `can_view` | grading components separate (Article III), source ref, relations | — | matrix suite |
| `GET /v1/claims/{id}/provenance` | — | case `can_view` | **generic** provenance for any claim-derived value: source records, all three grading dimensions, relations, identity-decision line (B-14) | — | `test_provenance` |
| `GET /v1/entities/{id}` | — | — | claims grouped by predicate; `?asOf=`, `?asOfRevision=` (§3) | — | matrix suite |
| `GET /v1/entities/{id}/why-connected/{other}` | — | — | claims, gradings, sources, relations, and the identity decisions behind the edge (GOAL.md §18) | max 200 claims | `test_why_connected` |
| `GET /v1/search/entities?q=` | — | — | `pg_trgm` over names/aliases/mention norm_keys; **authorization applied in candidate generation, not only hydration** (ADR-012, B-17); cursor | q ≤ 200 chars | `test_search`, matrix suite |

### 2.2 Review queue & identity (Articles VII, V)

| Route | R | F | Notes / filters | Limits | Tests |
|---|---|---|---|---|---|
| `GET /v1/review-queue?kind=&producer=&status=&record=` | analyst | — | typed rows (specs/02 §3.2); cursor | — | matrix suite |
| `POST /v1/review-queue/{id}/accept` | analyst | case `can_edit` | body may edit the payload; **dispatches through `target_action`** with the reviewer as actor (ADR-031 §2) — the route never writes tables | body 1 MiB | `test_review_dispatch` per kind |
| `POST /v1/review-queue/{id}/reject` | analyst | case `can_edit` | reason required | — | `test_actions.py` |
| `GET /v1/identity/candidates?disposition=&producer=` | analyst | — | `er_candidate` rows with full per-feature waterfall; pre-verified band first; cursor | — | `test_identity_candidates` |
| `POST /v1/identity/candidates/batch-confirm` | analyst | — | pre-verified band only; **one human action, one ledger decision per pair** (ADR-027); note required | ≤ 100 pairs | `test_batch_confirm` |
| `POST /v1/identity/decisions` | analyst | — | confirm/reject/split/unresolved; `parent_revision_id` required; **409 on stale scope** with intervening decisions in the body (specs/05 §2) | — | `test_concurrency` |
| `GET /v1/entities/{id}/identity-history` | — | — | the decision line: who, when, why, which revision | — | `test_identity_history` |

`POST /v1/entities/{id}/split` from the Phase-1 draft is **folded into**
`POST /v1/identity/decisions` (kind `split`) — one route, one concurrency rule,
one audit shape.

### 2.3 Sources & ingestion

| Route | R | F | Notes / filters | Limits | Tests |
|---|---|---|---|---|---|
| `POST /v1/sources` · `GET /v1/sources` | analyst | — | cursor on list | — | matrix suite |
| `POST /v1/ingest` (multipart) | analyst, investigator | — | lands, returns record_id + status; idempotent re-upload reports "already landed" | body 100 MiB | `test_ingestion.py` |
| `GET /v1/source-records/{id}` | — | — | provenance envelope, derivatives, quarantine state | — | matrix suite |
| `POST /v1/source-records/{id}/release` | supervisor | — | un-quarantine, audited | — | `test_ingestion.py` |

### 2.4 Evidence & custody

| Route | R | F | Notes / filters | Limits | Tests |
|---|---|---|---|---|---|
| `POST /v1/evidence` | investigator, evidence_officer | case `can_edit` | — | body 100 MiB | `test_evidence_migration.py` |
| `POST /v1/evidence/{id}/custody-events` | — | `can_transfer` | — | — | matrix suite |
| `GET /v1/evidence/{id}` | — | `can_view` | item + derivatives + custody chain + hash status | — | matrix suite |

### 2.5 Cases

| Route | R | F | Notes / filters | Limits | Tests |
|---|---|---|---|---|---|
| `POST /v1/cases` | analyst, investigator | — | **P** | — | `test_authz.py` |
| `GET /v1/cases/{id}` | — | `can_view` | 404 for non-members — **no case-existence leak** | — | `test_authz.py`, matrix suite |
| `POST /v1/cases/{id}/members` | supervisor | `can_approve` | creates or replaces; replacement queues + inline-deletes the old FGA tuple after commit (ADR-014) | — | `test_authz_openfga.py` |
| `DELETE /v1/cases/{id}/members/{user_id}` | supervisor | `can_approve` | canonical removal + outbox delete; inline best-effort FGA delete after commit | — | `test_revocation.py`, `test_authz_openfga.py` |

### 2.6 Graph, projections & analytics

| Route | R | F | Notes / filters | Limits | Tests |
|---|---|---|---|---|---|
| `POST /v1/graph/expand` | — | — | seed ids, max hops, categories, time window, max results; edges carry the **support summary and stamps**, never an aggregate weight (ADR-030) | ≤ 3 hops, ≤ 2 000 elements | `test_projections.py`, `test_graph_support` |
| `POST /v1/graph/paths` | — | — | bounded shortest/all paths | ≤ 5 hops | `test_projections.py` |
| `POST /v1/analytics/{algo}` | analyst | — | returns `AnalyticFinding` + caveat text (Article IX) — P6 | — | P6 |
| `POST /v1/findings/{id}/promote` | analyst | — | finding → review queue as an assessed-claim draft — P6 | — | P6 |
| `POST /v1/projections/rebuild` | admin | — | **controlled job/admin action only** (B-14): full rebuild is a DoS and staleness risk, not general analyst capability | 1 concurrent | `test_projections.py`, matrix suite |
| ~~`GET /api/graph`, `/api/stats`, `/api/cells`, `/api/query/{name}`~~ | — | — | **deleted at P2 T22** (ADR-026) with the `public_route` marker and the legacy explorer | — | `test_legacy_containment.py` until T22 |

### 2.7 Audit

| Route | R | F | Notes / filters | Limits | Tests |
|---|---|---|---|---|---|
| `GET /v1/audit?actor=&case=&action=&from=&to=` | auditor | — | **P** — querying audit is itself audited; cursor | — | `test_audit.py` |
| `POST /v1/audit/verify` | auditor, admin | — | chain verification report | — | `test_audit.py` |

## 3. Time and identity revision (ADR-029)

- `?asOf=<ts>` on knowledge reads filters `recorded_at <= ts AND (retracted_at
  IS NULL OR retracted_at > ts)` — "what did we know then". This is a
  **claim-recording snapshot**, not full multi-axis bitemporality (B-11, P4).
- `?asOfRevision=<id>` pins the identity revision used to resolve entity
  arguments. Without it, reads resolve through the **active** revision
  (specs/02 §3.1 rule 3). Passing `asOf` alone resolves identity as it is *now*,
  which is usually not what a historical question means — so any response
  carrying `asOf` **echoes the revision it resolved at**, and the UI shows both
  in its as-of banner (specs/07 §5).
- Every projection-backed response carries the build's identity revision,
  ontology version, and builder version (ADR-030), so a stale read is
  detectable rather than silently wrong.

## 4. Pagination (T24c, M-12)

- Cursor-based: `?cursor=<opaque>&limit=<n>`; default 50, max 200. `limit`
  above the max is clamped, not rejected.
- The cursor is **opaque** (base64 of the ordering key) and carries no
  authorization meaning — it is re-authorized on every request, so a leaked
  cursor grants nothing.
- Deterministic total ordering on every paginated route: ULID primary key as
  the final sort key, so iteration is stable under concurrent inserts.
- **No total counts** on authorization-filtered collections: a count is an
  existence leak (default 4). Responses carry `next_cursor` only.
- Applies to: review queue, identity candidates, entity search, sources, audit,
  and every P2 list view.

## 5. Governance seams (B-08 — nullable in P2, enforced P7)

Specified in specs/02 §1 and landed by T24a so P7 needs no reclassification
migration: `source_record.collection_policy_ref`, `source_record.retention_class`,
and legal-authority validity fields. P2 **stores and displays** them; it does
not enforce them. No route filters on them in P2, and none may claim to.

## 6. Conventions

- Exports (any bulk out-format) go through `POST /v1/exports` — P7 packages;
  P2 ships only an audited JSON dump of an authorized projection.
- Stable operation IDs are an API convention from P2 (ADR-032 §2) because the
  workspace's TypeScript client is generated from this OpenAPI document; P3
  (T36) adds the CI drift gate.
- Error bodies never disclose the existence of a resource the caller may not
  see: 404 and 403 are chosen per default 4, and the problem detail is generic.
