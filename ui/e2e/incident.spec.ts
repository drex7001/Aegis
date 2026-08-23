import { expect, test, type Page } from "@playwright/test";

import { stubGraphRoute, stubIdentityProvider } from "./oidc-stub";
import { ONTOLOGY_VERSION, stubCases, stubVocabulary } from "./workspace-stub";

/**
 * One incident, seen by a person, on three surfaces (T64 — charter exits №1–2).
 *
 * The server half (`tests/integration/test_incident_consistency.py`) proves the
 * three surfaces *agree*. This proves a reader can actually find that out: that
 * the arrest is on the map as an area rather than a pin, on the timeline as a
 * stated range rather than an instant, on the object view with all four
 * participants, and that walking between them carries the window.
 *
 * One fixture, three surfaces. Every stub below is the same incident described
 * once — if the surfaces were seeded separately this test could pass while the
 * product disagreed with itself, which is the failure it exists to catch.
 */

const EVENT_ID = "ent_arrest";
const PLACE_ID = "ent_district";
const WHEN = { earliest: "2019-03-12T00:00:00Z", latest: "2019-03-12T23:59:59Z" };

const PARTICIPANTS = [
  { id: "ent_a", label: "Fictional A", role: "has_arrestee" },
  { id: "ent_b", label: "Fictional B", role: "has_arrestee" },
  { id: "ent_c", label: "Fictional C", role: "has_arrestee" },
  { id: "ent_officer", label: "Inspector Fictional", role: "has_arresting_officer" },
];

/** The district: an administrative area, which must never draw as a point. */
const DISTRICT_GEOMETRY = {
  type: "Polygon",
  coordinates: [
    [
      [79.8, 6.9],
      [80.0, 6.9],
      [80.0, 7.1],
      [79.8, 7.1],
      [79.8, 6.9],
    ],
  ],
};

const PLACE_PROPERTIES = {
  entity_id: PLACE_ID,
  label: "Fictional District",
  entity_type: "location",
  geometry_state: "ok",
  admin_level: "subdivision",
  accuracy_m: null,
  derivation: "admin_unit_boundary",
  geometry_kind: "Polygon",
  claim_id: "clm_geometry",
  handling_code: "open",
  invalid_reason: null,
};

const STAMP = {
  as_of: null as string | null,
  identity_revision_id: 11,
  ontology_version: ONTOLOGY_VERSION,
};

function claim(overrides: Record<string, unknown>) {
  return {
    claim: {
      claim_id: "clm_x",
      subject_id: EVENT_ID,
      predicate: "has_arrestee",
      object_id: null,
      object_value: null,
      assertion_type: "reported",
      record_id: "rec_1",
      excerpt: null,
      recorded_at: "2026-01-01T00:00:00Z",
      retracted_at: null,
      retraction_reason: null,
      handling_code: "open",
      valid_from: null,
      valid_to: null,
      event_time_earliest: WHEN.earliest,
      event_time_latest: WHEN.latest,
      ...(overrides.claim as Record<string, unknown>),
    },
    grading: {
      reliability: "generally_reliable",
      credibility: "probably_true",
      verification: "unverified",
      analytic_confidence: null,
    },
    source: { source_id: "src_1", name: "Fictional Gazette", source_type: "open_source" },
    record: { record_id: "rec_1", source_id: "src_1", status: "landed" },
    corroborated_by: [],
    contradicted_by: [],
    subject_mention: null,
    object_mention: null,
  };
}

async function stubIncident(page: Page) {
  // The object view: the event, with every participation claim.
  await page.route(`**/v1/entities/${EVENT_ID}`, (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        entity: { entity_id: EVENT_ID, entity_type: "arrest", label: "An arrest" },
        resolved_entity_id: EVENT_ID,
        truncated: false,
        inbound_truncated: false,
        stamp: STAMP,
        claims_by_predicate: {
          has_arrestee: PARTICIPANTS.filter((p) => p.role === "has_arrestee").map((p) =>
            claim({ claim: { claim_id: `clm_${p.id}`, object_id: p.id } }),
          ),
          has_arresting_officer: [
            claim({
              claim: {
                claim_id: "clm_officer",
                predicate: "has_arresting_officer",
                object_id: "ent_officer",
              },
            }),
          ],
          took_place_at: [
            claim({
              claim: {
                claim_id: "clm_place",
                predicate: "took_place_at",
                object_id: PLACE_ID,
              },
            }),
          ],
        },
        inbound_claims_by_predicate: {},
      }),
    }),
  );
  await page.route("**/v1/entities/*/cases", (route) =>
    route.fulfill({ contentType: "application/json", body: "[]" }),
  );

  // The map: the incident at its district.
  await page.route("**/v1/geo/events*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            id: `${EVENT_ID}:${PLACE_ID}:took_place_at`,
            geometry: DISTRICT_GEOMETRY,
            properties: {
              ...PLACE_PROPERTIES,
              event_id: EVENT_ID,
              event_label: "An arrest",
              event_type: "arrest",
              place_id: PLACE_ID,
              place_role: "took_place_at",
              time_intervals: [{ ...WHEN, claim_id: "clm_place" }],
              participant_count: PARTICIPANTS.length,
            },
          },
        ],
        next_cursor: null,
        stamp: STAMP,
      }),
    }),
  );
  await page.route("**/v1/geo/locations*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        type: "FeatureCollection",
        features: [
          { type: "Feature", id: PLACE_ID, geometry: DISTRICT_GEOMETRY, properties: PLACE_PROPERTIES },
        ],
        next_cursor: null,
        stamp: STAMP,
      }),
    }),
  );

  // The timeline: one row per assertion — four participations and a place.
  await page.route("**/v1/timeline*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          ...PARTICIPANTS.map((p) => ({
            claim_id: `clm_${p.id}`,
            subject_id: EVENT_ID,
            subject_label: "An arrest",
            subject_type: "arrest",
            predicate: p.role,
            object_id: p.id,
            object_label: p.label,
            object_value: null,
            earliest: WHEN.earliest,
            latest: WHEN.latest,
            certainty: "bounded",
            record_id: "rec_1",
            handling_code: "open",
            recorded_at: "2026-01-01T00:00:00Z",
          })),
          {
            claim_id: "clm_place",
            subject_id: EVENT_ID,
            subject_label: "An arrest",
            subject_type: "arrest",
            predicate: "took_place_at",
            object_id: PLACE_ID,
            object_label: "Fictional District",
            object_value: null,
            earliest: WHEN.earliest,
            latest: WHEN.latest,
            certainty: "bounded",
            record_id: "rec_1",
            handling_code: "open",
            recorded_at: "2026-01-01T00:00:00Z",
          },
        ],
        next_cursor: null,
        undated_count: 0,
        stamp: STAMP,
      }),
    }),
  );
}

