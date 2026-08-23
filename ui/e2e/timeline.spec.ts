import { expect, test, type Page } from "@playwright/test";

import { stubGraphRoute, stubIdentityProvider } from "./oidc-stub";
import { ONTOLOGY_VERSION, stubCases, stubVocabulary } from "./workspace-stub";

/**
 * The timeline, in a browser (T61, spec 10 §11).
 *
 * The assertion that matters is that **certainty is in the shape**, not only in
 * a tooltip. A reader scanning the axis has to be able to tell a stated instant
 * from a stated range without hovering, or the honesty is only available to
 * someone who already suspected there was something to check.
 *
 * The second is that an undated claim is *said out loud*. A narrowed window
 * that silently dropped it would look like a complete account of everything
 * known, which is the failure §11.2 exists against.
 */

const ITEMS = [
  {
    claim_id: "clm_exact",
    subject_id: "ent_event",
    subject_label: "An arrest",
    subject_type: "arrest",
    predicate: "summarized_as",
    object_id: null,
    object_label: null,
    object_value: "Three men arrested",
    earliest: "2019-03-12T00:00:00Z",
    latest: "2019-03-12T00:00:00Z",
    certainty: "exact",
    record_id: "rec_1",
    handling_code: "open",
    recorded_at: "2026-01-01T00:00:00Z",
  },
  {
    claim_id: "clm_bounded",
    subject_id: "ent_person",
    subject_label: "Nimal Perera",
    subject_type: "person",
    predicate: "member_of",
    object_id: "ent_org",
    object_label: "Harbour Traders",
    object_value: null,
    // "Some time in April" — a range the source stated, and the thing that
    // must never be drawn at its midpoint.
    earliest: "2019-04-01T00:00:00Z",
    latest: "2019-04-30T00:00:00Z",
    certainty: "bounded",
    record_id: "rec_1",
    handling_code: "open",
    recorded_at: "2026-01-01T00:00:00Z",
  },
  {
    claim_id: "clm_open",
    subject_id: "ent_person",
    subject_label: "Nimal Perera",
    subject_type: "person",
    predicate: "known_as",
    object_id: null,
    object_label: null,
    object_value: "The Broker",
    earliest: "2019-05-01T00:00:00Z",
    latest: null,
    certainty: "open",
    record_id: "rec_1",
    handling_code: "open",
    recorded_at: "2026-01-01T00:00:00Z",
  },
];

async function stubTimeline(page: Page, undated = 2) {
  await page.route("**/v1/timeline*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: ITEMS,
        next_cursor: null,
        undated_count: undated,
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
});

test("an exact claim and a stated range are visibly different", async ({ page }) => {
  await stubTimeline(page);
  await page.goto("/timeline");

  const exact = page.getByTestId("timeline-item-clm_exact");
  const bounded = page.getByTestId("timeline-item-clm_bounded");
  await expect(exact).toHaveAttribute("data-certainty", "exact");
  await expect(bounded).toHaveAttribute("data-certainty", "bounded");

  // The range shows both ends. Rendering "2019-04-15" here would be a
  // precision nobody asserted.
  await expect(bounded).toContainText("2019-04-01 → 2019-04-30");
  await expect(exact).toContainText("2019-03-12");
  await expect(exact).not.toContainText("→");

  // ...and the difference is in the drawn width, not only in the text: the
  // bar for a stated instant is a hairline the CSS fixes, and the bar for a
  // range is proportional to the range.
  const exactWidth = await exact.locator(".timeline__bar").evaluate((el) => (el as HTMLElement).style.width);
  const boundedWidth = await bounded
    .locator(".timeline__bar")
    .evaluate((el) => (el as HTMLElement).style.width);
  expect(exactWidth).toBe("");
  expect(boundedWidth).not.toBe("");
});

test("an open-ended claim says which end is unknown", async ({ page }) => {
  await stubTimeline(page);
  await page.goto("/timeline");

  const open = page.getByTestId("timeline-item-clm_open");
  await expect(open).toHaveAttribute("data-certainty", "open");
  await expect(open).toContainText("after 2019-05-01");
});

test("undated claims are counted and named, never placed", async ({ page }) => {
  await stubTimeline(page, 2);
  await page.goto("/timeline");

  const undated = page.getByTestId("timeline-view-undated");
  await expect(undated).toContainText("2 claims");
  // The reason, in the product's own words: this is the line that stops a
  // narrowed window reading as a complete account.
  await expect(undated).toContainText("when a claim was recorded is not when it happened");
  // And no row was drawn for them.
  await expect(page.getByTestId("timeline-items").locator("li")).toHaveCount(ITEMS.length);
});

test("nothing undated is said when nothing is undated", async ({ page }) => {
  await stubTimeline(page, 0);
  await page.goto("/timeline");
  await expect(page.getByTestId("timeline-view-undated")).toHaveCount(0);
});

test("every item links to the entity it is about", async ({ page }) => {
  await stubTimeline(page);
  await page.goto("/timeline");
  await expect(
    page.getByTestId("timeline-item-clm_bounded").getByRole("link", { name: "Nimal Perera" }),
  ).toHaveAttribute("href", "/entities/ent_person");
});

test("the window lives in the URL, like the map's", async ({ page }) => {
  await stubTimeline(page);
  await page.goto("/timeline");
  await page.getByTestId("timeline-filter-from").fill("2019-01-01");
  await page.getByTestId("timeline-filter-to").fill("2019-12-31");
  await page.getByTestId("timeline-filter-apply").click();

  await expect(page).toHaveURL(/from=2019-01-01/);
  await expect(page).toHaveURL(/to=2019-12-31/);
});
