import { expect, test } from "@playwright/test";

import { ANNEX_PDF, stubIngest } from "./ingest-stub";
import { stubIdentityProvider } from "./oidc-stub";

/**
 * T23a's acceptance criteria as a browser journey: land a PDF and a pasted
 * note from the UI, see suggestions appear, see the re-upload no-op, and see a
 * quarantined record state its reason.
 *
 * The assertions are about what an operator can *tell* from the screen. A
 * landing screen that cannot distinguish "added" from "already had this" is not
 * a cosmetic problem — it is how the same document gets filed twice.
 */

async function signIn(page: import("@playwright/test").Page) {
  await stubIdentityProvider(page);
  const ingest = await stubIngest(page);
  await page.goto("/sources");
  await expect(page.getByTestId("username")).toBeVisible();
  return ingest;
}

async function uploadAnnex(page: import("@playwright/test").Page, name = "annex-b.pdf") {
  await page.getByTestId("intake-file").setInputFiles({
    name,
    mimeType: "application/pdf",
    buffer: ANNEX_PDF,
  });
  await page.getByTestId("intake-submit").click();
}

test("the sources view opens empty and says what to do", async ({ page }) => {
  await signIn(page);

  await expect(page.getByTestId("ledger-empty")).toContainText("Nothing landed yet");
});

test("landing a PDF files it and shows its digest", async ({ page }) => {
  await signIn(page);
  await uploadAnnex(page);

  const outcome = page.getByTestId("intake-outcome");
  await expect(outcome).toHaveAttribute("data-outcome", "landed");
  await expect(outcome).toContainText("annex-b.pdf is in the vault");
  // The digest is the identity of the artifact, and it is on screen.
  await expect(outcome.locator(".digest")).toContainText("sha256");

  await expect(page.getByTestId("record")).toHaveCount(1);
  await expect(page.getByTestId("record")).toContainText("annex-b.pdf");
});

test("re-uploading the same bytes reports the no-op and adds nothing", async ({ page }) => {
  const ingest = await signIn(page);

  await uploadAnnex(page);
  await expect(page.getByTestId("intake-outcome")).toHaveAttribute(
    "data-outcome",
    "landed",
  );

  await uploadAnnex(page);
  const outcome = page.getByTestId("intake-outcome");
  await expect(outcome).toHaveAttribute("data-outcome", "already_landed");
  await expect(outcome).toContainText("Nothing was added");

  expect(ingest.records()).toHaveLength(1);
  await expect(page.getByTestId("record")).toHaveCount(1);
});

test("a version conflict shows its quarantine reason", async ({ page }) => {
  await signIn(page);

  await uploadAnnex(page);
  await page.getByTestId("intake-file").setInputFiles({
    name: "annex-b.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 a different annex entirely\n"),
  });
  await page.getByTestId("intake-submit").click();

  const outcome = page.getByTestId("intake-outcome");
  await expect(outcome).toHaveAttribute("data-outcome", "quarantined");
  await expect(outcome).toContainText("version conflict");
  // Held, not lost, and the screen says who unblocks it.
  await expect(outcome).toContainText("supervisor");

  // These test ids exist only on a held row, so exactly one must appear —
  // asserting the count first also pins that the *other* upload stayed landed.
  await expect(page.getByTestId("record-status")).toHaveCount(1);
  await expect(page.getByTestId("record-status")).toHaveText("quarantined");
  await expect(page.getByTestId("record-reason")).toContainText("version conflict");
});

test("extracting a landed PDF records a derivative and queues a suggestion", async ({
  page,
}) => {
  await signIn(page);
  await uploadAnnex(page);

  await page.getByTestId("record").first().getByRole("button").first().click();
  await expect(page.getByTestId("record-suggestions")).toContainText(
    "No suggestions waiting",
  );

  await page.getByTestId("record-extract").click();

  await expect(page.getByTestId("record-derivative")).toContainText("pdfplumber");
  await expect(page.getByTestId("record-suggestions")).toContainText(
    "1 suggestion waiting for review",
  );
});

test("a pasted note lands and extracts without a derivative", async ({ page }) => {
  await signIn(page);

  await page.getByRole("tab", { name: "Paste text" }).click();
  await page.getByTestId("intake-filename").fill("field-note.txt");
  await page
    .getByTestId("intake-text")
    .fill("1. Fictional ALPHA - arrested 2023-02-14 - remanded, Northgate (2023-02-15 to 2023-06-30)");
  await page.getByTestId("intake-submit").click();

  await expect(page.getByTestId("intake-outcome")).toHaveAttribute(
    "data-outcome",
    "landed",
  );

  await page.getByTestId("record").first().getByRole("button").first().click();
  await page.getByTestId("record-extract").click();

  // Truthful rather than blank: a text record needs no transformation, and the
  // screen says so instead of leaving an empty slot to interpret.
  await expect(page.getByTestId("record-derivative")).toContainText(
    "Text is read from the record itself",
  );
  await expect(page.getByTestId("record-suggestions")).toContainText("1 suggestion");
});

test("a quarantined record offers release instead of extraction", async ({ page }) => {
  await signIn(page);

  await uploadAnnex(page);
  await page.getByTestId("intake-file").setInputFiles({
    name: "annex-b.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 conflicting content\n"),
  });
  await page.getByTestId("intake-submit").click();

  // Selected by what makes it quarantined, not by position. The register
  // refetches after a landing, so `.first()` can resolve to the row that was
  // there before the new one arrives — and Playwright's auto-wait does not
  // rescue that, because an element *is* present, just the wrong one.
  const held = page
    .getByTestId("record")
    .filter({ has: page.getByTestId("record-status") });
  await expect(held).toHaveCount(1);
  await held.getByRole("button").first().click();

  await expect(page.getByTestId("record-release")).toBeVisible();
  await expect(page.getByTestId("record-extract")).toHaveCount(0);

  await page.getByTestId("record-release").click();

  await expect(page.getByTestId("record-extract")).toBeVisible();
  await expect(page.getByTestId("record-status")).toHaveCount(0);
});

test("landing calls carry the bearer token", async ({ page }) => {
  const ingest = await signIn(page);
  await uploadAnnex(page);

  await expect(page.getByTestId("intake-outcome")).toBeVisible();
  expect(ingest.bearerTokens().length).toBeGreaterThan(0);
  expect(ingest.bearerTokens()[0]).toMatch(/^Bearer \S+\.\S+\.\S+$/);
});

test("a refused action is surfaced in the API's own words", async ({ page }) => {
  await stubIdentityProvider(page);
  await stubIngest(page);
  await page.route("**/v1/ingest/text", (route) =>
    route.fulfill({
      status: 403,
      contentType: "application/problem+json",
      body: JSON.stringify({
        type: "about:blank",
        title: "Forbidden",
        status: 403,
        detail: "handling code 'sensitive' is above your clearance",
      }),
    }),
  );

  await page.goto("/sources");
  await page.getByRole("tab", { name: "Paste text" }).click();
  await page.getByTestId("intake-filename").fill("note.txt");
  await page.getByTestId("intake-text").fill("a fictional note");
  await page.getByTestId("intake-submit").click();

  await expect(page.getByTestId("intake-error")).toContainText("above your clearance");
});

test("the nav moves between views without a reload", async ({ page }) => {
  await signIn(page);

  await page.getByRole("link", { name: "Graph" }).click();
  await expect(page).toHaveURL(/\/graph$/);

  await page.getByRole("link", { name: "Sources" }).click();
  await expect(page).toHaveURL(/\/sources$/);
  await expect(page.getByRole("heading", { name: "Land a source record" })).toBeVisible();
});
