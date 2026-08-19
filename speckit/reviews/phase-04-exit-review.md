# Phase 4 — Exit Review (T53)

Date: 2026-08-19
Release: Aegis 0.4.0
Tag after merge: `phase-4-workspace`

## Verdict

**PASS — Phase 4 is complete.** All five charter criteria are checked and
none is deferred or weakened. Work now happens inside access-scoped cases,
every value on a screen traces to its claims, and a hypothesis records what
would change the analyst's mind as a required field rather than a convention.

This closes Milestone III. It is not a deployment authorization — the pilot gate
remains open and untouched (§Deployment boundary).

## Exit criteria — non-deferrable (ADR-025)

- [x] **A non-member of a case cannot see its claims via any endpoint or screen,
  and cannot learn the case exists (no existence/count/timing leak — H-18).**

  Three surfaces, one rule. `tests/integration/test_investigation_routes.py`
  sweeps **all fifteen** investigation routes — writes included, because a 403
  on a write discloses a case as surely as one on a read — and asserts a hidden
  hypothesis and a nonexistent one return byte-identical responses.
  `tests/integration/test_case_graph.py` (6) refuses a non-member's case graph
  with 404 rather than an empty 200, which would say "that case exists and holds
  nothing you can see".

  The strongest evidence is `tests/integration/test_object_view.py` (8). The
  entity-360's case list is **derived only from rows the caller can already
  read**, then intersected with `can_view` — so the assertion is not "the
  restricted case is absent" (which a filtered implementation also passes) but
  that the response is *identical* to an entity in no case at all: same status,
  same body, same content type. The UI matches: no count, no marker, the same
  wording either way (`ui/e2e/object-view.spec.ts`).

- [x] **A hypothesis page shows both supporting and contradicting claims
  (Article VIII).**

  Both arrays are always present in `GET /v1/hypotheses/{id}`, empty or not, and
  both columns always render — the empty one saying "no contradicting evidence
  recorded" rather than disappearing. A page that hid it would tell the reader
  the question was never asked. The same claim linked under **both** stances
  appears on both sides, because a claim that cuts both ways is not a conflict
  to resolve. `ui/e2e/hypotheses.spec.ts` (10) plus a negative assertion that
  nothing on the page scores the two sides against each other — a "3 for, 1
  against" tally is the number that gets quoted without the lists it came from.

- [x] **"What was recorded before date X?" returns the defined claim-recording
  snapshot, stamped with snapshot + identity revision + ontology version.**

  `tests/integration/test_as_of.py` (10). `?asOf=` excludes a claim recorded
  after the timestamp and restores one retracted after it; every response
  carries `{as_of, identity_revision_id, ontology_version}` — **including a
  current one**, so a caller never re-reads its own request to learn which
  identity produced an answer.

  `?asOfRevision=` was specified in spec 06 §3 at P2 and had never been
  implemented, which meant `asOf` alone answered every historical question with
  *today's* identity. That trap is now a test of its own rather than a caveat.
  A revision above the head is **422, not clamped** — answering about now under
  a heading that says otherwise is the failure the parameter exists against.

- [x] **Adding a test object type via ontology alone yields a working object
  view with properties, links and provenance — no new React code.**

  `vessel` joined the `border-cargo` fixture *after* the generic screens
  existed, carrying every field a screen reads: a `display` with a subtitle, a
  required property, a `many` property, a `restricted` one, a
  `conflicts: preserve` one, and a shared reference with a declared label
  override. `tests/contract/test_ontology_to_screen.py` (9) asserts the
  generator emits a complete descriptor, that the governance fields survive, and
  that **no hand-written file under `aegis/` or `ui/src` names it**.

  The runtime half is honest about its limit: the bundle's descriptors are
  generated from the *shipped* ontology, so a fixture type cannot appear in
  them. What the browser proves is the same code path — two shipped types
  through one component, and an entity whose type the bundle has never seen
  still rendering, with the version banner explaining the missing caption.

- [x] **Re-verified: no unauthenticated read surface exists anywhere in the
  repo (ADR-026 held through the phase).**

  `tests/component/test_no_anonymous_surface.py` (15) re-checks through the
  grown surface rather than assuming it survived: every live route carries
  exactly one gate (walked from the dependency graph, not a maintained list),
  seven P4 routes are spot-checked end to end because a gate that exists but
  does not fire is what a walk cannot see, `public_route` appears nowhere in the
  repository, `/api/*` still 404s, and on the client every route sits inside
  `AuthGuard` and every declared route is rendered. The checklist sign-off is
  `phase-04-analyst-needs.md`.

## What Phase 4 actually changed

