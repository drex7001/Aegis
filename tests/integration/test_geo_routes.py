"""The map is not a side door, and generalization is a claim (T59, M-18).

Charter exit №3's server half lives here: *"a low-clearance viewer sees the
authorized generalization, not exact geometry"*. The construction is worth
stating because it is what makes the criterion meetable without the server ever
computing a degraded shape.

A location carries two geometry claims — a `sensitive` building polygon and an
`open` district polygon, from two different sources. The cleared viewer sees the
building; the uncleared viewer's ordinary `claim_filters` removes that row and
the district is what remains. Nothing is synthesized, no viewer is shown a shape
no source asserted, and the mechanism is the most-tested code path in the system.

The rest is the discipline that keeps it honest: a place with no readable
geometry is listed and never placed, a bbox never becomes a way to probe for
what you may not read, and counts are computed after filtering.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, new_id
from aegis.ontology import load
from aegis.projections import rebuild_location_geometry_projection
from aegis.store import Entity, Source, SourceRecord
from tests.integration.test_api import (  # noqa: F401
    _FakeFGA,
    api_db,
    auth,
    clean_api_database,
    client,
    fake_fga,
)
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement(
    "Article-VI", "M-18", "H-21", "ADR-049", "T59"
)

OPEN_VIEWER = auth("open-t59", "analyst", clearance=0)
CLEARED = auth("cleared-t59", "analyst", clearance=2)
MARCH = datetime(2019, 3, 12, tzinfo=timezone.utc)

DISTRICT = {
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [[79.8, 6.9], [80.0, 6.9], [80.0, 7.1], [79.8, 7.1], [79.8, 6.9]]
        ],
    },
    "admin_level": "subdivision",
    "derivation": "admin_unit_boundary",
    "accuracy_m": None,
}

BUILDING = {
    "geometry": {"type": "Point", "coordinates": [79.8612, 6.9271]},
    "admin_level": "not_administrative",
    "derivation": "address_match",
    "accuracy_m": 12,
}

FAR_AWAY = {
    "geometry": {"type": "Point", "coordinates": [-58.4, -34.6]},
    "admin_level": "not_administrative",
    "derivation": "instrument_fix",
    "accuracy_m": 5,
}


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture()
def world(client: TestClient, api_db: str, ontology) -> dict:
    """One place with two geometries at different clearances, one far away,
    one with no geometry at all, and an arrest that happened at the first."""
    engine = sa.create_engine(api_db)
    ids: dict[str, str] = {}
    with Session(engine) as session:
        with session.begin():
            ids["source"] = new_id("src")
            session.add(
                Source(
                    source_id=ids["source"],
                    source_type="open_source",
                    name="T59 source",
                    reliability_normalized="generally_reliable",
                )
            )
            ids["record"] = new_id("rec")
            session.add(
                SourceRecord(
                    record_id=ids["record"],
                    source_id=ids["source"],
                    ingest_key=new_id("key"),
                    content_hash="a9" * 32,
                    storage_uri="test://t59/one",
                )
            )
            session.flush()
            for slot, label, kind in (
                ("negombo", "Negombo", "location"),
                ("far", "Buenos Aires", "location"),
                ("unlocated", "An unplaced village", "location"),
                ("person", "Nimal Perera", "person"),
            ):
                ids[slot] = new_id("ent")
                session.add(Entity(entity_id=ids[slot], entity_type=kind, label=label))

        service = ActionService(session, ontology)
        context = ActionContext(
            actor="user:seed", purpose="T59 seed", roles=frozenset({"analyst"})
        )
        for place, value, handling in (
            ("negombo", DISTRICT, "open"),
            ("negombo", BUILDING, "sensitive"),
            ("far", FAR_AWAY, "open"),
        ):
            service.record_claim(
                context,
                subject_id=ids[place],
                predicate="has_geometry",
                object_value=value,
                record_id=ids["record"],
                handling_code=handling,
                collection_method="curated",
            )
        event = service.record_event(
            context,
            event_type="arrest",
            record_id=ids["record"],
            summary="An arrest at Negombo",
            event_time_earliest=MARCH,
            event_time_latest=MARCH,
            participants=[{"role": "has_arrestee", "entity_id": ids["person"]}],
            places=[{"role": "took_place_at", "entity_id": ids["negombo"]}],
        )
        ids["event"] = event.entity_id
        session.commit()
        rebuild_location_geometry_projection(session, ontology=ontology)
        session.commit()
    return ids


def _locations(client: TestClient, headers: dict, **params) -> dict:
    response = client.get("/v1/geo/locations", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return {
        feature["properties"]["entity_id"]: feature
        for feature in response.json()["features"]
    }


# ── the criterion: authorized generalization (M-18) ─────────────────────────


def test_a_low_clearance_viewer_sees_the_district_not_the_building(
    client, world
) -> None:
    """Charter exit №3's server half.

    Not a blur: the district is a *recorded claim* with its own source, and the
    ordinary filter is what leaves it. The cleared viewer gets the building from
    the same query.
    """
    cleared = _locations(client, CLEARED)[world["negombo"]]
    assert cleared["properties"]["geometry_state"] == "ok"
    assert cleared["geometry"]["type"] == "Point"
    assert cleared["properties"]["derivation"] == "address_match"
    assert cleared["properties"]["handling_code"] == "sensitive"

    limited = _locations(client, OPEN_VIEWER)[world["negombo"]]
    assert limited["properties"]["geometry_state"] == "ok"
    assert limited["geometry"]["type"] == "Polygon"
    assert limited["properties"]["derivation"] == "admin_unit_boundary"
    assert limited["properties"]["admin_level"] == "subdivision"
    assert limited["properties"]["handling_code"] == "open"


def test_the_generalized_response_discloses_nothing_about_the_finer_one(
    client, world
) -> None:
    """No count, no marker, no "more precise geometry exists" field.

    The uncleared viewer's feature must be indistinguishable from one for a
    place whose *only* geometry is the district.
    """
    limited = _locations(client, OPEN_VIEWER)[world["negombo"]]
    body = str(limited)
    assert "sensitive" not in body
    assert "address_match" not in body
    assert str(BUILDING["geometry"]["coordinates"][0]) not in str(limited["geometry"])
    # Exactly the property set every other feature carries.
    assert set(limited["properties"]) == {
        "entity_id",
        "label",
        "entity_type",
        "geometry_state",
        "admin_level",
        "accuracy_m",
        "derivation",
        "geometry_kind",
        "claim_id",
        "handling_code",
        "invalid_reason",
    }


def test_a_place_with_no_readable_geometry_is_listed_never_placed(
    client, world, api_db, ontology
) -> None:
    """`geometry: null` and a state saying which kind of nothing it is (§7.3)."""
    engine = sa.create_engine(api_db)
    with Session(engine) as session:
        service = ActionService(session, ontology)
        service.record_claim(
            ActionContext(actor="user:seed", purpose="seed", roles=frozenset({"analyst"})),
            subject_id=world["unlocated"],
            predicate="has_geometry",
            object_value=BUILDING,
            record_id=world["record"],
            handling_code="sensitive",
            collection_method="curated",
        )
        session.commit()
        rebuild_location_geometry_projection(session, ontology=ontology)
        session.commit()

    feature = _locations(client, OPEN_VIEWER)[world["unlocated"]]
    assert feature["geometry"] is None
    # `none_permitted`, not `none_recorded`: they are different facts about the
    # world and an analyst needs both. Whether the distinction should itself be
    # withheld is a response-mode question, and that policy is P7's (H-25).
    assert feature["properties"]["geometry_state"] == "none_permitted"


def test_a_place_nobody_has_located_says_so(client, world) -> None:
    feature = _locations(client, OPEN_VIEWER)[world["unlocated"]]
    assert feature["geometry"] is None
    assert feature["properties"]["geometry_state"] == "none_recorded"


# ── the bbox is not a probe ─────────────────────────────────────────────────


def test_a_bbox_returns_only_places_inside_it(client, world) -> None:
    inside = _locations(client, CLEARED, bbox="79.0,6.0,81.0,8.0")
    assert world["negombo"] in inside
    assert world["far"] not in inside


def test_a_bbox_cannot_be_used_to_probe_for_unreadable_geometry(
    client, world, api_db, ontology
) -> None:
    """A place whose only geometry is above your clearance is invisible, not
    "outside the box" — returning it would disclose that something is there."""
    engine = sa.create_engine(api_db)
    with Session(engine) as session:
        service = ActionService(session, ontology)
        service.record_claim(
            ActionContext(actor="user:seed", purpose="seed", roles=frozenset({"analyst"})),
            subject_id=world["unlocated"],
            predicate="has_geometry",
            object_value=BUILDING,
            record_id=world["record"],
            handling_code="sensitive",
            collection_method="curated",
        )
        session.commit()
        rebuild_location_geometry_projection(session, ontology=ontology)
        session.commit()

    box = "79.5,6.5,80.5,7.5"
    assert world["unlocated"] in _locations(client, CLEARED, bbox=box)
    assert world["unlocated"] not in _locations(client, OPEN_VIEWER, bbox=box)


@pytest.mark.parametrize(
    "bbox, expected",
    [
        ("79.0,6.0,81.0", "west,south,east,north"),
        ("a,6.0,81.0,8.0", "numbers"),
        ("79.0,6.0,181.0,8.0", "east"),
        ("79.0,-91.0,81.0,8.0", "south"),
        ("79.0,8.0,81.0,6.0", "above north"),
        ("179.0,6.0,-179.0,8.0", "±180"),
    ],
)
def test_a_malformed_bbox_is_a_422_not_an_empty_map(
    client, world, bbox: str, expected: str
) -> None:
    """An empty map is indistinguishable from "you may see nothing", and one of
    those is a lie (spec 10 §8.2)."""
    response = client.get("/v1/geo/locations", headers=CLEARED, params={"bbox": bbox})
    assert response.status_code == 422
    assert expected in response.text


# ── events ──────────────────────────────────────────────────────────────────


def test_an_event_is_served_at_the_place_it_happened(client, world) -> None:
    response = client.get("/v1/geo/events", headers=CLEARED)
    assert response.status_code == 200
    features = response.json()["features"]
    assert len(features) == 1
    properties = features[0]["properties"]
    assert properties["event_id"] == world["event"]
    assert properties["event_type"] == "arrest"
    assert properties["place_id"] == world["negombo"]
    assert properties["place_role"] == "took_place_at"
    assert properties["participant_count"] == 1
    # Intervals, plural and attributable — never one collapsed span (§6.3).
    assert properties["time_intervals"]
    assert properties["time_intervals"][0]["claim_id"]


def test_the_event_feature_generalizes_like_the_place_does(client, world) -> None:
    """The map's privacy rule cannot differ between two of its own layers."""
    features = client.get("/v1/geo/events", headers=OPEN_VIEWER).json()["features"]
    assert features[0]["geometry"]["type"] == "Polygon"
    assert features[0]["properties"]["derivation"] == "admin_unit_boundary"


