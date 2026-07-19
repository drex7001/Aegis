import {
  InMemoryWebStorage,
  UserManager,
  WebStorageStateStore,
} from "oidc-client-ts";
import type { AuthProviderProps } from "react-oidc-context";

/**
 * Keycloak OIDC with PKCE, via the maintained library rather than a hand-rolled
 * state machine (Article XII, ADR-032 §1).
 *
 * **Where the secrets live is the whole design.** ADR-032 says tokens in
 * memory, never localStorage, and that splits into two stores that are easy to
 * conflate:
 *
 * - `userStore` holds the access, id and refresh tokens. In memory: it dies
 *   with the tab, so an XSS that runs later finds nothing, and a shared machine
 *   leaks nothing between sessions.
 * - `stateStore` holds the PKCE code verifier and nonce *for the duration of
 *   one redirect*. It cannot be in memory — the browser leaves the page
 *   entirely and comes back — so it is sessionStorage: tab-scoped, cleared on
 *   close, and holding a single-use value that is worthless once redeemed.
 *
 * The cost is that a page reload has no user and must bounce through Keycloak
 * again. That round trip is invisible when the SSO session cookie is live, and
 * the alternative — persisting tokens to web storage so a reload can skip it —
 * is exactly what the ADR forbids.
 *
 * Renewal uses the refresh token rather than a hidden iframe, which is why the
 * CSP can say `frame-src 'none'` (aegis/api/security.py).
 *
 * The `UserManager` is constructed here rather than left to `AuthProvider` so
 * that the API client can ask it for the current token at request time. Passing
 * the token down through React instead would make it arrive one effect too
 * late: child effects run before parent effects, so the first query fires
 * before a parent could publish the token, and the request goes out
 * unauthenticated. That is not a hypothetical — the smoke journey caught it.
 */

const authority =
  import.meta.env.VITE_OIDC_AUTHORITY ?? "http://localhost:8180/realms/aegis";
const clientId = import.meta.env.VITE_OIDC_CLIENT_ID ?? "aegis-ui";

export const userManager = new UserManager({
  authority,
  client_id: clientId,
  redirect_uri: `${window.location.origin}/auth/callback`,
  post_logout_redirect_uri: window.location.origin,
  response_type: "code",
  /**
   * `openid` alone, deliberately. The realm defines exactly one client scope
   * (`aegis`) and that list replaces Keycloak's built-ins, so `profile` and
   * `email` do not exist there and asking for them fails the whole authorize
   * request with `invalid_scope`. Everything this app reads — `preferred_
   * username`, `realm_access.roles`, `clearance`, and the `aegis-api` audience
   * — is minted by the `aegis` scope's mappers (infra/keycloak/aegis-realm.json).
   */
  scope: "openid",

  userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
  stateStore: new WebStorageStateStore({ store: window.sessionStorage }),

  automaticSilentRenew: true,
  monitorSession: false,
});

export const oidcConfig: AuthProviderProps = {
  userManager,
  /**
   * Return to wherever the user actually was, and strip the callback from
   * history on the way.
   *
   * Two reasons, not one. The `code`/`state` query must go so a reload cannot
   * replay a spent authorization code and so a code never sits in the address
   * bar to be shoulder-read, bookmarked, or pasted into a bug report. And
   * `/auth/callback` is not a destination — leaving the user parked on it means
   * every sign-in ends on a URL that renders only by accident.
   */
  onSigninCallback: (user) => {
    const state = user?.state as { returnTo?: string } | undefined;
    const target = state?.returnTo ?? "/";
    window.history.replaceState({}, document.title, target);
  },
};

export const oidcAuthority = authority;
