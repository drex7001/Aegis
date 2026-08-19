# Phase 4 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them; narrower dependencies are noted in the task text. Reference specs in
parentheses. Numbering continues from Phase 3 (T40).

> **Status: COMPLETE 2026-08-19 — all five gate criteria checked**
> (`../reviews/phase-04-exit-review.md`). Opened 2026-08-17 with T41's
> re-validation. Authored
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

**T43. Investigation-model implementation — DONE (2026-08-19)** (spec 09 §2–§5; needs T41) —
storage/actions/routes for hypotheses (`hypothesis` + append-only
`hypothesis_revision` + `hypothesis_claim`, missing-info note required) and
tasks/leads (`investigation_task`: owner, status, dates) per spec 09; the
`case_reference` table of ADR-044; audited actions declared in the platform
module; `hypothesis` and `investigation_task` added to `REF_TARGETS`; the
`hypothesis`/`investigation_task` FGA types deriving `can_view`/`can_edit` from
their case; the fourth submission criterion `required_text_is_substantive`
(spec 09 §3.3); authz matrix rows added.
AC met: hypothesis, task and reference lifecycles round-trip through the API
with audit (`tests/integration/test_investigation_routes.py`, 9 cases); the
authorization matrix gained 15 rows and still asserts exact equality; a
non-member gets **404 from all 15 new routes, writes included**, and a hidden
hypothesis is byte-identical to a nonexistent one; a whitespace-only
missing-info note is refused by the criterion, audited as a denial that
survives the caller's rollback, and refused again by a CHECK constraint if
anything writes the table directly.
`tests/integration/test_investigation_model.py` (21) covers the actions layer
and `tests/contract/test_investigation_contract.py` (13) the declarations —
including that no investigation action declares a side effect, because a
`refresh_projection` here is the first step to a suspicion becoming an edge.
Ontology `1.6.1 → 1.7.0` (minor, proposal 006); migration `0010`. No UI
(Milestone D renders them).

**Scope note.** Spec 09 §2.4's case routes (`GET /v1/cases`, close, members,
references) landed **here** rather than at T46. H-17's whole point is that the
model and API are specified and accepted before any screen, and splitting the
case routes from the hypothesis routes would have put half the operational
plane behind a UI task. T46 is now purely the case UI.

## Milestone B — Object views

**T44. ⛓ Generic object view (entity-360) — DONE (2026-08-19)** (spec 09 §6; needs T42) — one
generic, descriptor-driven component renders any object type: claim-derived
properties with grading badges; conflicting values render **side by side**
with relation badges — two DOBs are two DOBs (Article VIII); links grouped by
predicate category; source list; cases the entity appears in via
`GET /v1/entities/{id}/cases` — **built only from rows the caller can already
read, then intersected with `can_view`: no hidden count, no relevance ordering,
no existence leak (H-18, spec 09 §6.5)**.
AC met: person and organization render through the same component — the
descriptor sweep over `ui/src` finds no domain name, and the divisions the
screen draws (property vs. link, and which category a link is in) come from
`PREDICATES`/`CATEGORIES`; a seeded property conflict shows both dates of birth
with the `contradicts` badge, through the **same** `PredicateGroup` the P2 panel
uses, so Article VIII cannot become true in one screen and false in the other; a
viewer authorized for the entity but not for a restricted case that references
it gets a response byte-identical to an entity in no case at all
(`tests/integration/test_object_view.py`, 8 cases); the only endpoint added is
`GET /v1/entities/{id}/cases`, which exists because H-18 requires the list to be
built server-side from readable rows.

Spec 09 §6.4 corrected: the heading is `entity.label`, not `display.title`
resolved against claims. `display.title` names a *property* and the response is
keyed by *predicate*, and the ontology declares no mapping between them.

**T45. Provenance drill-down + timeline strip — DONE (2026-08-19)** (spec 09 §6.6; needs T44) —
every displayed value and link opens its provenance (the P2 why-connected API,
consumed as-is — a gap there is a P2 regression to fix in that route, not a new
endpoint); a compact timeline strip on the object view shows the entity's claims
over time.
AC met: a value opens `GET /v1/claims/{id}/provenance` and a link opens
`GET /v1/entities/{a}/why-connected/{b}` — both P2 routes, consumed as-is, with
an e2e request sweep asserting the pair adds **no** endpoint; the drawer renders
all three grading dimensions, the source, and (for a link) the identity
decisions behind its endpoints, through the same `ClaimCard` as everywhere else.
The strip follows the claim time model exactly: an interval renders as a span
and an instant as a hairline, and a claim that states no world time is **listed
apart and said to state none** rather than placed at `recorded_at` — when we
wrote something down is a fact about us, not about the world.
`ClaimOut` gained `event_time_earliest`/`event_time_latest` (additive; the
columns existed and no response exposed them).

