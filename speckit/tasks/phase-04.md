# Phase 4 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them; narrower dependencies are noted in the task text. Reference specs in
parentheses. Numbering continues from Phase 3 (T40).

> **Status: ACTIVE — opened 2026-08-17 with T41's re-validation.** Authored
> 2026-07-17 ahead of phase start; the charter was amended 2026-07-18
> (ADR-032/ADR-033: the workspace exists from P2 and grows here; the legacy
> explorer is already gone; the investigation-domain model is specced before
> its UI — H-17). **T41 re-validated this plan against the P3-as-built system
> on 2026-08-17**; its five divergences are recorded in spec 09 §0 and
> ADR-043…045, and the tasks below carry the corrections. Charter:
> `../phases/phase-04-workspace-object-views.md` · specs:
> `../specs/09-investigation-domain.md` (authored by T41),
> `../specs/07-ui.md` (amended by T41).

## Milestone A — Foundation

**T41. ⛓ Spec 09 + re-validation — DONE (2026-08-17)** (charter §Specs) —
walked the pre-authored plan against the P3-as-built system; authored
`specs/09-investigation-domain.md` covering the investigation model (cases,
hypotheses, tasks/leads: storage, actions, authorization — model separate from
UI, H-17) and then the object-view descriptor contract (properties with
grading/conflict metadata, link groups, timeline strip, source list, authorized
case list).

Findings tagged P4 dispositioned: **H-17** — spec 09 §2–§5 defines the
operational model before any screen; **H-18** — spec 09 §6.5 makes the case
list leak-free by *construction* (derived only from rows the caller can already
read, then intersected with `can_view`), not by filtering an answer;
**H-19 remainder** — three genuinely open items found (undeclared realm session
timeouts, unwritten CSRF model, unstated multi-tab behaviour), spec 09 §10,
closed at T42; **B-11** — spec 09 §7 states the narrowed promise and names the
three missing pieces (`?asOfRevision=`, the response stamp, the banner); the
snapshot filter itself already exists.

Divergences found and dispositioned: **ADR-043** (descriptors are the generated
TypeScript module — `ui_meta.json` is not built; this closes the P3 carryover),
**ADR-044** (`claim.case_id` is the immutable recording scope and an access
predicate; case *references* are a separate, non-authorizing link),
**ADR-045** (the audit console moves to P7). Two smaller corrections carried
into the tasks below: T47's AC named the wrong enforcement mechanism (§3.3), and
spec 06 §2.7's claim that `ui_meta.json` supersedes the vocabulary route is
reversed.

AC met: spec 09 exists covering the investigation model and every surface the
generic object view renders; divergences are ADR'd; specs 06 §2.7 and 07 §2/§3/§6
corrected.

**T42. ⛓ Workspace v2 foundation — DONE (2026-08-17)** (specs/07 §3–4, spec 09 §6, §10; needs T41) —
the P2-born app (ADR-032 — the shell, auth, and serving decision already exist)
gains the case-centric layout and **ontology-driven navigation from the
generated descriptors** (ADR-043); all data access migrates to the P3 generated
client (hand-written domain types are defects, Article XI). Extend
`typescript_constants` with `display` and per-property metadata, and
`PredicateSpec`/`PropertySpec` with an optional `label` (additive ontology bump
+ proposal, spec 08 §7.3). Adopt a router now that routes take parameters —
`ui/src/routing.ts` has said since T23a that this belongs in P4 and that the
cost is re-testing the sign-in round trip, because the OIDC callback rewrites
the URL with `replaceState`.

Also closes the **H-19 remainder** (spec 09 §10): declare
`ssoSessionIdleTimeout` and `ssoSessionMaxLifespan` in the realm and assert
them; write the CSRF model into spec 03 and assert no route accepts a
cookie-borne identity; document multi-tab behaviour.

AC met: the rail lists every declared object type and interface from the
generated descriptors, and each has a live screen (`/types/:name`,
`/interfaces/:name`) rendering properties, clearance, conflict policy and
category-grouped links while calling **no endpoint**;
`tests/contract/test_workspace_descriptors.py` sweeps `ui/src` for every
domain-declared name — not just T39's one predicate — and finds none; all 42 P2
e2e journeys pass unchanged inside the new layout and through the router, plus
10 new ones covering the deep-link sign-in round trip and the back button; the
mismatch banner appears on disagreement and not on agreement; the three H-19
items are declared in the realm and in spec 03 §1.1–1.3 with
`tests/contract/test_session_policy.py` (9 cases) failing if any is dropped.
Ontology `1.6.0 → 1.6.1` (patch, proposal 005) for the four display labels the
generator's humanization gets wrong.

**T43. Investigation-model implementation** (spec 09 §2–§5; needs T41) —
storage/actions/routes for hypotheses (`hypothesis` + append-only
`hypothesis_revision` + `hypothesis_claim`, missing-info note required) and
tasks/leads (`investigation_task`: owner, status, dates) per spec 09; the
`case_reference` table of ADR-044; audited actions declared in the platform
module; `hypothesis` and `investigation_task` added to `REF_TARGETS`; the
`hypothesis`/`investigation_task` FGA types deriving `can_view`/`can_edit` from
their case; the fourth submission criterion `required_text_is_substantive`
(spec 09 §3.3); authz matrix rows added.
AC: hypothesis and task lifecycles round-trip through the API with audit;
matrix tests cover their allow/deny cases; a non-member gets 404 from every new
route, read **and** write; a whitespace-only missing-info note is denied and the
denial is audited; no UI yet (Milestone D renders them).

