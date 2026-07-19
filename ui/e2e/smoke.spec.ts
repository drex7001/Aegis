import { expect, test } from "@playwright/test";

import {
  AUTHORITY,
  CLIENT_ID,
  stubGraphRoute,
  stubIdentityProvider,
  USERNAME,
} from "./oidc-stub";

/**
 * The T22 acceptance criteria, as a browser journey:
 *
 *   unauthenticated visit → login redirect → authenticated shell → graph
 *   renders from a governed route
 *
 * plus the two properties ADR-032 §1 is specific about and which no unit test
 * can observe: the redirect really carries PKCE, and no token reaches web
 * storage.
 */

test("an unauthenticated visit leaves for the identity provider with PKCE", async ({
  page,
}) => {
  const idp = await stubIdentityProvider(page, { autoApprove: false });

  await page.goto("/");
  await expect
    .poll(() => idp.authorizeUrl()?.toString() ?? null, { timeout: 15_000 })
    .not.toBeNull();

  const url = idp.authorizeUrl()!;
  expect(url.origin + url.pathname).toBe(`${AUTHORITY}/protocol/openid-connect/auth`);
  expect(url.searchParams.get("client_id")).toBe(CLIENT_ID);
  expect(url.searchParams.get("response_type")).toBe("code");
  // The point of PKCE: the challenge travels, the verifier does not.
  expect(url.searchParams.get("code_challenge_method")).toBe("S256");
  expect(url.searchParams.get("code_challenge")).toBeTruthy();
});

test("a signed-in analyst reaches the shell and the graph draws", async ({ page }) => {
  await stubIdentityProvider(page);
  await stubGraphRoute(page);

  await page.goto("/");

  await expect(page.getByTestId("username")).toHaveText(USERNAME);
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  // Article IX in the smallest possible form: the provenance of the picture is
  // on the picture. A canvas with no build stamp is a claim with no source.
  await expect(page.getByTestId("stamps")).toContainText("identity revision 7");

  // Cytoscape renders into <canvas> children, so "it drew" cannot be asserted
  // from the DOM tree — only that the canvas layers exist.
  const layers = await page.evaluate(
    () =>
      document.querySelector("[data-testid='graph-canvas']")?.querySelectorAll("canvas")
        .length ?? 0,
  );
  expect(layers).toBeGreaterThan(0);

  // The authorization code must not survive in the address bar.
  expect(new URL(page.url()).search).toBe("");
});

test("the graph call carries the bearer token", async ({ page }) => {
  await stubIdentityProvider(page);
  const graph = await stubGraphRoute(page);

  await page.goto("/");
  await expect(page.getByTestId("graph-canvas")).toBeVisible();

  expect(graph.bearerTokens().length).toBeGreaterThan(0);
  expect(graph.bearerTokens()[0]).toMatch(/^Bearer \S+\.\S+\.\S+$/);
});

test("no token is written to web storage", async ({ page }) => {
  await stubIdentityProvider(page);
  await stubGraphRoute(page);

  await page.goto("/");
  await expect(page.getByTestId("graph-canvas")).toBeVisible();

  const stored = await page.evaluate(() => ({
    local: Object.entries({ ...window.localStorage }),
    session: JSON.stringify({ ...window.sessionStorage }),
  }));

  // localStorage must be untouched — that is the ADR-032 requirement.
  expect(stored.local).toEqual([]);
  // sessionStorage may hold the redirect state (PKCE verifier + nonce), which
  // has to survive a full-page redirect and is worthless once redeemed. It must
  // never hold a token.
  expect(stored.session).not.toContain("access_token");
  expect(stored.session).not.toContain("refresh_token");
  expect(stored.session).not.toContain("id_token");
});

test("an API failure is surfaced, not swallowed", async ({ page }) => {
  await stubIdentityProvider(page);
  await stubGraphRoute(page, {
    status: 403,
    contentType: "application/problem+json",
    body: {
      type: "about:blank",
      title: "Forbidden",
      status: 403,
      detail: "role not permitted for this operation",
    },
  });

  await page.goto("/");

  await expect(page.getByTestId("graph-error")).toContainText(
    "role not permitted for this operation",
  );
});
