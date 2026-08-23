import { expect, test } from "@playwright/test";

import { stubGeoRoutes } from "./map-stub";
import { stubGraphRoute, stubIdentityProvider } from "./oidc-stub";
import { ONTOLOGY_VERSION, stubCases, stubVocabulary } from "./workspace-stub";

/**
 * The map, in a browser (T60, charter exit №3).
 *
 * The criterion under test is "a location known only at admin-area level never
 * renders as a point **at any zoom**", and this is the half a unit test cannot
 * reach: that the rule survives the wiring — the source split, the layer
 * assignment, and the camera. `marks.spec.ts` proves the *coverage* over the
 * whole vocabulary; this proves it is actually what the map does.
 *
 * The other assertion here is about the network. The map contacts **nothing**:
 * no basemap tiles, no glyphs, no geocoder (M-19). That is checked by watching
 * requests rather than by reading the style, because the style is what a
 * reviewer sees and the requests are what a third party would.
 */

test.beforeEach(async ({ page }) => {
  await stubIdentityProvider(page);
  await stubGraphRoute(page);
  await stubVocabulary(page, { version: ONTOLOGY_VERSION });
  await stubCases(page);
  await stubGeoRoutes(page);
});

test("a country-level location never renders as a point, at any zoom", async ({ page }) => {
  await page.goto("/map");
  await expect(page.getByTestId("map-view")).toBeVisible();
  await expect(page.getByTestId("map-canvas")).toBeVisible();

  const country = page.getByTestId("map-feature-ent_country");
  const city = page.getByTestId("map-feature-ent_city");
  const building = page.getByTestId("map-feature-ent_building");

  for (const zoom of [3, 8, 14]) {
    await page.evaluate(async (z) => {
      // Zoom through the canvas rather than a test-only global: the point of
      // the criterion is that the mark does not change with the camera, and the
      // camera is the thing that has to actually move.
      const canvas = document.querySelector<HTMLElement>("[data-testid='map-canvas'] canvas");
      canvas?.dispatchEvent(new WheelEvent("wheel", { deltaY: z, bubbles: true }));
    }, zoom);

    await expect(country, `zoom ${zoom}: an administrative area drawn as a point`).toHaveAttribute(
      "data-mark",
      "area",
    );
    await expect(city, `zoom ${zoom}: a centroid drawn as a point`).toHaveAttribute(
      "data-mark",
      "circle",
    );
    // ...and the one thing that *should* be a pin still is, so the assertions
    // above are not passing because nothing is drawn at all.
    await expect(building).toHaveAttribute("data-mark", "point");
  }
});

test("a centroid is drawn as a circle of its stated radius", async ({ page }) => {
  await page.goto("/map");
  const city = page.getByTestId("map-feature-ent_city");
  await expect(city).toHaveAttribute("data-mark", "circle");
  await expect(city).toHaveAttribute("data-radius", "6000");
  await expect(city).toContainText("Within ~6.0 km");
});

test("a place whose geometry is withheld is listed, never placed", async ({ page }) => {
  await page.goto("/map");
  const undrawable = page.getByTestId("map-undrawable");
  await expect(undrawable).toContainText("A place you may not locate");
  // The reason distinguishes a clearance limit from a gap in the record — "not
  // shown" alone would leave a reader unable to tell them apart.
  await expect(undrawable).toContainText("above your clearance");
});

test("the map contacts no third party", async ({ page }) => {
  /*
   * "Third" is the operative word. The app's own origin and the identity
   * provider are first parties — `connect-src` names exactly those two and
   * nothing else. What must never appear is a *map* origin: a tile host, a
   * glyph server, a geocoder. Sending a viewport to one is telling it which
   * places an investigation is looking at (M-19, spec 10 §10).
   *
   * Watched as requests rather than read off the style, because the style is
   * what a reviewer sees and this is what a third party would.
   */
  const FIRST_PARTY = [/^http:\/\/127\.0\.0\.1:\d+$/, /^http:\/\/localhost:8180$/];
  const foreign: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (url.startsWith("data:") || url.startsWith("blob:")) return;
    const origin = new URL(url).origin;
    if (!FIRST_PARTY.some((pattern) => pattern.test(origin))) foreign.push(url);
  });

  await page.goto("/map");
  await expect(page.getByTestId("map-canvas")).toBeVisible();
  await page.waitForTimeout(500);

  expect(foreign, `the map fetched: ${foreign.join(", ")}`).toEqual([]);
});

test("the legend names every mark the map can draw", async ({ page }) => {
  await page.goto("/map");
  const legend = page.getByTestId("map-legend");
  for (const testId of [
    "legend-point",
    "legend-circle",
    "legend-area",
    "legend-coverage",
    "legend-estimate",
  ]) {
    await expect(legend.getByTestId(testId)).toBeVisible();
  }
});

test("the time filter lives in the URL, so a view can be sent to someone", async ({ page }) => {
  await page.goto("/map");
  await page.getByTestId("map-time-filter-from").fill("2019-01-01");
  await page.getByTestId("map-time-filter-to").fill("2019-12-31");
  await page.getByTestId("map-time-filter-apply").click();

  await expect(page).toHaveURL(/from=2019-01-01/);
  await expect(page).toHaveURL(/to=2019-12-31/);
});

test("the map shows what it was computed against", async ({ page }) => {
  await page.goto("/map");
  await expect(page.getByTestId("map-stamp")).toContainText("Ontology 2.1.0");
  await expect(page.getByTestId("map-stamp")).toContainText("identity revision 11");
});