test.beforeEach(async ({ page }) => {
  await stubIdentityProvider(page);
  await stubGraphRoute(page);
  await stubVocabulary(page, { version: ONTOLOGY_VERSION });
  await stubCases(page);
  await stubIncident(page);
});

test("the incident's object view shows all four participants", async ({ page }) => {
  await page.goto(`/entities/${EVENT_ID}`);
  await expect(page.getByTestId("object-view")).toBeVisible();

  const links = page.getByTestId("object-view-links");
  await expect(links.getByTestId("predicate-has_arrestee")).toBeVisible();
  await expect(links.getByTestId("predicate-has_arresting_officer")).toBeVisible();
  await expect(links.getByTestId("predicate-took_place_at")).toBeVisible();
  // Charter exit №2: three arrestees, plus the officer — an event with more
  // than three participants, rendered through the generic screen with no
  // type-specific code.
  await expect(
    links.getByTestId("predicate-has_arrestee").locator("[data-testid^='claim-']"),
  ).toHaveCount(3);
});

test("the same incident is an area on the map, never a pin", async ({ page }) => {
  await page.goto("/map");
  await expect(page.getByTestId("map-canvas")).toBeVisible();

  // Charter exit №1's precision half, on the incident itself: the arrest is
  // known to a district, and a district is not a position.
  const feature = page.getByTestId(`map-feature-${PLACE_ID}`);
  await expect(feature).toHaveAttribute("data-mark", "area");
  await expect(feature).toContainText("Administrative area");
});

test("the same incident is a stated range on the timeline, never an instant", async ({
  page,
}) => {
  await page.goto("/timeline");
  const rows = page.getByTestId("timeline-items").locator("li");
  // One row per assertion — four participations and a place. No row for "the
  // event", because an event appears through its claims (spec 10 §11.1).
  await expect(rows).toHaveCount(5);

  const first = page.getByTestId("timeline-item-clm_ent_a");
  await expect(first).toHaveAttribute("data-certainty", "bounded");
  await expect(first).toContainText("2019-03-12 → 2019-03-12");
});

/*
 * KNOWN LOCAL SENSITIVITY, recorded at T71 so the next person to see a red run
 * here does not spend an afternoon on it.
 *
 * The two tests below navigate from `/map` — the heaviest view in the
 * workspace — and time out under **local** parallel load. Measured across six
 * full local runs they failed in three, all of them while something else was
 * saturating the machine, and passed in every isolated run. The CI workspace
 * job has been green on every run since T64 landed this file.
 *
 * Deliberately **not** given a retry. The project forbids retries added to get
 * green, and a retry here would hide the one signal worth having: if this ever
 * fails in CI, the classification changes and it is a defect rather than a
 * machine under load.
 */
test("one window carries the incident across all three surfaces", async ({ page }) => {
  await page.goto("/map");
  await page.getByTestId("map-time-filter-from").fill("2019-01-01");
  await page.getByTestId("map-time-filter-to").fill("2019-12-31");
  await page.getByTestId("map-time-filter-apply").click();
  await expect(page.getByTestId(`map-feature-${PLACE_ID}`)).toBeVisible();

  await page.getByTestId("surface-link-timeline").click();
  await expect(page).toHaveURL(/from=2019-01-01/);
  await expect(page.getByTestId("timeline-item-clm_ent_a")).toBeVisible();

  await page.getByTestId("surface-link-graph").click();
  await expect(page).toHaveURL(/from=2019-01-01/);
  await expect(page.getByTestId("graph-time-filter-from")).toHaveValue("2019-01-01");
});

test("the map's selection reaches the timeline and the object view", async ({ page }) => {
  await page.goto(`/map?selected=${PLACE_ID}`);
  await expect(page.getByTestId("map-detail")).toContainText("Fictional District");
  await expect(page.getByTestId("map-detail-admin")).toHaveText("subdivision");
  await expect(page.getByTestId("map-detail-derivation")).toHaveText("admin_unit_boundary");

  await page.getByTestId("surface-link-timeline").click();
  await expect(page.getByTestId("timeline-selection")).toBeVisible();
});

test("every surface says what it was computed against", async ({ page }) => {
  await page.goto("/map");
  await expect(page.getByTestId("map-stamp")).toContainText("identity revision 11");

  await page.getByTestId("surface-link-timeline").click();
  await expect(page.getByTestId("timeline-stamp")).toContainText("identity revision 11");
});