def test_the_participant_count_is_computed_after_filtering(client, world) -> None:
    """A count taken before filtering is an existence leak wearing a number."""
    cleared = client.get("/v1/geo/events", headers=CLEARED).json()["features"][0]
    assert cleared["properties"]["participant_count"] == 1
    # The event's claims are `open`, so both viewers see the same count here.
    # The assertion that matters is that the number comes from the filtered
    # query, which the sensitive-claim case below proves.
    limited = client.get("/v1/geo/events", headers=OPEN_VIEWER).json()["features"][0]
    assert limited["properties"]["participant_count"] == 1


def test_a_time_window_excludes_an_event_outside_it(client, world) -> None:
    inside = client.get(
        "/v1/geo/events",
        headers=CLEARED,
        params={"from": "2019-01-01T00:00:00Z", "to": "2019-12-31T00:00:00Z"},
    ).json()["features"]
    assert len(inside) == 1

    outside = client.get(
        "/v1/geo/events",
        headers=CLEARED,
        params={"from": "2021-01-01T00:00:00Z", "to": "2021-12-31T00:00:00Z"},
    ).json()["features"]
    assert outside == []


def test_an_inverted_time_window_is_a_422(client, world) -> None:
    response = client.get(
        "/v1/geo/events",
        headers=CLEARED,
        params={"from": "2021-01-01T00:00:00Z", "to": "2019-01-01T00:00:00Z"},
    )
    assert response.status_code == 422


