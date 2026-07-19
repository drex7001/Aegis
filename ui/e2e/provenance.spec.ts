import { expect, test, type Page } from "@playwright/test";

import { stubGraphRoute, stubIdentityProvider } from "./oidc-stub";
import {
  EARLIER_DOB,
  ENTITY_B,
  LATER_DOB,
  stubProvenanceRoutes,
} from "./provenance-stub";

/**
 * The T23c acceptance criteria as a browser journey:
 *
 *   every rendered edge opens the panel · contradictory DOB claims both render
 *   with a visible `contradicts` badge · search finds and focuses an entity
 *
 * Cytoscape draws into `<canvas>`, so an edge cannot be clicked through the DOM
 * tree. These tests reach the selection the way the canvas does — by firing the
 * tap handler the component registered — which exercises the same state path a
 * real click takes without asserting on pixel positions.
 */

async function signedInGraph(page: Page): Promise<void> {
  await stubIdentityProvider(page);
  await stubGraphRoute(page);
  await stubProvenanceRoutes(page);
  await page.goto("/");
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
}

/** Tap an element on the Cytoscape instance the canvas owns. */
async function tap(page: Page, kind: "edge" | "node", id: string): Promise<void> {
  await page.evaluate(
    ([selectorKind, elementId]) => {
      const container = document.querySelector("[data-testid='graph-canvas']");
      // Cytoscape hangs its instance off the container element it was given.
      const cy = (container as unknown as { _cyreg?: { cy: any } })?._cyreg?.cy;
      if (!cy) throw new Error("cytoscape instance not found on the canvas");
      cy.$(`${selectorKind}#${elementId}`).emit("tap");
    },
    [kind, id] as const,
  );
}

test("clicking an edge opens the provenance panel with its evidence", async ({
  page,
}) => {
  await signedInGraph(page);
  await tap(page, "edge", "edg_fictional_1");

  const panel = page.getByTestId("provenance-panel");
  await expect(panel).toBeVisible();
  // Record count, never "independent sources" (ADR-030 §3).
  await expect(page.getByTestId("tally")).toContainText("2 source records");
  await expect(panel).toContainText("Fictional Registry");
});

test("the edge panel shows the identity decisions behind the endpoints", async ({
  page,
}) => {
  await signedInGraph(page);
  await tap(page, "edge", "edg_fictional_1");

  // An edge can exist only because a human merged two mentions; a panel that
  // showed evidence without the decision would hide the auditable step.
  const line = page.getByTestId("identity-line");
  await expect(line).toContainText("analyst@example.test");
  await expect(line).toContainText("Same NIC on both records.");
});

test("the three grading dimensions are rendered apart, with no combined score", async ({
  page,
}) => {
  await signedInGraph(page);
  await tap(page, "edge", "edg_fictional_1");

  const grading = page.getByTestId("grading").first();
  await expect(grading).toContainText("Source reliability");
  await expect(grading).toContainText("Claim credibility");
  await expect(grading).toContainText("Verification");
  // Article III: a single figure is the one thing every reader would reach for
  // and cannot be turned back into the judgements behind it.
  await expect(grading).not.toContainText("score");
});

test("clicking a node opens its claims", async ({ page }) => {
  await signedInGraph(page);
  await tap(page, "node", "ent_fictional_a");

  await expect(page.getByTestId("provenance-panel")).toBeVisible();
  await expect(page.getByTestId("predicate-date_of_birth")).toBeVisible();
});

test("contradictory dates of birth both render, with a contradicts badge", async ({
  page,
}) => {
  await signedInGraph(page);
  await tap(page, "node", "ent_fictional_a");

  const group = page.getByTestId("predicate-date_of_birth");
  await expect(group.getByTestId("contradicts-badge")).toBeVisible();
  // *Both* readings survive. Showing only the better-sourced one would be the
  // UI making the judgement the analyst is there to make (Article VIII).
  await expect(group).toContainText(EARLIER_DOB);
  await expect(group).toContainText(LATER_DOB);
});

test("a contested group is marked contested and an uncontested one is not", async ({
  page,
}) => {
  await signedInGraph(page);
  await tap(page, "node", "ent_fictional_a");

  await expect(page.getByTestId("predicate-date_of_birth")).toHaveAttribute(
    "data-contested",
    "true",
  );
  // The badge has to mean something: a panel that marked everything contested
  // would pass the test above while telling the reader nothing.
  await expect(page.getByTestId("predicate-known_as")).toHaveAttribute(
    "data-contested",
    "false",
  );
});

test("the two disagreeing sources are named alongside their claims", async ({
  page,
}) => {
  await signedInGraph(page);
  await tap(page, "node", "ent_fictional_a");

  const group = page.getByTestId("predicate-date_of_birth");
  // Side by side is only useful if what differs is visible on each side.
  await expect(group).toContainText("Fictional Registry");
  await expect(group).toContainText("Fictional Court Filing");
});

test("selecting a node does not re-lay out the graph underneath the reader", async ({
  page,
}) => {
  await signedInGraph(page);
  await expect(page.getByTestId("graph-mode")).toHaveText("Bounded overview");

  await tap(page, "node", "ent_fictional_a");

  await expect(page.getByTestId("provenance-panel")).toBeVisible();
  // Focusing is offered in the panel; it is not a side effect of reading.
  await expect(page.getByTestId("graph-mode")).toHaveText("Bounded overview");
});

test("the panel closes", async ({ page }) => {
  await signedInGraph(page);
  await tap(page, "edge", "edg_fictional_1");
  await expect(page.getByTestId("provenance-panel")).toBeVisible();

  await page.getByRole("button", { name: "Close" }).click();
  await expect(page.getByTestId("provenance-panel")).toHaveCount(0);
});

test("searching finds an entity and focusing it seeds the graph", async ({ page }) => {
  await signedInGraph(page);

  await page.getByTestId("search-input").fill("fictional");
  await expect(page.getByTestId("search-results")).toBeVisible();

  await page.getByTestId(`search-hit-${ENTITY_B}`).click();
  // "Search first, expand second" (spec 07 §5), now literally that.
  await expect(page.getByTestId("graph-mode")).toHaveText(`Expanding from ${ENTITY_B}`);
});

test("a phonetic hit is labelled as one rather than shown as a name match", async ({
  page,
}) => {
  await signedInGraph(page);

  await page.getByTestId("search-input").fill("fictional");
  // Metaphone collapses genuinely different names, so presenting a phonetic
  // hit like a name hit would overstate what the index actually found.
  await expect(page.getByTestId("matched-phonetic")).toHaveText("sounds like");
  await expect(page.getByTestId("matched-label")).toHaveText("name");
});

test("a search below the minimum length does not query", async ({ page }) => {
  await signedInGraph(page);

  let calls = 0;
  await page.route("**/v1/search/entities**", (route) => {
    calls += 1;
    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ query: "f", results: [], next_cursor: null }),
    });
  });

  await page.getByTestId("search-input").fill("f");
  await page.waitForTimeout(600);
  expect(calls).toBe(0);
});