| Task | Landed |
|---|---|
| T41 | Spec 09 authored; five divergences → ADR-043…045 |
| T42 | Router, case-centric rail, descriptors extended, H-19 remainder closed |
| T43 | The operational plane: 5 tables, 9 actions, 15 routes, a 4th criterion |
| T44 | Entity-360 through one generic component; `GET /v1/entities/{id}/cases` |
| T45 | Provenance drill-down over P2 routes; the timeline strip |
| T46 | Case screens, case switcher, case-scoped graph |
| T47/T48 | Hypothesis page with both sides; the task board |
| T49 | `?asOfRevision=`, the stamp, the non-dismissible banner |
| T50/T51 | Runbook honesty pass; the ontology-to-screen proof |
| T52 | Authenticated-surface re-verification + the analyst-needs checklist |

Ontology `1.6.0 → 1.7.0` across two bumps, each with a proposal: `005`
(display labels, the first **patch**) and `006` (the investigation actions).
Migration `0010`. Ten pull requests, #49–#58.

## Decisions taken during the phase

Three ADRs, all from T41's re-validation — the plan was written before Phase 3
existed and three of its assumptions had stopped being true:

- **ADR-043** — the UI descriptor is the **generated TypeScript module**, not a
  fetched `ui_meta.json`. P3 already generated and drift-gated it; a second
  artifact would carry the same facts with no type-check. What was missing was
  fields, not an artifact. Closes the P3 carryover of the same name, together
  with the bundle/server version banner.
- **ADR-044** — `claim.case_id` is the immutable **recording scope** and an
  access predicate in `claim_filters`, so "link a claim to a case" cannot mean
  reassigning it. A case *reference* is a separate link that grants nothing —
  which is also why linking is an ordinary case-scoped write rather than a
  privileged one.
- **ADR-045** — the audit console moves to **P7**, where sealing and break-glass
  give it its first real reader. Spec 07 §6 said P4 and the charter never listed
  it; leaving the disagreement would have meant shipping an unplanned screen or
  closing with a spec quietly unmet.

## Defects found and fixed

Five, none of which the phase set out to look for:

1. **Every 401 had been losing `WWW-Authenticate: Bearer`.** Wrapping errors in
   problem+json (T36, P3) rebuilt the response from the exception's *body* and
   dropped its *headers*. RFC 7235 §3.1 requires the field, and it is the only
   thing telling a client how to authenticate. Nothing failed; it stopped being
   correct HTTP. Found by T52 — exactly what a re-verification task is for.
2. **`.notice` had been `position: absolute` since T22**, when the only notice
   in the product floated over the graph canvas. Every P4 screen reuses the
   class in ordinary prose, so each was rendering at the top-left of whatever
   was positioned above it. Now in flow, with the overlay kept where it was
   meant (`.graph__body > .notice`).
3. **`.case-graph` had no positioning context**, so Cytoscape's `inset: 0`
   layers sized themselves against the viewport and covered the page —
   swallowing the clicks of the forms above them. Found by a browser journey
   timing out on a click; no assertion about text would have caught it.
4. **`ClaimOut` had never exposed `event_time_earliest`/`event_time_latest`.**
   The columns have existed since P1 and no response carried them, so no client
   could render event time at all. Additive fix at T45.
5. **Three P3-era tests pinned the *current* release state** — `release.json`'s
   proposal, a module's version, a claim's literal `ontology_version` — and went
   red for changes that had nothing to do with them. Each now asserts the
   durable fact instead.

And one of my own, recorded because CI caught it rather than review:
`test_nothing_new_is_mounted` assumed `ui/dist` exists, so it passed locally and
failed in CI. The convention was already right in `test_route_gating.py`.

## Constitution conformance

| Article | Finding | Evidence |
|---|---|---|
| I — claims, not facts | Pass | Hypotheses are assertions about our reasoning and share no table, route prefix or projection with claims; `claim.case_id` is never reassigned (ADR-044) |
| II — no inherent derogatory status | Pass | No status is computed about a person; a hypothesis is authored, attributed and revisable |
| III — grading dimensions separate | Pass | The drill-down renders all three apart; no screen composes them |
| IV — evidence is not intelligence | Pass | Untouched |
| V — reversible identity | **Pass, extended** | `?asOfRevision=` replays the ledger, so a merge can be *un-asked* in a query as well as undone in the record |
| VI — authorization at query time | **Pass, re-verified** | T52's 15 cases; the case-graph filter joins `claim_filters` rather than filtering a result |
| VII — machines suggest, humans decide | Pass | No new machine write path; hypotheses and tasks are human-authored actions |
| VIII — disagreement preserved | **Pass, strengthened** | One shared component renders conflicts for every screen, asserted so neither can keep a private copy; both hypothesis columns always render |
| IX — association is not guilt | Pass | No hypothesis is projected; no page scores supporting against contradicting; the case graph cannot overstate a case's evidence |
| X — everything audited | Pass | Nine new audited actions, each carrying the old value beside the new |
| XI — ontology is domain truth | Pass | The screens read generated descriptors; the sweep finds no domain name in `ui/src` |
| XII — adopt before build | Pass | `react-router` adopted rather than the hand-rolled history code extended |
| XIII — projections are caches | Pass | The pinned identity resolution is *computed* rather than cached, precisely because the map caches only the active answer |
| XIV — core is domain-neutral | **Pass, extended** | A type added to the fixture domain reaches a working screen with no code; `vessel` appears in no hand-written file |

