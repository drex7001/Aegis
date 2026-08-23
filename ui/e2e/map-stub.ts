import type { Page } from "@playwright/test";

/**
 * `/v1/geo/*` at the network boundary (T60).
 *
 * The fixture is chosen to make the charter's third criterion visible: a
 * `country`-level location beside an exact one, so "never a point at any zoom"
 * is a comparison rather than an assertion about an empty map. Nothing here
 * stubs an ontology endpoint — the mark rules read the generated geo
 * vocabularies compiled into the bundle, so stubbing them would be testing the
 * stub.
 */

export const STAMP = {
  as_of: null as string | null,
  identity_revision_id: 11,
  ontology_version: "2.1.0",
};

function feature(
  id: string,
  geometry: Record<string, unknown> | null,
  properties: Record<string, unknown>,
) {
  return {
    type: "Feature",
    id,
    geometry,
    properties: {
      entity_id: id,
      label: id,
      entity_type: "location",
      geometry_state: "ok",
      admin_level: "not_administrative",
      accuracy_m: null,
      derivation: "instrument_fix",
      geometry_kind: geometry ? (geometry.type as string) : null,
      claim_id: `clm_${id}`,
      handling_code: "open",
      invalid_reason: null,
      ...properties,
    },
  };
}

/** A whole country, as a boundary polygon. Must never draw as a point. */
export const COUNTRY = feature(
  "ent_country",
  {
    type: "Polygon",
    coordinates: [
      [
        [79.5, 5.9],
        [81.9, 5.9],
        [81.9, 9.8],
        [79.5, 9.8],
        [79.5, 5.9],
      ],
    ],
  },
  {
    label: "Fictionland",
    admin_level: "country",
    derivation: "admin_unit_boundary",
    geometry_kind: "Polygon",
  },
);

/** A city, known only as its centroid — a circle of its stated radius. */
export const CITY = feature(
  "ent_city",
  { type: "Point", coordinates: [80.2, 7.3] },
  {
    label: "Fictional City",
    admin_level: "locality",
    derivation: "admin_unit_centroid",
    accuracy_m: 6000,
    geometry_kind: "Point",
  },
);

/** A building, matched to an address. The one thing that draws as a pin. */
export const BUILDING = feature(
  "ent_building",
  { type: "Point", coordinates: [80.05, 7.05] },
  {
    label: "Fictional Warehouse",
    derivation: "address_match",
    accuracy_m: 12,
    geometry_kind: "Point",
  },
);

/** Geometry exists and this viewer may not read it. Listed, never placed. */
export const WITHHELD = feature("ent_withheld", null, {
  label: "A place you may not locate",
  geometry_state: "none_permitted",
  admin_level: null,
  derivation: null,
  geometry_kind: null,
  claim_id: null,
  handling_code: null,
});

export const EVENT = {
  ...feature(
    "ent_event:ent_city:took_place_at",
    { type: "Point", coordinates: [80.2, 7.3] },
    {
      entity_id: "ent_city",
      label: "Fictional City",
      admin_level: "locality",
      derivation: "admin_unit_centroid",
      accuracy_m: 6000,
      geometry_kind: "Point",
      event_id: "ent_event",
      event_label: "An arrest",
      event_type: "arrest",
      place_id: "ent_city",
      place_role: "took_place_at",
      time_intervals: [
        {
          earliest: "2019-03-12T00:00:00Z",
          latest: "2019-03-12T23:59:59Z",
          claim_id: "clm_event",
        },
      ],
      participant_count: 3,
    },
  ),
};

export async function stubGeoRoutes(page: Page): Promise<void> {
  await page.route("**/v1/geo/locations*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        type: "FeatureCollection",
        features: [COUNTRY, CITY, BUILDING, WITHHELD],
        next_cursor: null,
        stamp: STAMP,
      }),
    }),
  );
  await page.route("**/v1/geo/events*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        type: "FeatureCollection",
        features: [EVENT],
        next_cursor: null,
        stamp: STAMP,
      }),
    }),
  );
}
