import { expect, test } from "@playwright/test";

import { stubGraphRoute, stubIdentityProvider } from "./oidc-stub";
import { PERSON, stubEntityRoutes } from "./object-view-stub";
import { ONTOLOGY_VERSION, stubVocabulary } from "./workspace-stub";

/**
 * T45: every value and every link opens its evidence, and the timeline says
 * what it does not know.
 *
 * Two questions, two P2 routes consumed **as-is** — a value asks "where did
 * this come from" (`/v1/claims/{id}/provenance`), a link asks "why are these
 * two connected" (`/v1/entities/{a}/why-connected/{b}`). The request sweep at
 * the end is the load-bearing assertion: T45 adds no endpoint.
 */

const CLAIM_PROVENANCE = PERSON.claims_by_predicate.born_on[0];

const WHY_CONNECTED = {
  claims: PERSON.claims_by_predicate.member_of,
  record_count: 1,
  corroboration_count: 0,
  contradiction_count: 0,
  truncated: false,
  resolved_subject_id: "ent_person",
  resolved_object_id: "ent_org",
  identity_line: [
    {
      decision_id: "dec_1",
      kind: "confirm_match",
      decided_by: "analyst-1",
      result_revision_id: 4,
      decision_note: "Same person; the registry filing matches.",
      entity_id: "ent_person",
    },
  ],
};

test.beforeEach(async ({ page }) => {
  await stubIdentityProvider(page);
  await stubGraphRoute(page);
  await stubVocabulary(page, { version: ONTOLOGY_VERSION });
  await stubEntityRoutes(page);
  await page.route("**/v1/claims/*/provenance", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(CLAIM_PROVENANCE) }),
  );
  await page.route("**/v1/entities/*/why-connected/*", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(WHY_CONNECTED) }),
  );
});

test("a value opens its own evidence", async ({ page }) => {
  await page.goto("/entities/ent_person");
  await page.getByTestId("drill-clm_dob_a").click();

  const drawer = page.getByTestId("provenance-drawer");
  await expect(drawer).toBeVisible();
  // Parity with the P2 panel: all three grading dimensions and the source.
  await expect(drawer.getByTestId("grading")).toContainText("generally_reliable");
  await expect(drawer.getByTestId("grading")).toContainText("probably_true");
  await expect(drawer.getByTestId("grading")).toContainText("unverified");
  await expect(drawer).toContainText("Fictional Gazette");
});

test("a link opens why-connected, with the identity decisions behind it", async ({
  page,
}) => {
  await page.goto("/entities/ent_person");
  await page.getByTestId("drill-clm_member").click();

  const drawer = page.getByTestId("provenance-drawer");
  await expect(drawer).toBeVisible();
  await expect(drawer).toContainText("Why connected");
  await expect(drawer.getByTestId("drawer-tally")).toContainText("1 source record");
  // The step most worth auditing: an edge exists only because a human merged
  // two mentions, and evidence without that decision hides it.
  await expect(drawer.getByTestId("drawer-identity-line")).toContainText("analyst-1");
  await expect(drawer.getByTestId("drawer-identity-line")).toContainText("confirm_match");
});

test("the drawer closes and leaves the page as it was", async ({ page }) => {
  await page.goto("/entities/ent_person");
  await page.getByTestId("drill-clm_dob_a").click();
  await expect(page.getByTestId("provenance-drawer")).toBeVisible();

  await page.getByTestId("provenance-drawer").getByRole("button", { name: "Close" }).click();
  await expect(page.getByTestId("provenance-drawer")).toHaveCount(0);
  await expect(page.getByTestId("object-view-title")).toHaveText("Fictional A");
});

test("an interval and an instant render differently", async ({ page }) => {
  await page.goto("/entities/ent_person");

  const strip = page.getByTestId("timeline-strip");
  await expect(strip).toBeVisible();
  // A stated date is an instant...
  await expect(page.getByTestId("timeline-clm_dob_a")).toHaveAttribute("data-exact", "true");
  // ...and "some time in 1981" is a range that must not be drawn as a point.
  await expect(page.getByTestId("timeline-clm_dob_b")).toHaveAttribute("data-exact", "false");
  await expect(strip).toContainText("1981-01-01 → 1981-12-31");
});

test("a claim with no stated time is said to have none, not placed at its recording", async ({
  page,
}) => {
  await page.goto("/entities/ent_person");

  const untimed = page.getByTestId("timeline-untimed");
  await expect(untimed).toBeVisible();
  await expect(untimed).toContainText("state");
  await expect(untimed).toContainText("not when it happened");
  // `known_as` and `member_of` state no world time, so neither may appear on
  // the axis at `recorded_at` — that would turn a fact about us into a fact
  // about the world.
  await expect(page.getByTestId("timeline-clm_name")).toHaveCount(0);
  await expect(page.getByTestId("timeline-clm_member")).toHaveCount(0);
  await expect(page.getByTestId("timeline-strip")).not.toContainText("2026-01-01");
});

test("the drill-downs add no endpoint the P2 screens did not already have", async ({
  page,
}) => {
  const calls: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/v1/")) calls.push(url.pathname);
  });

  await page.goto("/entities/ent_person");
  await page.getByTestId("drill-clm_dob_a").click();
  await expect(page.getByTestId("provenance-drawer")).toBeVisible();
  await page.getByTestId("provenance-drawer").getByRole("button", { name: "Close" }).click();
  await page.getByTestId("drill-clm_member").click();
  await expect(page.getByTestId("drawer-identity-line")).toBeVisible();

  expect([...new Set(calls)].sort()).toEqual([
    "/v1/claims/clm_dob_a/provenance",
    "/v1/entities/ent_person",
    "/v1/entities/ent_person/cases",
    "/v1/entities/ent_person/why-connected/ent_org",
    "/v1/ontology/vocabulary",
  ]);
});
