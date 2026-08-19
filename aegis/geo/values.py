"""Validate and read a geometry claim's value (spec 10 §4.3).

Seven rules, and the last three are the interesting ones: they are the
**write-side half of "no bare pin exists"**. The renderer cannot draw a point
where a point would be a lie, because the store will not accept the claim that
would license one (§9.2). A guarantee enforced only in React is a guarantee
until someone writes a second screen.

What is *not* checked here is topology. ``ST_IsValid`` is PostGIS's answer and
the write path must not depend on the projection database being reachable; an
invalid ring is caught at projection time, recorded with its reason, and never
repaired — silently fixing a self-intersecting polygon changes what a source
said (§4.3, §6.1).

Coordinates are **WGS84 / EPSG:4326 only**, which is what RFC 7946 mandates.
There is no CRS negotiation and no reprojection: a second CRS is a second way to
be wrong about where something is.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from aegis.ontology.registries import (
    GEO_ADMIN_LEVELS,
    GEO_ADMIN_VALUES,
    GEO_DERIVATIONS,
    GEO_DERIVATIONS_REQUIRING_ACCURACY,
    GEO_NOT_ADMINISTRATIVE,
)

#: RFC 7946 §1.4. `GeometryCollection` is deliberately absent: it is a container
#: with no single kind, so "what mark do I draw" has no answer for it, and every
#: use it would serve is a MultiPoint/MultiLineString/MultiPolygon.
GEOMETRY_TYPES = (
    "Point",
    "MultiPoint",
    "LineString",
    "MultiLineString",
    "Polygon",
    "MultiPolygon",
)

#: Derivations that describe an actual position rather than an area. Only these
#: may carry a `Point` at an administrative level — and then only as a stated
#: centroid, which is rule 6's other half.
_POSITION_DERIVATIONS = frozenset(
    {"instrument_fix", "source_stated_coordinates", "address_match"}
)

#: Administrative levels, as a set for membership tests. `not_administrative` is
#: excluded on purpose: it is not a rung on the ladder.
_ADMINISTRATIVE = frozenset(GEO_ADMIN_LEVELS)

_REQUIRED_FIELDS = ("geometry", "admin_level", "derivation")
_ALLOWED_FIELDS = frozenset({*_REQUIRED_FIELDS, "accuracy_m"})


class GeoValueError(ValueError):
    """A geometry claim's value is not one this system will record.

    Carries ``field`` so the API can name it: a 422 that says "invalid geometry"
    tells an analyst to guess.
    """

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


@dataclass(frozen=True)
class GeoValue:
    """A validated geometry claim value, with the geometry kind derived.

    ``kind`` is not a fifth axis and is never asserted — it is a fact about the
    value, read off the geometry itself, which is why a source cannot disagree
    with it.
    """

    geometry: dict[str, Any]
    admin_level: str
    derivation: str
    accuracy_m: float | None
    kind: str

    @property
    def is_administrative(self) -> bool:
        return self.admin_level in _ADMINISTRATIVE

    @property
    def is_areal(self) -> bool:
        return self.kind in ("Polygon", "MultiPolygon")


def geometry_kind(geometry: Any) -> str | None:
    """The RFC 7946 type of a geometry, or None if it does not have one."""
    if isinstance(geometry, dict):
        kind = geometry.get("type")
        if isinstance(kind, str):
            return kind
    return None


def parse_geo_value(value: Any) -> GeoValue:
    """Validate ``value`` and return it read; raise ``GeoValueError`` otherwise."""
    if not isinstance(value, dict):
        raise GeoValueError("object_value", "a geometry claim's value must be an object")
    unknown = sorted(set(value) - _ALLOWED_FIELDS)
    if unknown:
        raise GeoValueError(
            "object_value",
            f"unknown field(s) {unknown}; a geometry value carries exactly "
            f"{sorted(_ALLOWED_FIELDS)}",
        )
    for field in _REQUIRED_FIELDS:
        if value.get(field) is None:
            raise GeoValueError(f"object_value.{field}", "is required")

    geometry = value["geometry"]
    admin_level = value["admin_level"]
    derivation = value["derivation"]
    accuracy = value.get("accuracy_m")

    kind = _validate_geometry(geometry)                              # rules 1–4
    _validate_vocabulary(admin_level, derivation)
    accuracy = _validate_accuracy(accuracy, derivation)              # rule 5
    _validate_representation(kind, admin_level, derivation)          # rules 6–7

    return GeoValue(
        geometry=geometry,
        admin_level=admin_level,
        derivation=derivation,
        accuracy_m=accuracy,
        kind=kind,
    )


def validate_geo_value(value: Any) -> None:
    """``parse_geo_value`` for callers that only want the exception."""
    parse_geo_value(value)


# ── rules 1–4: the geometry itself ──────────────────────────────────────────


def _validate_geometry(geometry: Any) -> str:
    if not isinstance(geometry, dict):
        raise GeoValueError("object_value.geometry", "must be a GeoJSON geometry object")
    if "crs" in geometry:
        raise GeoValueError(
            "object_value.geometry.crs",
            "RFC 7946 removed the `crs` member; coordinates are WGS84 (EPSG:4326) "
            "and nothing else",
        )
    kind = geometry.get("type")
    if kind not in GEOMETRY_TYPES:
        raise GeoValueError(
            "object_value.geometry.type",
            f"{kind!r} is not one of {list(GEOMETRY_TYPES)}",
        )
    coordinates = geometry.get("coordinates")
    if coordinates is None:
        raise GeoValueError("object_value.geometry.coordinates", "is required")

    depth = {
        "Point": 0,
        "MultiPoint": 1,
        "LineString": 1,
        "MultiLineString": 2,
        "Polygon": 2,
        "MultiPolygon": 3,
    }[kind]
    _walk(coordinates, depth, "object_value.geometry.coordinates")

    if kind == "Polygon":
        _validate_rings(coordinates, "object_value.geometry.coordinates")
    elif kind == "MultiPolygon":
        for index, polygon in enumerate(coordinates):
            _validate_rings(polygon, f"object_value.geometry.coordinates[{index}]")
    return kind


def _walk(node: Any, depth: int, where: str) -> None:
    """Descend to the positions and check each one (rules 1–2)."""
    if depth == 0:
        _validate_position(node, where)
        return
    if not isinstance(node, list) or not node:
        raise GeoValueError(where, "expected a non-empty array of coordinates")
    for index, child in enumerate(node):
        _walk(child, depth - 1, f"{where}[{index}]")


def _validate_position(position: Any, where: str) -> None:
    if not isinstance(position, (list, tuple)) or not 2 <= len(position) <= 3:
        raise GeoValueError(where, "a position is [longitude, latitude] or [lon, lat, alt]")
    for value in position:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise GeoValueError(where, "coordinates must be numbers")
        if not math.isfinite(value):
            raise GeoValueError(where, "coordinates must be finite")
    longitude, latitude = position[0], position[1]
    if not -180 <= longitude <= 180:
        raise GeoValueError(where, f"longitude {longitude} is outside [-180, 180]")
    if not -90 <= latitude <= 90:
        raise GeoValueError(where, f"latitude {latitude} is outside [-90, 90]")


def _validate_rings(rings: Any, where: str) -> None:
    """Rule 3 (closed, ≥ 4 positions) and rule 4 (the antimeridian)."""
    if not isinstance(rings, list) or not rings:
        raise GeoValueError(where, "a polygon needs at least one linear ring")
    for index, ring in enumerate(rings):
        at = f"{where}[{index}]"
        if len(ring) < 4:
            raise GeoValueError(at, "a linear ring needs at least four positions")
        if list(ring[0][:2]) != list(ring[-1][:2]):
            raise GeoValueError(at, "a linear ring must be closed (last position = first)")
        longitudes = [position[0] for position in ring]
        if max(longitudes) - min(longitudes) > 180:
            raise GeoValueError(
                at,
                "spans more than 180° of longitude — RFC 7946 §3.1.9 requires a "
                "geometry crossing the antimeridian to be split into two, rather "
                "than written as one that wraps the wrong way round the planet",
            )


# ── rules 5–7: what the axes may say together ───────────────────────────────


def _validate_vocabulary(admin_level: Any, derivation: Any) -> None:
    if admin_level not in GEO_ADMIN_VALUES:
        raise GeoValueError(
            "object_value.admin_level",
            f"{admin_level!r} is not one of {sorted(GEO_ADMIN_VALUES)}",
        )
    if derivation not in GEO_DERIVATIONS:
        raise GeoValueError(
            "object_value.derivation",
            f"{derivation!r} is not one of {sorted(GEO_DERIVATIONS)}",
        )


def _validate_accuracy(accuracy: Any, derivation: str) -> float | None:
    if accuracy is not None:
        if isinstance(accuracy, bool) or not isinstance(accuracy, (int, float)):
            raise GeoValueError("object_value.accuracy_m", "must be a number of metres")
        if not math.isfinite(accuracy) or accuracy < 0:
            raise GeoValueError("object_value.accuracy_m", "must be a finite, non-negative radius")
        accuracy = float(accuracy)
    elif derivation in GEO_DERIVATIONS_REQUIRING_ACCURACY:
        # Rule 5. A centroid without a radius is a pin pretending to be a city.
        raise GeoValueError(
            "object_value.accuracy_m",
            f"is required when derivation is {derivation!r} — a value that stands "
            "for an area must say how large the area is",
        )
    return accuracy


def _validate_representation(kind: str, admin_level: str, derivation: str) -> None:
    if kind == "Point" and admin_level in _ADMINISTRATIVE:
        # Rule 6. The only honest way a Point represents an administrative unit
        # is as its stated centroid, carrying the radius rule 5 then requires.
        if derivation != "admin_unit_centroid":
            raise GeoValueError(
                "object_value.derivation",
                f"a Point at admin_level {admin_level!r} must be derived as "
                f"'admin_unit_centroid' (with an accuracy_m), not {derivation!r} — "
                "an administrative area is not a position",
            )
    if derivation == "admin_unit_boundary" and kind not in ("Polygon", "MultiPolygon"):
        # Rule 7. A boundary is an area or it is not a boundary.
        raise GeoValueError(
            "object_value.geometry.type",
            f"derivation 'admin_unit_boundary' needs a Polygon or MultiPolygon, "
            f"not {kind!r}",
        )
    if derivation in _POSITION_DERIVATIONS and admin_level != GEO_NOT_ADMINISTRATIVE:
        # The mirror of rule 6: a GPS fix is not a district, however coarse its
        # accuracy. Saying otherwise would let a point claim an area's meaning
        # without the centroid derivation that rule 6 requires of it.
        raise GeoValueError(
            "object_value.admin_level",
            f"derivation {derivation!r} fixes a position, so admin_level must be "
            f"{GEO_NOT_ADMINISTRATIVE!r}, not {admin_level!r}",
        )
