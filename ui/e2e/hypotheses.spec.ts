import { expect, test } from "@playwright/test";

import { stubGraphRoute, stubIdentityProvider } from "./oidc-stub";
import { ONTOLOGY_VERSION, stubCases, stubVocabulary } from "./workspace-stub";

/**
 * T47 and T48 as browser journeys.
 *
 * The load-bearing assertion is Article VIII as a *rendering* obligation: both
 * columns are present whether or not they hold anything, and the empty one says
 * "no contradicting evidence recorded" rather than disappearing. A page that
 * hid the empty side would tell the reader the question was never asked.
 *
 * The second is GOAL.md §18: the missing-information note is a required field
 * with its own heading, and the server's refusal of a blank one is surfaced in
 * the server's own words — a generic "please fill in all fields" would hide
 * which rule fired, and this is a rule worth reading.
 */

const CASE = {
  case_id: "cas_1",
  title: "Fictional enquiry",
  status: "open",
  purpose: "T47",
  handling_code: "open",
  opened_by: "dev-analyst",
  opened_at: "2026-08-01T09:00:00Z",
  closed_at: null as string | null,
};

const REVISION = {
  hypothesis_id: "hyp_1",
  version: 1,
  statement: "The two fictional parties act as one enterprise.",
  status: "open",
  missing_info: "The registry filing has not been checked.",
  note: null as string | null,
  authored_by: "dev-analyst",
  authored_at: "2026-08-02T09:00:00Z",
};

function hypothesis(overrides: Record<string, unknown> = {}) {
  return {
    hypothesis_id: "hyp_1",
    case_id: "cas_1",
    opened_by: "dev-analyst",
    opened_at: "2026-08-02T09:00:00Z",
    handling_code: "open",
    current: REVISION,
    revisions: [REVISION],
    supporting: [],
    contradicting: [],
    ...overrides,
  };
}

function link(claimId: string, note: string) {
  return {
    claim_id: claimId,
    stance: "supports",
    note,
    linked_by: "dev-analyst",
    linked_at: "2026-08-03T09:00:00Z",
  };
}

test.beforeEach(async ({ page }) => {
  await stubIdentityProvider(page);
  await stubGraphRoute(page);
  await stubVocabulary(page, { version: ONTOLOGY_VERSION });
  await stubCases(page, [CASE]);
  await page.route("**/v1/cases/cas_1", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(CASE) }),
  );
  for (const path of ["members", "references"]) {
    await page.route(`**/v1/cases/cas_1/${path}`, (route) =>
      route.fulfill({ contentType: "application/json", body: "[]" }),
    );
  }
});

test("both sides of a hypothesis render, and the empty one says so", async ({ page }) => {
  await page.route(
    (url) => url.pathname === "/v1/hypotheses/hyp_1",
    (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        hypothesis({ supporting: [link("clm_a", "the filing names both")] }),
      ),
    }),
  );
  await page.goto("/hypotheses/hyp_1");

  await expect(page.getByTestId("hypothesis-supports")).toContainText("clm_a");
  // Present and explicit, not omitted. This is the assertion the whole screen
  // exists for.
  await expect(page.getByTestId("hypothesis-contradicts")).toBeVisible();
  await expect(page.getByTestId("hypothesis-contradicts-empty")).toHaveText(
    "No contradicting evidence recorded.",
  );
});

test("a claim linked under both stances appears on both sides", async ({ page }) => {
  await page.route(
    (url) => url.pathname === "/v1/hypotheses/hyp_1",
    (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        hypothesis({
          supporting: [link("clm_both", "reads as support")],
          contradicting: [{ ...link("clm_both", "and as contradiction"), stance: "contradicts" }],
        }),
      ),
    }),
  );
  await page.goto("/hypotheses/hyp_1");

  // Not a conflict to resolve: the same claim may cut both ways (spec 09 §3.2).
  await expect(page.getByTestId("hypothesis-supports")).toContainText("clm_both");
  await expect(page.getByTestId("hypothesis-contradicts")).toContainText("clm_both");
});

