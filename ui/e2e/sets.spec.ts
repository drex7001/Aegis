import { expect, test, type Page } from "@playwright/test";

import { stubIdentityProvider } from "./oidc-stub";

/**
 * The set builder as a browser journey (T71).
 *
 * The T71 acceptance criterion is that a set is built, composed and shared
 * "entirely from the workspace through typed SDK calls", and that the builder
 * "offers only grammar the spec defines". Both are checked here, along with
 * the thing a screen is uniquely able to get wrong: implying that a set has
 * results.
 *
 * It does not. A set stores a **question**; members are computed per caller,
 * per evaluation. The panel labels them "as you can see them" and shows the
 * evaluation digest, because two people sharing one set correctly see
 * different members — and a UI that hid that would be teaching a model the
 * system does not have.
 *
 * Fictional fixtures throughout.
 */

const SET_ID = "oset_fictional_1";
const PERSON = "ent_fictional_person";

const SAVED = {
  set_id: SET_ID,
  name: "Fictional couriers",
  description: null,
  case_id: null,
  owner: "user:analyst",
  created_at: "2026-08-23T10:00:00Z",
  latest: {
    set_id: SET_ID,
    version: 1,
    ast: { kind: "type", object_type: "person", interface: null },
    ontology_version: "2.1.0",
    track_interface_members: false,
    as_of: null,
    as_of_revision: null,
    note: null,
    created_by: "user:analyst",
    created_at: "2026-08-23T10:00:00Z",
  },
};

const EVALUATION = {
  set_id: SET_ID,
  version: 1,
  members: [
    { entity_id: PERSON, label: "Fictional LIMA", entity_type: "person" },
  ],
  truncated: false,
  evaluation_digest: "a1b2c3d4e5f600112233445566778899aabbccddeeff00112233445566778899",
};

async function stubSets(page: Page): Promise<{ created: unknown[] }> {
  const created: unknown[] = [];
  let saved = false;

  await page.route("**/v1/object-sets", async (route) => {
    if (route.request().method() === "POST") {
      created.push(route.request().postDataJSON());
      saved = true;
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(SAVED),
      });
    }
    return route.fulfill({
      contentType: "application/json",
      // No total, in either state — the stub keeps the property the real
      // route has, so the panel cannot pass a test the API would fail.
      body: JSON.stringify({ items: saved ? [SAVED] : [], next_cursor: null }),
    });
  });

  await page.route("**/v1/object-sets/*/evaluate**", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(EVALUATION) }),
  );
  await page.route("**/v1/object-sets/*/share", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(SAVED) }),
  );
  return { created };
}

async function openBuilder(page: Page): Promise<void> {
  await stubIdentityProvider(page);
  await page.goto("/sets");
  await expect(page.getByTestId("set-builder")).toBeVisible();
}

test("the builder offers only vocabulary the ontology declares", async ({ page }) => {
  await stubSets(page);
  await openBuilder(page);

  // The menus are fed from the generated descriptors, so a second domain's
  // types appear here with no change to the workspace (Article XIV). There is
  // deliberately no free-text condition box: that would be a second grammar.
  const types = page.getByTestId("add-type-filter");
  await expect(types.locator("option", { hasText: "Person" })).toHaveCount(1);
  await expect(types.locator("option", { hasText: "Wizard" })).toHaveCount(0);
  await expect(page.getByTestId("add-predicate-filter")).toBeVisible();
});

test("a set is built and saved from the workspace", async ({ page }) => {
  const stub = await stubSets(page);
  await openBuilder(page);

  await page.getByTestId("set-name").fill("Fictional couriers");
  await page.getByTestId("add-type-filter").selectOption("person");
  await expect(page.getByTestId("filter-0")).toContainText("type = person");

  await page.getByTestId("save-set").click();
  await expect(page.getByTestId(`set-${SET_ID}`)).toBeVisible();

  // The AST reached the API as the grammar's own shape, not as text.
  expect(stub.created).toHaveLength(1);
  expect(stub.created[0]).toMatchObject({
    name: "Fictional couriers",
    ast: { kind: "type", object_type: "person" },
    track_interface_members: false,
  });
});

test("following future interface members is off unless asked for", async ({ page }) => {
  const stub = await stubSets(page);
  await openBuilder(page);

  await page.getByTestId("set-name").fill("Places");
  await page.getByTestId("add-type-filter").selectOption("location");
  // ADR-054: a saved set that widens when a domain module lands changes the
  // meaning of findings people already acted on, so the default is off and the
  // opt-in is a deliberate act.
  await expect(page.getByTestId("track-interface-members")).not.toBeChecked();
  await page.getByTestId("track-interface-members").check();
  await page.getByTestId("save-set").click();

  expect(stub.created[0]).toMatchObject({ track_interface_members: true });
});

test("evaluating shows members as this caller sees them, with the digest", async ({
  page,
}) => {
  await stubSets(page);
  await openBuilder(page);

  await page.getByTestId("set-name").fill("Fictional couriers");
  await page.getByTestId("add-type-filter").selectOption("person");
  await page.getByTestId("save-set").click();
  await page.getByTestId(`run-${SET_ID}`).click();

  await expect(page.getByTestId("set-results")).toContainText("as you can see them");
  await expect(page.getByTestId(`member-${PERSON}`)).toHaveText("Fictional LIMA");
  // The digest is what makes "two people, one set, different answers" legible
  // before somebody compares two findings and wonders why they disagree.
  await expect(page.getByTestId("evaluation-digest")).toHaveText("a1b2c3d4e5f6");
});

test("the results panel renders no count of what it did not show", async ({ page }) => {
  await stubSets(page);
  await openBuilder(page);

  await page.getByTestId("set-name").fill("Fictional couriers");
  await page.getByTestId("add-type-filter").selectOption("person");
  await page.getByTestId("save-set").click();
  await page.getByTestId(`run-${SET_ID}`).click();

  const panel = page.getByTestId("set-results");
  await expect(panel).not.toContainText("1 of");
  await expect(panel).not.toContainText("total");
});

test("a set can be shared from the workspace", async ({ page }) => {
  await stubSets(page);
  await openBuilder(page);

  await page.getByTestId("set-name").fill("Fictional couriers");
  await page.getByTestId("add-type-filter").selectOption("person");
  await page.getByTestId("save-set").click();

  await page.getByTestId(`share-input-${SET_ID}`).fill("user:colleague");
  await page.getByTestId(`share-${SET_ID}`).click();
  await expect(page.getByTestId(`share-input-${SET_ID}`)).toHaveValue("");
});

test("an empty list says nothing you can see, not nothing exists", async ({ page }) => {
  await stubSets(page);
  await openBuilder(page);

  // An unshared set is absent from the list, so "no sets" and "no sets you may
  // see" are the same response — and the wording has to be the honest one.
  await expect(page.getByTestId("no-sets")).toHaveText("No sets you can see.");
});