## Milestone B — Object views

**T44. ⛓ Generic object view (entity-360)** (spec 09 §6; needs T42) — one
generic, descriptor-driven component renders any object type: claim-derived
properties with grading badges; conflicting values render **side by side**
with relation badges — two DOBs are two DOBs (Article VIII); links grouped by
predicate category; source list; cases the entity appears in via
`GET /v1/entities/{id}/cases` — **built only from rows the caller can already
read, then intersected with `can_view`: no hidden count, no relevance ordering,
no existence leak (H-18, spec 09 §6.5)**.
AC: person and organization render through the same component with zero
type-specific React code; a seeded property conflict shows both values and
their `contradicts` badge; a viewer authorized for the entity but not a
restricted case that references it gets a response byte-identical to the
no-case response; every rendered value came through the client.

**T45. Provenance drill-down + timeline strip** (spec 09 §6.6; needs T44) —
every displayed value and link opens its provenance (the P2 why-connected API,
consumed as-is — a gap there is a P2 regression to fix in that route, not a new
endpoint); a compact timeline strip on the object view shows the entity's claims
over time.
AC: clicking any value or edge resolves to claims with all three grading
fields and their sources (parity with the P2 panel, same API, no new
endpoint); the strip's items match the claim time model.

## Milestone C — Cases

**T46. ⛓ Case UI + membership** (spec 09 §2; needs T42) — create/join/manage
cases via the existing FGA-scoped actions, plus the routes spec 09 §2.4 adds:
`GET /v1/cases` (only viewable cases, key-ordered, no count),
`POST /v1/cases/{id}/close`, `GET /v1/cases/{id}/members`, and the
`case_reference` link/unlink pair. **Referencing is not re-scoping** (ADR-044):
`claim.case_id` and `evidence_item.case_id` are never reassigned. Case-scoped
graph view (embedded Cytoscape reusing the projection API with a case filter).
AC: the Phase-1 authz matrix extends to the UI — a non-member sees nothing
about a case via any screen or endpoint it calls (exit criterion); membership
changes are audited actions; the case graph never renders out-of-case data; a
reference to a claim the caller cannot read is simply absent, and grants
nothing.

## Milestone D — Hypotheses & tasks

**T47. Hypotheses UI** (GOAL.md §18, spec 09 §3; needs T43, T44, T46) — screens
over the T43 hypothesis actions: supporting/contradicting claim links and the
**required missing-information note**; the hypothesis page always renders
both sides (Article VIII) plus what's missing, and an empty side renders as
"no contradicting evidence recorded" rather than being omitted.
AC: creation without a missing-info note — **absent or blank** — is rejected,
by the generated request model and by the `required_text_is_substantive`
submission criterion respectively (spec 09 §3.3; the pre-authored AC named only
the criterion, which does not fire on an absent field); a seeded hypothesis
shows supporting and contradicting claims simultaneously (exit criterion); the
revision history returns every version in order; all changes in audit.

**T48. Tasks / leads UI** (spec 09 §4; needs T43, T46) — screens over the T43
task/lead actions: lightweight status columns on cases; no workflow engine and
no transition graph (plan §2 trigger untouched).
AC: a lead moves through its statuses from the case screen; every transition
is an audited action carrying old and new value; no new infrastructure appears
in the diff.

## Milestone E — Time

**T49. Timeline + as-of mode (narrowed — B-11)** (spec 09 §7, specs/02 time
model; needs T44) — claim/event times with uncertainty rendered honestly;
`?asOf=` end-to-end in the UI as the defined **claim-recording snapshot** (the
filter already exists in `aegis/authz/filters.py`; what is missing is the rest).
Add `?asOfRevision=<id>` — specified in spec 06 §3 since P2 and never
implemented — the response stamp `{as_of, identity_revision_id,
ontology_version}` echoed whether or not the revision was pinned, and a
persistent, non-dismissible banner stating exactly what the view holds constant.
AC: an as-of query in the UI excludes a claim recorded after X in a seeded
test; the response carries all three stamps (exit criterion); a pinned revision
resolves entity arguments differently from the active one in a seeded merge;
uncertain dates render visually distinct from exact ones, and a claim with no
stated time renders "time not stated" rather than its `recorded_at`.

## Milestone F — Cutover & proof

**T50. P2-screen reorganization** (needs T44–T46) — the P2 review-queue,
search, adjudication, and provenance screens (same app — ADR-032) re-homed
into the case-centric layout; their APIs unchanged. No audit console: ADR-045
moves it to P7.
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
routes/screens, the cookie-identity assertion from T42, and the analyst-needs
checklist sign-off.
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
(P7), the audit console (P7 — ADR-045), collaboration beyond case membership
(comments, presence — GOAL.md §31 stays future), mobile, offline, any new
analytics or AI surface (P6/P8). Spec 09 §9 holds the full list, including the
ones only visible from inside the investigation model: no workflow engine, no
sealing enforcement, no hypothesis→claim promotion, and no projection of
hypotheses or tasks.
