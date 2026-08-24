import { expect, test } from "@playwright/test";

import { stubGraphRoute, stubIdentityProvider } from "./oidc-stub";
import { stubEntityRoutes, stubWithheldEntity } from "./object-view-stub";
import { ONTOLOGY_VERSION, stubCases, stubVocabulary } from "./workspace-stub";

/**
 * T44's acceptance criteria as browser journeys.
 *
 * The claim: **one component renders any object type**, and the divisions it
 * draws — property vs. link, and which category a link belongs to — come from
 * the generated descriptors rather than from the response or from a branch in
 * React. Person and organization go through the same code here, which is why
 * both are exercised with the same assertions where they overlap.
 *
 * The other half is Article VIII: two dates of birth render **side by side**
 * with a `contradicts` badge, not one value with the disagreement folded away.
 */

test.beforeEach(async ({ page }) => {
  await stubIdentityProvider(page);
  await stubGraphRoute(page);
  await stubVocabulary(page, { version: ONTOLOGY_VERSION });
  await stubCases(page);
});

test("a person renders with properties, links and sources", async ({ page }) => {
  await stubEntityRoutes(page);
  await page.goto("/entities/ent_person");

  await expect(page.getByTestId("object-view-title")).toHaveText("Fictional A");
  // The type is a link to its schema page — the ontology reads from both sides.
  await expect(page.getByTestId("object-view-type")).toHaveText("Person");

  const properties = page.getByTestId("object-view-properties");
  // `known_as` and `born_on` have literal objects, so they are properties...
  await expect(properties.getByTestId("predicate-known_as")).toBeVisible();
  await expect(properties.getByTestId("predicate-born_on")).toBeVisible();
  // ...and the caption is the descriptor's label, not the raw predicate name.
  await expect(properties.getByRole("heading", { name: /Known as/ })).toBeVisible();

  // `member_of` has an entity object, so it is a link and must not be here.
  await expect(properties.getByTestId("predicate-member_of")).toHaveCount(0);
  await expect(
    page.getByTestId("object-view-links").getByTestId("predicate-member_of"),
  ).toBeVisible();

  await expect(page.getByTestId("object-view-sources")).toContainText("Fictional Gazette");
  await expect(page.getByTestId("object-view-sources")).toContainText("Fictional Registry");
});

test("two disagreeing dates of birth render side by side with their badge", async ({
  page,
}) => {
  await stubEntityRoutes(page);
  await page.goto("/entities/ent_person");

  const group = page.getByTestId("predicate-born_on");
  await expect(group).toHaveAttribute("data-contested", "true");
  await expect(group.getByTestId("contradicts-badge")).toBeVisible();
  // Both values, not one — Article VIII is that neither has been chosen.
  await expect(group).toContainText("1979-04-02");
  await expect(group).toContainText("1981-11-17");
  await expect(group).toContainText("neither has been chosen");

  // ...and an uncontested group is not marked, so the mark means something.
  await expect(page.getByTestId("predicate-known_as")).toHaveAttribute(
    "data-contested",
    "false",
  );
});

test("an organization renders through the same component", async ({ page }) => {
  await stubEntityRoutes(page);
  await page.goto("/entities/ent_org");

  await expect(page.getByTestId("object-view")).toBeVisible();
  await expect(page.getByTestId("object-view-title")).toHaveText("Fictional Co");
  await expect(page.getByTestId("object-view-type")).toHaveText("Organization");
  await expect(page.getByTestId("object-view-properties")).toContainText("Fictional Co");
});

test("one claim reaches both pages: a link here, a reference there", async ({ page }) => {
  /*
   * T57, spec 10 §13. `member_of` points from the person to the organization,
   * so before the inbound set the organization's page showed no members at all.
   * Phase 5 made this acute rather than creating it — participation claims are
   * subjected to the *event*, so an arrest would have listed its participants
   * and each participant's page would have shown no arrest.
   */
  await stubEntityRoutes(page);

  await page.goto("/entities/ent_person");
  await expect(
    page.getByTestId("object-view-links").getByTestId("predicate-member_of"),
  ).toBeVisible();
  // Nothing refers to this person, and the region still renders saying so — an
  // absent heading would read as "the question was never asked".
  await expect(page.getByTestId("object-view-inbound")).toContainText(
    "Nothing you are cleared to see refers to this",
  );

  await page.goto("/entities/ent_org");
  const inbound = page.getByTestId("object-view-inbound");
  await expect(inbound.getByTestId("predicate-member_of")).toBeVisible();
  // Under "Referenced by", not under Links: who asserted what about whom is the
  // distinction a reader most needs, and merging the two would erase it.
  await expect(page.getByTestId("object-view-links")).toContainText(
    "No links you are cleared to see",
  );
});

test("links are grouped by the ontology's own category", async ({ page }) => {
  await stubEntityRoutes(page);
  await page.goto("/entities/ent_person");

  const { PREDICATES, CATEGORIES } = await import("../src/api/ontology");
  // Read the expected group from the descriptors, so a re-categorization in the
  // ontology moves this test with it rather than breaking it.
  const category = PREDICATES.member_of.category as keyof typeof CATEGORIES;
  await expect(page.getByTestId("object-view-links")).toContainText(
    CATEGORIES[category].label,
  );
});

test("a viewer with no visible cases sees the same thing as an entity in none", async ({
  page,
}) => {
  // H-18: the route returns an identical body for both, and the UI must not
  // distinguish them — no count, no "some hidden", no different wording.
  await stubEntityRoutes(page, { cases: [] });
  await page.goto("/entities/ent_person");

  await expect(page.getByTestId("object-view-no-cases")).toHaveText("Not part of any case.");
  await expect(page.getByTestId("object-view-cases")).toHaveCount(0);
  const body = await page.getByTestId("object-view").innerText();
  for (const tell of ["hidden", "restricted", "more case"]) {
    expect(body.toLowerCase()).not.toContain(tell);
  }
});

