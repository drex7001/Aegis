# Phase 4 — analyst-needs checklist (T52)

The Phase 4 charter names a risk and a defence:

> **Parity trap (designing against the legacy explorer).** Replacement, not
> parity (ADR-023): scope is a short analyst-needs list written up front (graph,
> filters, detail panel); legacy features absent from it are dropped without
> debate.

This is that list, signed off at T52 and carried into the exit review. It is
deliberately short. Anything not on it was not promised, and the last section
names what was dropped — because "we decided not to" and "we forgot" look
identical a year later.

## What an analyst has to be able to do

| # | Need | Where it is met | Verified by |
|---|---|---|---|
| 1 | Find a person or organization by name, including across scripts | Entity search (P2), reachable from the graph view | `tests/integration/test_search.py`, `ui/e2e/provenance.spec.ts` |
| 2 | See everything claimed about one entity, in one place | Object view `/entities/:id` — properties, links, sources, cases, timeline | `ui/e2e/object-view.spec.ts` |
| 3 | Ask why any value is on the screen | "Where did this come from?" on every claim card → `GET /v1/claims/{id}/provenance` | `ui/e2e/provenance-drill.spec.ts` |
| 4 | Ask why two entities are connected — including who decided they were one person | "Why connected?" on every link → `why-connected`, with the identity decisions | `ui/e2e/provenance-drill.spec.ts` |
| 5 | See disagreement as disagreement, never as a resolved value | Conflicting claims render side by side with a `contradicts` badge, through one shared component | `ui/e2e/object-view.spec.ts`, `test_workspace_descriptors.py` |
| 6 | Expand a graph from a known starting point, bounded and explained | `POST /v1/graph/expand` with seeds, hops, categories, element budget; truncation stated on the answer | `tests/integration/test_graph_routes.py` |
| 7 | Work inside a case, and see only that case's evidence | Case screen, case switcher, case-scoped graph (`case_id` joins `claim_filters`) | `tests/integration/test_case_graph.py`, `ui/e2e/cases.spec.ts` |
| 8 | Write down what is believed, what supports it, what contradicts it, and what is missing | Hypothesis page: both columns always, required missing-information note | `ui/e2e/hypotheses.spec.ts`, `tests/integration/test_investigation_model.py` |
| 9 | Keep track of what is left to do | Task board on the case screen; task/lead, owner, status, due date | `ui/e2e/hypotheses.spec.ts` |
| 10 | Ask what had been recorded before a date | `?asOf=` with `?asOfRevision=`, stamped and bannered | `tests/integration/test_as_of.py`, `ui/e2e/as-of.spec.ts` |
| 11 | Land a source, review what was proposed from it, and accept or reject it | The P2 loop, unchanged, inside the new layout | `docs/MVP_DEMO.md`, `ui/e2e/sources.spec.ts`, `ui/e2e/review.spec.ts` |
| 12 | Trust that what is shown is what they are allowed to see | Authorization applied in the query, not the render; absence rather than a marked redaction | `tests/integration/test_authz.py`, `test_object_view.py`, `test_investigation_routes.py` |

## The no-unauthenticated-surface re-verification

The charter's fifth criterion, re-checked through the grown surface rather than
assumed to have survived it. `tests/component/test_no_anonymous_surface.py`:

- every route in the live application carries **exactly one** authorization
  gate — walked from the dependency graph, not from a maintained list;
- seven Phase 4 routes are spot-checked end to end for a 401, because a gate
  that exists but does not fire is the failure a graph walk cannot see;
- `public_route` — the exemption ADR-026 deleted — appears nowhere in the
  repository, swept over scripts, fixtures and helpers as well as `aegis/`;
- exactly one mount exists, and it is the workspace bundle: a second mount is a
  second way to serve bytes without a gate, and it appears in no route walk;
- `/api/*` still answers 404 rather than falling through to the workspace HTML;
- every client route sits inside `AuthGuard`, every declared route is rendered,
  and the client reaches no origin but its own and Keycloak.

Plus, from T42: no route accepts a cookie-borne identity, and no response sets
one (`tests/contract/test_session_policy.py`).

**One defect found.** Wrapping errors in problem+json at T36 rebuilt the
response from the exception's body and dropped its headers, so every 401 had
been losing `WWW-Authenticate: Bearer` — required by RFC 7235 §3.1 and the only
field telling a client how to authenticate. Nothing failed; it simply stopped
being correct HTTP. Fixed, with a regression test.

## What was dropped, deliberately

From the legacy explorer, and from the wider wish-list, none of these is in
Phase 4 and none is an oversight:

| Dropped | Why |
|---|---|
| Cell colouring / community detection on the canvas | An analytic finding rendered as a colour with no caveat is the Article IX failure; findings arrive at P6 with their run manifests |
| Temporal slider with play | The timeline strip and as-of answer the question; an animation over uncertain intervals would imply precision nobody asserted |
| Confidence filter as a slider | There is no single confidence to filter on — three grading dimensions stay apart (Article III), and a slider would be the composite score the model refuses |
| A claims picker for hypothesis links | No "claims in this case" route exists to populate one; asking for the id the analyst is looking at beats a search over a route that does not exist. Not a gate criterion |
| Audit console | ADR-045 — moves to P7, where sealing and break-glass give it its first real reader |
| Map view, object sets, global search | P5, P6 — the charter's explicit non-goals |
| Comments, presence, review requests | GOAL.md §31 stays north-star until a real second analyst exists |

## Sign-off

Every need above is met by a shipped surface with a named test. The
no-unauthenticated-surface property holds through the grown Phase 4 API and
client, re-verified rather than inherited, and the one defect it found is fixed.

Recorded at T52, 2026-08-19, for the Phase 4 exit review.
