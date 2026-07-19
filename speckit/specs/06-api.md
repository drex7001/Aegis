# Spec 06 — API v1

Status: **rewritten 2026-07-18 by P2 T17d as the authoritative route-by-route
authorization matrix (B-14).** Every route P2 ships has a row naming its role
gate, FGA relation, filters, purpose requirement, limits, and the tests that
prove it. T24b turns this table into an executable suite; T24a implements
field-sensitivity filtering; T24c implements cursor pagination.

**T22 (2026-07-19)** landed the graph routes, deleted the anonymous `/api/*`
surface together with the `public_route` exemption, and made stable operation
IDs, per-caller rate limits and security headers real; the rows and defaults
below say so where they changed. Where this text conflicts with
ADR-026/029/030/031, the ADRs win. · Constitutional basis:
Articles VI, X, XIII · ADR-012, ADR-026, ADR-029, ADR-030, ADR-031

FastAPI, `/v1/*`, OIDC bearer auth. Errors: RFC 7807 problem+json. Writes are
actions (validate → write → audit in one transaction).

**This file is authoritative for authorization.** A route that ships without a
row here is a defect, and the deny-by-default lint
(`find_ungated_routes`, `aegis/api/deps.py:127`) fails CI for a route with no
gate. Since T22 there is **no `public_route` exemption** — the marker and its
lint branch are deleted (ADR-026), and `test_route_gating.py` asserts the symbol
has not come back.

## 1. Defaults that apply to every route

Stated once so the matrix stays readable. A matrix cell says only what *differs*.

1. **Authenticated.** No anonymous route survives P2 (ADR-026, Article VI).
   **Satisfied at T22**: the legacy `/api/*` surface is deleted, `public_route`
   and its lint branch are gone, and `find_ungated_routes` now has no exemption
   to grant. The one thing served without a token is the workspace *bundle* — a
   static mount with no dependency graph and no database access, pinned by
   `test_route_gating.py` as the only mount the app may carry.
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
   (`aegis/api/deps.py:159`). Collection routes return the authorized subset
   with no "n hidden" affordance.
5. **Audited.** Every decision, allow and deny, writes an audit row with actor,
   purpose, resource, and decision (Article X). Denials record the failed check.
6. **Limits.** Default body limit 10 MiB (ingest: 100 MiB), default page size
   50, max 200. Rate limits per authenticated subject, not per IP —
   implemented at T22 (`aegis/api/ratelimit.py`) as a default limit on every
   route, keyed by a digest of the bearer token. The `sub` inside the token is
   deliberately not the key: the limiter runs before the gate validates the
   token, so an attacker-chosen `sub` could be rotated to escape the limit or
   pinned to a victim's to exhaust theirs. Configured by
   `AEGIS_API_RATE_LIMIT_PER_MINUTE` (default 600).
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
| `GET /v1/claims/{id}/provenance` | — | case `can_view` | **generic** provenance for any claim-derived value: source records, all three grading dimensions, relations, identity-decision line (B-14) | — | `test_why_connected.py` (T21) |
| `GET /v1/entities/{id}` | — | — | claims grouped by predicate; `?asOf=`, `?asOfRevision=` (§3) | — | matrix suite |
| `GET /v1/entities/{id}/why-connected/{other}` | — | — | claims, gradings, sources, relations, and the identity decisions behind the edge (GOAL.md §18); **undirected**, and resolves through the canonical map so claims written against an absorbed id still answer | max 200 claims, `truncated` disclosed | `test_why_connected.py` (T21) |
| `GET /v1/search/entities?q=` | — | — | `pg_trgm` over names/aliases/mention norm_keys; **authorization applied in candidate generation, not only hydration** (ADR-012, B-17); cursor | q ≤ 200 chars | `test_search`, matrix suite |

### 2.2 Review queue & identity (Articles VII, V)

| Route | R | F | Notes / filters | Limits | Tests |
|---|---|---|---|---|---|
| `GET /v1/review-queue?kind=&producer=&status=&record=` | analyst | — | typed rows (specs/02 §3.2); cursor | — | matrix suite |
| `POST /v1/review-queue/{id}/accept` | analyst | case `can_edit` | body may edit the payload; **dispatches through `target_action`** with the reviewer as actor (ADR-031 §2) — the route never writes tables | body 1 MiB | `test_review_dispatch` per kind |
| `POST /v1/review-queue/{id}/reject` | analyst | case `can_edit` | reason required | — | `test_actions.py` |
| `GET /v1/identity/candidates?disposition=&producer=` | analyst | — | `er_candidate` rows with full per-feature waterfall; pre-verified band first, then strongest score (nulls last — a rule computes no score and must not sort above a confident one); cursor. Returns `{revision_id, candidates}`: the revision travels with the list because `parent_revision_id` means *the state the analyst decided from*, and a separate lookup would let a client send one newer than the screen it read (T23b) | limit ≤ 200 | `test_identity_candidates` |
| `POST /v1/identity/candidates/batch-confirm` | analyst | — | pre-verified band only; **one human action, one ledger decision per pair** (ADR-027); note required | ≤ 100 pairs | `test_batch_confirm` |
| `POST /v1/identity/decisions` | analyst | — | confirm/reject/split/unresolved; `parent_revision_id` required; **409 on stale scope** with intervening decisions in the body (specs/05 §2). The body is a **discriminated union on `mode`**, not one bag of optional fields: only reject carries `evidence_basis`, only split names an entity and the mentions leaving it, so the document states it rather than leaving clients to learn it by 422 (T23b) | — | `test_concurrency` |
| `GET /v1/entities/{id}/identity-history` | — | — | the decision line: who, when, why, which revision | — | `test_why_connected.py` (T21) |

