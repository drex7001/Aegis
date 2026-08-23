import { expect, test, type Page } from "@playwright/test";

import { stubIdentityProvider } from "./oidc-stub";

/**
 * The findings panel (T73, charter exit №2).
 *
 * The criterion is that **no metric has a caveat-free rendering path**, and the
 * test is parameterised over every metric for that reason: a caveat asserted
 * for one metric proves nothing about the next one somebody adds.
 *
 * The other half is the wording. Article IX's risk table names the failure
 * exactly — "most connected = leader" — so this asserts the rendered page
 * contains none of the vocabulary that turns a count of recorded connections
 * into a claim about a person's role.
 *
 * Fictional fixtures throughout.
 */

const METRICS = [
  {
    metric: "degree",
    label: "Recorded connections",
    caveat:
      "A count of recorded connections. An entity scores highly when it is frequently reported, which reflects the reporting. This is not a measure of influence, seniority, control, or responsibility, and the highest score in a graph is not evidence of any of them.",
    value: { degree: 4 },
  },
  {
    metric: "betweenness",
    label: "Betweenness",
    caveat:
      "How often an entity lies on a shortest recorded path between others. It measures the shape of what has been written down, not the flow of anything real. A high score is a reason to ask why the records connect through this entity — it is not an answer.",
    value: { betweenness: 0.5 },
  },
  {
    metric: "community",
    label: "Community",
    caveat:
      "A partition computed from edge weights the caller supplied. A cell is a question to investigate, not a finding about membership, affiliation, or shared purpose. Two people in one cell may never have met.",
    value: { cluster_id: 0, size: 3 },
  },
];

/** The words a centrality score must never be described with (Article IX). */
const FORBIDDEN = [
  "leader",
  "leadership",
  "kingpin",
  "mastermind",
  "ringleader",
  "in charge",
  "seniority",
  "hierarchy",
  "most important",
  "key player",
  "guilt",
  "perpetrator",
];

const RUN = {
  run_id: "run_fictional_1",
  method: "degree",
  method_version: "analytics-v1",
  implementation: "builtin",
  parameters: {},
  seed: null,
  input_kind: "projection",
  object_set_id: null,
  object_set_version: null,
  evaluation_digest: null,
  edge_digest: "e1e2e3e4e5e600112233445566778899aabbccddeeff00112233445566778899",
  projection_built_at_revision_id: 11,
  projection_builder_version: "edges-v3",
  projection_aggregation_method_version: "support-summary-v1",
  ontology_version: "2.1.0",
  identity_revision_id: 11,
  code_version: "0.5.0",
  settings_digest: "5e77111122223333444455556666777788889999aaaabbbbccccddddeeeeffff",
  actor: "user:analyst",
  purpose: "mapping the harbour network",
  authorization_digest: "a0a1a2a3a4a5a600112233445566778899aabbccddeeff00112233445566778899",
  caveat_version: "1",
  started_at: "2026-08-23T10:00:00Z",
  finished_at: "2026-08-23T10:00:01Z",
};

function findingsFor(entries: typeof METRICS) {
  return entries.map((entry, index) => ({
    finding_id: `find_${entry.metric}`,
    run_id: RUN.run_id,
    finding_type: entry.metric,
    subjects: [`ent_fictional_${index}`],
    value: entry.value,
    caveat_text: entry.caveat,
    caveat_version: "1",
    finding_digest: `d${index}`.padEnd(64, "0"),
    promoted_claim_id: null,
    handling_code: "open",
    created_at: "2026-08-23T10:00:01Z",
  }));
}

async function stubFindings(page: Page, entries = METRICS): Promise<void> {
  await page.route("**/v1/ontology/vocabulary", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        version: "2.1.0",
        handling_codes: ["open", "restricted", "sensitive"],
        source_types: ["open_source"],
        assertion_types: ["assessed", "inferred", "observed", "reported"],
        analytic_metrics: METRICS.map(({ metric, label }) => ({ metric, label })),
      }),
    }),
  );
  await page.route("**/v1/object-sets**", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: [], next_cursor: null }),
    }),
  );
  await page.route("**/v1/findings**", (route) =>
    route.fulfill({
      contentType: "application/json",
      // No total, matching the route — a stub that added one would let the
      // panel pass a test the API would fail.
      body: JSON.stringify({ items: findingsFor(entries), next_cursor: null }),
    }),
  );
  // Registered *after* the list, because Playwright matches the most recently
  // registered route first — so the specific pattern has to come last or the
  // list handler answers `/v1/findings/{id}` with a body that has no manifest.
  await page.route("**/v1/findings/*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ run: RUN, findings: [findingsFor(entries)[0]] }),
    }),
  );
}

