# Phase 2 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them. Reference specs in parentheses. Numbering continues from Phase 1 (T16);
lettered subtasks keep the global T-numbering stable for pre-authored P3+ files.

> **Status: ACTIVE.** Rewritten 2026-07-18 (ADR-033) after the external-review
> disposition (`../reviews/2026-07-18-external-review-disposition.md`). Phase 2
> closes with the **★ MVP gate** — see the charter. Gate criteria are
> non-deferrable (ADR-025). Phase 1 closure addendum (T16a–T16d) blocks
> Milestones B–D; Milestone A may run in parallel with it.

## Milestone A — Design pack (⛓ blocks B–D; specs rewritten before code) — **COMPLETE 2026-07-18**

Delivered T17a–T17d as four PRs. Specs rewritten: `../specs/05-entity-resolution.md`
(full), `../specs/02-data-model.md` §1 seams / §2 ledger / §3 + §3.1 claim
arguments / §3.2 typed envelope / §7 + §7.1 projection v2 / §8 indexes,
`../specs/04-ingestion.md` §4, `../specs/06-api.md` (full — the authoritative
authorization matrix). Design decisions taken during the pack, recorded in the
PR bodies rather than as new ADRs because none changed a chartered deliverable:
scoped (not global) optimistic concurrency on the parent revision; the anchor
requirement as an actions-layer invariant rather than a CHECK; `edge_projection`
as a table rather than a matview, since time segmentation is not a `GROUP BY`;
no `entity_draft` kind — entity creation folds into `claim_draft` acceptance;
`POST /v1/entities/{id}/split` folded into `POST /v1/identity/decisions`.

Milestone B may now start. Note that ADR-033 §2's prose enumerates the pack as
"identity ledger, claim arguments, typed envelope, projection semantics", which
reads as if T17d were projection semantics; the charter and this file agree that
projection semantics belong to T17b and T17d is the authorization matrix. The
four deliverables are unchanged — only ADR-033's wording is loose.

**T17a. ⛓ Identity decision ledger design** (ADR-028; rewrites specs/05 + specs/02 §2)
— schema for `identity_decision` (kind, actor, evidence note, inputs, parent
revision → new revision, transaction time), revision-keyed
`identity_membership` with a partial-unique **one-active-membership-per-mention**
invariant, `er_candidate` (producer, settings version, feature breakdown,
disposition), versioned negative constraints, optimistic concurrency on the
parent revision, `entity_canonical_map` as a rebuildable projection of the
ledger (cycle/tombstone rules), `merged_into` as ledger metadata (not a claim).
Migration plan from the Phase-1 tables.
AC: specs/05 and specs/02 §2 rewritten and reviewed; migration plan covers
existing one-mention clusters; reversal test *plan* enumerates multi-merge,
partial split, concurrent decision, and late-mention cases.

**T17b. ⛓ Claim arguments & projection semantics design** (ADR-029, ADR-030;
rewrites specs/02 §3 + §7) — optional `subject_mention_id`/`object_mention_id`
anchors (required for extracted/reported claims), identity-revision stamp at
`recorded_at`, projection resolution through the active revision (pinnable for
as-of), unanchored-claim rule (splits route them to re-adjudication), honest
aggregation: interval sets / time-segmented edges, support summary (grading
refs, contradiction + corroboration counts, method + version), `record_count`
naming, projection stamps (identity revision, ontology version, builder
version).
AC: specs/02 §3/§7 rewritten and reviewed; blocking-test plan covers
merge-collapse, split-restore-without-claim-rewrite, ambiguous-unanchored →
review queue.

**T17c. ⛓ Typed suggestion envelope design** (ADR-031; rewrites specs/02 queue
section) — `suggestion_kind` closed list (P2 kinds: `claim_draft`,
`identity_candidate`, `claim_relation`), per-kind payload schemas generated
from target-action parameters, producer identity/version, idempotency key,
supersession/expiry, typed result reference, acceptance dispatching through
the declared action; data migration for existing Phase-1 queue rows; the
review **inbox** defined as a UI composition over queue + `er_candidate`.
AC: spec rewritten and reviewed; every P2 kind names its target action and
result type; migration plan for live rows exists.

**T17d. Route authorization matrix & governance seams** (B-14, B-08; updates
specs/06) — authoritative route-by-route table: role gate, FGA relation,
row/field filters, purpose requirement, no-existence-leak behavior, rate/body
limits; `POST /v1/projections/rebuild` restricted to a controlled job/admin
action; generic claim-provenance endpoint for property values; nullable
governance seam columns specced (`source_record.collection_policy_ref`,
`retention_class`, authority validity fields — enforced P7).
AC: specs/06 has the matrix for every route P2 ships; each row names its
tests; seam columns in the T18 migration plan.

## Milestone B — Identity core

