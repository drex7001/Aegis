import { expect, test, type Page } from "@playwright/test";

import { stubIdentityProvider } from "./oidc-stub";
import { stubReview } from "./review-stub";

/**
 * T23b as a browser journey: read what a producer proposed, see *why* it
 * proposed it, and decide.
 *
 * The assertions are about what a reviewer can tell from the screen. A queue
 * that cannot show its reasoning is one where "accept" means "I trust the
 * model", which is the opposite of what Article VII asks a person to do.
 */

async function openReview(page: Page) {
  await stubIdentityProvider(page);
  const stub = await stubReview(page);
  await page.goto("/review");
  await expect(page.getByTestId("username")).toBeVisible();
  return stub;
}

async function openIdentityTab(page: Page) {
  await page.getByRole("tab", { name: "Identity" }).click();
  await expect(page.getByTestId("candidate-list")).toBeVisible();
}

test("the queue opens on what is waiting, not on everything", async ({ page }) => {
  await openReview(page);

  await expect(page.getByTestId("suggestion")).toHaveCount(1);
  await expect(page.getByTestId("suggestion-kind")).toHaveText("claim draft");
});

test("a suggestion shows the producer metadata that makes it checkable", async ({
  page,
}) => {
  await openReview(page);
  await page.getByTestId("suggestion").click();

  const producer = page.locator(".suggestion__producer");
  await expect(producer).toContainText("semantic");
  // The model and the prompt are what a reader needs to reproduce or dispute
  // the suggestion; a bare confidence number would not be checkable.
  await expect(producer).toContainText("mock");
  await expect(producer).toContainText("a1b2c3d4");
});

test("accepting records the reviewer, not the producer", async ({ page }) => {
  const stub = await openReview(page);
  await page.getByTestId("suggestion").click();
  await page.getByTestId("suggestion-accept").click();

  await expect(page.getByTestId("queue-empty")).toBeVisible();
  expect(stub.suggestions()[0]?.status).toBe("accepted");
  expect(stub.suggestions()[0]?.decided_by).toBe("dev-analyst");
});

test("changing the assertion type is recorded as an edit, not a plain accept", async ({
  page,
}) => {
  const stub = await openReview(page);
  await page.getByTestId("suggestion").click();

  await page.getByTestId("accept-assertion").selectOption("observed");
  await expect(page.getByTestId("accept-edited")).toContainText("Changed from reported");

  await page.getByTestId("suggestion-accept").click();
  await expect(page.getByTestId("queue-empty")).toBeVisible();
  expect(stub.suggestions()[0]?.payload["assertion_type"]).toBe("observed");
});

test("a rejection needs a reason before it can be sent", async ({ page }) => {
  const stub = await openReview(page);
  await page.getByTestId("suggestion").click();

  await expect(page.getByTestId("suggestion-reject")).toBeDisabled();
  await page.getByTestId("reject-reason").fill("the source does not say this");
  await expect(page.getByTestId("suggestion-reject")).toBeEnabled();

  await page.getByTestId("suggestion-reject").click();
  await expect(page.getByTestId("queue-empty")).toBeVisible();
  expect(stub.suggestions()[0]?.status).toBe("rejected");
  expect(stub.suggestions()[0]?.decision_note).toBe("the source does not say this");
});

test("a candidate shows its waterfall, both directions", async ({ page }) => {
  await openReview(page);
  await openIdentityTab(page);

  // The probabilistic pair opens with its evidence showing.
  const waterfall = page.getByTestId("candidate-waterfall").last();
  await expect(waterfall).toContainText("splink");

  const rungs = waterfall.getByTestId("waterfall-rung");
  await expect(rungs).toHaveCount(2);
  // One column supports the match and one argues against it — a single score
  // would have hidden the disagreement entirely.
  await expect(rungs.filter({ hasText: "supports" })).toHaveCount(1);
  await expect(rungs.filter({ hasText: "argues against" })).toHaveCount(1);
});

