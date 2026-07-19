# Investigation workspace (spec 07, ADR-032)

The single durable Aegis UI: React 18 + TypeScript + Vite. Started in **Phase 2**
(T22) and grown in place through every later phase — there is no interim stack
and no second UI generation (ADR-023's replace-never-extend, applied to our own
work). It replaced the legacy Cytoscape explorer and its anonymous `/api/*`
surface, both deleted in the same change (ADR-026).

## What ships today (P2)

- **Auth shell** — Keycloak OIDC with PKCE via `react-oidc-context` /
  `oidc-client-ts`; an unauthenticated visit redirects to sign in.
- **Graph view** — Cytoscape.js reading `POST /v1/graph/expand`: authenticated,
  authorization-filtered, and bounded. Entity search (T23c) seeds it, so spec 07
  §5's "search first, expand second" is literally that rather than the bounded
  overview standing in. Clicking an edge or a node opens the provenance panel;
  **selecting does not re-lay out the graph** — focusing is a button inside the
  panel, because re-drawing the canvas under someone who clicked to read is how
  they lose the thing they were looking at.
- **Sources view** (T23a) — land a file or a pasted note with its provenance,
  read the register of what has landed, and run the derivative + extraction
  stages per record. Quarantined records show their reason and offer release.
- **Review view** (T23b) — the inbox, composed over two sources rather than
  merged into one: `review_queue` suggestions (accept, edit-then-accept, reject
  with a reason) and `er_candidate` identity pairs (confirm, reject, "cannot
  tell", plus batch-confirm for the pre-verified band). Every suggestion shows
  the producer metadata that makes it checkable; every candidate shows its
  per-feature waterfall.

- **Provenance panel** (T23c) — two modes over two routes, because they answer
  different questions. An **edge** asks "why are these two connected?"
  (`why-connected`: relation claims, their sources, and the identity decisions
  that made the endpoints these endpoints). A **node** asks "what is claimed
  about this one?" (`GET /v1/entities/{id}`: property claims grouped by
  predicate). Disagreeing claims about one property render **side by side** in
  a comparison grid with a `contradicts` badge — see rule 3.

P4 adds object views, cases and timeline to this same app.

## Two rules the screens follow

Worth knowing before adding a third view, because both are easy to break by
accident:

1. **Only the exceptional state is marked.** A left rail means "this needs you"
   and nothing else. An ordinary record keeps the same geometry with no colour,
   so the register stays scannable and a mark still carries information.
   Quarantine uses the caution bronze — a governance hold is not an alarm, and
   the failure colour is reserved for a request that failed, never for an
   entity, a category or a claim (spec 07 §5).
2. **Monospace means machine identity.** Content hashes and record ids, where
   character-by-character comparison is the point. Prose stays in the body face.
   The digest chip is what makes "already landed" believable: you can see the
   hash coming back is the hash of what you sent.
3. **Evidence is shown in both directions** (T23b). A candidate's waterfall runs
   left and right from a centre line, because a Bayes factor below 1 argues
   *against* the match. A one-directional bar would render only the half that
   agrees, and a single combined score would hide the disagreement entirely —
   which is the one thing a reviewer is there to weigh. The column arguing
   against uses the caution bronze, never the failure colour: it is a judgement
   about evidence, not a request that failed.
4. **A contradiction is a lens, not a weakening** (T23c). Contested support is
   *marked*, never dimmed — a dashed edge on the canvas, a bronze rail and a
   `contradicts` badge in the panel. Dimming would read as "weaker evidence";
   the point is that two sources disagree and neither has been chosen. Both
   readings render side by side, in columns, so the reader compares values
   across one line instead of holding the first in memory while reading the
   second — and corroboration is shown *beside* contradiction, never subtracted
   from it (Article VIII).
5. **The search says how it found each hit** (T23c). A phonetic match is a lead,
   not a name match: metaphone collapses genuinely different names, so it is
   scored low, labelled "sounds like", and chipped with a dashed border. A list
   that rendered it like a name hit would overstate what the index found.

## Navigation

`src/routing.ts` — path-based, on the History API, no router library. Three
views do not need one; they do need real URLs, a back button and a path the auth
guard can return to.

The rule that matters: **anything that moves the URL has to announce it.**
`pushState` and `replaceState` fire no event. The sign-in callback rewrites the
URL to the page the user originally asked for, *after* the app has mounted at
`/auth/callback` — so without `notifyNavigated()` the app renders the fallback
view at the correct address, which is exactly what the first build did.

A router library arrives with P4's view count. The reason to wait is that it
would own the history stack and therefore not observe the callback's write, so
adopting one means re-testing the whole sign-in round trip.

## Running it