test("nothing on the page scores the two sides against each other", async ({ page }) => {
  await page.route(
    (url) => url.pathname === "/v1/hypotheses/hyp_1",
    (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        hypothesis({
          supporting: [link("clm_a", "a"), link("clm_b", "b"), link("clm_c", "c")],
          contradicting: [{ ...link("clm_d", "d"), stance: "contradicts" }],
        }),
      ),
    }),
  );
  await page.goto("/hypotheses/hyp_1");

  const text = (await page.getByTestId("hypothesis-view").innerText()).toLowerCase();
  // A "3 for, 1 against" tally is the number that gets quoted without the
  // lists it came from.
  expect(text).not.toMatch(/\b3\s*(for|-|–|vs)\s*1\b/);
  expect(text).not.toContain("confidence");
  expect(text).not.toContain("score");
});

test("what would change the analyst's mind has its own heading", async ({ page }) => {
  await page.route(
    (url) => url.pathname === "/v1/hypotheses/hyp_1",
    (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(hypothesis()) }),
  );
  await page.goto("/hypotheses/hyp_1");

  const missing = page.getByTestId("hypothesis-missing");
  await expect(missing.getByRole("heading", { name: "What is missing" })).toBeVisible();
  await expect(missing).toContainText("The registry filing has not been checked.");
});

test("every revision keeps its own statement", async ({ page }) => {
  await page.route(
    (url) => url.pathname === "/v1/hypotheses/hyp_1",
    (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        hypothesis({
          current: { ...REVISION, version: 2, status: "supported", note: "filing found" },
          revisions: [
            REVISION,
            { ...REVISION, version: 2, status: "supported", note: "filing found" },
          ],
        }),
      ),
    }),
  );
  await page.goto("/hypotheses/hyp_1");

  const revisions = page.getByTestId("hypothesis-revisions");
  await expect(revisions).toContainText("v1");
  await expect(revisions).toContainText("v2");
  // A revision is a snapshot, so the earlier statement is readable here rather
  // than only in an audit payload (spec 09 §3.1).
  await expect(revisions).toContainText(REVISION.statement);
  await expect(page.getByTestId("hypothesis-status")).toHaveText("supported");
});

test("a blank missing-info note is refused in the server's own words", async ({ page }) => {
  // A URL predicate, not a glob: `**/v1/hypotheses` does not match
  // `/v1/hypotheses?case=cas_1`, which is how the list is fetched.
  await page.route(
    (url) => url.pathname === "/v1/hypotheses",
    (route) => {
    if (route.request().method() !== "POST") {
      return route.fulfill({ contentType: "application/json", body: '{"items": []}' });
    }
    return route.fulfill({
      status: 422,
      contentType: "application/problem+json",
      body: JSON.stringify({
        type: "about:blank",
        title: "validation failed",
        status: 422,
        detail:
          "['missing_info'] must contain more than whitespace; a blank note is not a note",
        path: "actions.open_hypothesis.submission_criteria.required_text_is_substantive",
      }),
    });
    },
  );

  await page.goto("/cases/cas_1");
  // Wait for the sign-in round trip to finish before touching the page: the
  // stub IdP does a real document redirect, and a locator read that races it
  // dies with "execution context was destroyed".
  await expect(page.getByTestId("case-title")).toBeVisible();
  await page.getByTestId("hypothesis-statement-input").fill("They are one enterprise.");
  // The browser's own `required` stops an empty field, so the blank case is
  // whitespace — which is exactly the hole the fourth criterion closes.
  await page.getByTestId("hypothesis-missing-input").fill("   ");
  await page.getByTestId("hypothesis-open").click();

  await expect(page.getByTestId("hypothesis-open-error")).toContainText(
    "a blank note is not a note",
  );
});

test("the missing-info field is labelled as what it is", async ({ page }) => {
  await page.route(
    (url) => url.pathname === "/v1/hypotheses",
    (route) =>
      route.fulfill({ contentType: "application/json", body: '{"items": []}' }),
  );
  await page.goto("/cases/cas_1");
  // Wait for the sign-in round trip to finish before touching the page: the
  // stub IdP does a real document redirect, and a locator read that races it
  // dies with "execution context was destroyed".
  await expect(page.getByTestId("case-title")).toBeVisible();

  // "Notes" would invite a blank. The label is the first line of defence, and
  // the criterion is the second.
  await expect(page.getByTestId("hypothesis-form")).toContainText(
    "What would change your mind (required)",
  );
});

