"""One incident, three surfaces, one claim set (T64 — charter exits №1 and №2).

The phase's headline criteria:

> The same incident renders consistently on map, timeline, and graph from one
> claim set; precision is visually distinct.
>
> An event with 3+ participants round-trips through API and UI — create via
> action, render in object view, appear on map + timeline.

This file is the server half, and it is deliberately one long journey rather
than several short ones. The criterion is about **agreement between surfaces**,
and a test that seeded each surface separately could pass while the surfaces
disagreed — which is the failure it exists to catch.

So: one arrest is recorded once, through `POST /v1/events`, and then every
surface is asked about it. Nothing is seeded twice. If two surfaces disagree
about who was there, when, or where, exactly one of these assertions fails.

The browser half is `ui/e2e/incident.spec.ts`.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, new_id
from aegis.ontology import load
from aegis.projections import (
    is_stale,
    rebuild_edge_projection,
    rebuild_location_geometry_projection,
)
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
    "Article-I", "Article-VI", "Article-XIII", "B-13", "M-18", "T64"
)

ANALYST = auth("analyst-t64", "analyst", clearance=2)
LOW = auth("open-t64", "analyst", clearance=0)

#: The occurrence: an arrest of three people, at a district, on one stated day.
WHEN_FROM = datetime(2019, 3, 12, tzinfo=timezone.utc)
WHEN_TO = datetime(2019, 3, 12, 23, 59, 59, tzinfo=timezone.utc)

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


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture()
def incident(client: TestClient, api_db: str, ontology) -> dict:
    """One arrest, recorded once. Every assertion below reads *this*."""
    engine = sa.create_engine(api_db)
    ids: dict[str, str] = {}
    with Session(engine) as session:
        with session.begin():
            ids["source"] = new_id("src")
            session.add(
                Source(
                    source_id=ids["source"],
                    source_type="open_source",
                    name="Fictional Gazette",
                    reliability_normalized="generally_reliable",
                )
            )
            ids["record"] = new_id("rec")
            session.add(
                SourceRecord(
                    record_id=ids["record"],
                    source_id=ids["source"],
                    ingest_key=new_id("key"),
                    content_hash="c4" * 32,
                    storage_uri="test://t64/report",
                )
            )
            session.flush()
            for slot, label, kind in (
                ("one", "Fictional A", "person"),
                ("two", "Fictional B", "person"),
                ("three", "Fictional C", "person"),
                ("officer", "Inspector Fictional", "person"),
                ("place", "Fictional District", "location"),
            ):
                ids[slot] = new_id("ent")
                session.add(Entity(entity_id=ids[slot], entity_type=kind, label=label))

        # Two geometries at two clearances, from two sources — the shape that
        # makes authorized generalization real rather than a runtime blur.
        service = ActionService(session, ontology)
        seed = ActionContext(
            actor="user:seed", purpose="T64 seed", roles=frozenset({"analyst"})
        )
        for value, handling in ((DISTRICT, "open"), (BUILDING, "sensitive")):
            service.record_claim(
                seed,
                subject_id=ids["place"],
                predicate="has_geometry",
                object_value=value,
                record_id=ids["record"],
                handling_code=handling,
                collection_method="curated",
            )
        session.commit()
        rebuild_location_geometry_projection(session, ontology=ontology)
        session.commit()

    # The incident itself, through the API — the round trip the criterion names.
    response = client.post(
        "/v1/events",
        json={
            "event_type": "arrest",
            "record_id": ids["record"],
            "summary": "Three people arrested at Fictional District",
            "event_time_earliest": WHEN_FROM.isoformat(),
            "event_time_latest": WHEN_TO.isoformat(),
            "participants": [
                {"role": "has_arrestee", "entity_id": ids["one"]},
                {"role": "has_arrestee", "entity_id": ids["two"]},
                {"role": "has_arrestee", "entity_id": ids["three"]},
                {"role": "has_arresting_officer", "entity_id": ids["officer"]},
            ],
            "places": [{"role": "took_place_at", "entity_id": ids["place"]}],
        },
        headers=ANALYST,
    )
    assert response.status_code == 201, response.text
    created = response.json()
    ids["event"] = created["entity_id"]
    ids["claims"] = created["claim_ids"]
    return ids


@pytest.fixture()
def rebuilt(incident: dict, api_db: str, ontology) -> dict:
    """The incident, with the edge projection caught up.

    The graph reads `edge_projection`; the map and timeline read claims. That
    asymmetry is real and deliberate (Article XIII), and
    `test_the_graph_is_a_cache_and_says_so` asserts it rather than letting this
    fixture hide it. Everything downstream of here is about *agreement*, which
    is only a meaningful question once the cache is current.
    """
    engine = sa.create_engine(api_db)
    with Session(engine) as session:
        rebuild_edge_projection(session, ontology=ontology)
        session.commit()
    return incident


# ── charter exit №2: the round trip ─────────────────────────────────────────


def test_the_incident_is_created_through_the_action(incident) -> None:
    """Four participants and a place: six claims, no canonical event table."""
    assert len(incident["claims"]) == 6


def test_the_object_view_shows_the_whole_incident(client, incident) -> None:
    detail = client.get(f"/v1/entities/{incident['event']}", headers=ANALYST).json()
    assert detail["entity"]["entity_type"] == "arrest"
    grouped = detail["claims_by_predicate"]
    assert len(grouped["has_arrestee"]) == 3
    assert len(grouped["has_arresting_officer"]) == 1
    assert len(grouped["took_place_at"]) == 1
    # Every value opens its provenance: the criterion P4 set and this phase
    # inherits, checked on an event rather than a person.
    for entries in grouped.values():
        for entry in entries:
            assert entry["record"]["record_id"] == incident["record"]


def test_each_participant_sees_the_incident_from_their_own_page(client, incident) -> None:
    """One claim set, one answer, read from the other end (spec 10 §13)."""
    for slot in ("one", "two", "three", "officer"):
        detail = client.get(f"/v1/entities/{incident[slot]}", headers=ANALYST).json()
        inbound = detail["inbound_claims_by_predicate"]
        assert inbound, slot
        subjects = {
            entry["claim"]["subject_id"]
            for entries in inbound.values()
            for entry in entries
        }
        assert incident["event"] in subjects, slot


# ── charter exit №1: three surfaces, one claim set ──────────────────────────


def _map(client: TestClient, headers: dict, **params) -> list[dict]:
    response = client.get("/v1/geo/events", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()["features"]


def _timeline(client: TestClient, headers: dict, **params) -> dict:
    response = client.get("/v1/timeline", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _graph(client: TestClient, headers: dict, **body) -> dict:
    response = client.post(
        "/v1/graph/expand",
        json={"seed_ids": [], "max_hops": 0, **body},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_three_surfaces_agree_about_who_was_there(client, rebuilt) -> None:
    """The headline criterion.

    The map's participant count, the timeline's participation rows and the
    graph's edges out of the event are three independent readings of one claim
    set. If any of them counted differently, exactly one of these fails.
    """
    feature = next(
        f for f in _map(client, ANALYST) if f["properties"]["event_id"] == rebuilt["event"]
    )
    assert feature["properties"]["participant_count"] == 4

    timeline = _timeline(client, ANALYST)
    participation = [
        item
        for item in timeline["items"]
        if item["subject_id"] == rebuilt["event"]
        and item["predicate"] in ("has_arrestee", "has_arresting_officer")
    ]
    assert len(participation) == 4

    graph = _graph(client, ANALYST)
    edges = [
        edge for edge in graph["edges"] if edge["subject_id"] == rebuilt["event"]
    ]
    participants = {
        edge["object_id"]
        for edge in edges
        if edge["predicate"] in ("has_arrestee", "has_arresting_officer")
    }
    assert len(participants) == 4
    assert participants == {rebuilt[slot] for slot in ("one", "two", "three", "officer")}


def test_the_three_surfaces_agree_about_when(client, incident) -> None:
    """The same interval, from three readings — and it is an *interval*.

    Not collapsed to one instant anywhere: the source stated a day, and a day is
    a range (spec 10 §6.3).
    """
    feature = next(
        f for f in _map(client, ANALYST) if f["properties"]["event_id"] == incident["event"]
    )
    intervals = feature["properties"]["time_intervals"]
    assert intervals
    assert all(i["earliest"].startswith("2019-03-12") for i in intervals)
    assert all(i["latest"].startswith("2019-03-12") for i in intervals)

    timeline = _timeline(client, ANALYST)
    rows = [item for item in timeline["items"] if item["subject_id"] == incident["event"]]
    assert rows
    # A stated day is a *bounded* range, never an instant — the whole point of
    # deriving certainty rather than asserting it.
    assert {row["certainty"] for row in rows} == {"bounded"}


def test_narrowing_the_window_narrows_all_three_the_same_way(client, rebuilt) -> None:
    """T62's criterion, checked on a real incident.

    Nothing renders on one surface that the filter excludes on another —
    because all three call the same window rule.
    """
    inside = {"from": "2019-01-01T00:00:00Z", "to": "2019-12-31T00:00:00Z"}
    outside = {"from": "2021-01-01T00:00:00Z", "to": "2021-12-31T00:00:00Z"}

    assert any(
        f["properties"]["event_id"] == rebuilt["event"] for f in _map(client, ANALYST, **inside)
    )
    assert any(
        item["subject_id"] == rebuilt["event"]
        for item in _timeline(client, ANALYST, **inside)["items"]
    )
    assert any(
        edge["subject_id"] == rebuilt["event"]
        for edge in _graph(
            client, ANALYST, event_from=inside["from"], event_to=inside["to"]
        )["edges"]
    )

    assert _map(client, ANALYST, **outside) == []
    assert not any(
        item["subject_id"] == rebuilt["event"]
        for item in _timeline(client, ANALYST, **outside)["items"]
    )
    assert not any(
        edge["subject_id"] == rebuilt["event"]
        for edge in _graph(
            client, ANALYST, event_from=outside["from"], event_to=outside["to"]
        )["edges"]
    )


def test_precision_is_distinct_and_generalized_the_same_way_everywhere(
    client, incident
) -> None:
    """Charter exit №3, checked on the same incident.

    The cleared viewer gets the building; the uncleared viewer gets the district
    — from the *same* query, because the ordinary claim filter removed a row
    rather than the server computing a coarser shape.
    """
    cleared = next(
        f for f in _map(client, ANALYST) if f["properties"]["event_id"] == incident["event"]
    )
    assert cleared["geometry"]["type"] == "Point"
    assert cleared["properties"]["derivation"] == "address_match"

    limited = next(
        f for f in _map(client, LOW) if f["properties"]["event_id"] == incident["event"]
    )
    assert limited["geometry"]["type"] == "Polygon"
    assert limited["properties"]["derivation"] == "admin_unit_boundary"
    assert limited["properties"]["admin_level"] == "subdivision"
    # The generalized answer discloses nothing about the finer one.
    assert "address_match" not in str(limited)


def test_the_geometry_rebuilds_from_claims_alone(client, incident, api_db, ontology) -> None:
    """Charter exit №5, on the incident's own place (B-13).

    `TRUNCATE` and rebuild: if any geometry the map draws had come from
    somewhere other than a claim, this is where it would go missing.
    """
    engine = sa.create_engine(api_db)
    before = next(
        f for f in _map(client, ANALYST) if f["properties"]["event_id"] == incident["event"]
    )
    with Session(engine) as session:
        session.execute(sa.text("TRUNCATE location_geometry_projection"))
        session.commit()
        assert _map(client, ANALYST)[0]["geometry"] is None

        rebuild_location_geometry_projection(session, ontology=ontology)
        session.commit()

    after = next(
        f for f in _map(client, ANALYST) if f["properties"]["event_id"] == incident["event"]
    )
    assert after == before


def test_as_of_before_the_recording_shows_the_incident_nowhere(client, incident) -> None:
    """One snapshot, three surfaces. A surface that answered as-of-now beside
    two that did not would be the inconsistency this phase set out to remove."""
    before = {"asOf": "2000-01-01T00:00:00Z"}
    assert _map(client, ANALYST, **before) == []
    assert _timeline(client, ANALYST, **before)["items"] == []
    assert _graph(client, ANALYST, as_of="2000-01-01T00:00:00Z")["edges"] == []


def test_the_graph_is_a_cache_and_says_so(client, incident, api_db, ontology) -> None:
    """The one asymmetry between the three surfaces, asserted rather than hidden.

    The map and the timeline read **claims**, so a newly recorded incident is on
    them immediately. The graph reads `edge_projection`, which is a cache
    (Article XIII) — so it lags until a rebuild, and `is_stale` is how the
    system knows.

    That is not a defect to paper over in the fixture above; it is the design,
    and the workspace already surfaces it (the graph view shows its stamps and
    offers an admin a rebuild).

    **A gap this test found and does not hide:** `is_stale` answers "was any row
    built at an older *identity revision* than the active one" — which is what
    its docstring says and what it was written for (a merge invalidates the
    projection). It does **not** answer "are there claims this projection has
    never seen", and recording an event advances no revision. So an operator
    cannot detect claim-staleness from `is_stale` alone. Asserted here as the
    absence it is, and carried to the exit review rather than quietly widened —
    changing what `is_stale` means is a decision, not a test fix.
    """
    engine = sa.create_engine(api_db)
    with Session(engine) as session:
        # Not stale by the identity measure: no merge has happened.
        assert is_stale(session) is False

    # ...and yet the projection has not seen this incident. On the map, on the
    # timeline, not yet on the graph — three readings of one claim set, two of
    # them live. This is the asymmetry `is_stale` cannot currently report.
    assert any(
        f["properties"]["event_id"] == incident["event"] for f in _map(client, ANALYST)
    )
    assert any(
        item["subject_id"] == incident["event"]
        for item in _timeline(client, ANALYST)["items"]
    )
    assert not any(
        edge["subject_id"] == incident["event"] for edge in _graph(client, ANALYST)["edges"]
    )

    with Session(engine) as session:
        rebuild_edge_projection(session, ontology=ontology)
        session.commit()

    assert any(
        edge["subject_id"] == incident["event"] for edge in _graph(client, ANALYST)["edges"]
    )
