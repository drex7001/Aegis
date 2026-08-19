"""The seven rules a geometry claim's value must pass (T56, spec 10 §4.3).

Rules 5–7 are the ones worth reading. They are the **write-side half** of "no
bare pin exists": the renderer cannot draw a point where a point would be a lie,
because the store will not accept the claim that would license one. A guarantee
enforced only in React is a guarantee until someone writes a second screen.
"""

from __future__ import annotations

import pytest

from aegis.geo import GeoValueError, parse_geo_value, validate_geo_value

pytestmark = pytest.mark.requirement("Article-I", "H-21", "ADR-048", "T56")


def _value(**overrides):
    """A district polygon — coarse, valid, and administrative."""
    base = {
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[79.8, 6.9], [79.9, 6.9], [79.9, 7.0], [79.8, 7.0], [79.8, 6.9]]
            ],
        },
        "admin_level": "subdivision",
        "derivation": "admin_unit_boundary",
        "accuracy_m": None,
    }
    return {**base, **overrides}


def _point(**overrides):
    base = {
        "geometry": {"type": "Point", "coordinates": [79.861, 6.927]},
        "admin_level": "not_administrative",
        "derivation": "instrument_fix",
        "accuracy_m": 8,
    }
    return {**base, **overrides}


# ── shape of the value itself ───────────────────────────────────────────────


def test_a_valid_value_parses_and_derives_its_kind() -> None:
    parsed = parse_geo_value(_value())
    assert parsed.kind == "Polygon"          # derived, never asserted
    assert parsed.is_areal
    assert parsed.is_administrative
    assert parsed.accuracy_m is None


def test_the_four_fields_are_the_whole_value() -> None:
    """An unknown field is a rejection, not a silently ignored one.

    A value carrying `precision: "city"` would otherwise look accepted while
    meaning nothing — which is exactly the field this model replaced.
    """
    with pytest.raises(GeoValueError) as exc:
        parse_geo_value(_value(precision="city"))
    assert "unknown field(s) ['precision']" in exc.value.message


@pytest.mark.parametrize("field", ["geometry", "admin_level", "derivation"])
def test_each_required_field_is_required(field: str) -> None:
    value = _value()
    value[field] = None
    with pytest.raises(GeoValueError) as exc:
        parse_geo_value(value)
    assert exc.value.field == f"object_value.{field}"


def test_a_non_object_value_is_rejected() -> None:
    with pytest.raises(GeoValueError):
        validate_geo_value("6.927,79.861")


# ── rule 1: RFC 7946, and no CRS negotiation ────────────────────────────────


def test_a_crs_member_is_refused() -> None:
    """RFC 7946 removed it; a second CRS is a second way to be wrong."""
    value = _value()
    value["geometry"]["crs"] = {"type": "name", "properties": {"name": "EPSG:3857"}}
    with pytest.raises(GeoValueError) as exc:
        parse_geo_value(value)
    assert exc.value.field == "object_value.geometry.crs"


def test_an_unsupported_geometry_type_is_refused() -> None:
    with pytest.raises(GeoValueError) as exc:
        parse_geo_value(_value(geometry={"type": "GeometryCollection", "geometries": []}))
    assert exc.value.field == "object_value.geometry.type"


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_a_non_finite_coordinate_is_refused(bad: float) -> None:
    with pytest.raises(GeoValueError):
        parse_geo_value(_point(geometry={"type": "Point", "coordinates": [bad, 6.9]}))


def test_a_string_coordinate_is_refused() -> None:
    with pytest.raises(GeoValueError):
        parse_geo_value(_point(geometry={"type": "Point", "coordinates": ["79.8", 6.9]}))


# ── rule 2: coordinates are in range ────────────────────────────────────────


@pytest.mark.parametrize(
    "coordinates, expected",
    [
        ([181.0, 6.9], "longitude"),
        ([-181.0, 6.9], "longitude"),
        ([79.8, 91.0], "latitude"),
        ([79.8, -91.0], "latitude"),
    ],
)
def test_out_of_range_coordinates_are_refused(coordinates, expected: str) -> None:
    with pytest.raises(GeoValueError) as exc:
        parse_geo_value(_point(geometry={"type": "Point", "coordinates": coordinates}))
    assert expected in exc.value.message


# ── rule 3: rings are closed and long enough ────────────────────────────────


def test_an_open_ring_is_refused() -> None:
    with pytest.raises(GeoValueError) as exc:
        parse_geo_value(
            _value(
                geometry={
                    "type": "Polygon",
                    "coordinates": [
                        [[79.8, 6.9], [79.9, 6.9], [79.9, 7.0], [79.8, 7.0]]
                    ],
                }
            )
        )
    assert "must be closed" in exc.value.message


