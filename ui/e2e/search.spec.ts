import { expect, test, type Page } from "@playwright/test";

import { stubGraphRoute, stubIdentityProvider } from "./oidc-stub";

/**
 * Grouped search in the browser (T67, spec 11 §5).
 *
 * Three things the panel must get right, and each fails silently if it does
 * not:
 *
 * **Group headings come from the server**, which takes them from the ontology.
 * Nothing in the workspace enumerates domain types, so a second domain's
 * objects appear here with their own names and no code change (Article XIV).
 *
 * **One "load more", never one per group.** Groups are how a page is displayed;
 * per-group cursors would leave informative gaps where restricted rows were
 * removed (B-17).
 *
 * **A hit with nowhere to go does not pretend otherwise.** A document has no
 * detail view yet, so it renders without an "Open" rather than with one that
 * lands on a 404.
 *
 * Fictional fixtures throughout.
 */

const PERSON = "ent_fictional_person";
const CLAIM = "clm_fictional_1";
const DOCUMENT = "dtp_fictional_1";
const RECORD = "rec_fictional_1";

const PAGE_ONE = {
  query: "harbour",
  next_cursor: "cursor-page-2",
  stamp: { as_of: null, identity_revision_id: 3, ontology_version: "2.1.0" },
  groups: [
    {
      group: "person",
      label: "Person",
      hits: [
        {
          kind: "entity",
          id: PERSON,
          group: "person",
          label: "Fictional ECHO",
          detail: null,
          parent_id: null,
          score: 0.91,
          matched: "label",
        },
      ],
    },
    {
      group: "claim",
      label: "Claims",
      hits: [
        {
          kind: "claim",
          id: CLAIM,
          group: "claim",
          label: "Fictional ECHO — has_role",
          detail: "has_role",
          parent_id: PERSON,
          score: 0.66,
          matched: "excerpt",
        },
      ],
    },
    {
      group: "document",
      label: "Documents",
      hits: [
        {
          kind: "document",
          id: DOCUMENT,
          group: "document",
          label: RECORD,
          detail: RECORD,
          parent_id: RECORD,
          score: 0.31,
          matched: "text",
        },
      ],
    },
  ],
};

const PAGE_TWO = {
  ...PAGE_ONE,
  next_cursor: null,
  groups: [
    {
      group: "person",
      label: "Person",
      hits: [
        {
          kind: "entity",
          id: "ent_fictional_second",
          group: "person",
          label: "Fictional FOXTROT",
          detail: null,
          parent_id: null,
          score: 0.2,
          matched: "phonetic",
        },
      ],
    },
  ],
};

async function stubSearch(page: Page): Promise<number[]> {
  const cursors: number[] = [];
  await page.route("**/v1/search**", (route) => {
    const url = new URL(route.request().url());
    const cursor = url.searchParams.get("cursor");
    cursors.push(cursor ? 1 : 0);
    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(cursor ? PAGE_TWO : PAGE_ONE),
    });
  });
  return cursors;
}

async function signedIn(page: Page): Promise<void> {
  await stubIdentityProvider(page);
  await stubGraphRoute(page);
  await page.goto("/");
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
}

test("results are grouped under labels the server supplied", async ({ page }) => {
  await stubSearch(page);
  await signedIn(page);

  await page.getByTestId("search-input").fill("harbour");
  await expect(page.getByTestId("search-results")).toBeVisible();

  // The labels are the ontology's, not this file's — "Person" is what the
  // module declares, and nothing in the workspace maps a type name to it.
  await expect(page.getByTestId("search-group-person")).toContainText("Person");
  await expect(page.getByTestId("search-group-claim")).toContainText("Claims");
  await expect(page.getByTestId("search-group-document")).toContainText("Documents");
});

test("the results are one panel, not one panel per group", async ({ page }) => {
  await stubSearch(page);
  await signedIn(page);

  await page.getByTestId("search-input").fill("harbour");
  await expect(page.getByTestId("search-results")).toBeVisible();

  // The bug this catches: the overlay styling once lived on the result *list*,
  // so splitting results into one list per group turned every group into its
  // own floating panel, stacked on the others. The top group's rows were
  // unclickable because a lower group's chip sat over them — visible only to a
  // test that actually clicks, which is the one below.
  await expect(page.locator(".search__panel")).toHaveCount(1);
});

test("an entity hit still seeds the graph, as it did before T67", async ({ page }) => {
  await stubSearch(page);
  await signedIn(page);

  await page.getByTestId("search-input").fill("harbour");
  await page.getByTestId(`search-hit-${PERSON}`).click();
  await expect(page.getByTestId("graph-mode")).toHaveText(`Expanding from ${PERSON}`);
});

test("a claim hit opens the entity it is about", async ({ page }) => {
  await stubSearch(page);
  await signedIn(page);

  await page.getByTestId("search-input").fill("harbour");
  // A claim's page is the page of the thing it is about — there is no
  // free-standing claim screen, and inventing a link to one would be a link
  // that goes nowhere.
  await expect(page.getByTestId(`search-open-${CLAIM}`)).toHaveAttribute(
    "href",
    `/entities/${PERSON}`,
  );
});

test("a document hit offers no destination it does not have", async ({ page }) => {
  await stubSearch(page);
  await signedIn(page);

  await page.getByTestId("search-input").fill("harbour");
  await expect(page.getByTestId(`search-hit-${DOCUMENT}`)).toBeVisible();
  // An "Open" that 404s is worse than no "Open".
  await expect(page.getByTestId(`search-open-${DOCUMENT}`)).toHaveCount(0);
});

test("how each hit was found is shown, and weak evidence says so", async ({ page }) => {
  await stubSearch(page);
  await signedIn(page);

  await page.getByTestId("search-input").fill("harbour");
  await expect(page.getByTestId("matched-label")).toHaveText("name");
  await expect(page.getByTestId("matched-excerpt")).toHaveText("in the excerpt");
  await expect(page.getByTestId("matched-text")).toHaveText("in the text");
});

test("there is one Load more for the page, not one per group", async ({ page }) => {
  await stubSearch(page);
  await signedIn(page);

  await page.getByTestId("search-input").fill("harbour");
  await expect(page.getByTestId("search-results")).toBeVisible();

  // Three groups, one control. Several cursors advanced independently would
  // leave gaps exactly where restricted rows were removed (B-17).
  const more = page.getByRole("button", { name: "Load more" });
  await expect(more).toHaveCount(1);

  await more.click();
  // The second page's group merges into the existing heading rather than
  // opening a second "Person" section.
  await expect(page.getByTestId("search-group-person")).toContainText("Fictional FOXTROT");
  await expect(page.getByTestId("search-group-person")).toHaveCount(1);
});
