# Phase 4 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them; narrower dependencies are noted in the task text. Reference specs in
parentheses. Numbering continues from Phase 3 (T40).

> **Status: PRE-AUTHORED, NOT ACTIVE.** Phases 2 (MVP gate) and 3 (modules &
> contracts — the TypeScript client and UI descriptors this phase consumes)
> must close first. Authored 2026-07-17 ahead of phase start; **the charter was
> amended 2026-07-18 (ADR-032/ADR-033: the workspace exists from P2 and grows
> here; the legacy explorer is already gone; the investigation-domain model is
> specced before its UI — H-17)**. T41 re-validates this plan against the
> amended charter and the P3-as-built client, and dispositions the 2026-07
> review findings tagged P4 (H-17, H-18, H-19 remainder, B-11), before any
> other task starts. Charter: `../phases/phase-04-workspace-object-views.md` ·
> specs: `../specs/07-ui.md`, `../specs/09-investigation-domain.md` (authored
> by T41).

## Milestone A — Foundation

**T41. ⛓ Specs 09 + re-validation** (charter §Specs) — re-validate this plan
against the amended charter (ADR-032/ADR-033) and the P3-as-built TS client
and UI descriptors; disposition the 2026-07 findings tagged P4 (H-17, H-18,
H-19 remainder, B-11); author `specs/09-investigation-domain.md` **first**
(cases/hypotheses/tasks/leads model, actions, authorization — model separate
from UI, H-17), then the object-view descriptor contract (properties with
grading/conflict metadata, link groups, timeline strip, source list,
authorized case list).
AC: spec 09 exists covering the investigation model and every surface the
generic object view renders; divergences from this plan are ADR'd.

**T42. ⛓ Workspace v2 foundation** (specs/07 §3–4; needs T41) — the P2-born
app (ADR-032 — the shell, auth, and serving decision already exist) gains the
case-centric layout and **ontology-driven navigation from UI descriptors**;
all data access migrates to the P3 generated client (hand-written domain
types are defects, Article XI).
AC: nav lists object types and interfaces from descriptors alone; `grep`
finds no hand-written domain model in `ui/src`; existing P2 screens still
pass their e2e smoke inside the new layout.

**T43. Investigation-model implementation** (specs/09; needs T41) —
storage/actions/routes for hypotheses (versions, evidence basis, missing-info
note required) and tasks/leads (owner, status, dates) per spec 09; audited
actions; authz matrix rows added.
AC: hypothesis and task lifecycles round-trip through the API with audit;
matrix tests cover their allow/deny cases; no UI yet (Milestone D renders
them).

## Milestone B — Object views

**T44. ⛓ Generic object view (entity-360)** (specs/09; needs T42) — one
generic, descriptor-driven component renders any object type: claim-derived
properties with grading badges; conflicting values render **side by side**
with relation badges — two DOBs are two DOBs (Article VIII); links grouped by
predicate category; source list; cases the entity appears in — **each case
reference independently authorized: only visible cases listed, no hidden
count, no existence leak (H-18)**.
AC: person and organization render through the same component with zero
type-specific React code; a seeded property conflict shows both values and
their `contradicts` badge; a viewer authorized for the entity but not a
restricted case sees no trace of that case; every rendered value came through
the client.

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

**T47. Hypotheses UI** (GOAL.md §18; needs T43, T44, T46) — screens over the
T43 hypothesis actions: supporting/contradicting claim links and the
**required missing-information note**; the hypothesis page always renders
both sides (Article VIII) plus what's missing.
AC: creation without a missing-info note is rejected by the action's
submission criteria (P3 mechanism); a seeded hypothesis shows supporting and
contradicting claims simultaneously (exit criterion); all changes in audit.

**T48. Tasks / leads UI** (needs T43, T46) — screens over the T43 task/lead
actions: lightweight status columns on cases; no workflow engine (plan §2
trigger untouched).
AC: a lead moves through its statuses from the case screen; every transition
is an audited action; no new infrastructure appears in the diff.

## Milestone E — Time

**T49. Timeline + as-of mode (narrowed — B-11)** (specs/02 time model; needs
T44) — claim/event times with uncertainty rendered honestly; `?asOf=`
end-to-end in the UI as the defined **claim-recording snapshot**: claims
recorded and unretracted at the timestamp, resolved under a pinned identity
revision (ADR-029), response stamped with snapshot + identity revision +
ontology version; a persistent banner states exactly what the view holds
constant.
AC: an as-of query in the UI excludes a claim recorded after X in a seeded
test; the response carries its snapshot/revision stamps (exit criterion);
uncertain dates render visually distinct from exact ones.

## Milestone F — Cutover & proof

**T50. P2-screen reorganization** (needs T44–T46) — the P2 review-queue,
search, adjudication, and provenance screens (same app — ADR-032) re-homed
into the case-centric layout; their APIs unchanged.
AC: the MVP demo runbook (`docs/MVP_DEMO.md`) re-runs start-to-finish in the
reorganized layout; the diff touches no API code.

**T51. Ontology-to-screen proof** (charter exit №4; needs T44) — add a test
object type via the ontology alone (+ proposal + regen, P3 discipline): a
working object view with properties, links, and provenance appears with **no
new React code**.
AC: the change's diff is ontology + proposal + regenerated files only; a UI
test loads the new type's object view and drills into provenance.

**T52. No-unauthenticated-surface re-verification** (charter exit №5; needs
T50 and the T41 checklist) — the legacy explorer and `/api/*` were deleted in
P2 (T22, ADR-026); this task re-verifies through the grown P4 surface: repo
grep for any `public_route`-style exemption, authz-matrix run across all P4
routes/screens, and the analyst-needs checklist sign-off.
AC: no unauthenticated read surface exists anywhere in the repo; the
checklist sign-off is in the exit review.

**T53. Phase exit review** — walk the charter's gate criteria (non-deferrable,
ADR-025); update speckit docs where reality diverged; append ADRs; write
`../reviews/phase-04-exit-review.md`; tag `phase-4-workspace` per the git
workflow.
AC: every gate criterion checked; non-blocking deliverables carried over with
owner + target phase recorded.

## Explicit non-goals for Phase 4

Map view (P5), full multilingual search and object sets (P6), compartment UX
(P7), collaboration beyond case membership (comments, presence — GOAL.md §31
stays future), mobile, offline, any new analytics or AI surface (P6/P8).
