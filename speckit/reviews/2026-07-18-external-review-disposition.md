# External review disposition — 2026-07-18

Two external AI reviews (raw text: [`2026-07-18-external-review.md`](2026-07-18-external-review.md),
findings B-01…B-19 + H/M series — the authoritative definition of every
finding ID cited across charters and task files) were evaluated **critically,
not adopted wholesale**. This file is the disposition record: what was
accepted, what was rejected or narrowed, and where each accepted finding now
lives. Documentation changes landed with this record; ADR-025…ADR-033 in
`../decisions.md` carry the load-bearing decisions.

Legend: **accept** (finding valid, fix adopted) · **narrow** (valid core,
recommendation reduced/changed) · **reject** (not adopted, reason given) ·
**defer** (valid, scheduled later with an owner).

## Blockers

| # | Finding | Disposition | Resolution / home |
|---|---|---|---|
| B-01 | Phase 1 marked complete while Article VI unmet (anonymous routes, field filters, revocation) | **accept, split** | Phase 1 relabelled *complete with closure addendum* (tasks T16a–T16d, `tasks/phase-01.md`); anonymous `/api/*` retired via ADR-026 (interim loopback bind, deleted when the P2 UI shell lands); field-level filtering and revocation safety are **hard P2 gate criteria**, not "eventually" |
| B-02 | Algorithmic canonical writes contradict Article VII in four places | **accept** | Article VII kept strict; auto-accept (spec 04), auto-merge (spec 05/T18), and `system_claim` (spec 08/GOAL.md §7.8) all removed — ADR-027. Deterministic derivations become rebuildable derived records, never canon |
| B-03 | Identity model cannot prove exact merge reversal | **accept** | Identity decision ledger: revisioned decisions, one-active-membership invariant, persisted candidates + negative constraints, optimistic concurrency; `merged_into` moves from domain claim to ledger metadata — ADR-028; P2 task T17a |
| B-04 | MVP gate requires UI ingestion/extraction that no task builds | **accept** | P2 recomposed around a durable React shell incl. source landing/extraction/status UI — ADR-032, tasks T22–T23a |
| B-05 | Generic JSON review queue cannot represent its workloads | **accept** | Typed suggestion envelope with per-kind schema and dispatch through the declared action — ADR-031; P2 task T17c |
| B-06 | "Checked or explicitly deferred" negates hard gates | **accept, do now** | Gate criteria vs non-blocking deliverables defined in `roadmap.md`; every exit task's AC rewritten; "soft dependency" language replaced by explicit early-start notes — ADR-025. (User placed this pre-P2-exit; pulled forward because it defines what "exit" means) |
| B-07 | Platform claim has no module architecture | **accept, P3** | Module composition becomes P3's headline deliverable (platform module + domain module manifests, second-domain CI fixture); generic functions machinery deferred out of P3 — ADR-033 |
| B-08 | Legal authority/purpose/retention promised but absent | **narrow** | Full enforcement stays P7 (user's call, agreed). Cheap schema seams (collection-policy reference, retention class, authority validity fields — nullable) land in P2 so P7 needs no reclassification migration — P2 task T24a |
| B-09 | Evidence/audit tamper-evident only, not immutable (WORM, external anchor) | **defer, pilot gate** | Pilot security baseline (roadmap §Pilot gate): MinIO Object Lock + signed audit checkpoint export before any second-user/non-local deployment. Dev mode documented exception |
| B-10 | Security baseline arrives after real-person use | **accept, split** | Minimum operating baseline extracted from P9 into a named **pilot gate** checklist (TLS, secrets, lockfile, limits, encrypted backups, headers); P9 remains production certification — ADR-033. Lockfile pulled all the way into P1 closure (T16c) |
| B-11 | As-of promise exceeds the time model | **narrow, P4** | P4 promise narrowed to a precisely defined claim-recording snapshot returning snapshot + identity-revision + ontology IDs (which ADR-028/029 provide); full multi-axis as-of stays north-star |
| B-12 | Edge projection fabricates time and confidence | **accept** | Time-segmented aggregation, no max-credibility collapse, support summary with conflict count, "distinct records" not "independent sources" — ADR-030; P2 task T21 |
| B-13 | Event/geo plans reintroduce facts outside claims | **accept, P5** | P5 charter amended: claims-first canonical model, PostGIS as projection; precision split from geometry representation; required-property change treated as major |
| B-14 | API authorization contract incomplete/stale | **accept, phased** | Route-by-route authz matrix authored in P2 (T24b) for the routes P2 ships, maintained as the authoritative artifact before SDK generation (P3); rebuild endpoint restricted; provenance endpoint added |
| B-15 | Living runbooks bypass the governed pipeline | **accept, P1 closure** | T16d: legacy-only runbooks moved under `legacy/` with unsafe-for-governed-data banner; active ingestion runbook rewritten around `aegis ingest` |
| B-16 | Backup misses security/evidence state (Keycloak users, FGA, versions, keys) | **defer, pilot gate** | Recovery-boundary definition + automated encrypted backup of all non-reconstructible components in the pilot baseline; full DR automation stays P9 |
| B-17 | Search/object sets leak or widen scope | **defer, P6** | P6 charter amended: authorization in candidate generation, versioned/pinned set definitions, AST-only storage, complexity limits |
| B-18 | AI egress governance missing | **defer, P8** | P8 charter amended: data-egress policy, provider allowlist, least-privilege producer credentials, realistic reproducibility definition |
| B-19 | Claims disconnected from mention evidence / identity revisions | **accept — the load-bearing finding** | Claim arguments carry optional mention anchors + identity-revision stamp; projections resolve through the active revision; split routes ambiguous unanchored claims to re-adjudication — ADR-029; P2 task T17b. Adopted the hybrid claim-argument design, **not** mention-only references |

## Notable H/M findings folded in

- **H-07/H-08** (unsafe deterministic ER, weak Splink criteria): exact
  identifiers become *pre-verified candidates* (one-click batch confirm, still a
  human action); same-name-in-document auto-merge removed; numeric
  precision/recall thresholds + review-load bound in T26 — ADR-027/ADR-028.
- **H-09** (real corpus owns the MVP gate): the blocking automated demo runs on
  a **fictional, local, deterministic fixture**; the real-OSINT walkthrough is an
  authorized manual smoke test — ADR-033.
- **H-10** (throwaway P2 UI): resolved by ADR-032 (React from P2). The review's
  "Jinja2+HTMX is reasonable" alternative was **rejected**: the destination is
  already React+TS (P4/ADR-021), the project is greenfield, and a second interim
  stack is deliberate waste.
- **H-11** (P3 over-scoped): accepted — P3 narrowed; TS client generated from
  the FastAPI OpenAPI document (adopt-before-build) instead of a bespoke
  full-client generator; Python SDK deferred until a consumer exists.
- **H-14** (delete/reproduce byte-for-byte conflicts with immutability):
  accepted — derived records live in rebuildable tables keyed by content
  identity; equality tested on canonical digests, not DB bytes (ADR-027).
- **H-33** (no lockfile/pins): lockfile now (T16c); full supply-chain work at
  pilot/P9.
- **H-36** (core imports legacy `clustering`): accepted; scheduled with the P2
  projection work (T21) — move Leiden usage behind `aegis/analytics/` or vendor
  the small function.
- **M-01** (stale statuses): accepted — statuses corrected in this pass; spec
  status lines now name the ADRs that amend them.
- **M-12** (pagination too late): accepted — cursor pagination is a P2 task
  (T24c).
- **M-25** (git workflow `[skip ci]` contradiction): accepted — workflow doc to
  be aligned with AGENTS.md (no-skip) in T16d.

## Rejected or deliberately not adopted

- **Amending Article VII to permit a machine-write class**: rejected. Removing
  the three machine-write paths is simpler, matches the product's core promise,
  and loses nothing — deterministic derivations are exactly what Article XIII
  projections are for.
- **Mention-only claim references** (external suggestion, noted in the raw
  review §B-19): rejected in favour of the hybrid argument model —
  analyst/assessment claims legitimately lack a textual mention.
- **A new ADR mandating Jinja2+HTMX**: rejected (see H-10 above); ADR-032
  decides the opposite.
- **Typed claim-value columns now** (H-38): not locked in — JSONB canonical
  input + expression-indexed typed projections remains the working model;
  revisit with measured P4–P6 query patterns, per the review's own caveat.
- **Immediate WORM/pgAudit/external anchoring**: not now — solo, localhost,
  dev-tier deployment; bound to the pilot gate instead (B-09/B-16 rows).

## Priority order after disposition

1. **Now (this documentation pass):** B-06, statuses, ADR-025…033.
2. **P1 closure addendum (T16a–T16d):** interim exposure containment,
   revocation inline delete, lockfile, runbook/doc honesty.
3. **P2 design pack before implementation (T17a–T17d):** identity ledger, claim
   arguments, typed envelope, projection semantics — specs 02/05 rewritten.
4. **P2 build:** identity core, React shell + full UI loop, field filters,
   pagination, authz matrix, numeric ER gates, fictional demo fixture.
5. **P3:** module composition + contracts (narrowed).
6. **Pilot gate (before any second user / non-localhost):** the minimum
   operating baseline checklist (roadmap §Pilot gate).
7. **P5–P9:** charter amendments recorded now, executed in phase.