## Deliverables and reality check

Every charter deliverable landed. Two were **narrowed with reasons recorded**:

- **`?asOf=` is on entity reads only.** The graph and search do not take it. The
  criterion asks for the claim-recording snapshot and its stamps, which the
  entity route provides end to end; extending it is mechanical and belongs with
  the phase that needs a historical graph.
- **The hypothesis claim-link form takes a claim id, not a picker.** No "claims
  in this case" route exists to populate one, and a client-side search over a
  route that does not exist would be worse than asking for the id the analyst is
  already looking at. Not a gate criterion.

The **audit console** was dropped outright, with an ADR (045). Explicit
non-goals held: no map, no object sets, no global search, no compartment UX, no
collaboration beyond case membership, no workflow engine, no sealing
enforcement, no hypothesis→claim promotion, and no projection of hypotheses or
tasks.

## Carryovers

| Item | Owner | Target | Dependency impact |
|---|---|---|---|
| `?asOf=` on graph and search | P5/P6 owner | With the historical questions those surfaces raise | None; the entity route carries the criterion |
| Claims picker for hypothesis links | P6 owner | With object sets / a case-claims query | None; the id form works |
| Audit console | P7 owner | With sealing and break-glass (ADR-045) | None; `GET /v1/audit` is callable today |
| `hypothesis` / `investigation_task` FGA types are declared but not queried | P7 owner | When a direct check becomes meaningful | None — the routes check the parent case, which is what the derivations compute; stated in spec 09 §5 so it is not mistaken for enforcement |
| FGA object-type stub codegen | P7 owner | When a **domain** type first gets an FGA relation | None (P3 carryover, unchanged) |
| Python SDK | P8 owner | P8 producers | None (ADR-033, unchanged) |
| Functions execution + side-effect outbox | P5/P6 owners | Spec 08 §11.1–11.2 | None (P3 carryover, unchanged) |
| Pilot gate (TLS, secrets, restore boundary, Object Lock, health/throughput) | Deployment owner | Before any non-loopback listener or second real user | Blocks deployment, not P5 development |

## Verification

Run on the exact reviewed tree, against PostgreSQL 16 on `127.0.0.1:5433`:

```
uv run pytest -q tests/unit tests/component tests/contract   # 433 passed
uv run pytest -q tests/integration                           # 336 passed
uv run aegis ontology validate                               # OK v1.7.0, 2 modules
uv run aegis ontology generate --check                       # OK: 4 artifacts current
uv run aegis ontology check-release                          # OK: v1.7.0 (minor, proposal 006, from 1.6.1)
uv run aegis api check-contract                              # OK: 0 breaking
uv lock --check                                              # clean
cd ui && npm run typecheck && npm run build && npx playwright test   # clean; 92 passed
```

**System tests were not runnable on the development machine** — the OpenFGA
container cannot bind its port there — so CI's `system-tests` job is their only
execution. It passed on every one of the ten Phase 4 pull requests (#49–#58).
This is the same arrangement T28 and T40 recorded, stated again for the same
reason: the reader should know which evidence came from where.

Phase 4 added **131 tests** (433 + 336 against P3's 355 + 282), plus 41 browser
journeys (92 against 51).

## Deployment boundary

Unchanged and unauthorized. 0.4.0 is a localhost development release. The pilot
gate's seven items are all still open, `aegis serve` still refuses a non-loopback
bind without an explicit override, and nothing in this phase
may be represented as pilot-ready.

## Release action

`pyproject.toml` and `uv.lock` advance from 0.3.0 to **0.4.0**. After the review
PR is squash-merged, tag that master commit:

```bash
git tag -a phase-4-workspace -m "Phase 4 exit: investigation workspace v2 and object views"
git push origin phase-4-workspace
```

## Final decision

All five gate criteria are checked. Phase 4 is complete and **Phase 5 — events,
geospatial & time** may begin with its own re-validation task (T54), which
should disposition the carryovers above before anything else.