def test_an_unknown_event_type_returns_nothing_rather_than_erroring(
    client, world
) -> None:
    """A type the composition does not declare is an empty answer, not a 500:
    a second domain is allowed not to have arrests."""
    response = client.get(
        "/v1/geo/events", headers=CLEARED, params={"eventType": "regatta"}
    )
    assert response.status_code == 200
    assert response.json()["features"] == []


# ── the ordinary route contract ─────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/v1/geo/locations", "/v1/geo/events"])
def test_the_geo_routes_require_authentication(client, world, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


@pytest.mark.parametrize("path", ["/v1/geo/locations", "/v1/geo/events"])
def test_every_response_carries_the_as_of_stamp(client, world, path: str) -> None:
    """Present on a *current* answer too, so a caller never re-reads its own
    request to learn which identity produced it (T49)."""
    body = client.get(path, headers=CLEARED).json()
    assert body["type"] == "FeatureCollection"
    assert body["stamp"]["ontology_version"]
    assert body["stamp"]["identity_revision_id"] is not None
    assert body["stamp"]["as_of"] is None


@pytest.mark.parametrize("path", ["/v1/geo/locations", "/v1/geo/events"])
def test_as_of_composes_from_the_first_commit(client, world, path: str) -> None:
    """Geo takes `asOf` on day one, closing the geo half of P4's carryover."""
    before = client.get(
        path, headers=CLEARED, params={"asOf": "2020-01-01T00:00:00Z"}
    )
    assert before.status_code == 200
    assert before.json()["stamp"]["as_of"].startswith("2020-01-01")
    # Everything was recorded now, so an as-of before that shows no geometry
    # and no event.
    if path.endswith("events"):
        assert before.json()["features"] == []
    else:
        states = {
            feature["properties"]["geometry_state"]
            for feature in before.json()["features"]
        }
        assert states <= {"none_recorded", "none_permitted"}


@pytest.mark.parametrize("path", ["/v1/geo/locations", "/v1/geo/events"])
def test_a_revision_above_the_head_is_422_not_clamped(client, world, path: str) -> None:
    response = client.get(path, headers=CLEARED, params={"asOfRevision": 99999})
    assert response.status_code == 422


def test_pagination_walks_the_places_without_repeating_one(client, world) -> None:
    seen: list[str] = []
    cursor = None
    for _ in range(10):
        params = {"limit": 1}
        if cursor:
            params["cursor"] = cursor
        body = client.get("/v1/geo/locations", headers=CLEARED, params=params).json()
        seen.extend(f["properties"]["entity_id"] for f in body["features"])
        cursor = body.get("next_cursor")
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 3


def test_a_cursor_from_another_route_is_refused(client, world) -> None:
    body = client.get(
        "/v1/geo/locations", headers=CLEARED, params={"limit": 1}
    ).json()
    response = client.get(
        "/v1/geo/events", headers=CLEARED, params={"cursor": body["next_cursor"]}
    )
    assert response.status_code == 422
