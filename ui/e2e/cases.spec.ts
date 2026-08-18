import { expect, test } from "@playwright/test";

import { GRAPH_FIXTURE, stubGraphRoute, stubIdentityProvider } from "./oidc-stub";
import { ONTOLOGY_VERSION, stubCases, stubVocabulary } from "./workspace-stub";

/**
 * T46's case surfaces as browser journeys.
 *
 * The assertions that matter are the ones about **what is not said**. A case
 * list carries no total, because a count over an authorization-filtered
 * collection is an existence leak; an empty one reads "none you are a member
 * of", never "none exist"; and a case you cannot reach reads as absence rather
 * than as a refusal. The authorization itself lives in
 * `tests/integration/test_case_graph.py` and `test_investigation_routes.py`,
 * where a real database can prove it — this checks the workspace does not
 * undo it in wording.
 */

const CASE = {
  case_id: "cas_1",
  title: "Fictional enquiry",
  status: "open",
  purpose: "T46 verification",
  handling_code: "open",
  opened_by: "dev-analyst",
  opened_at: "2026-08-01T09:00:00Z",
  // Widened so a closed-case variant can spread over it.
  closed_at: null as string | null,
};

async function stubCaseDetail(
  page: import("@playwright/test").Page,
  {
    detail = CASE,
    members = [{ case_id: "cas_1", user_id: "dev-analyst", role: "supervisor" }],
    references = [] as Array<Record<string, unknown>>,
  } = {},
): Promise<void> {
  await page.route("**/v1/cases/cas_1", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(detail) }),
  );
  await page.route("**/v1/cases/cas_1/members", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(members) }),
  );
  await page.route("**/v1/cases/cas_1/references", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(references) }),
  );
  await page.route("**/v1/cases/cas_missing", (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/problem+json",
      body: JSON.stringify({ type: "about:blank", title: "Not Found", status: 404 }),
    }),
  );
}

test.beforeEach(async ({ page }) => {
  await stubIdentityProvider(page);
  await stubGraphRoute(page);
  await stubVocabulary(page, { version: ONTOLOGY_VERSION });
});

test("the rail lists the caller's cases and links to each", async ({ page }) => {
  await stubCases(page, [CASE]);
  await stubCaseDetail(page);
  await page.goto("/graph");

  const switcher = page.getByTestId("case-switcher");
  await expect(switcher).toContainText("Fictional enquiry");
  await switcher.getByRole("link", { name: "Fictional enquiry" }).click();
  await expect(page.getByTestId("case-title")).toHaveText("Fictional enquiry");
});

test("no case is reported as a membership, not as an absence of cases", async ({
  page,
}) => {
  await stubCases(page, []);
  await page.goto("/cases");

  await expect(page.getByTestId("cases-empty")).toHaveText(
    "You are not a member of any case.",
  );
  // Never "no cases exist" — that answers a question the caller was not
  // permitted to ask.
  const text = (await page.getByTestId("cases-view").innerText()).toLowerCase();
  expect(text).not.toContain("no cases exist");
  expect(text).not.toContain("none exist");
});

test("the case list renders no count", async ({ page }) => {
  await stubCases(page, [CASE, { ...CASE, case_id: "cas_2", title: "Second enquiry" }]);
  await page.goto("/cases");

  await expect(page.getByTestId("cases-table")).toContainText("Fictional enquiry");
  // A total over an authorization-filtered collection is an existence leak
  // (spec 06 §4 default 4), so there must be nothing shaped like one.
  const text = await page.getByTestId("cases-view").innerText();
  expect(text).not.toMatch(/\b2 cases\b/i);
  expect(text.toLowerCase()).not.toContain("showing 2");
  expect(text.toLowerCase()).not.toContain("total");
});

test("a case you cannot reach reads as absence, not as a refusal", async ({ page }) => {
  await stubCases(page, []);
  await stubCaseDetail(page);
  await page.goto("/cases/cas_missing");

  const absent = page.getByTestId("case-absent");
  await expect(absent).toBeVisible();
  const text = (await absent.innerText()).toLowerCase();
  for (const tell of ["forbidden", "permission", "not allowed", "denied", "member"]) {
    expect(text).not.toContain(tell);
  }
});

test("the case screen says a reference grants nothing", async ({ page }) => {
  await stubCases(page, [CASE]);
  await stubCaseDetail(page, {
    references: [
      {
        case_id: "cas_1",
        target_type: "entity",
        target_id: "ent_fictional_a",
        note: "named in the filing",
        linked_by: "dev-analyst",
        linked_at: "2026-08-02T09:00:00Z",
      },
    ],
  });
  await page.goto("/cases/cas_1");

  // ADR-044 in the operator's own words. A UI that called these "the case's
  // claims" would teach the reader the opposite of how access works.
  await expect(page.getByTestId("case-view")).toContainText(
    "A reference grants no access to its target and does not move a claim into this case.",
  );
  await expect(page.getByTestId("case-references")).toContainText("ent_fictional_a");
});

test("the case graph asks for that case's evidence and says what it shows", async ({
  page,
}) => {
  await stubCases(page, [CASE]);
  await stubCaseDetail(page);

  const bodies: unknown[] = [];
  await page.route("**/v1/graph/expand", async (route) => {
    bodies.push(route.request().postDataJSON());
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(GRAPH_FIXTURE),
    });
  });

  await page.goto("/cases/cas_1");
  await expect(page.getByTestId("case-graph")).toBeVisible();

  // The filter travels to the server, where it is threaded into `claim_filters`
  // — the UI never filters a graph it was given.
  expect(bodies).toContainEqual(expect.objectContaining({ case_id: "cas_1" }));
  await expect(page.getByTestId("case-view")).toContainText(
    "Only the evidence this case recorded",
  );
});

test("a closed case offers no close control", async ({ page }) => {
  await stubCases(page, [CASE]);
  await stubCaseDetail(page, {
    detail: { ...CASE, status: "closed", closed_at: "2026-08-10T09:00:00Z" },
  });
  await page.goto("/cases/cas_1");

  await expect(page.getByTestId("case-status")).toHaveText("closed");
  await expect(page.getByTestId("case-close-form")).toHaveCount(0);
});

test("opening a case sends its purpose as the audited query parameter", async ({
  page,
}) => {
  await stubCases(page, []);
  const urls: string[] = [];
  // A URL predicate, not a glob: `**/v1/cases` does not match
  // `/v1/cases?purpose=…`, and the whole point of this test is that the
  // purpose travels in the query string.
  await page.route(
    (url) => url.pathname === "/v1/cases",
    async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      urls.push(request.url());
      return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(CASE) });
    }
    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: [], next_cursor: null }),
    });
    },
  );

  await page.goto("/cases");
  await page.getByTestId("case-title").fill("New fictional enquiry");
  await page.getByTestId("case-purpose").fill("verify the filing");
  await page.getByTestId("case-open").click();

  await expect.poll(() => urls.length).toBeGreaterThan(0);
  // The gate reads `purpose` before the handler sees a body, and audits the
  // allow with it (GOAL.md §12.4) — so it has to be on the URL.
  expect(new URL(urls[0]!).searchParams.get("purpose")).toBe("verify the filing");
});