test("visible cases are listed", async ({ page }) => {
  await stubEntityRoutes(page, {
    cases: [{ case_id: "cas_1", title: "Fictional enquiry", status: "open" }],
  });
  await page.goto("/entities/ent_person");

  await expect(page.getByTestId("object-view-cases")).toContainText("Fictional enquiry");
  await expect(page.getByTestId("object-view-no-cases")).toHaveCount(0);
});

test("an entity you cannot see reads as absence, not as a refusal", async ({ page }) => {
  await stubEntityRoutes(page);
  await page.goto("/entities/ent_missing");

  const error = page.getByTestId("object-view-error");
  await expect(error).toBeVisible();
  // 404 is both "absent" and "not for you" by design (spec 06 default 4), so
  // the wording must not turn it into a permission prompt.
  await expect(error).toContainText("Nothing here");
  const text = (await error.innerText()).toLowerCase();
  for (const tell of ["forbidden", "permission", "not allowed", "denied"]) {
    expect(text).not.toContain(tell);
  }
});

test("an entity of a type this bundle has never seen still renders", async ({ page }) => {
  /*
   * The other side of the version banner (spec 09 §6.3). When the server is
   * ahead of the bundle, an entity can arrive with a type the compiled
   * descriptors do not contain — and the object view must degrade to something
   * readable rather than a blank page or a crash, because the *data* is correct
   * and only the captions are missing.
   *
   * The descriptor half of the charter's fourth exit criterion is proved at the
   * contract layer (`tests/contract/test_ontology_to_screen.py`): the bundle is
   * built from the shipped ontology, so a type added to a fixture cannot appear
   * in it. This is the runtime half — the component's behaviour when it meets
   * one anyway.
   */
  // The realistic shape of this: the server is ahead, so the vocabulary route
  // reports a version the bundle was not built against *and* serves an entity
  // whose type the bundle does not know. The banner reads the route, not the
  // response stamp — the stamp says what an answer was computed against, which
  // is a different question.
  await stubVocabulary(page, { version: "9.9.9" });
  await page.route(
    (url) => url.pathname === "/v1/entities/ent_unknown_type",
    (route) =>
      route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          entity: {
            entity_id: "ent_unknown_type",
            entity_type: "not_in_this_bundle",
            label: "Fictional Unknown",
          },
          resolved_entity_id: "ent_unknown_type",
          truncated: false,
          stamp: { as_of: null, identity_revision_id: 7, ontology_version: "9.9.9" },
          claims_by_predicate: {},
        }),
      }),
  );
  await page.goto("/entities/ent_unknown_type");

  await expect(page.getByTestId("object-view")).toBeVisible();
  // The label is the server's, so the heading is right even when the type is
  // unknown; the type falls back to its raw name rather than to nothing.
  await expect(page.getByTestId("object-view-title")).toHaveText("Fictional Unknown");
  await expect(page.getByTestId("object-view-type")).toHaveText("not_in_this_bundle");
  // ...and the version banner is what tells the reader why.
  await expect(page.getByTestId("ontology-mismatch")).toBeVisible();
});

test("the object view reads no endpoint the P2 screens do not already have", async ({
  page,
}) => {
  await stubEntityRoutes(page);
  const calls: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/v1/")) calls.push(url.pathname);
  });

  await page.goto("/entities/ent_person");
  await expect(page.getByTestId("object-view-title")).toBeVisible();

  // `/v1/entities/{id}/cases` is the one addition T44 makes, and it exists
  // because H-18 requires the list to be built server-side from readable rows.
  // `/v1/cases` and `/v1/ontology/vocabulary` are the shell's, not this
  // screen's — the rail and the version banner call them on every page.
  expect([...new Set(calls)].sort()).toEqual([
    "/v1/cases",
    "/v1/entities/ent_person",
    "/v1/entities/ent_person/cases",
    "/v1/ontology/vocabulary",
  ]);
});

/**
 * The `marked` response mode, on the screen a person actually reads (T79).
 *
 * The reason this needs a browser test rather than only an API one: the whole
 * argument for marking is about what a *reader* concludes from a gap. An
 * assertion that the JSON contains a marker does not tell you the page shows
 * it, and the failure mode here — the marker silently not rendering — looks
 * exactly like the old behaviour it was added to fix.
 */
test("a withheld predicate is named on the page, with no value beside it", async ({
  page,
}) => {
  await stubWithheldEntity(page);
  await page.goto("/entities/ent_person");

  const properties = page.getByTestId("object-view-properties");
  // The readable property is still rendered normally.
  await expect(properties.getByTestId("predicate-known_as")).toBeVisible();
  // The withheld one is named — and is not a claim group, because there is no
  // claim.
  await expect(properties.getByTestId("predicate-has_nic")).toHaveCount(0);
  const marker = page.getByTestId("object-view-withheld");
  await expect(marker).toBeVisible();
  await expect(marker).toContainText("withheld at your clearance");
  await expect(marker.locator("[data-predicate='has_nic']")).toBeVisible();
});

test("the empty-properties notice does not claim there is nothing when there is a marker", async ({
  page,
}) => {
  /*
   * The regression that would otherwise be invisible: "No property claims you
   * are cleared to see" beside a marker saying a field exists is the page
   * contradicting itself, and it is what the naive `properties.length === 0`
   * check produced.
   */
  await stubWithheldEntity(page);
  await page.goto("/entities/ent_person");

  await expect(page.getByTestId("object-view-properties")).not.toContainText(
    "No property claims you are cleared to see",
  );
});