async function openFindings(page: Page): Promise<void> {
  await stubIdentityProvider(page);
  await page.goto("/findings");
  await expect(page.getByTestId("findings-panel")).toBeVisible();
}

for (const entry of METRICS) {
  test(`${entry.metric} renders its caveat, with no path that skips it`, async ({
    page,
  }) => {
    await stubFindings(page);
    await openFindings(page);

    const caveat = page.getByTestId(`caveat-find_${entry.metric}`);
    // Visible without any interaction: not behind a toggle, not in a tooltip,
    // not conditional on the metric. A caveat somebody has to open is a caveat
    // nobody reads.
    await expect(caveat).toBeVisible();
    await expect(caveat).toHaveText(entry.caveat);
  });
}

test("every finding on the page carries a caveat", async ({ page }) => {
  await stubFindings(page);
  await openFindings(page);

  // Counted rather than spot-checked: a metric added later must not be able to
  // render without one, and this fails the moment the counts diverge.
  const findings = page.locator("[data-testid^='finding-find_']");
  const caveats = page.locator("[data-testid^='caveat-']");
  await expect(findings).toHaveCount(METRICS.length);
  await expect(caveats).toHaveCount(METRICS.length);
});

test("centrality never renders with leadership language", async ({ page }) => {
  await stubFindings(page);
  await openFindings(page);

  const rendered = ((await page.getByTestId("findings-panel").innerText()) ?? "").toLowerCase();
  for (const word of FORBIDDEN) {
    // `seniority` is allowed to appear *inside* a caveat, because a caveat's
    // job is to name the wrong reading and deny it — so the check is that the
    // word never appears outside one.
    const insideCaveat = METRICS.some((entry) =>
      entry.caveat.toLowerCase().includes(word),
    );
    if (insideCaveat) continue;
    expect(rendered, `"${word}" appears in the rendered panel`).not.toContain(word);
  }
});

test("a superlative never labels a metric", async ({ page }) => {
  await stubFindings(page);
  await openFindings(page);

  // "Most connected" does the same work as "leader" with none of the
  // vocabulary, so the label is "Recorded connections".
  await expect(page.getByTestId("finding-label-find_degree")).toHaveText(
    "Recorded connections",
  );
});

test("a finding opens its manifest, including what it was authorized to see", async ({
  page,
}) => {
  await stubFindings(page);
  await openFindings(page);

  await page.getByTestId("open-find_degree").click();
  const manifest = page.getByTestId("finding-manifest");
  await expect(manifest).toBeVisible();

  // The three fields that answer "can I trust this, and can I get it again".
  await expect(page.getByTestId("manifest-implementation")).toHaveText("builtin");
  await expect(page.getByTestId("manifest-edges-read")).toHaveText("e1e2e3e4e5e6");
  // Shown because it is the field that explains a disagreement between two
  // analysts running one metric under different clearances.
  await expect(page.getByTestId("manifest-authorization")).toHaveText("a0a1a2a3a4a5");
});

test("an unseeded run says unseeded rather than showing a zero", async ({ page }) => {
  await stubFindings(page);
  await openFindings(page);

  await page.getByTestId("open-find_degree").click();
  await expect(page.getByTestId("manifest-seed")).toHaveText("unseeded");
});

test("running a metric requires a purpose", async ({ page }) => {
  await stubFindings(page);
  await openFindings(page);

  // Recording an answer about people is the kind of act Article X keeps a
  // record of, and there is no "just looking" version of it.
  await expect(page.getByTestId("run-metric")).toBeDisabled();
  await page.getByTestId("run-purpose").fill("mapping the harbour network");
  await expect(page.getByTestId("run-metric")).toBeEnabled();
});

test("an empty list says nothing you can see, not nothing exists", async ({ page }) => {
  await stubFindings(page, []);
  await openFindings(page);
  await expect(page.getByTestId("no-findings")).toHaveText("No findings you can see.");
});