test("a lead moves through its statuses from the case screen", async ({ page }) => {
  const task = {
    task_id: "tsk_1",
    case_id: "cas_1",
    kind: "lead",
    title: "Check the registry filing",
    detail: null,
    status: "open",
    owner: null,
    due_date: null,
    hypothesis_id: null,
    created_by: "dev-analyst",
    created_at: "2026-08-02T09:00:00Z",
    updated_at: "2026-08-02T09:00:00Z",
    closed_at: null,
  };
  let status = "open";
  const moves: string[] = [];

  await page.route(
    (url) => url.pathname === "/v1/hypotheses",
    (route) =>
      route.fulfill({ contentType: "application/json", body: '{"items": []}' }),
  );
  await page.route(
    (url) => url.pathname === "/v1/tasks",
    (route) =>
      route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ items: [{ ...task, status }] }),
      }),
  );
  await page.route("**/v1/tasks/tsk_1", async (route) => {
    const body = route.request().postDataJSON() as { status?: string };
    if (body?.status) {
      moves.push(body.status);
      status = body.status;
    }
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ ...task, status }),
    });
  });

  await page.goto("/cases/cas_1");
  // Wait for the sign-in round trip to finish before touching the page: the
  // stub IdP does a real document redirect, and a locator read that races it
  // dies with "execution context was destroyed".
  await expect(page.getByTestId("case-title")).toBeVisible();
  await expect(page.getByTestId("tasks-open")).toContainText("Check the registry filing");

  await page.getByTestId("task-status-tsk_1").selectOption("in_progress");
  await expect(page.getByTestId("tasks-in_progress")).toContainText("Check the registry");
  await page.getByTestId("task-status-tsk_1").selectOption("done");
  await expect(page.getByTestId("tasks-done")).toContainText("Check the registry");

  expect(moves).toEqual(["in_progress", "done"]);
});

test("every status is offered from every status", async ({ page }) => {
  const task = {
    task_id: "tsk_2",
    case_id: "cas_1",
    kind: "task",
    title: "Already finished",
    detail: null,
    status: "done",
    owner: "dev-analyst",
    due_date: null,
    hypothesis_id: null,
    created_by: "dev-analyst",
    created_at: "2026-08-02T09:00:00Z",
    updated_at: "2026-08-02T09:00:00Z",
    closed_at: "2026-08-03T09:00:00Z",
  };
  await page.route(
    (url) => url.pathname === "/v1/hypotheses",
    (route) =>
      route.fulfill({ contentType: "application/json", body: '{"items": []}' }),
  );
  await page.route(
    (url) => url.pathname === "/v1/tasks",
    (route) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [task] }) }),
  );

  await page.goto("/cases/cas_1");
  // Wait for the sign-in round trip to finish before touching the page: the
  // stub IdP does a real document redirect, and a locator read that races it
  // dies with "execution context was destroyed".
  await expect(page.getByTestId("case-title")).toBeVisible();
  // No transition graph: a finished task can be reopened, and the absence of a
  // state machine is the design rather than an omission (plan §2).
  const options = await page
    .getByTestId("task-status-tsk_2")
    .locator("option")
    .allTextContents();
  expect(options).toEqual(["open", "in_progress", "blocked", "done", "dropped"]);
});

test("an unassigned task says so rather than inventing an owner", async ({ page }) => {
  const task = {
    task_id: "tsk_3",
    case_id: "cas_1",
    kind: "task",
    title: "Nobody has picked this up",
    detail: null,
    status: "open",
    owner: null,
    due_date: null,
    hypothesis_id: null,
    created_by: "dev-analyst",
    created_at: "2026-08-02T09:00:00Z",
    updated_at: "2026-08-02T09:00:00Z",
    closed_at: null,
  };
  await page.route(
    (url) => url.pathname === "/v1/hypotheses",
    (route) =>
      route.fulfill({ contentType: "application/json", body: '{"items": []}' }),
  );
  await page.route(
    (url) => url.pathname === "/v1/tasks",
    (route) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [task] }) }),
  );

  await page.goto("/cases/cas_1");
  // Wait for the sign-in round trip to finish before touching the page: the
  // stub IdP does a real document redirect, and a locator read that races it
  // dies with "execution context was destroyed".
  await expect(page.getByTestId("case-title")).toBeVisible();
  // Unassigned is a real state; showing a placeholder owner would make the
  // queue look attended when it is not.
  await expect(page.getByTestId("task-tsk_3")).toContainText("unassigned");
});
