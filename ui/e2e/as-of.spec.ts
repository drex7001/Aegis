import { expect, test } from "@playwright/test";

import { stubGraphRoute, stubIdentityProvider } from "./oidc-stub";
import { stubEntityRoutes } from "./object-view-stub";
import { ONTOLOGY_VERSION, stubCases, stubVocabulary } from "./workspace-stub";

/**
 * As-of in the workspace (T49, B-11).
 *
 * The banner is the whole point of these journeys. A snapshot the reader has
 * forgotten they are in is worse than no snapshot — every value on the screen
 * is historical and nothing else says so — which is why it is persistent, not
 * dismissible, and states the **limits** as well as the promise. B-11 was a
 * finding about an overstated promise; a banner reading only "showing 1 March"
 * would repeat it.
 */

test.beforeEach(async ({ page }) => {
  await stubIdentityProvider(page);
  await stubGraphRoute(page);
  await stubVocabulary(page, { version: ONTOLOGY_VERSION });
  await stubCases(page);
  await stubEntityRoutes(page);
});

test("a current view carries its stamp but no banner", async ({ page }) => {
  await page.goto("/entities/ent_person");

  await expect(page.getByTestId("as-of-banner")).toHaveCount(0);
  // Quiet, but present: knowing which identity produced an answer is what lets
  // two answers taken at different times be compared.
  await expect(page.getByTestId("stamp-line")).toContainText("Identity revision");
  await expect(page.getByTestId("stamp-line")).toContainText("7");
});

test("asking a historical question raises the banner and narrows the claims", async ({
  page,
}) => {
  await page.goto("/entities/ent_person");
  await expect(page.getByTestId("object-view-title")).toBeVisible();

  await page.getByTestId("as-of-date").fill("2026-03-01");
  await page.getByTestId("as-of-apply").click();

  const banner = page.getByTestId("as-of-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("2026-03-01");
  // The claim recorded after the snapshot is gone from the page.
  await expect(page.getByTestId("predicate-born_on")).toHaveCount(0);
  await expect(page.getByTestId("predicate-known_as")).toBeVisible();
});

test("the banner states the limits, not only the date", async ({ page }) => {
  await page.goto("/entities/ent_person?asOf=2026-03-01T00:00:00.000Z");

  const banner = page.getByTestId("as-of-banner");
  await expect(banner).toContainText("recorded and not retracted");
  await expect(banner).toContainText("identity revision");
  // The narrowing, in the reader's line of sight: as-of restores which claims
  // existed and nothing else.
  await expect(banner).toContainText("Labels, source evaluations, grading, policy");
  await expect(banner).toContainText("are current, not historical");
});

test("the banner cannot be dismissed", async ({ page }) => {
  await page.goto("/entities/ent_person?asOf=2026-03-01T00:00:00.000Z");

  const banner = page.getByTestId("as-of-banner");
  await expect(banner).toBeVisible();
  // No close control anywhere inside it: a dismissal would put the reader one
  // click from a historical page that looks current, irreversibly for the
  // session.
  await expect(banner.getByRole("button")).toHaveCount(0);
  await expect(banner.locator("[aria-label='Close']")).toHaveCount(0);
});

test("the pinned revision travels and is echoed back", async ({ page }) => {
  await page.goto("/entities/ent_person");
  await expect(page.getByTestId("object-view-title")).toBeVisible();

  await page.getByTestId("as-of-date").fill("2026-03-01");
  await page.getByTestId("as-of-revision").fill("3");
  await page.getByTestId("as-of-apply").click();

  await expect(page.getByTestId("as-of-banner")).toContainText("3");
  // The request carried it, rather than the page assuming it.
  expect(new URL(page.url()).searchParams.get("asOfRevision")).toBe("3");
});

test("a historical view is a URL, so it survives a reload and can be shared", async ({
  page,
}) => {
  await page.goto("/entities/ent_person?asOf=2026-03-01T00:00:00.000Z&asOfRevision=3");
  await expect(page.getByTestId("as-of-banner")).toBeVisible();

  await page.reload();
  // A snapshot that vanished on reload would be a different answer at the same
  // address.
  await expect(page.getByTestId("as-of-banner")).toBeVisible();
  await expect(page.getByTestId("as-of-banner")).toContainText("2026-03-01");
});

test("returning to now clears the banner", async ({ page }) => {
  await page.goto("/entities/ent_person?asOf=2026-03-01T00:00:00.000Z");
  await expect(page.getByTestId("as-of-banner")).toBeVisible();

  await page.getByTestId("as-of-clear").click();
  await expect(page.getByTestId("as-of-banner")).toHaveCount(0);
  await expect(page.getByTestId("stamp-line")).toBeVisible();
});

test("the as-of request carries the parameters the server documents", async ({ page }) => {
  const urls: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/v1/entities/ent_person") urls.push(url.search);
  });

  await page.goto("/entities/ent_person?asOf=2026-03-01T00:00:00.000Z&asOfRevision=3");
  await expect(page.getByTestId("as-of-banner")).toBeVisible();

  const sent = urls.find((search) => search.includes("asOf"));
  expect(sent).toBeTruthy();
  expect(new URLSearchParams(sent!).get("asOf")).toBe("2026-03-01T00:00:00.000Z");
  expect(new URLSearchParams(sent!).get("asOfRevision")).toBe("3");
});
