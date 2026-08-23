import { expect, test, type Page } from "@playwright/test";

import { stubGeoRoutes } from "./map-stub";
import { stubGraphRoute, stubIdentityProvider } from "./oidc-stub";
import { ONTOLOGY_VERSION, stubCases, stubVocabulary } from "./workspace-stub";

/**
 * One window and one selection across three surfaces (T62, spec 10 §11.2).
 *
 * The acceptance criteria are *"narrowing the time filter updates all three
 * consistently"* and *"nothing renders on one surface that the filter excludes
 * on another"*. Both follow from there being **one** window rather than three
 * kept in step — it lives in the URL, and all three surfaces read the same
 * `useSearchParams`.
 *
 * So what these tests check is that the sharing is real: that the window
 * survives moving between surfaces, that each surface actually *sends* it, and
 * that a selection made on one is the selection the others show. Three
 * components synchronizing state could pass a screenshot test and still drift
 * on whichever path someone forgot.
 */

/** Every query string each surface sent, so "did it apply the window" is answerable. */
async function recordRequests(page: Page): Promise<URL[]> {
  const seen: URL[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/v1/")) seen.push(url);
  });
  return seen;
}

async function stubTimeline(page: Page) {
  await page.route("**/v1/timeline*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [],
        next_cursor: null,
        undated_count: 3,
        stamp: { as_of: null, identity_revision_id: 11, ontology_version: ONTOLOGY_VERSION },
      }),
    }),
  );
}

test.beforeEach(async ({ page }) => {
  await stubIdentityProvider(page);
  await stubGraphRoute(page);
  await stubVocabulary(page, { version: ONTOLOGY_VERSION });
  await stubCases(page);
  await stubGeoRoutes(page);
  await stubTimeline(page);
});

test("a window narrowed on the map survives the walk to the timeline and graph", async ({
  page,
}) => {
  await page.goto("/map");
  await page.getByTestId("map-time-filter-from").fill("2019-01-01");
  await page.getByTestId("map-time-filter-to").fill("2019-12-31");
  await page.getByTestId("map-time-filter-apply").click();
  await expect(page).toHaveURL(/from=2019-01-01/);

  // The links between surfaces carry it, so moving is a click rather than a
  // re-narrowing — which is also what makes the criterion checkable by a person.
  await page.getByTestId("surface-link-timeline").click();
  await expect(page).toHaveURL(/\/timeline\?/);
  await expect(page).toHaveURL(/from=2019-01-01/);
  await expect(page.getByTestId("timeline-filter-from")).toHaveValue("2019-01-01");

  await page.getByTestId("surface-link-graph").click();
  await expect(page).toHaveURL(/\/graph\?/);
  await expect(page.getByTestId("graph-time-filter-from")).toHaveValue("2019-01-01");
});

test("every surface actually sends the window it is showing", async ({ page }) => {
  const seen = await recordRequests(page);

  await page.goto("/map?from=2019-01-01T00:00:00.000Z&to=2019-12-31T00:00:00.000Z");
  await expect(page.getByTestId("map-canvas")).toBeVisible();

  const events = seen.find((url) => url.pathname === "/v1/geo/events");
  expect(events?.searchParams.get("from")).toBe("2019-01-01T00:00:00.000Z");
  expect(events?.searchParams.get("to")).toBe("2019-12-31T00:00:00.000Z");

  await page.getByTestId("surface-link-timeline").click();
  await expect(page.getByTestId("timeline-view")).toBeVisible();
  const timeline = seen.find((url) => url.pathname === "/v1/timeline");
  expect(timeline?.searchParams.get("from")).toBe("2019-01-01T00:00:00.000Z");
  expect(timeline?.searchParams.get("to")).toBe("2019-12-31T00:00:00.000Z");
});

test("the graph sends the event-time window, not the validity one", async ({ page }) => {
  /*
   * The distinction T62 had to preserve. "Was a member during 2019" and "an
   * arrest happened in 2019" are different questions; the graph keeps
   * `valid_from`/`valid_to` for the first and takes `event_from`/`event_to` for
   * the second. One parameter answering both would mean different things on
   * different surfaces, which is the inconsistency this task exists to remove.
   */
  const bodies: Record<string, unknown>[] = [];
  await page.route("**/v1/graph/expand", async (route) => {
    bodies.push(route.request().postDataJSON());
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ nodes: [], edges: [], truncated: false, stamps: null }),
    });
  });

  await page.goto("/graph?from=2019-01-01T00:00:00.000Z&to=2019-12-31T00:00:00.000Z");
  await expect(page.getByTestId("graph-time-filter-from")).toHaveValue("2019-01-01");

  const body = bodies.at(-1) as Record<string, unknown> | undefined;
  expect(body?.event_from).toBe("2019-01-01T00:00:00.000Z");
  expect(body?.event_to).toBe("2019-12-31T00:00:00.000Z");
  expect(body?.valid_from).toBeUndefined();
  expect(body?.valid_to).toBeUndefined();
});

test("a selection made on the map is the selection the timeline shows", async ({ page }) => {
  await page.goto("/map?selected=ent_city");
  await expect(page.getByTestId("map-detail")).toContainText("Fictional City");

  await page.getByTestId("surface-link-timeline").click();
  await expect(page).toHaveURL(/selected=ent_city/);
  await expect(page.getByTestId("timeline-selection")).toBeVisible();
});

test("clearing the selection clears it everywhere, because there is only one", async ({
  page,
}) => {
  await page.goto("/timeline?selected=ent_city");
  await expect(page.getByTestId("timeline-selection")).toBeVisible();

  await page.getByTestId("timeline-clear-selection").click();
  await expect(page).not.toHaveURL(/selected=/);
  await expect(page.getByTestId("timeline-selection")).toHaveCount(0);

  await page.getByTestId("surface-link-map").click();
  await expect(page.getByTestId("map-detail")).toHaveCount(0);
});

test("as-of composes with the window and reaches all three", async ({ page }) => {
  const seen = await recordRequests(page);
  const bodies: Record<string, unknown>[] = [];
  await page.route("**/v1/graph/expand", async (route) => {
    bodies.push(route.request().postDataJSON());
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ nodes: [], edges: [], truncated: false, stamps: null }),
    });
  });

  const url = "?from=2019-01-01T00:00:00.000Z&asOf=2020-06-01T00:00:00.000Z";
  await page.goto(`/map${url}`);
  await expect(page.getByTestId("map-canvas")).toBeVisible();
  expect(
    seen.find((u) => u.pathname === "/v1/geo/locations")?.searchParams.get("asOf"),
  ).toBe("2020-06-01T00:00:00.000Z");

  await page.getByTestId("surface-link-graph").click();
  await expect(page.getByTestId("graph-time-filter-from")).toHaveValue("2019-01-01");
  // The graph half of Phase 4's `?asOf=` carryover: a time-synced map beside a
  // graph that silently answered as-of-now would be exactly the inconsistency
  // this phase set out to remove.
  expect((bodies.at(-1) as Record<string, unknown>)?.as_of).toBe("2020-06-01T00:00:00.000Z");
});

test("clearing the window returns all three to all time", async ({ page }) => {
  await page.goto("/timeline?from=2019-01-01T00:00:00.000Z&to=2019-12-31T00:00:00.000Z");
  await page.getByTestId("timeline-filter-clear").click();
  await expect(page).not.toHaveURL(/from=/);
  await expect(page).not.toHaveURL(/to=/);

  await page.getByTestId("surface-link-map").click();
  await expect(page.getByTestId("map-time-filter-from")).toHaveValue("");
});
