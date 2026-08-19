"""Rebuild the geometry projection from claims (T56, spec 10 §6, Article XIII).

The whole table is derived. `TRUNCATE` it, run this, and it comes back
byte-identical — which is the phase's B-13 spot check, and the reason no
canonical mutable geometry column exists anywhere.

Two decisions are visible in the code and worth naming:

* **One row per claim.** Not per place. Two geometry claims for one location at
  different handling codes stay two rows, so a viewer's ordinary
  ``claim_filters`` leaves them whichever they may read (spec 10 §7.2). Picking
  a winner here is where map privacy would die.
* **Invalid geometry is recorded, never repaired.** ``ST_IsValid`` runs in the
  database — it is PostGIS's answer, and the write path must not depend on the
  projection database being reachable — and a geometry that fails is stored with
  ``is_valid = false``, its reason, and a NULL ``geom``. ``ST_MakeValid`` would
  change what a source said.

Which claims carry geometry is asked of the ontology
(``aegis.ontology.shapes.geometry_predicates``), never hardcoded: the rule is
"the predicate declares a property of type ``geo``" (ADR-047), so a second
domain gets this by declaring a type that implements ``place``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from aegis.geo import GeoValueError, parse_geo_value
from aegis.ontology import Ontology
from aegis.ontology.shapes import geometry_predicates, place_object_types
from aegis.store import Claim, Entity, LocationGeometryProjection

#: Bumped when the shape of a row changes, so a stale table is identifiable
#: rather than merely wrong. Mirrors `edges.BUILDER_VERSION`.
BUILDER_VERSION = "location-geometry-v1"


@dataclass
class GeometryProjectionReport:
    """What a rebuild did, in the terms a reader would ask about."""

    rows: int = 0
    invalid: int = 0
    rejected: int = 0
    ontology_version: str = ""
    builder_version: str = BUILDER_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "invalid": self.invalid,
            "rejected": self.rejected,
            "ontology_version": self.ontology_version,
            "builder_version": self.builder_version,
        }


def rebuild_location_geometry_projection(
    session: Session, *, ontology: Ontology
) -> GeometryProjectionReport:
    """Rebuild the whole table from claims. Idempotent by construction."""
    report = GeometryProjectionReport(ontology_version=ontology.version)
    predicates = set(geometry_predicates(ontology))
    places = set(place_object_types(ontology))

    session.execute(delete(LocationGeometryProjection))
    if not predicates or not places:
        # A composition with no place types is not an error — it is a domain
        # that has no geography, and the empty table is the right answer.
        return report

    rows = session.execute(
        select(Claim, Entity.entity_type)
        .join(Entity, Entity.entity_id == Claim.subject_id)
        .where(Claim.predicate.in_(predicates), Entity.entity_type.in_(places))
        .order_by(Claim.claim_id)
    ).all()

    for claim, _entity_type in rows:
        try:
            value = parse_geo_value(claim.object_value)
        except GeoValueError:
            # A claim recorded before this validator existed, or under an older
            # ontology. Skipped and counted rather than crashing the rebuild:
            # a projection is a cache, and one unreadable row must not make the
            # other ten thousand unavailable. It is counted so the number is
            # visible instead of silently zero.
            report.rejected += 1
            continue

        geojson = json.dumps(value.geometry, sort_keys=True)
        # One round trip: build the geometry, ask PostGIS whether it is valid,
        # and keep the reason if it is not. `ST_IsValidReason` is what a reader
        # needs — "invalid" alone tells an analyst to guess.
        checked = session.execute(
            text(
                "SELECT ST_IsValid(g) AS valid, ST_IsValidReason(g) AS reason, "
                "       replace(ST_GeometryType(g), 'ST_', '') AS kind, "
                "       ST_AsBinary(g) AS wkb "
                "FROM ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326) AS g"
            ),
            {"geojson": geojson},
        ).one()

        is_valid = bool(checked.valid)
        if not is_valid:
            report.invalid += 1

        session.execute(
            text(
                "INSERT INTO location_geometry_projection ("
                "  claim_id, place_id, geom, geometry_kind, admin_level, accuracy_m,"
                "  derivation, is_valid, invalid_reason, handling_code, handling_rank,"
                "  case_id, recorded_at, retracted_at, ontology_version, builder_version"
                ") VALUES ("
                "  :claim_id, :place_id,"
                "  CASE WHEN :is_valid THEN ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326) END,"
                "  :geometry_kind, :admin_level, :accuracy_m,"
                "  :derivation, :is_valid, :invalid_reason, :handling_code, :handling_rank,"
                "  :case_id, :recorded_at, :retracted_at, :ontology_version, :builder_version"
                ")"
            ),
            {
                "claim_id": claim.claim_id,
                "place_id": claim.subject_id,
                "geojson": geojson,
                "is_valid": is_valid,
                "geometry_kind": checked.kind or value.kind,
                "admin_level": value.admin_level,
                "accuracy_m": value.accuracy_m,
                "derivation": value.derivation,
                "invalid_reason": None if is_valid else checked.reason,
                "handling_code": claim.handling_code,
                "handling_rank": ontology.handling_rank(claim.handling_code),
                "case_id": claim.case_id,
                "recorded_at": claim.recorded_at,
                "retracted_at": claim.retracted_at,
                "ontology_version": ontology.version,
                "builder_version": BUILDER_VERSION,
            },
        )
        report.rows += 1

    return report


__all__ = [
    "BUILDER_VERSION",
    "GeometryProjectionReport",
    "rebuild_location_geometry_projection",
]