```bash
make up && make bootstrap        # postgres, keycloak, openfga, minio
uv run aegis serve               # API on http://127.0.0.1:8000

cd ui
npm ci
npm run dev                      # workspace on http://127.0.0.1:5173, /v1 proxied
```

Sign in as `dev-analyst` / `analyst` (fictional dev credentials from
`infra/keycloak/aegis-realm.json`).

For the served-bundle path — what `aegis serve` actually hosts in production:

```bash
npm run build                    # → ui/dist, mounted at / by the API
uv run aegis serve               # workspace and API on one origin
```

| Command | What it does |
|---|---|
| `npm run dev` | Vite dev server, `/v1` proxied to `127.0.0.1:8000` |
| `npm run typecheck` | `tsc --noEmit` (also the first half of `build`) |
| `npm run build` | type-check + production bundle into `dist/` |
| `npm run generate:api` | regenerate `src/api/schema.d.ts` from `openapi.json` |
| `npm run test:e2e` | the hermetic browser smoke journey |

`make openapi` from the repo root does both halves of the client refresh:
re-export `ui/openapi.json` from the FastAPI routes, then regenerate the types.
`tests/contract/test_openapi.py` fails if the committed document drifts from the
routes, because a stale document produces a client that type-checks and 404s.

## How auth is wired, and why

`src/auth/config.ts` is worth reading before changing anything here.

- **Tokens live in memory** (`InMemoryWebStorage`), never in localStorage —
  ADR-032 §1. They die with the tab, so an XSS that runs later finds nothing.
- **The PKCE state lives in sessionStorage**, because it must survive a
  full-page redirect to Keycloak and back. It holds a single-use code verifier
  and nonce, never a token.
- **A page reload therefore has no user** and bounces through Keycloak again.
  That round trip is invisible while the SSO session cookie is live; the
  alternative is persisting tokens to web storage, which the ADR forbids.
- **The API client asks the `UserManager` for the token per request** rather
  than receiving it through React. Child effects run before parent effects, so a
  token handed down from a provider arrives *after* the first query has already
  fired — the smoke journey caught exactly that.

### Keycloak client configuration

The workspace signs in as the `aegis-ui` public client. Two things about the
realm are non-obvious and cost real debugging time:

1. **The realm's `clientScopes` list replaces Keycloak's built-ins.** Only
   `aegis` exists — there is no `profile` or `email` scope — so the workspace
   requests `scope: "openid"` alone. Asking for `profile`/`email` fails the
   whole authorize request with `invalid_scope`. Every claim the app reads
   (`preferred_username`, `realm_access.roles`, `clearance`, and the
   `aegis-api` audience) is minted by the `aegis` scope's mappers.
2. **`redirectUris` and `webOrigins` list both `127.0.0.1` and `localhost`** on
   ports 8000 (served bundle), 5173 (dev) and 4173 (preview). Each bare origin
   is a valid post-logout destination and each `/auth/callback` is a valid
   sign-in destination. They are different origins to a browser, and `origin`
   is what the redirect URI is matched against.

The API tolerates 60s of clock skew on token validation
(`AEGIS_OIDC_CLOCK_SKEW_SECONDS`): the identity provider is a different host,
and the dev stack's Keycloak container measurably runs ~2s ahead. Zero looks
stricter but only means every freshly minted token is "not yet valid".

## Build-time configuration

| Variable | Default |
|---|---|
| `VITE_OIDC_AUTHORITY` | `http://localhost:8180/realms/aegis` |
| `VITE_OIDC_CLIENT_ID` | `aegis-ui` |

Vite bakes these at build time. Runtime configuration for a deployed bundle is a
pilot-gate concern (ADR-033 §4), not a P2 one.

## Testing

`e2e/smoke.spec.ts` and `e2e/sources.spec.ts` run against the **built** bundle
via `vite preview`, under a copy of the production CSP, with Keycloak and the
API stubbed at the network boundary (`e2e/oidc-stub.ts`, `e2e/ingest-stub.ts`).
`oidc-client-ts` runs its real PKCE state machine — only the server's replies
are fabricated — so the journey exercises every line of ours: the redirect
carries a real S256 challenge, the code is redeemed, the bearer token reaches
the API, and nothing lands in localStorage.

The ingest stub keeps the service's *rules*, not just its shapes: it is
content-addressed, so re-sending the same bytes is a no-op and a same-name
different-body upload is a version conflict. A stub that answered every landing
with "landed" would let the journey pass while the screen was incapable of
telling an operator that nothing had happened — which is how the same document
gets filed twice. It is not a second implementation; it has no vault, no audit
log and no authorization, and those are proven in
`tests/integration/test_ingest_routes.py` against the real service.

The full ingest → suggest → review → adjudicate → explore loop against a live
stack is T25/T27's blocking demo, not this job.