test("a rule candidate says it has no score instead of inventing one", async ({ page }) => {
  await openReview(page);
  await openIdentityTab(page);

  await expect(page.getByTestId("candidate-score").first()).toHaveText("no score");
  await expect(page.getByTestId("candidate-verified")).toHaveCount(1);
});

test("only the pre-verified band is offered for batch confirmation", async ({ page }) => {
  const stub = await openReview(page);
  await openIdentityTab(page);

  const batch = page.getByTestId("batch-confirm");
  // One of the two candidates is pre-verified; the offer must name that count
  // and not the size of the list.
  await expect(batch).toContainText("1 pre-verified");

  await expect(page.getByTestId("batch-submit")).toBeDisabled();
  await page.getByTestId("batch-note").fill("checked both passport numbers");
  await page.getByTestId("batch-submit").click();

  await expect(page.getByTestId("batch-result")).toContainText("Confirmed 1");
  expect(stub.decisions()).toHaveLength(1);
  expect(stub.decisions()[0]?.note).toBe("checked both passport numbers");
});

test("deciding a pair needs an evidence note", async ({ page }) => {
  const stub = await openReview(page);
  await openIdentityTab(page);

  const scored = page.getByTestId("candidate").filter({ hasText: "Fictional BRAVO" });
  await expect(scored.getByTestId("decide-submit")).toBeDisabled();
  await scored.getByTestId("decide-note").fill("same person, two spellings");
  await scored.getByTestId("decide-submit").click();

  await expect.poll(() => stub.decisions().length).toBe(1);
  expect(stub.decisions()[0]?.kind).toBe("confirm");
});

test("rejecting a pair additionally requires what rules it out", async ({ page }) => {
  const stub = await openReview(page);
  await openIdentityTab(page);

  const scored = page.getByTestId("candidate").filter({ hasText: "Fictional BRAVO" });
  await scored.getByTestId("decide-reject_match").click();
  await scored.getByTestId("decide-note").fill("different people");

  // The note alone is not enough: a reject writes a durable constraint.
  await expect(scored.getByTestId("decide-submit")).toBeDisabled();
  await scored.getByTestId("decide-basis").fill("birth certificates differ");
  await expect(scored.getByTestId("decide-submit")).toBeEnabled();

  await scored.getByTestId("decide-submit").click();
  await expect.poll(() => stub.decisions().length).toBe(1);
  expect(stub.decisions()[0]?.kind).toBe("reject");
});

test("'cannot tell' is offered as a decision of its own", async ({ page }) => {
  const stub = await openReview(page);
  await openIdentityTab(page);

  const scored = page.getByTestId("candidate").filter({ hasText: "Fictional BRAVO" });
  await scored.getByTestId("decide-mark_unresolved").click();
  await scored.getByTestId("decide-note").fill("the records do not settle it");
  await scored.getByTestId("decide-submit").click();

  // Recorded, rather than left to look like a pair nobody reached.
  await expect.poll(() => stub.decisions().length).toBe(1);
  expect(stub.decisions()[0]?.kind).toBe("unresolved");
});

test("a decision overtaken by someone else is re-presented, not retried", async ({
  page,
}) => {
  const stub = await openReview(page);
  await openIdentityTab(page);

  const scored = page.getByTestId("candidate").filter({ hasText: "Fictional BRAVO" });
  await scored.getByTestId("decide-note").fill("same person");
  // Someone at another desk decides on these people first.
  stub.advanceRevision();
  await scored.getByTestId("decide-submit").click();

  const stale = page.getByTestId("decide-stale");
  await expect(stale).toContainText("Someone decided on these people");
  // What happened, as data — not a bare "conflict" that trains people to retry.
  await expect(stale).toContainText("dev-supervisor");
  await expect(stale).toContainText("merged these two from the other desk");
  expect(stub.decisions()).toHaveLength(0);
});

test("the review view is reachable from the nav without a reload", async ({ page }) => {
  await stubIdentityProvider(page);
  await stubReview(page);
  await page.goto("/sources");

  await page.getByRole("link", { name: "Review" }).click();
  await expect(page).toHaveURL(/\/review$/);
  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
});