## Milestone C — Cases

**T46. ⛓ Case UI + membership — DONE (2026-08-19)** (spec 09 §2; needs T42, T43) — screens over the
routes T43 landed: the case switcher in the rail's reserved slot, create/join/
manage, close, and the `case_reference` link/unlink pair. **Referencing is not
re-scoping** (ADR-044) and the UI must not imply otherwise. Case-scoped graph
view (embedded Cytoscape reusing the projection API with a case filter).
AC met: the case switcher fills the slot T42 reserved; a non-member sees
nothing about a case through any screen or the endpoints it calls — the case
list is empty, the detail reads as absence rather than refusal, and the case
graph answers 404 identically for a hidden case and a nonexistent one
(`tests/integration/test_case_graph.py`, 6 cases); membership changes go through
the audited `assign_case_member`; **the case graph never renders out-of-case
data, and never overstates the case's evidence** — `case_id` is threaded into
`claim_filters` rather than applied to the result, so an edge supported by one
case claim and one open claim renders with a tally of one in the case graph and
two in the open one; the reference list says in the operator's own words that a
reference grants no access and does not move a claim into the case (ADR-044).

`POST /v1/graph/expand` gained an optional `case_id`. Additive, and a
*narrowing* one: an unauthorized case id is refused with 404 rather than
ignored, because an ignored filter would return the caller's whole readable
graph under a heading that says otherwise.

## Milestone D — Hypotheses & tasks

**T47. Hypotheses UI — DONE (2026-08-19)** (GOAL.md §18, spec 09 §3; needs T43, T44, T46) — screens
over the T43 hypothesis actions: supporting/contradicting claim links and the
**required missing-information note**; the hypothesis page always renders
both sides (Article VIII) plus what's missing, and an empty side renders as
"no contradicting evidence recorded" rather than being omitted.
AC met: creation without a missing-info note — **absent or blank** — is
rejected, by the generated request model and by the
`required_text_is_substantive` criterion respectively (the pre-authored AC named
only the criterion, which does not fire on an absent field), and the refusal is
surfaced in the server's own words rather than translated to a generic message;
**both columns render whether or not they hold anything**, with the empty side
reading "no contradicting evidence recorded" — the assertion the screen exists
for; a claim linked under both stances appears on both sides; the revision
history shows every version's own statement; nothing on the page scores the two
sides against each other, asserted as a negative.

**T48. Tasks / leads UI — DONE (2026-08-19)** (spec 09 §4; needs T43, T46) — screens over the T43
task/lead actions: lightweight status columns on cases; no workflow engine and
no transition graph (plan §2 trigger untouched).
AC met: a lead moves open → in progress → done from the case screen, each move
a `POST /v1/tasks/{id}` the server audits with its old value beside the new;
every status is offered from every status, asserted directly, because the
absence of a transition graph is the design rather than an omission; an
unassigned task says "unassigned" rather than inventing an owner. No new
infrastructure in the diff.

**Landed with T47** in one change: both are panels on the case screen, over
actions T43 already shipped, and splitting them would have meant two pull
requests editing the same file (the P3 precedent is T37/T38).

## Milestone E — Time

**T49. Timeline + as-of mode (narrowed — B-11) — DONE (2026-08-19)** (spec 09 §7, specs/02 time
model; needs T44) — claim/event times with uncertainty rendered honestly;
`?asOf=` end-to-end in the UI as the defined **claim-recording snapshot** (the
filter already exists in `aegis/authz/filters.py`; what is missing is the rest).
Add `?asOfRevision=<id>` — specified in spec 06 §3 since P2 and never
implemented — the response stamp `{as_of, identity_revision_id,
ontology_version}` echoed whether or not the revision was pinned, and a
persistent, non-dismissible banner stating exactly what the view holds constant.
AC met (`tests/integration/test_as_of.py`, 10 cases; `ui/e2e/as-of.spec.ts`,
8): an as-of query excludes a claim recorded after the timestamp and restores
one retracted after it; **every** response carries `{as_of,
identity_revision_id, ontology_version}`, including a current one, so a caller
never re-reads its own request to learn which identity produced an answer; a
pinned revision resolves a seeded merge differently from the active one, and
the trap is asserted as its own test — `asOf` alone answers a January question
with today's identity, which is why the revision is echoed and the banner names
it; a revision that has not happened is **422 rather than clamped**, because
answering about now under a heading that says otherwise is the failure the
parameter exists against. Uncertainty rendering landed with T45's strip.

The banner is persistent and **not dismissible**, and states the limits as well
as the promise — labels, source evaluations, grading, policy and the ontology
are current, not historical. B-11 was a finding about an overstated promise; a
banner reading only "showing 1 March" would repeat it.

