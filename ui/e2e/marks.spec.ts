import { expect, test } from "@playwright/test";

import { GEO_ADMIN_LEVELS, GEO_DERIVATIONS, GEO_NOT_ADMINISTRATIVE } from "../src/api/ontology";
import { markFor, POINT_ACCURACY_THRESHOLD_M, type MarkInput } from "../src/views/map/marks";

/**
 * The whole `admin_level × derivation × geometry kind` matrix (T60, spec 10 §9).
 *
 * The charter's third criterion — "a location known only at admin-area level
 * never renders as a point" — is enforced in three places, and this is the one
 * that proves *coverage* rather than wiring:
 *
 * * the **store** refuses the claim that would license a false pin (§4.3);
 * * `markFor` has exactly **one** point branch, unreachable for an
 *   administrative level;
 * * the browser journey checks it survives at three zoom levels.
 *
 * A browser test can only assert the cases it thinks to try. This enumerates
 * every case there is, from the generated vocabularies — so a new derivation
 * added to the ontology fails here until someone decides how it draws.
 */

const KINDS = ["Point", "MultiPoint", "LineString", "Polygon", "MultiPolygon"];
const ADMIN_VALUES = [...GEO_ADMIN_LEVELS, GEO_NOT_ADMINISTRATIVE];

function every(): MarkInput[] {
  const inputs: MarkInput[] = [];
  for (const adminLevel of ADMIN_VALUES) {
    for (const derivation of GEO_DERIVATIONS) {
      for (const geometryKind of KINDS) {
        for (const accuracyM of [null, 10, 5000]) {
          inputs.push({
            geometryState: "ok",
            geometryKind,
            adminLevel: adminLevel as MarkInput["adminLevel"],
            derivation: derivation as MarkInput["derivation"],
            accuracyM,
          });
        }
      }
    }
  }
  return inputs;
}

test("no administrative level can produce a point mark, in any combination", () => {
  const offenders = every()
    .filter((input) => input.adminLevel !== GEO_NOT_ADMINISTRATIVE)
    .filter((input) => markFor(input).kind === "point");

  expect(offenders, "an administrative area drawn as a point").toEqual([]);
});

test("the point branch is reachable, and only under the conditions §9.1 names", () => {
  // If nothing reached it the test above would pass vacuously, which is the
  // failure mode an exhaustive negative check invites.
  const points = every().filter((input) => markFor(input).kind === "point");
  expect(points.length).toBeGreaterThan(0);

  for (const input of points) {
    expect(input.adminLevel).toBe(GEO_NOT_ADMINISTRATIVE);
    expect(["instrument_fix", "source_stated_coordinates", "address_match"]).toContain(
      input.derivation,
    );
    expect(["Point", "MultiPoint", "LineString"]).toContain(input.geometryKind);
    expect(input.accuracyM === null || input.accuracyM <= POINT_ACCURACY_THRESHOLD_M).toBe(true);
  }
});

test("a stated position with a wide radius becomes a circle, not a pin", () => {
  const tight = markFor({
    geometryState: "ok",
    geometryKind: "Point",
    adminLevel: GEO_NOT_ADMINISTRATIVE,
    derivation: "instrument_fix",
    accuracyM: 10,
  });
  const loose = markFor({
    geometryState: "ok",
    geometryKind: "Point",
    adminLevel: GEO_NOT_ADMINISTRATIVE,
    derivation: "instrument_fix",
    accuracyM: 5000,
  });
  expect(tight.kind).toBe("point");
  // A "position" known to ±5 km is an area wearing a coordinate.
  expect(loose.kind).toBe("circle");
  expect(loose.radiusM).toBe(5000);
});

test("a centroid is a circle of its stated radius, whatever the zoom", () => {
  const mark = markFor({
    geometryState: "ok",
    geometryKind: "Point",
    adminLevel: "locality",
    derivation: "admin_unit_centroid",
    accuracyM: 4200,
  });
  expect(mark.kind).toBe("circle");
  expect(mark.radiusM).toBe(4200);
});

test("an analyst's estimate is always dashed", () => {
  for (const geometryKind of KINDS) {
    const mark = markFor({
      geometryState: "ok",
      geometryKind,
      adminLevel: GEO_NOT_ADMINISTRATIVE,
      derivation: "analyst_estimate",
      accuracyM: 100,
    });
    expect(mark.kind).toBe("estimate");
    expect(mark.dashed).toBe(true);
  }
});

test("every mark kind is reachable, so the legend describes nothing imaginary", () => {
  const reached = new Set(every().map((input) => markFor(input).kind));
  expect(reached).toEqual(new Set(["point", "circle", "area", "coverage", "estimate"]));
});

test("nothing undrawable is drawn, and each says why", () => {
  for (const state of ["none_permitted", "none_recorded", "invalid"] as const) {
    const mark = markFor({
      geometryState: state,
      geometryKind: "Polygon",
      adminLevel: "subdivision",
      derivation: "admin_unit_boundary",
      accuracyM: null,
    });
    expect(mark.kind).toBe("none");
    // A reader is told *which* kind of nothing this is; "not shown" alone
    // leaves them unable to tell a clearance limit from a gap in the record.
    expect(mark.reason).toBeTruthy();
  }
});

test("a derivation this build has never heard of draws nothing, not a pin", () => {
  const mark = markFor({
    geometryState: "ok",
    geometryKind: "Point",
    adminLevel: GEO_NOT_ADMINISTRATIVE,
    // A server ahead of this bundle. The version banner is already saying so;
    // drawing a confident pin would be the wrong way to be stale.
    derivation: "satellite_guess" as MarkInput["derivation"],
    accuracyM: 5,
  });
  expect(mark.kind).toBe("none");
  expect(mark.reason).toContain("does not know");
});
