# Phase 4 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them; narrower dependencies are noted in the task text. Reference specs in
parentheses. Numbering continues from Phase 3 (T40).

> **Status: PRE-AUTHORED, NOT ACTIVE.** Phases 2 (MVP gate) and 3 (ontology v2 —
> the TypeScript SDK and UI descriptors this phase consumes) must close first.
> Authored 2026-07-17 ahead of phase start; T41 re-validates this plan against
> the P3-as-built SDK before any other task starts. Charter:
> `../phases/phase-04-workspace-object-views.md` · specs: `../specs/07-ui.md`
> (stage 3), `../specs/09-workspace-object-views.md` (authored by T41).

## Milestone A — Foundation & shell

**T41. ⛓ Spec 09 + cutover scope** (charter §Specs; specs/07 stage 3) —
re-validate this plan against the P3-as-built TS SDK and UI descriptors; author
`specs/09-workspace-object-views.md` (the object-view descriptor contract:
properties with grading/conflict metadata, link groups, timeline strip, source
list, case list); and write the **analyst-needs cutover checklist** up front —
the short list of what the workspace must do before the legacy explorer dies
(graph, filters, detail panel — replacement scope, never legacy parity,
ADR-023).
AC: spec 09 exists and covers every surface the generic object view renders;
the cutover checklist is agreed and frozen in the spec; divergences from this
plan are ADR'd.

**T42. ⛓ Workspace shell + auth** (specs/07 stage 3; needs T41) — React +
TypeScript app; Keycloak OIDC (PKCE) login; **all** data access through the
generated TS SDK (hand-written domain types are defects, Article XI);
ontology-driven navigation built from UI descriptors; serving/deployment
decision (mounted by aegis-api vs. separate dev server) recorded as an ADR.
AC: login round-trips against the dev realm; nav lists object types and
interfaces from descriptors alone; an unauthenticated visitor reaches nothing
but the login screen; `grep` finds no hand-written domain model in the app.

**T43. Cursor pagination** (specs/06 — deferred from Phase 1; lands here at
the latest) — stable-ordered cursor pagination on list endpoints the workspace
consumes (entities, claims, review queue, search); SDKs regenerate.
AC: a list larger than one page walks completely and without duplicates via
cursors; both SDKs expose the pagination surface; API docs render it.

## Milestone B — Object views

**T44. ⛓ Generic object view (entity-360)** (specs/09; needs T42) — one
generic, descriptor-driven component renders any object type: claim-derived
properties with grading badges; conflicting values render **side by side**
with relation badges — two DOBs are two DOBs (Article VIII); links grouped by
predicate category; source list; cases the entity appears in.
AC: person and organization render through the same component with zero
type-specific React code; a seeded property conflict shows both values and
their `contradicts` badge; every rendered value came through the SDK.

**T45. Provenance drill-down + timeline strip** (needs T44) — every displayed
value and link opens its provenance (the P2 why-connected API, consumed
as-is); a compact timeline strip on the object view shows the entity's claims
over time.
AC: clicking any value or edge resolves to claims with all three grading
fields and their sources (parity with the P2 panel, same API, no new
endpoint); the strip's items match the claim time model.

## Milestone C — Cases

**T46. ⛓ Case UI + membership** (needs T42) — create/join/manage cases via
the existing FGA-scoped actions; link claims and evidence to cases; case-scoped
graph view (embedded Cytoscape reusing the projection API with a case filter).
AC: the Phase-1 authz matrix extends to the UI — a non-member sees nothing
about a case via any screen or endpoint it calls (exit criterion); membership
changes are audited actions; the case graph never renders out-of-case data.

## Milestone D — Hypotheses & tasks

**T47. Hypotheses** (GOAL.md §18; needs T44, T46) — hypothesis records with
supporting/contradicting claim links and a **required missing-information
note**; create/update are audited actions; the hypothesis page always renders
both sides (Article VIII) plus what's missing.
AC: creation without a missing-info note is rejected by the action's
submission criteria (P3 mechanism); a seeded hypothesis shows supporting and
contradicting claims simultaneously (exit criterion); all changes in audit.

**T48. Tasks / leads** (needs T46) — lightweight status columns on cases; no
workflow engine (plan §2 trigger untouched).
AC: a lead moves through its statuses from the case screen; every transition
is an audited action; no new infrastructure appears in the diff.

## Milestone E — Time

**T49. Timeline + as-of mode** (specs/02 time model; needs T44) — claim/event
times with uncertainty rendered honestly; `?asOf=` supported end-to-end in the
UI ("what did we know on date X?").
AC: an as-of query in the UI excludes a claim recorded after X in a seeded
test and the answer is defensible from the response alone (exit criterion);
uncertain dates render visually distinct from exact ones.

## Milestone F — Cutover & proof

**T50. Panel migration** (needs T44–T46) — the P2 review-queue, search, and
provenance surfaces re-rendered inside the workspace; their APIs unchanged.
AC: the MVP demo runbook (`docs/MVP_DEMO.md`) re-runs start-to-finish entirely
in the workspace; the diff touches no API code; the legacy panels are no
longer reachable from the workspace.

**T51. Ontology-to-screen proof** (charter exit №4; needs T44) — add a test
object type via the ontology alone (+ proposal + regen, P3 discipline): a
working object view with properties, links, and provenance appears with **no
new React code**.
AC: the change's diff is ontology + proposal + regenerated files only; a UI
test loads the new type's object view and drills into provenance.

**T52. Legacy explorer deletion + ADR-019 review** (charter exit №5; needs
T50 and the T41 checklist) — verify the analyst-needs checklist in the
workspace, then delete `app/static` and the deprecated `app/server.py`
(replacement, not parity — ADR-023); review ADR-019's public open-only
`/api/*` projection surface: keep or retire, recorded as an ADR either way.
AC: no legacy explorer code remains in the repo; nothing serves
unauthenticated graph data except an explicitly kept `public_route` (or none,
per the new ADR); the checklist sign-off is in the exit review.

**T53. Phase exit review** — walk the charter's exit criteria; update speckit
docs where reality diverged; append ADRs; write
`../reviews/phase-04-exit-review.md`; tag `phase-4-workspace` per the git
workflow.
AC: all exit boxes checked or explicitly deferred with reason.

## Explicit non-goals for Phase 4

Map view (P5), full multilingual search and object sets (P6), compartment UX
(P7), collaboration beyond case membership (comments, presence — GOAL.md §31
stays future), mobile, offline, any new analytics or AI surface (P6/P8).