def test_a_ring_of_three_positions_is_refused() -> None:
    with pytest.raises(GeoValueError) as exc:
        parse_geo_value(
            _value(
                geometry={
                    "type": "Polygon",
                    "coordinates": [[[79.8, 6.9], [79.9, 6.9], [79.8, 6.9]]],
                }
            )
        )
    assert "at least four positions" in exc.value.message


# ── rule 4: the antimeridian ────────────────────────────────────────────────


def test_a_ring_spanning_the_antimeridian_is_refused() -> None:
    """RFC 7946 §3.1.9: split it, do not wrap it.

    The failure this prevents is silent and enormous — a polygon written to
    cross ±180 is read as one going the *other* way round the planet, so a
    two-degree bay becomes most of the northern hemisphere.
    """
    with pytest.raises(GeoValueError) as exc:
        parse_geo_value(
            _value(
                geometry={
                    "type": "Polygon",
                    "coordinates": [
                        [[179.0, 6.9], [-179.0, 6.9], [-179.0, 7.0], [179.0, 7.0], [179.0, 6.9]]
                    ],
                }
            )
        )
    assert "180°" in exc.value.message


# ── rule 5: an area must say how large it is ────────────────────────────────


@pytest.mark.parametrize("derivation", ["admin_unit_centroid", "coverage_area"])
def test_an_area_derivation_without_a_radius_is_refused(derivation: str) -> None:
    """A centroid without a radius is a pin pretending to be a city."""
    with pytest.raises(GeoValueError) as exc:
        parse_geo_value(
            _point(admin_level="locality", derivation=derivation, accuracy_m=None)
        )
    assert exc.value.field == "object_value.accuracy_m"


def test_a_centroid_with_a_radius_is_accepted() -> None:
    parsed = parse_geo_value(
        _point(admin_level="locality", derivation="admin_unit_centroid", accuracy_m=4200)
    )
    assert parsed.accuracy_m == 4200
    assert parsed.is_administrative


@pytest.mark.parametrize("accuracy", [-1, float("inf"), "wide"])
def test_a_nonsensical_radius_is_refused(accuracy) -> None:
    with pytest.raises(GeoValueError) as exc:
        parse_geo_value(_point(accuracy_m=accuracy))
    assert exc.value.field == "object_value.accuracy_m"


# ── rules 6–7: what a shape is allowed to mean ──────────────────────────────


def test_a_point_may_not_claim_an_administrative_area_except_as_its_centroid() -> None:
    """The charter criterion, enforced at the write.

    "A `country`-level location never renders as a point" is not left to the
    renderer to remember: the claim that would license one cannot be recorded.
    """
    with pytest.raises(GeoValueError) as exc:
        parse_geo_value(
            _point(admin_level="country", derivation="source_stated_coordinates")
        )
    assert exc.value.field == "object_value.derivation"
    assert "an administrative area is not a position" in exc.value.message


def test_a_boundary_derivation_needs_an_area() -> None:
    """A LineString rather than a Point, to isolate rule 7 from rule 6.

    A Point here would be refused by rule 6 first, and a test that cannot say
    which rule caught it is not testing either.
    """
    with pytest.raises(GeoValueError) as exc:
        parse_geo_value(
            _value(
                geometry={
                    "type": "LineString",
                    "coordinates": [[79.8, 6.9], [79.9, 7.0]],
                },
                derivation="admin_unit_boundary",
            )
        )
    assert exc.value.field == "object_value.geometry.type"
    assert "Polygon" in exc.value.message


def test_a_position_fix_may_not_claim_an_administrative_level() -> None:
    """The mirror of rule 6: a GPS fix is not a district, however coarse.

    Without this a point could borrow an area's meaning while skipping the
    centroid derivation rule 6 requires of it — the same false precision by a
    different route.
    """
    with pytest.raises(GeoValueError) as exc:
        parse_geo_value(
            _value(
                geometry={
                    "type": "LineString",
                    "coordinates": [[79.8, 6.9], [79.9, 7.0]],
                },
                admin_level="site",
                derivation="instrument_fix",
                accuracy_m=5,
            )
        )
    assert exc.value.field == "object_value.admin_level"


def test_an_undeclared_vocabulary_value_is_refused() -> None:
    with pytest.raises(GeoValueError) as exc:
        parse_geo_value(_value(admin_level="parish"))
    assert exc.value.field == "object_value.admin_level"

    with pytest.raises(GeoValueError) as exc:
        parse_geo_value(_value(derivation="vibes"))
    assert exc.value.field == "object_value.derivation"