`POST /v1/entities/{id}/split` from the Phase-1 draft is **folded into**
`POST /v1/identity/decisions` (kind `split`) — one route, one concurrency rule,
one audit shape.

### 2.3 Sources & ingestion

| Route | R | F | Notes / filters | Limits | Tests |
|---|---|---|---|---|---|
| `POST /v1/sources` · `GET /v1/sources` | analyst | — | cursor on list | — | matrix suite |
| `POST /v1/ingest/file` (multipart) | analyst, investigator | — | lands; `outcome` (`landed`/`already_landed`/`quarantined`) is what the *request* did, `record.status` is what the *record* is — they differ when re-sending something already quarantined | body `AEGIS_INGEST_MAX_BYTES`, default 100 MiB → `413` | `test_ingest_routes.py` (T23a) |
| `POST /v1/ingest/text` (JSON) | analyst, investigator | — | pasted entry, same rules and same `land_bytes`. Split from the multipart route rather than one route with two optional bodies: they carry different inputs, and "exactly one of" is a validation rule the type system can express as two operations instead | as above | `test_ingest_routes.py` |
| `GET /v1/source-records` | analyst | — | handling-filtered; rows above clearance are **absent, not counted** (§1 default 4). Deterministic order (`received_at desc, record_id desc`) so T24c's cursor is stable | limit ≤ 200 | `test_ingest_routes.py` |
| `GET /v1/source-records/{id}` | — | — | provenance envelope, derivatives, quarantine state | — | matrix suite |
| `GET /v1/source-records/{id}/derivatives` | analyst | — | recorded transformations (tool, version, params, output hash); 404 when the record is above clearance | — | `test_ingest_routes.py` |
| `POST /v1/source-records/{id}/extract` | analyst | — | derivative stage + one producer, **synchronously** (ADR-034); `409` on a quarantined record, `422` on a media type with no tool. Writes suggestions only, never claims (Article VII) | one producer per call | `test_ingest_routes.py` |
| `POST /v1/source-records/{id}/release` | supervisor | — | un-quarantine, audited | — | `test_ingest_routes.py` |

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
| `POST /v1/graph/expand` | — | — | seed ids, max hops, categories, time window, max results; edges carry the **support summary and stamps**, never an aggregate weight (ADR-030). An edge is visible when ≥ 1 supporting claim passes `claim_filters`, and its summary is rebuilt from **only those** claims (T22) | ≤ 3 hops, ≤ 2 000 elements (nodes + edges), ≤ 100 seeds; over-asking is clamped and disclosed as `truncated` | `test_graph_routes.py` |
| `POST /v1/graph/paths` | — | — | shortest routes only, not all routes (T22): a path nobody can audit is machine-produced insinuation (Article IX) | ≤ 5 hops, ≤ 25 paths | `test_graph_routes.py` |
| `POST /v1/analytics/{algo}` | analyst | — | returns `AnalyticFinding` + caveat text (Article IX) — P6 | — | P6 |
| `POST /v1/findings/{id}/promote` | analyst | — | finding → review queue as an assessed-claim draft — P6 | — | P6 |
| `POST /v1/projections/rebuild` | admin | — | **controlled job/admin action only** (B-14): full rebuild is a DoS and staleness risk, not general analyst capability | 1 concurrent | `test_projections.py`, matrix suite |
| ~~`GET /api/graph`, `/api/stats`, `/api/cells`, `/api/query/{name}`~~ | — | — | **deleted at T22** (ADR-026) with the `public_route` marker and the legacy explorer. `/api` stays a reserved path prefix so a caller of a retired route gets 404, not the workspace's HTML | — | `test_route_gating.py`, `test_workspace_serving.py` |

### 2.7 Ontology vocabulary

| Route | R | F | Notes / filters | Limits | Tests |
|---|---|---|---|---|---|
| `GET /v1/ontology/vocabulary` | — | — | handling codes (**ordered** — clearance is an index into the list), source types, and `assertion_types`, so no client hard-codes a vocabulary the server owns. The first two come from `aegis.yaml` (Article XI); `assertion_types` is **platform epistemics, not domain vocabulary** (Article XIV), so it comes from a code-owned constant and is sorted — unlike handling codes, its order carries no meaning (T23b). Authenticated but unrestricted by role: it is the shape of the domain, not an assertion about anyone in it. Superseded in P4 by the generated `ui_meta.json` (spec 07 §3) | — | `test_ingest_routes.py`, `test_openapi.py` |

### 2.8 Audit

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
  workspace's TypeScript client is generated from this OpenAPI document.
  **Implemented at T22**: every route declares an explicit camelCase
  `operation_id`, and `tests/contract/test_openapi.py` fails on a missing one, a
  duplicate, or FastAPI's generated default — which embeds the Python function
  name, so an ordinary refactor would silently rename a client method. The same
  test fails when the committed `ui/openapi.json` drifts from the live routes.
  P3 (T36) extends the gate to the ontology-generated SDK.
- **Security headers** are served with every response (T22,
  `aegis/api/security.py`): `default-src 'none'` plus `no-store` on API paths,
  the workspace policy on the bundle, and a CDN exception scoped to `/docs`.
  HSTS is emitted only over TLS.
- Error bodies never disclose the existence of a resource the caller may not
  see: 404 and 403 are chosen per default 4, and the problem detail is generic.
