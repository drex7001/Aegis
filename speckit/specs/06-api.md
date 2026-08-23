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
ADR-026/029/030/031, the ADRs win.

**T29 (2026-08-17)** added §7 — the contract conventions Phase 3 builds the
generated client on: operation-id rules, the error envelope as a documented
component schema (P2 ships it at runtime but not in the contract), and the
contract-diff gate T36 enforces. · Constitutional basis:
Articles VI, X, XIII · ADR-012, ADR-026, ADR-029, ADR-030, ADR-031, ADR-039

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
| `GET /v1/entities/{id}` | — | — | claims grouped by predicate, **each with its grading, source and both relation directions** so a property disagreement is named rather than left to be noticed (ADR-036); resolves through the canonical map, reporting `resolved_entity_id`; `?asOf=`, `?asOfRevision=` (§3) | max 200 claims, `truncated` disclosed | `test_entity_provenance.py` (T23c), matrix suite |
| `GET /v1/entities/{id}/why-connected/{other}` | — | — | claims, gradings, sources, relations, and the identity decisions behind the edge (GOAL.md §18); **undirected**, and resolves through the canonical map so claims written against an absorbed id still answer | max 200 claims, `truncated` disclosed | `test_why_connected.py` (T21) |
| `GET /v1/search?q=&types=` | — | — | **One route for every searchable thing** (ADR-050, M-11): entities, claims (`excerpt` + literal values) and documents (`document_text_projection`, ADR-051), grouped by ontology object type plus the `claim` and `document` groups — the group list is enumerated from `ontology.object_types`, never hard-coded (Article XIV). `pg_trgm` over names/aliases/**mention keys** — `norm_key` plus the stored `latin_key`/`phonetic_key`, which is what makes a romanized query reach a Sinhala name (ADR-035); each hit reports `matched` so a phonetic lead is not read as a name match; **identifiers match exactly, never fuzzily** (ADR-053). **Authorization applied in candidate generation, not only hydration** (ADR-012, B-17): a hit the caller's filters exclude is absent from the scan, so no total, approximate total or hidden count is returned in any group, and an empty group is omitted rather than returned empty. `asOf`/`asOfRevision` per §3. Supersedes `GET /v1/search/entities`, removed with `BREAKING API CHANGE` | q ≤ 200 chars, limit ≤ 50 per group, ≤ 12 groups, 3 000 ms statement timeout | `test_search.py`, `test_search_authz.py`, `test_search_quality.py` (T67, T68) |
| ~~`GET /v1/search/entities?q=`~~ | — | — | **Removed at T67** (ADR-050). P2's first implementation of the route above, under a narrower name; M-11 asks for one endpoint with an additive backend, and two parallel search routes would be two rankings, two paginations and two copies of B-17's leak surface | — | `test_openapi.py` (contract diff) |

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
| `GET /v1/source-records/{id}?purpose=` | — | — | provenance envelope, derivatives, quarantine state. **Purpose is required when the record's handling code ranks above the first one the ontology declares** (spec 11 §7) — an index, not the literal name `open`, so a renamed ladder keeps the rule. Missing or blank is `422`: the caller is permitted and the *request* is incomplete, and a 403 would disclose more than the 404 an over-clearance caller already gets. The allow is audited with the purpose and the record id (Article X). Conditional, so the **gate** cannot express it — the route does, and `test_purpose_capture.py` proves it | — | `test_purpose_capture.py` (T67), matrix suite |
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
| `GET /v1/cases` | — | per row | **Only the caller's own cases** — derived from canonical `case_member`, not filtered afterwards. Cursor; **no total** (§4 default 4); ordered by `case_id`, never by activity, so a hidden row leaves no gap in a ranking | cursor | `test_investigation_routes.py` |
| `GET /v1/cases/{id}` | — | `can_view` | 404 for non-members — **no case-existence leak** | — | `test_authz.py`, matrix suite |
| `POST /v1/cases/{id}/close` | supervisor | `can_approve` | audited; sets `status='closed'` + `closed_at`. Never deletes, and a closed case cannot be closed again | — | `test_investigation_model.py` |
| `POST /v1/cases/{id}/members` | supervisor | `can_approve` | creates or replaces; replacement queues + inline-deletes the old FGA tuple after commit (ADR-014) | — | `test_authz_openfga.py` |
| `DELETE /v1/cases/{id}/members/{user_id}` | supervisor | `can_approve` | canonical removal + outbox delete; inline best-effort FGA delete after commit | — | `test_revocation.py`, `test_authz_openfga.py` |
| `GET /v1/cases/{id}/members` | — | `can_view` | members of a case you can view; 404 otherwise | — | `test_investigation_routes.py` |
| `GET /v1/cases/{id}/references` | — | `can_view` | attached references only (detached rows are tombstoned, not deleted) | — | `test_investigation_routes.py` |
| `POST /v1/cases/{id}/references` | analyst, investigator | `can_edit` | **ADR-044**: "this investigation refers to that". Grants **no** read access to the target and never touches `claim.case_id`, which is the immutable recording scope `claim_filters` reads | — | `test_investigation_model.py` |
| `DELETE /v1/cases/{id}/references/{target_type}/{target_id}` | analyst, investigator | `can_edit` | tombstone + `reason`; re-linking clears it rather than inserting a second row | — | `test_investigation_model.py` |

### 2.5.1 Hypotheses & tasks (P4 — spec 09 §3–§5)

Neither resource has authorization of its own: both belong to exactly one case,
and `can_view`/`can_edit` derive from it in the FGA model. **A non-member gets
404 from every route below, writes included** — a 403 on a write discloses the
case just as surely as one on a read.

| Route | R | F | Notes / filters | Limits | Tests |
|---|---|---|---|---|---|
| `POST /v1/hypotheses` | analyst, investigator | `can_edit` on the case | writes the hypothesis and its first revision in one transaction. `missing_info` is required **and** must be non-blank (`required_text_is_substantive`, spec 09 §3.3) | — | `test_investigation_routes.py` |
| `GET /v1/hypotheses?case={id}` | — | `can_view` | case is required; there is no global hypothesis list | — | `test_investigation_routes.py` |
| `GET /v1/hypotheses/{id}` | — | `can_view` via its case | current revision + full history + `supporting`/`contradicting`. Both arrays are **always present**, empty or not: Article VIII is a rendering obligation, and a client cannot render "no contradicting evidence recorded" from an omitted field | — | `test_investigation_routes.py` |
| `POST /v1/hypotheses/{id}/revisions` | analyst, investigator | `can_edit` | a revision is a **snapshot, not a diff** — unsupplied fields carry forward | — | `test_investigation_model.py` |
| `POST /v1/hypotheses/{id}/claims` | analyst, investigator | `can_edit` | stance `supports`/`contradicts`. The same claim may be linked under **both** (spec 09 §3.2). Linking grants no access to the claim | — | `test_investigation_model.py` |
| `DELETE /v1/hypotheses/{id}/claims/{claim_id}/{stance}` | analyst, investigator | `can_edit` | tombstone + `reason` | — | `test_investigation_model.py` |
| `POST /v1/tasks` | analyst, investigator | `can_edit` on the case | `kind` is `task` or `lead`; unassigned is a real state | — | `test_investigation_routes.py` |
| `GET /v1/tasks?case={id}` | — | `can_view` | case-scoped, key-ordered | — | `test_investigation_routes.py` |
| `POST /v1/tasks/{id}` | analyst, investigator | `can_edit` | **no transition graph** — any status may follow any other, and the audit row carries the old value beside the new one. `closed_at` follows the status rather than the caller | — | `test_investigation_model.py` |

### 2.6 Graph, projections & analytics

| Route | R | F | Notes / filters | Limits | Tests |
|---|---|---|---|---|---|
| `POST /v1/graph/expand` | — | `can_view` when `case_id` is given | seed ids, max hops, categories, time window, max results; edges carry the **support summary and stamps**, never an aggregate weight (ADR-030). An edge is visible when ≥ 1 supporting claim passes `claim_filters`, and its summary is rebuilt from **only those** claims (T22). **`case_id` (T46)** narrows to one case's own evidence by joining `claim_filters`, not by filtering the result — so edge visibility *and* every tally move together, and the case graph cannot overstate what the investigation has. An unauthorized case id is **404**, never silently ignored: an ignored filter would return the caller's whole readable graph under a heading saying otherwise | ≤ 3 hops, ≤ 2 000 elements (nodes + edges), ≤ 100 seeds; over-asking is clamped and disclosed as `truncated` | `test_graph_routes.py` |
| `POST /v1/graph/paths` | — | — | shortest routes only, not all routes (T22): a path nobody can audit is machine-produced insinuation (Article IX) | ≤ 5 hops, ≤ 25 paths | `test_graph_routes.py` |
| `POST /v1/analytics/{metric}` | analyst | `can_view` when the input set is case-scoped | **Records an answer**, where `/v1/graph/*` above only answers (ADR-057). Writes one immutable `analytic_run` manifest — method, implementation and library version, seed, object-set id + version, evaluation digest, projection stamps + edge digest, ontology version, identity revision, code version, actor, purpose, authorization digest, caveat version (ADR-055) — then one or more `AnalyticFinding` rows, each carrying its caveat text **copied into the row** (spec 12 §9.3). Metrics: `k_hop`, `shortest_path`, `community`, `betweenness`, `degree`, `shared_identifier`. **No weighted paths** — ADR-030 removed the aggregate weight on purpose. A finding's handling code is the maximum of its contributing claims | evaluated input ≤ 50 000 objects; 10 000 ms | `test_analytics.py`, `test_run_manifest.py` (T72) |
| `GET /v1/findings/{id}` · `GET /v1/findings?run=&set=&type=` | — | per row | findings the caller may read, with their manifest and caveat; cursor, no total | limit ≤ 50 | `test_analytics.py` |
| `POST /v1/findings/{id}/promote` | analyst | `can_edit` when case-scoped | finding → **typed suggestion** (`finding_promotion`) → on acceptance an `assessed` claim written with the **reviewer** as actor (ADR-031 §2). Rationale required and substantive; the finding is **not consumed** — it stays, linked through `promoted_claim_id` and a `claim_relation` of kind `analytic_basis`. Promoting the same finding twice is `409` | — | `test_promotion.py` (T74) |
| `POST /v1/projections/rebuild` | admin | — | **controlled job/admin action only** (B-14): full rebuild is a DoS and staleness risk, not general analyst capability. Returns the build report (edges, segments, anchor/map split, `built_at_revision_id`) and is audited as an operator action (Article X) | 1 concurrent, enforced by a transaction-scoped Postgres advisory lock → 409 | `test_projection_routes.py` (T23c), matrix suite |
| ~~`GET /api/graph`, `/api/stats`, `/api/cells`, `/api/query/{name}`~~ | — | — | **deleted at T22** (ADR-026) with the `public_route` marker and the legacy explorer. `/api` stays a reserved path prefix so a caller of a retired route gets 404, not the workspace's HTML | — | `test_route_gating.py`, `test_workspace_serving.py` |

### 2.7 Ontology vocabulary

| Route | R | F | Notes / filters | Limits | Tests |
|---|---|---|---|---|---|
| `GET /v1/ontology/vocabulary` | — | — | handling codes (**ordered** — clearance is an index into the list), source types, and `assertion_types`, so no client hard-codes a vocabulary the server owns. The first two come from `aegis.yaml` (Article XI); `assertion_types` is **platform epistemics, not domain vocabulary** (Article XIV), so it comes from a code-owned constant and is sorted — unlike handling codes, its order carries no meaning (T23b). Authenticated but unrestricted by role: it is the shape of the domain, not an assertion about anyone in it. **Not** superseded in P4: ADR-043 makes the generated `ui/src/api/ontology.ts` the descriptor, and this route becomes the runtime half of the bundle/server version comparison (spec 09 §6.3) — it also serves `assertion_types`, which appear in no ontology module | — | `test_ingest_routes.py`, `test_openapi.py` |

### 2.8 Audit

| Route | R | F | Notes / filters | Limits | Tests |
|---|---|---|---|---|---|
| `GET /v1/audit?actor=&case=&action=&from=&to=` | auditor | — | **P** — querying audit is itself audited; cursor | — | `test_audit.py` |
| `POST /v1/audit/verify` | auditor, admin | — | chain verification report | — | `test_audit.py` |

### 2.9 Object sets, watchlists & alerts (P6 — spec 12)

A set stores a **query, never results** (spec 12 §3), evaluates under **one
snapshot and one authorization context** per request (M-16), and grants nothing.
An unshared set is **absent** from every list, not 403 — the same rule cases
already follow (§2.5).

| Route | R | F | Notes / filters | Limits | Tests |
|---|---|---|---|---|---|
| `POST /v1/object-sets` | analyst, investigator | `can_edit` when `case_id` is given | body is a **validated AST**, never SQL; every leaf names ontology vocabulary and fails `422` with the offending path when it does not. Pins the composition version and freezes interface expansion at save (ADR-054) unless `track_interface_members` is set | depth ≤ 8, ≤ 64 nodes, ≤ 8 set refs, composition depth ≤ 3; cycles refused at **save** | `test_object_sets.py` (T69) |
| `GET /v1/object-sets` · `GET /v1/object-sets/{id}` | — | `viewer` | only sets shared with the caller; cursor, no total. A `property` node above the caller's clearance reads back `withheld: true` with a null value and an **unchanged shape** — a set definition is protected data (B-17, spec 12 §5.2) | limit ≤ 50 | `test_object_sets.py` |
| `POST /v1/object-sets/{id}/versions` | analyst, investigator | `editor` | an edit is a **new immutable version** with a note; a finding that names `(set_id, version)` names something that cannot move under it | — | `test_object_sets.py` |
| `POST /v1/object-sets/{id}/evaluate` | — | `viewer` **or** an explicit evaluate grant | evaluates under the **caller's** `claim_filters` in candidate generation — never the owner's. One repeatable-read snapshot for the whole request, composed subsets included (M-16). Returns member ids, readable labels, `truncated`, and the `evaluation_digest`; **no total** | ≤ 50 000 objects, 10 000 ms | `test_set_evaluation.py` (T70) |
| `POST /v1/object-sets/{id}/share` · `DELETE .../share/{user_id}` | analyst, investigator | `editor` | FGA `object_set` viewer/editor grants; audited with what was shared and with whom | — | `test_set_sharing.py` (T70) |
| `GET /v1/object-sets/{id}/notices` | — | `viewer` | composition bumps that added a member to an interface this set uses — delivered to pinned and tracking sets alike (spec 12 §4.3) | — | `test_object_sets.py` |
| `POST /v1/watchlists` · `GET /v1/watchlists` | analyst | `can_edit` / per row | a set plus an **exact-identifier** rule and its version. Fuzzy matching is deliberately absent and its absence is asserted, not assumed | — | `test_watchlists.py` (T75) |
| `GET /v1/alerts?watchlist=&status=` | analyst | per row | detections are **typed suggestions** (`watchlist_hit`) in the queue that already exists — Article VII applies to alerts (H-24). Dedupe key `(watchlist_id, rule_version, matched_value, entity_id)` | limit ≤ 50 | `test_watchlists.py` |
| `POST /v1/alerts/{id}/triage` | analyst | — | `new → reviewing → closed`; **every** transition audited, and `closed` without a reason is `422`. No transition graph beyond that — the same decision spec 09 made for investigation tasks | — | `test_watchlists.py` |

**Evaluation is explicit** (ADR-056): `aegis watchlists evaluate` sweeps and
records an `analytic_run` with an `evaluated_through` watermark, so an
unevaluated window is a visible gap rather than silence. There is no write-path
hook, because the side-effect outbox spec 08 §6.5 declares is still executed by
nothing. Watchlist sweeps run under the **owner's** authorization context, which
is recorded in the manifest — the one place a saved artifact does not use the
caller's clearance, stated here rather than discovered later.

## 3. Time and identity revision (ADR-029)

- `?asOf=<ts>` on knowledge reads filters `recorded_at <= ts AND (retracted_at
  IS NULL OR retracted_at > ts)` — "what did we know then". This is a
  **claim-recording snapshot**, not full multi-axis bitemporality (B-11, P4).
- `?asOfRevision=<id>` pins the identity revision used to resolve entity
  arguments. Without it, reads resolve through the **active** revision
  (specs/02 §3.1 rule 3). Passing `asOf` alone resolves identity as it is *now*,
  which is usually not what a historical question means — so any response
  carrying `asOf` **echoes the revision it resolved at**, and the UI shows both
  in its as-of banner (specs/07 §5). **Implemented at T49** on
  `GET /v1/entities/{id}`: the pinned resolution replays the identity ledger up
  to that revision (`aegis/er/canonical.py`) rather than reading
  `entity_canonical_map`, which caches only the active answer. A revision above
  the head is **422, never clamped** — answering about *now* under a heading
  that says otherwise is the failure the parameter exists against.
- Every as-of-capable read carries `stamp: {as_of, identity_revision_id,
  ontology_version}`, **including when no snapshot was asked for**. A stamp
  present only in as-of mode would leave a caller unable to tell a current
  answer from a historical one without re-reading its own request.
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
- Applies to: review queue, identity candidates, search, sources, audit,
  object sets, findings, alerts, and every P2 list view.

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
  The naming rules are §7.1; P3 (T36) adds the contract-diff gate (§7.3) and
  the ontology-constants drift gate (spec 08 §8).
- **Security headers** are served with every response (T22,
  `aegis/api/security.py`): `default-src 'none'` plus `no-store` on API paths,
  the workspace policy on the bundle, and a CDN exception scoped to `/docs`.
  HSTS is emitted only over TLS.
- Error bodies never disclose the existence of a resource the caller may not
  see: 404 and 403 are chosen per default 4, and the problem detail is generic.

## 7. Contract conventions (P3 — T29 specifies, T36 enforces)

The OpenAPI document is the contract the workspace client is generated from
(ADR-032 §2, ADR-039). §6 records what P2 made true; this section states the
rules a P3 route must follow and the one gap P3 closes.

### 7.1 Operation IDs

Every operation declares an explicit `operation_id`. The rules, in force since
T22 and now written down:

1. **`lowerCamelCase`, no underscores.** `tests/contract/test_openapi.py`
   rejects any id containing `_`, which is exactly the shape of FastAPI's
   generated default — so a default can never survive review.
2. **`<verb><Noun>`**, where the verb is the domain action and not the HTTP
   method: `recordIdentityDecision`, not `postIdentityDecision`. Reads that
   return a collection use `list`, single-resource reads use `get`.
3. **Globally unique** across the document (tested).
4. **Stable across refactors.** An operation id is the generated client's
   method name, so renaming one is a breaking API change and follows §7.3 —
   renaming the Python function behind it is not.
5. Ids are **not versioned** in their name. The `/v1` prefix carries the
   version; `getEntityV2` would put it in two places.

### 7.2 The error envelope

Errors are RFC 7807 `application/problem+json` and always have been at runtime
(`aegis/api/errors.py`). What P2 shipped is **absent from the contract**: every
operation documents only its success codes plus FastAPI's default `422`, so no
error shape reaches the generated client and `ui/src/api/client.ts` hand-writes
`ProblemDetail` and `StaleRevisionProblem`. T36 closes this.

The base envelope, as a named component schema:

| Field | Meaning |
|---|---|
| `type` | `about:blank` — Aegis does not publish per-error URIs, because a stable error taxonomy is a disclosure surface (default 4) |
| `title` | short, generic, caller-safe |
| `status` | the HTTP status, repeated in the body |
| `detail` | human-readable prose. **Opaque to clients**: written so that asking cannot confirm a resource exists, and never parsed for meaning |

Two documented extensions, and no others may be added without a row here:

- **422 validation** — `path` (a stable ontology/data path such as
  `predicates.member_of`, from `ActionValidationError`) or `errors[]`
  (`{loc, msg, type}`, from request-model validation).
- **409 stale revision** — `parent_revision_id` and `intervening[]`
  (`{decision_id, kind, decided_by, note, result_revision_id}`). This is the
  one error body a client reads for meaning, because specs/05 §2 requires the
  analyst to be **re-presented** with what changed rather than told to retry.
  It is a discriminated extension, not an optional field on the base envelope.

Each operation documents the error responses it can actually return — `401`
(unauthenticated), `403`/`404` per default 4, `409` where a concurrency or
lock conflict is reachable, `413` on the ingest routes, `422` on any route with
a body or typed parameters, `429` under the rate limiter. Documenting a status
a route cannot return is as much a contract defect as omitting one it can.

### 7.3 Contract diff

The committed `ui/openapi.json` is the contract. On top of the P2 drift test,
`aegis api check-contract` compares it against the baseline branch and fails on
a breaking change. It catches what drift cannot: a route renamed in Python and
faithfully re-exported passes the drift test and breaks every caller.

| Breaking | Additive |
|---|---|
| an operation removed **or renamed** (one event from the client's side — a method that stops existing) | a new operation |
| an operation moved to another path or method | a newly documented response |
| a documented response code dropped | a new **optional** parameter |
| a parameter removed, or becoming required | a parameter becoming optional |
| a request body becoming required | |

A break is accepted by the phrase `BREAKING API CHANGE` in a commit message on
the branch making the change, so the reason lands in the history the break will
later be explained from. `--allow-breaking` accepts it locally, for a run
before the commit exists.

> **Corrected at T67.** This section, and ADR-042, described the phrase as the
> escape hatch — and until T67 **nothing read it**. Only the flag worked, and
> CI passes no flags, so an intended breaking change could not be landed at
> all. Found while trying to use the hatch for ADR-050's route removal, which
> is the first break the project has made.
>
> `declaring_commit()` now scans `baseline..HEAD`. The scope is the rule: a
> marker may only accept a break made on the branch that declared it. A stale
> marker licensing every later break would read as governance while enforcing
> nothing.
>
> **The workflow had the other half of the gap.** On a `pull_request` event
> GitHub checks out a synthetic merge commit; at `fetch-depth: 1` the commit
> carrying the declaration is a parent that was never fetched. The gate
> rejected a break the branch declared, while the `push` run on the same
> commits accepted it — a verdict that depends on which event triggered it is
> not a verdict. The fast-tests job now checks out at `fetch-depth: 0`; the
> other jobs stay shallow, because they run tests rather than read history.
>
> When the gate still fails in a shallow clone it **says so** and names the
> fix, rather than leaving the next reader to rediscover this. It does not
> deepen the clone itself: a read-only check that fetches would mutate the
> repository and touch the network, and treating an unreachable commit as
> probably-declared would defeat the point of asking.

> **Corrected at T36 (ADR-042).** This section previously called the check "the
> API-side analogue of the ontology compatibility diff… comparison against a
> committed artifact, not git archaeology". It is not, and the two sentences it
> used contradicted each other. The ontology's rule (H-16) exists because
> `claim.ontology_version` is stamped on immutable rows and must stay
> interpretable forever, which makes the previous ontology a first-class
> archived artifact. **Nothing stores an API version.** The only meaningful
> baseline is "the contract on the branch we are merging into", which *is* a
> git ref; versioning and archiving the document per route change would be
> ceremony with no consumer. The document is still a committed artifact — it is
> the *baseline selection* that is a ref.
