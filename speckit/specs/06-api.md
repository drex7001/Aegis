# Spec 06 — API v1

Status: implemented in Phase 1 (v1 reference) — **P2 T17d makes this file the
authoritative route-by-route authorization matrix** (role, FGA relation,
row/field filters, purpose, no-existence-leak behavior, limits — B-14) and P2
adds field filters (T24a) + cursor pagination (T24c); stable operation IDs
land in P3 (T36). · Constitutional basis: Articles VI, X, XIII

FastAPI, `/v1/*`, OIDC bearer auth. Every route lists its authorization gate
(**R** = role gate, **F** = FGA check, **H** = handling/row filters always applied,
**P** = purpose string required). Errors: RFC 7807 problem+json. Writes are actions
(validate → write → audit in one transaction).

## Knowledge

| Route | Auth | Notes |
|---|---|---|
| `POST /v1/claims` | R:analyst,investigator · F:case edit (if case-scoped) | body validated against ontology; returns claim |
| `POST /v1/claims/{id}/retract` | R:analyst · F | reason required; soft (Article VIII) |
| `POST /v1/claims/{id}/relations` | R:analyst | corroborates/contradicts link |
| `GET /v1/claims/{id}` | H | includes grading components, source ref, relations |
| `GET /v1/entities/{id}` | H | label + claims grouped by predicate; `?asOf=` supported (ADR-008) |
| `GET /v1/entities/{id}/why-connected/{other}` | H | Phase 2: claims/sources/contradictions behind any connection (GOAL.md §18) |
| `POST /v1/search` | H · P (if sensitive scope) | ids first, hydration re-filtered (ADR-012) |

## Review queue (Article VII)

| Route | Auth |
|---|---|
| `GET /v1/review-queue?status=&producer=&record=` | R:analyst · H |
| `POST /v1/review-queue/{id}/accept` | R:analyst — body may edit the draft; validates, records claim |
| `POST /v1/review-queue/{id}/reject` | R:analyst — reason required |

## Sources & ingestion

| Route | Auth |
|---|---|
| `POST /v1/sources` · `GET /v1/sources` | R:analyst |
| `POST /v1/ingest` (multipart) | R:analyst,investigator — lands, returns record_id + status |
| `GET /v1/source-records/{id}` | H — provenance envelope, derivatives, quarantine state |
| `POST /v1/source-records/{id}/release` | R:supervisor — un-quarantine, audited |

## Evidence & custody

| Route | Auth |
|---|---|
| `POST /v1/evidence` | R:investigator,evidence_officer · F:case |
| `POST /v1/evidence/{id}/custody-events` | F:can_transfer |
| `GET /v1/evidence/{id}` | F:can_view · H — item + derivatives + custody chain + hash status |

## Cases

| Route | Auth |
|---|---|
| `POST /v1/cases` | R:analyst,investigator — purpose required |
| `POST /v1/cases/{id}/members` | F:can_approve — mirrors FGA tuple |
| `GET /v1/cases/{id}` | F:can_view |

## Projections & analytics

| Route | Auth | Notes |
|---|---|---|
| ~~`GET /api/graph`, `/api/stats`, `/api/cells`, `/api/query/{name}`~~ | — | **retired at P2 T22** (ADR-026) — interim: loopback-bound + limits (T16a) |
| `POST /v1/graph/expand` | H | seed ids, max hops, categories, time window, min confidence band, max results (GOAL.md §29 controls) |
| `POST /v1/graph/paths` | H | bounded shortest/all paths |
| `GET /v1/claims/{id}/provenance` | H | P2 (T17d): generic provenance for property-valued claims — every displayed value opens its provenance (B-14) |
| `POST /v1/analytics/{algo}` | R:analyst · H | returns `AnalyticFinding` + caveat text (Article IX) |
| `POST /v1/findings/{id}/promote` | R:analyst | finding → review queue as assessed-claim draft |
| `POST /v1/projections/rebuild` | R:admin (controlled job) | Article XIII — restricted from general analyst use (DoS/staleness risk, B-14) |

## Identity (Phase 2)

| Route | Auth |
|---|---|
| `GET /v1/identity/candidates` | R:analyst — Splink pairs with weight breakdowns |
| `POST /v1/identity/candidates/{id}/decision` | R:analyst — confirm/reject/unresolved, note required |
| `POST /v1/entities/{id}/split` | R:analyst |
| `GET /v1/entities/{id}/identity-history` | H |

## Audit

| Route | Auth |
|---|---|
| `GET /v1/audit?actor=&case=&action=&from=&to=` | R:auditor · P — querying audit is itself audited |
| `POST /v1/audit/verify` | R:auditor,admin — chain verification report |

## Conventions

- `?asOf=<ts>` on knowledge reads: filters `recorded_at <= ts AND (retracted_at IS
  NULL OR retracted_at > ts)` — "what did we know then".
- Pagination: cursor-based (`?cursor=`, ULID-ordered).
- No existence leaks: unauthorized and nonexistent both return 404 on single-resource
  GETs (specs/03 §4).
- Exports (any bulk out-format) go through `POST /v1/exports` (Phase 7 packages;
  Phase 1: audited JSON dump of an authorized projection only).
