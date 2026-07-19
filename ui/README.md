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
  authorization-filtered, and bounded. Clicking a node expands from it; clicking
  an edge opens its support summary.

T23a–c add source landing, the review queue, identity adjudication, the full
provenance panel, and entity search. P4 adds object views, cases and timeline to
this same app.

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
   ports 8000 (served bundle), 5173 (dev) and 4173 (preview). They are different
   origins to a browser, and `origin` is what the redirect URI is matched
   against.

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

`e2e/smoke.spec.ts` runs against the **built** bundle via `vite preview`, under
a copy of the production CSP, with Keycloak and the API stubbed at the network
boundary (`e2e/oidc-stub.ts`). `oidc-client-ts` runs its real PKCE state
machine — only the server's replies are fabricated — so the journey exercises
every line of ours: the redirect carries a real S256 challenge, the code is
redeemed, the bearer token reaches the API, and nothing lands in localStorage.

The full ingest → suggest → review → adjudicate → explore loop against a live
stack is T25/T27's blocking demo, not this job.