**T17. ⛓ Ledger migration + mention extraction & backfill** (specs/05 §1–2) —
implement the T17a/T17b/T17c/T17d schemas in one Alembic series; populate
`mention` rows (raw_text, norm_key, offsets, language/script when known —
H-06 minimum) from existing and newly landed source records; verify the legacy
one-mention clusters as revision 0 of the ledger; backfill claim
identity-revision stamps.
AC: migrations up/down clean; every entity has ≥ 1 mention; one-active-
membership invariant enforced by the DB; idempotent re-run; Phase-1 tests
green on the new schema.

**T18. Deterministic ER → pre-verified candidates** (specs/05 §2.1, ADR-027) —
rule engine emitting **candidates** (never merges) for exact registry
identifiers (NIC when lawfully present, vehicle registration + jurisdiction,
passport + country) with issuer/validity conflict checks (H-07);
same-norm_key-within-one-document also a candidate, ranked top-of-queue with
`producer='rule:<name>'`; batch-confirm flow specced for the adjudication UI.
AC: a fixture NIC pair produces a pre-verified candidate, not a membership
change; confirming it in one human action creates a ledger decision with the
human as `decided_by`; cross-document same-slug never lands above the
pre-verified band.

**T19. Splink pipeline** (specs/05 §2.2) — DuckDB backend; transliteration-aware
features (ICU Latin key + raw-script key, Jaro-Winkler + token-set, alias
cross-match, affiliation overlap, DOB conflict as negative evidence);
graph-context feature computed from a **versioned projection snapshot**
recorded with each run (H-07); blocking rules; candidates above threshold land
in `er_candidate` with per-feature waterfall weights; settings versioned in
`aegis/er/settings.py`; negative constraints consulted before emission.
AC: the seeded Sinhala/English transliteration pair scores above threshold with
per-feature weights persisted; a rejected pair is never re-emitted; the run
records its settings version + graph snapshot id.

**T20. ⛓ Adjudication actions over the ledger** (specs/05 §3) —
`confirm_match`, `reject_match`, `split_entity`, `mark_unresolved` as
`adjudicate_identity` (evidence note required; dual-control hook honored);
each decision creates a revision with optimistic concurrency; rejects write
negative constraints; single transaction with audit; `entity_canonical_map`
rebuild hook.
AC: merge → intervening claim edits → split restores mention-attributable
state exactly; a decision against a stale revision is rejected and
re-presented; every decision carries a human actor + note in audit.

## Milestone C — Workspace & governed UI loop

**T21. ⛓ Projection rebuild v2 + "why connected?" API** (ADR-029, ADR-030;
specs/06) — `edge_projection` resolves entity arguments through the active
identity revision; time-segmented aggregation; support summary; projection
stamps; core stops importing `legacy.pipeline.clustering` (H-36 — move/vendor
Leiden into `aegis/analytics/`); why-connected endpoint returns the claims,
gradings, sources, relations, and the identity-decision line behind any edge.
AC: merge collapses nodes/edges and split restores them with zero claim-row
rewrites (blocking test); a disjoint-interval fixture yields segmented edges,
not one continuous edge; every edge resolves to ≥ 1 source record; `aegis`
package imports nothing from `legacy.*`.

**T22. ⛓ Workspace shell + legacy retirement** (ADR-032, ADR-026; specs/07) —
`ui/`: React 18 + TypeScript + Vite; Keycloak OIDC PKCE via
`oidc-client-ts`/`react-oidc-context` (tokens in memory, no localStorage;
logout + refresh handled by the lib); OpenAPI-generated typed client (stable
operation IDs added to FastAPI routes); app layout (nav, auth guard, error
envelope handling); CSP + security headers on the serving path; CI:
type-check + build + one smoke e2e. **Same change:** legacy explorer,
`/api/*` routes, and the `public_route` lint exemption deleted; graph view
(Cytoscape-in-React) reads `/v1/graph/*`.
AC: unauthenticated visit → login redirect → authenticated shell; graph
renders from governed routes; repo grep finds no `public_route` marker and no
`legacy/app` serving path; UI CI job green.

**T23a. Source landing & extraction UI** (B-04; specs/04) — upload/paste with
required provenance fields, source picker/creation, landing status
(landed/quarantined + reason), derivative + extraction progress (sync or job
status — decided here), idempotent re-upload feedback ("already landed"),
quarantine release for supervisors, extraction trigger per record.
AC: browser e2e — land a fixture PDF and a pasted text from the UI, see
suggestions appear in the queue; re-upload shows the no-op; quarantined
fixture shows its reason; every action authorized + audited.

