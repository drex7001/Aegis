import type { Page } from "@playwright/test";

/**
 * A stand-in for Keycloak, so the smoke journey can be hermetic.
 *
 * What it stubs is the *network*, not the app: `oidc-client-ts` runs its real
 * PKCE state machine — it generates the verifier, stores it, sends the
 * challenge, redeems the code, validates the id_token's issuer, audience,
 * subject and nonce. Only the server's replies are fabricated. That is the line
 * worth holding: a stub of our own auth layer would prove nothing, while a stub
 * of the identity provider still exercises every line of ours.
 *
 * `oidc-client-ts` does not verify id_token signatures (it relies on the token
 * endpoint being reached over TLS), so an unsigned token is accepted here
 * exactly as the library would accept a real one.
 */

export const AUTHORITY = "http://localhost:8180/realms/aegis";
export const CLIENT_ID = "aegis-ui";
export const SUBJECT = "0d3f4d3a-fictional-subject";
export const USERNAME = "dev-analyst";

function base64url(value: string): string {
  return btoa(value).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function unsignedJwt(claims: Record<string, unknown>): string {
  const header = base64url(JSON.stringify({ alg: "RS256", typ: "JWT", kid: "stub" }));
  return `${header}.${base64url(JSON.stringify(claims))}.stub-signature`;
}

export interface StubHandle {
  /** The authorize URL the app navigated to, once it has. */
  authorizeUrl(): URL | null;
}

/**
 * Install the stub. `autoApprove` decides whether the authorize request comes
 * back as a redirect carrying a code (a live SSO session) or is simply
 * recorded (so a test can assert the redirect itself and stop there).
 */
export async function stubIdentityProvider(
  page: Page,
  { autoApprove = true }: { autoApprove?: boolean } = {},
): Promise<StubHandle> {
  let authorize: URL | null = null;
  let nonce: string | null = null;

  await page.route(`${AUTHORITY}/.well-known/openid-configuration`, (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        issuer: AUTHORITY,
        authorization_endpoint: `${AUTHORITY}/protocol/openid-connect/auth`,
        token_endpoint: `${AUTHORITY}/protocol/openid-connect/token`,
        end_session_endpoint: `${AUTHORITY}/protocol/openid-connect/logout`,
        jwks_uri: `${AUTHORITY}/protocol/openid-connect/certs`,
        response_types_supported: ["code"],
        subject_types_supported: ["public"],
        id_token_signing_alg_values_supported: ["RS256"],
        code_challenge_methods_supported: ["S256"],
      }),
    }),
  );

  await page.route(`${AUTHORITY}/protocol/openid-connect/auth*`, async (route) => {
    authorize = new URL(route.request().url());
    nonce = authorize.searchParams.get("nonce");
    if (!autoApprove) {
      return route.fulfill({ status: 200, contentType: "text/html", body: "<h1>IdP</h1>" });
    }
    const state = authorize.searchParams.get("state") ?? "";
    const redirect = authorize.searchParams.get("redirect_uri") ?? "";
    await route.fulfill({
      status: 302,
      headers: { location: `${redirect}?code=fictional-code&state=${state}` },
    });
  });

  await page.route(`${AUTHORITY}/protocol/openid-connect/token`, async (route) => {
    const now = Math.floor(Date.now() / 1000);
    const common = {
      iss: AUTHORITY,
      aud: "aegis-api",
      azp: CLIENT_ID,
      sub: SUBJECT,
      iat: now,
      exp: now + 300,
      preferred_username: USERNAME,
      realm_access: { roles: ["analyst"] },
      clearance: 2,
    };
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        access_token: unsignedJwt(common),
        id_token: unsignedJwt({ ...common, aud: CLIENT_ID, nonce }),
        refresh_token: "fictional-refresh-token",
        token_type: "Bearer",
        expires_in: 300,
        scope: "openid profile email",
      }),
    });
  });

  return { authorizeUrl: () => authorize };
}

export interface GraphStub {
  /** `Authorization` headers the app attached, in call order. */
  bearerTokens(): string[];
}

/**
 * Stand in for `POST /v1/graph/expand`.
 *
 * The token is read here rather than from a `page.on("request")` listener
 * because `request.headers()` is the synchronous, best-effort view and omits
 * headers the browser has not finished attributing; `allHeaders()` is the
 * complete one, and "did the bearer token actually go out" is precisely the
 * assertion that must not be answered from a partial view.
 */
export async function stubGraphRoute(
  page: Page,
  response: { status?: number; contentType?: string; body: unknown } = {
    body: GRAPH_FIXTURE,
  },
): Promise<GraphStub> {
  const bearers: string[] = [];
  await page.route("**/v1/graph/expand", async (route) => {
    const headers = await route.request().allHeaders();
    if (headers["authorization"]) bearers.push(headers["authorization"]);
    await route.fulfill({
      status: response.status ?? 200,
      contentType: response.contentType ?? "application/json",
      body: JSON.stringify(response.body),
    });
  });
  return { bearerTokens: () => bearers };
}

/** A two-node, one-edge graph in the exact shape `/v1/graph/expand` returns. */
export const GRAPH_FIXTURE = {
  nodes: [
    { entity_id: "ent_fictional_a", label: "Fictional A", entity_type: "person" },
    { entity_id: "ent_fictional_b", label: "Fictional B", entity_type: "person" },
  ],
  edges: [
    {
      edge_id: "edg_fictional_1",
      subject_id: "ent_fictional_a",
      object_id: "ent_fictional_b",
      predicate: "allied_with",
      category: "association",
      segment_from: "2019-01-01",
      segment_to: null,
      record_count: 1,
      support: {
        method: "segmented-support",
        method_version: 1,
        claims: [
          {
            claim_id: "clm_fictional_1",
            record_id: "rec_fictional_1",
            reliability: "generally_reliable",
            credibility: "probably_true",
            verification: "unverified",
            analytic_confidence: null,
            assertion_type: "reported",
            handling_code: "open",
            corroborated_by: 0,
            contradicted_by: 0,
          },
        ],
        corroboration_count: 0,
        contradiction_count: 0,
        record_count: 1,
      },
    },
  ],
  seed_ids: [],
  resolved_seed_ids: [],
  truncated: false,
  stamps: {
    built_at_revision_id: 7,
    active_revision_id: 7,
    ontology_version: "1.2.0",
    builder_version: "edge-projection-v2",
    stale: false,
  },
};
