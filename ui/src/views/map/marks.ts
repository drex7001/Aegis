/**
 * How a geometry is drawn, chosen from the four axes (T60, spec 10 §9).
 *
 * Split out of the map component and kept pure for one reason: this is where
 * the charter's third criterion is enforced on the client, and a rule that
 * matters that much should be provable without a browser. The unit test walks
 * the whole `admin_level × derivation × geometryKind` matrix; the browser test
 * proves the wiring at three zoom levels.
 *
 * **There is exactly one branch that emits a point mark**, and it is
 * unreachable for any administrative level. That is the renderer half of "no
 * bare pin exists" — the other half is the store, which will not accept the
 * claim that would license one (spec 10 §4.3 rules 5–7). Enforced twice
 * because a guarantee that lives only in React is a guarantee until someone
 * writes a second screen.
 *
 * Nothing here reads a domain name. The vocabularies are the generated
 * geo constants (Article XI), so a second domain's places render by the same
 * rules with no code change.
 */

import { GEO_ADMIN_LEVELS, type GeoAdminLevel, type GeoDerivation } from "../../api/ontology";

/** Above this radius a "position" is really an area, and is drawn as one. */
export const POINT_ACCURACY_THRESHOLD_M = 250;

export type GeometryState = "ok" | "none_permitted" | "none_recorded" | "invalid";

export type MarkKind =
  /** A specific place, known specifically. The only pin. */
  | "point"
  /** A stated position with a radius, or a centroid standing for an area. */
  | "circle"
  /** A boundary or footprint the source actually drew. */
  | "area"
  /** The area something covers, rather than where a thing is. */
  | "coverage"
  /** An analyst's reasoned estimate — dashed, never solid. */
  | "estimate"
  /** Not drawable: no permitted geometry, none recorded, or invalid. */
  | "none";

export interface MarkInput {
  geometryState: GeometryState;
  geometryKind: string | null;
  adminLevel: GeoAdminLevel | null;
  derivation: GeoDerivation | null;
  accuracyM: number | null;
}

export interface Mark {
  kind: MarkKind;
  /** Metres, for the two circle-shaped marks. Null for everything else. */
  radiusM: number | null;
  /** Dashed outlines say "estimated" without a legend lookup. */
  dashed: boolean;
  /** What a reader is told when there is nothing to draw. */
  reason: string | null;
}

const ADMINISTRATIVE = new Set<string>(GEO_ADMIN_LEVELS);

const NOT_DRAWN: Record<Exclude<GeometryState, "ok">, string> = {
  none_permitted: "Geometry is recorded but above your clearance.",
  none_recorded: "No geometry has been recorded for this place.",
  invalid: "The recorded geometry is not a valid shape and is shown as recorded, not repaired.",
};

const AREAL = new Set(["Polygon", "MultiPolygon"]);

/**
 * The mark for one feature. Total: every input produces a mark, and an input
 * this does not recognise produces `none` rather than a default pin.
 */
export function markFor(input: MarkInput): Mark {
  if (input.geometryState !== "ok") {
    return { kind: "none", radiusM: null, dashed: false, reason: NOT_DRAWN[input.geometryState] };
  }

  const { derivation, adminLevel, accuracyM, geometryKind } = input;
  const areal = geometryKind !== null && AREAL.has(geometryKind);

  switch (derivation) {
    case "admin_unit_boundary":
      // The source drew this outline. It is an area or the store would not
      // have accepted it (§4.3 rule 7).
      return { kind: "area", radiusM: null, dashed: false, reason: null };

    case "coverage_area":
      // What something covers, not where it is. Hatched so it never reads as a
      // place; a radius is mandatory on this derivation (§4.3 rule 5).
      return areal
        ? { kind: "coverage", radiusM: null, dashed: false, reason: null }
        : { kind: "circle", radiusM: accuracyM, dashed: false, reason: null };

    case "admin_unit_centroid":
      // The centre of a named unit, standing for the whole unit. Always a
      // circle of its stated radius — at every zoom, which is the criterion.
      return { kind: "circle", radiusM: accuracyM, dashed: false, reason: null };

    case "analyst_estimate":
      return { kind: "estimate", radiusM: areal ? null : accuracyM, dashed: true, reason: null };

    case "instrument_fix":
    case "source_stated_coordinates":
    case "address_match":
      break;

    default:
      // An unknown derivation means the bundle is older than the server. The
      // version banner is already saying so; drawing a confident pin would be
      // the wrong way to be stale.
      return {
        kind: "none",
        radiusM: null,
        dashed: false,
        reason: "This geometry uses a derivation this build does not know.",
      };
  }

  // ── the only point branch ────────────────────────────────────────────────
  //
  // Guarded twice over. An administrative level cannot reach here: the store
  // refuses a Point at one unless its derivation is `admin_unit_centroid`,
  // which returned above — and this re-checks rather than trusting that,
  // because the two halves of a guarantee should not depend on each other.
  if (adminLevel !== null && ADMINISTRATIVE.has(adminLevel)) {
    return { kind: "circle", radiusM: accuracyM, dashed: false, reason: null };
  }
  if (areal) {
    return { kind: "area", radiusM: null, dashed: false, reason: null };
  }
  if (accuracyM !== null && accuracyM > POINT_ACCURACY_THRESHOLD_M) {
    // A "position" known to ±5 km is an area wearing a coordinate.
    return { kind: "circle", radiusM: accuracyM, dashed: false, reason: null };
  }
  return { kind: "point", radiusM: null, dashed: false, reason: null };
}

/** Human-readable, for the legend and the popup. */
export function describeMark(mark: Mark, input: MarkInput): string {
  switch (mark.kind) {
    case "point":
      return "Exact position";
    case "circle":
      return mark.radiusM !== null
        ? `Within ~${formatMetres(mark.radiusM)}`
        : "Approximate position";
    case "area":
      return input.derivation === "admin_unit_boundary" ? "Administrative area" : "Recorded outline";
    case "coverage":
      return "Coverage area";
    case "estimate":
      return "Analyst estimate";
    case "none":
      return "Not shown on the map";
  }
}

export function formatMetres(metres: number): string {
  return metres >= 1000 ? `${(metres / 1000).toFixed(1)} km` : `${Math.round(metres)} m`;
}
