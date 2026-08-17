import { expect, test } from "@playwright/test";

import { stubGraphRoute, stubIdentityProvider } from "./oidc-stub";
import { ONTOLOGY_VERSION, stubVocabulary } from "./workspace-stub";

/**
 * T42's acceptance criteria as browser journeys.
 *
 * The claim under test is narrow and load-bearing: **the rail and both
 * descriptor screens are generated, not written**. Nothing here stubs an
 * ontology endpoint for them, because they call none — every label, property,
 * sensitivity and category comes from `src/api/ontology.ts`, which
 * `aegis ontology generate` writes and CI checks for drift. A test that stubbed
 * those values would be testing the stub.
 *
 * The router is the other half. P2 routed on the History API and deferred a
 * router to P4 for one specific reason: the OIDC callback rewrote the URL
 * behind the app's back. So the sign-in round trip is re-tested here, deep link
 * included, which is the risk `src/routing.ts` named.
 */

test.beforeEach(async ({ page }) => {
  await stubIdentityProvider(page);
  await stubGraphRoute(page);
});

test("the rail lists every declared object type and interface", async ({ page }) => {
  await stubVocabulary(page, { version: ONTOLOGY_VERSION });
  await page.goto("/");

  await expect(page.getByTestId("username")).toBeVisible();

  // Read straight from the generated module — the same source the rail reads,
  // so adding a type to a domain module extends both without touching this file.
  const { OBJECT_TYPES, INTERFACES } = await import("../src/api/ontology");

  const types = page.getByTestId("nav-object-types");
  for (const spec of Object.values(OBJECT_TYPES)) {
    await expect(types.getByRole("link", { name: spec.label, exact: true })).toBeVisible();
  }
  const interfaces = page.getByTestId("nav-interfaces");
  for (const spec of Object.values(INTERFACES)) {
    await expect(
      interfaces.getByRole("link", { name: spec.label, exact: true }),
    ).toBeVisible();
  }
});

test("an object type page renders its properties, governance and links", async ({
  page,
}) => {
  await stubVocabulary(page, { version: ONTOLOGY_VERSION });
  await page.goto("/types/person");

  await expect(page.getByTestId("object-type-label")).toHaveText("Person");

  const properties = page.getByTestId("object-type-properties");
  // A declared label beats the humanized default (proposal 005) — "Nic" would
  // be what this said without it.
  await expect(properties).toContainText("NIC");
  await expect(properties).not.toContainText("Nic ");
  // Humanized where nothing is declared.
  await expect(properties).toContainText("Date of birth");
  // Governance is rendered, not hidden: the clearance a field needs is a fact
  // about the schema and answers "why can I not see this" before anyone looks
  // for the row.
  await expect(properties).toContainText("restricted");
  // Article VIII in the schema: two dates of birth may both stand.
  await expect(properties).toContainText("conflicts preserved");

  // `display` says which properties T44 will draw an entity's heading from.
  await expect(page.getByTestId("object-type-display")).toContainText("Name");
  await expect(page.getByTestId("object-type-display")).toContainText("Aliases");

  // Interfaces are links, so the ontology can be read from either side.
  await page.getByTestId("object-type-implements").getByRole("link", { name: "Party" }).click();
  await expect(page.getByTestId("interface-label")).toHaveText("Party");
  await expect(page.getByTestId("interface-implementors")).toContainText("Person");
});

test("an interface page shows what was declared against it, not the expansion", async ({
  page,
}) => {
  await stubVocabulary(page, { version: ONTOLOGY_VERSION });
  await page.goto("/interfaces/party");

  await expect(page.getByTestId("interface-label")).toHaveText("Party");
  // `controls` was declared `subject: [party]` and expands to concrete types in
  // the store (spec 08 §4). The interface page is where the declaration shows.
  await expect(page.getByTestId("interface-predicates")).toContainText("Controls");
});

test("an unknown type is said to be unknown, not rendered blank", async ({ page }) => {
  await stubVocabulary(page, { version: ONTOLOGY_VERSION });
  await page.goto("/types/not-a-declared-type");
  await expect(page.getByTestId("object-type-unknown")).toBeVisible();
});

test("a deep link survives the sign-in round trip", async ({ page }) => {
  await stubVocabulary(page, { version: ONTOLOGY_VERSION });

  // Straight to a parameterized route while signed out: the guard redirects,
  // the stub IdP approves, and the callback must land back here rather than on
  // the default view. This is the regression P2 deferred the router to avoid.
  await page.goto("/types/organization");

  await expect(page.getByTestId("object-type-label")).toHaveText("Organization");
  expect(new URL(page.url()).pathname).toBe("/types/organization");
  // The authorization code must not survive in the address bar.
  expect(new URL(page.url()).search).toBe("");
});

test("the back button returns to the previous view, not to the callback", async ({
  page,
}) => {
  await stubVocabulary(page, { version: ONTOLOGY_VERSION });
  await page.goto("/types/person");
  await expect(page.getByTestId("object-type-label")).toHaveText("Person");

  await page.getByTestId("nav-object-types").getByRole("link", { name: "Vehicle" }).click();
  await expect(page.getByTestId("object-type-label")).toHaveText("Vehicle");

  await page.goBack();
  await expect(page.getByTestId("object-type-label")).toHaveText("Person");
  // `replace: true` on the callback is what keeps a spent `/auth/callback` out
  // of history; walking back must never reach it.
  expect(new URL(page.url()).pathname).toBe("/types/person");
});

test("a server on a different ontology version raises the banner", async ({ page }) => {
  await stubVocabulary(page, { version: "99.0.0" });
  await page.goto("/types/person");

  const banner = page.getByTestId("ontology-mismatch");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText(ONTOLOGY_VERSION);
  await expect(banner).toContainText("99.0.0");
  // Non-blocking: the page still renders, because the server is authoritative
  // for the data and only the captions may be stale (spec 09 §6.3).
  await expect(page.getByTestId("object-type-label")).toHaveText("Person");
});

test("no banner when the versions agree", async ({ page }) => {
  await stubVocabulary(page, { version: ONTOLOGY_VERSION });
  await page.goto("/types/person");

  await expect(page.getByTestId("object-type-label")).toHaveText("Person");
  await expect(page.getByTestId("ontology-mismatch")).toHaveCount(0);
});

test("the descriptor screens call no endpoint of their own", async ({ page }) => {
  await stubVocabulary(page, { version: ONTOLOGY_VERSION });

  const apiCalls: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/v1/")) apiCalls.push(url.pathname);
  });

  await page.goto("/types/person");
  await expect(page.getByTestId("object-type-label")).toHaveText("Person");
  await page.getByTestId("nav-interfaces").getByRole("link", { name: "Party" }).click();
  await expect(page.getByTestId("interface-label")).toHaveText("Party");

  // The version check is the only permitted call: everything these screens
  // render is compiled in (ADR-043).
  expect([...new Set(apiCalls)]).toEqual(["/v1/ontology/vocabulary"]);
});