`canonical_entity_at` / `absorbed_ids_at` replay the ledger up to a revision
rather than reading `entity_canonical_map`, which caches exactly one answer —
the active one. The cost is a replay per pinned read, bounded by the number of
identity decisions, which a human produces one at a time.

## Milestone F — Cutover & proof

**T50. P2-screen reorganization — DONE (2026-08-19)** (needs T44–T46) — the P2 review-queue,
search, adjudication, and provenance screens (same app — ADR-032) re-homed
into the case-centric layout; their APIs unchanged. No audit console: ADR-045
moves it to P7.
AC met: the loop is unchanged and the diff touches no API code — the
reorganization itself happened at **T42**, which wrapped the P2 screens in the
new Shell, so what T50 owed was the honesty pass and the proof. `docs/MVP_DEMO.md`
gains a "Where things are (P4 layout)" section naming the rail's three groups and
the two banners an operator can meet, and
`tests/contract/test_mvp_demo_runbook.py` asserts both — plus that no step in the
loop reaches for `curl`, the CLI or `psql`, because a loop that no longer closes
in the product is not the loop the MVP gate measured.

**T51. Ontology-to-screen proof — DONE (2026-08-19)** (charter exit №4; needs
T44) — add a test object type via the ontology alone (+ proposal + regen, P3 discipline): a
working object view with properties, links, and provenance appears with **no
new React code**.
AC met: `vessel` was added to the `border-cargo` fixture **after** the generic
screens existed — which is what makes it a proof rather than a fixture that
happened to be there first — carrying every field a generic screen reads: a
`display` with a subtitle, a required property, a `many` property, a
`restricted` one, a `conflicts: preserve` one, and a shared reference with a
declared label override. The diff is the fixture module, its version, and the
composition pin: `tests/contract/test_ontology_to_screen.py` (9 cases) asserts
the generator emits a complete descriptor for it, that the governance fields
survive the journey, and that **no hand-written file under `aegis/` or `ui/src`
names it**, and that the **shipped** ontology is untouched — a fixture type
must never leak into the product's vocabulary.

The runtime half is `ui/e2e/object-view.spec.ts`: two shipped types render
through one component, and an entity whose type the bundle has *never seen*
still renders — the case an operator meets when the server is ahead, where the
version banner is what explains it. The descriptor half is proved at the
contract layer because the bundle is built from the shipped ontology, so a type
added to a fixture cannot appear in it; the test says so rather than implying
otherwise.

**T52. No-unauthenticated-surface re-verification — DONE (2026-08-19)** (charter exit №5; needs
T50 and the T41 checklist) — the legacy explorer and `/api/*` were deleted in
P2 (T22, ADR-026); this task re-verifies through the grown P4 surface: repo
grep for any `public_route`-style exemption, authz-matrix run across all P4
routes/screens, the cookie-identity assertion from T42, and the analyst-needs
checklist sign-off.
AC met: `tests/component/test_no_anonymous_surface.py` (15 cases) re-verifies
through the grown surface — every live route carries exactly one gate (walked
from the dependency graph, not a maintained list), seven P4 routes are
spot-checked end to end for a 401 because a gate that exists but does not fire
is what a graph walk cannot see, `public_route` appears nowhere in the
repository, exactly one mount exists, `/api/*` still 404s, every client route
sits inside `AuthGuard`, every declared route is rendered, and the client
reaches no origin but its own and Keycloak. The checklist is
`../reviews/phase-04-analyst-needs.md`, and it records what was **dropped** as
well as what was met.

**One defect found.** Wrapping errors in problem+json at T36 rebuilt the
response from the exception's body and dropped its headers, so every 401 had
been losing `WWW-Authenticate: Bearer` — RFC 7235 §3.1, and the only field
telling a client how to authenticate. Nothing failed; it stopped being correct
HTTP. Fixed with a regression test in `test_error_envelope.py`.

**T53. Phase exit review — DONE (2026-08-19)** — walk the charter's gate criteria (non-deferrable,
ADR-025); update speckit docs where reality diverged; append ADRs; write
`../reviews/phase-04-exit-review.md`; tag `phase-4-workspace` per the git
workflow.
AC met: all five checked with their evidence; three ADRs (043–045) and five
defects recorded, one of them a 401 that had been losing its
`WWW-Authenticate` header since T36; eight carryovers carried with an owner, a
target phase and a dependency impact. Release 0.3.0 → 0.4.0; tag
`phase-4-workspace`.

## Explicit non-goals for Phase 4

Map view (P5), full multilingual search and object sets (P6), compartment UX
(P7), the audit console (P7 — ADR-045), collaboration beyond case membership
(comments, presence — GOAL.md §31 stays future), mobile, offline, any new
analytics or AI surface (P6/P8). Spec 09 §9 holds the full list, including the
ones only visible from inside the investigation model: no workflow engine, no
sealing enforcement, no hypothesis→claim promotion, and no projection of
hypotheses or tasks.