**T23b. Review queue & adjudication UI** (ADR-031; specs/04 §4) — typed inbox
(queue + `er_candidate`), filters by kind/producer/status/document;
accept / edit-then-accept / reject with reason; assertion-type picker on
accept (plan §4.2); producer metadata (model, prompt hash, rule, score
waterfall) rendered per kind; identity candidates: pre-verified batch-confirm
flow + full waterfall view; bulk-reject for hallucinated entities.
AC: a Gemini-pass suggestion accepted in the UI appears in the rebuilt
projection and a rejected one never does; a Splink candidate is confirmed
end-to-end from the browser and the graph reflects the merge; batch-confirm
writes one human-actored decision per pair.

**T23c. Provenance panel, contradiction surfacing & entity search** (specs/06,
ADR-012 minimal) — edge/node click opens the why-connected panel (all three
grading dimensions per claim, sources, contradiction/corroboration badges;
conflicting property claims render side by side — Article VIII);
`GET /v1/search/entities?q=` with `pg_trgm` over names/aliases/mention
norm_keys, authorization-filtered, cursor-paginated; search box focusing the
graph.
AC: every rendered edge opens the panel; seeded contradictory DOB claims both
render with a visible `contradicts` badge; a transliterated query variant
finds the seeded entity; results respect handling + case filters.

**T24a. Field-level sensitivity filtering** (specs/03 §4; hard gate) —
property `sensitivity` from the ontology enforced on every read path (absent,
not marked — the P7 marked-redaction mode is a different, later policy);
governance seam columns from T17d land in the schema.
AC: a `sensitivity: restricted` property is absent for a low-clearance caller
on every shipped route (matrix test); no count/existence leak; seam columns
exist and are nullable.

**T24b. Authorization matrix tests** (T17d; specs/06) — the matrix becomes an
executable test suite: (role × handling × membership × field-sensitivity) per
route, allow and deny cases, 404-on-unauthorized single GETs, rebuild
restricted; the deny-by-default lint runs with zero exemptions.
AC: matrix suite green in CI; lint green with the exemption branch deleted;
a seeded restricted row proves strict-subset search behavior (M-13).

**T24c. Cursor pagination** (specs/06 conventions; M-12) — ULID-ordered cursor
pagination + deterministic ordering on queue, search, entities, audit list
routes.
AC: stable iteration under concurrent inserts; UI list views page correctly.

## Milestone D — MVP close-out

**T25. Fictional demo fixture** (H-09) — deterministic, fully local fixture
corpus (`data/sample/mvp/`): documents seeding known entities, a
transliteration pair, a distinct same-name pair, a contradiction, a restricted
field, and a quarantine case; loads via `aegis ingest` in one command; reset
path (restore baseline, rebuild projections).
AC: fixture load → demo loop is reproducible offline with no hosted-model
dependency (extraction runs structural pass; a cached LLM-output fixture
exercises the semantic path); CI smoke runs the loop headlessly.

**T26. ER evaluation harness with numeric gates** (specs/05 §5; H-08) — golden
set (fictional: transliteration pairs incl. Sinhala script, hard negatives,
common names, missing fields); CI computes pairwise precision/recall and
review-load (candidates per 1,000 mentions); **blocking thresholds recorded in
the spec at first passing run** (starting floor: precision ≥ 0.95 on
pre-verified rules, recall ≥ 0.7 on the seeded transliteration set; tune with
evidence, change only with the eval diff); Splink settings changes show their
eval results in the same PR.
AC: CI publishes the numbers and fails below threshold; the seeded distinct
pair stays unmerged in the full pipeline run; no real-person identifiers in
CI fixtures.

**T27. MVP demo runbook + real-corpus smoke** — `docs/MVP_DEMO.md`: scripted
walkthrough of the full loop **on the T25 fixture** (the ★ gate); separate
appendix: authorized real-OSINT manual smoke (operator-run, no captured
sensitive output, provider/egress notes, cleanup path).
AC: a person who didn't build the system completes the fixture loop in one
sitting following only the document; the real-corpus smoke is documented as
manual and non-blocking; drift between doc and product fails the phase review.

**T28. Phase exit review** — walk the charter's gate criteria (non-deferrable,
ADR-025); verify the constitution-conformance spot-check (Articles VI/VII
tests); update speckit docs where reality diverged; append ADRs for changed
decisions; write `../reviews/phase-02-exit-review.md`.
AC: every gate criterion checked; non-blocking deliverables carried over with
owner + target phase recorded; statuses updated everywhere (M-01).

## Explicit non-goals for Phase 2

Object views/cases/hypotheses/timeline (P4), ontology modules/interfaces and
the ontology-generated SDK (P3 — P2 uses the OpenAPI-generated client),
PostGIS geometry and events (P5), full multilingual FTS, object sets and
watchlists (P6), compartments and disclosure packages (P7), new LLM
capabilities beyond the existing extraction producers (P8), UI polish beyond
function (P4).
