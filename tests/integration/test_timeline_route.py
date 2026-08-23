"""One timeline, no duplicates, and undated said out loud (T61, spec 10 §11).

Two properties carry the task's acceptance criteria.

**No duplicates is structural.** Timeline items are claims, and an event appears
through the claims that assert it — so an arrest with three arrestees is four
rows because four things were asserted, not one row plus three copies of it.
Nothing de-duplicates; there was never a second copy to remove.

**Undated is a state, not an absence.** A claim with no stated time is excluded
from a bounded window and *counted* in the response, because a narrowed window
that silently dropped it would look like a complete account of everything known.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, new_id
from aegis.ontology import load
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

pytestmark = pytest.mark.requirement("Article-VI", "Article-VIII", "T61")

ANALYST = auth("analyst-t61", "analyst", clearance=0)
CLEARED = auth("cleared-t61", "analyst", clearance=2)

MARCH = datetime(2019, 3, 12, tzinfo=timezone.utc)
MARCH_END = datetime(2019, 3, 12, 23, 59, 59, tzinfo=timezone.utc)
APRIL_START = datetime(2019, 4, 1, tzinfo=timezone.utc)
APRIL_END = datetime(2019, 4, 30, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture()
def world(client: TestClient, api_db: str, ontology) -> dict:
    engine = sa.create_engine(api_db)
    ids: dict[str, str] = {}
    with Session(engine) as session:
        with session.begin():
            ids["source"] = new_id("src")
            session.add(
                Source(
                    source_id=ids["source"],
                    source_type="open_source",
                    name="T61 source",
                    reliability_normalized="generally_reliable",
                )
            )
            ids["record"] = new_id("rec")
            session.add(
                SourceRecord(
                    record_id=ids["record"],
                    source_id=ids["source"],
                    ingest_key=new_id("key"),
                    content_hash="b1" * 32,
                    storage_uri="test://t61/one",
                )
            )
            session.flush()
            for slot, label, kind in (
                ("one", "Nimal Perera", "person"),
                ("two", "Kamala Silva", "person"),
                ("three", "Ranjan Fernando", "person"),
                ("org", "Harbour Traders", "organization"),
            ):
                ids[slot] = new_id("ent")
                session.add(Entity(entity_id=ids[slot], entity_type=kind, label=label))

        service = ActionService(session, ontology)
        context = ActionContext(
            actor="user:seed", purpose="T61 seed", roles=frozenset({"analyst"})
        )
        # An exact arrest with three participants.
        event = service.record_event(
            context,
            event_type="arrest",
            record_id=ids["record"],
            summary="Three men arrested",
            event_time_earliest=MARCH,
            event_time_latest=MARCH,
            participants=[
                {"role": "has_arrestee", "entity_id": ids[slot]}
                for slot in ("one", "two", "three")
            ],
        )
        ids["event"] = event.entity_id
        # A range: "some time in April".
        service.record_claim(
            context,
            subject_id=ids["one"],
            predicate="member_of",
            object_id=ids["org"],
            record_id=ids["record"],
            event_time_earliest=APRIL_START,
            event_time_latest=APRIL_END,
            collection_method="curated",
        )
        # Open-ended: "after March, end unknown".
        service.record_claim(
            context,
            subject_id=ids["two"],
            predicate="known_as",
            object_value="The Broker",
            record_id=ids["record"],
            event_time_earliest=MARCH_END,
            collection_method="curated",
        )
        # Undated, and it must stay that way.
        service.record_claim(
            context,
            subject_id=ids["three"],
            predicate="known_as",
            object_value="Ranjan",
            record_id=ids["record"],
            collection_method="curated",
        )
        session.commit()
    return ids


def _timeline(client: TestClient, headers: dict = CLEARED, **params) -> dict:
    response = client.get("/v1/timeline", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_four_certainties_are_derived_from_the_interval(client, world) -> None:
    """Never asserted — so nothing downstream can render "in April" as 1 April."""
    body = _timeline(client)
    by_certainty: dict[str, list[dict]] = {}
    for item in body["items"]:
        by_certainty.setdefault(item["certainty"], []).append(item)

    assert {"exact", "bounded", "open"} <= set(by_certainty)
    assert by_certainty["exact"][0]["earliest"] == by_certainty["exact"][0]["latest"]
    april = by_certainty["bounded"][0]
    assert april["earliest"] < april["latest"]
    assert by_certainty["open"][0]["latest"] is None


def test_an_event_appears_through_its_claims_not_as_a_row_of_its_own(
    client, world
) -> None:
    """The acceptance criterion, and it is structural.

    Four assertions were made about the arrest — a summary and three arrestees —
    so there are four rows. There is no fifth row for "the event", and nothing
    de-duplicates, because there was never a second copy to remove.
    """
    body = _timeline(client)
    event_rows = [item for item in body["items"] if item["subject_id"] == world["event"]]
    assert len(event_rows) == 4
    assert {item["predicate"] for item in event_rows} == {"summarized_as", "has_arrestee"}
    assert all(item["claim_id"] for item in event_rows)
    # Every row is a claim, so every row opens its own provenance.
    for item in event_rows:
        assert client.get(f"/v1/claims/{item['claim_id']}", headers=CLEARED).status_code == 200


def test_an_entity_filter_sees_both_directions(client, world) -> None:
    """An arrest's date reaches a participant's timeline only through the claim
    the *event* is the subject of (spec 10 §13)."""
    body = _timeline(client, entityId=world["one"])
    predicates = {item["predicate"] for item in body["items"]}
    assert "has_arrestee" in predicates   # inbound: the arrest names them
    assert "member_of" in predicates      # outbound: they assert this


def test_an_undated_claim_is_counted_never_placed(client, world) -> None:
    body = _timeline(client)
    assert body["undated_count"] == 1
    assert all(item["certainty"] != "undated" or item["earliest"] is None for item in body["items"])


def test_a_bounded_window_excludes_undated_and_still_counts_it(client, world) -> None:
    """Charter §11.2: an undated claim is not in a bounded window — and a window
    that silently dropped it would look like a complete account."""
    body = _timeline(
        client, **{"from": "2019-03-01T00:00:00Z", "to": "2019-03-31T00:00:00Z"}
    )
    assert body["undated_count"] == 1
    assert all(item["certainty"] != "undated" for item in body["items"])
    # The April claim intersects nothing in March.
    assert all(item["predicate"] != "member_of" for item in body["items"])


def test_the_window_rule_is_intersection_not_containment(client, world) -> None:
    """A claim spanning the whole of April is in a window covering half of it."""
    body = _timeline(
        client, **{"from": "2019-04-15T00:00:00Z", "to": "2019-04-20T00:00:00Z"}
    )
    assert any(item["predicate"] == "member_of" for item in body["items"])


def test_an_open_ended_claim_intersects_everything_after_its_bound(
    client, world
) -> None:
    body = _timeline(
        client, **{"from": "2020-01-01T00:00:00Z", "to": "2020-12-31T00:00:00Z"}
    )
    assert any(item["predicate"] == "known_as" for item in body["items"])


def test_the_timeline_is_filtered_like_every_other_read(client, world, api_db, ontology) -> None:
    engine = sa.create_engine(api_db)
    with Session(engine) as session:
        ActionService(session, ontology).record_claim(
            ActionContext(actor="user:seed", purpose="seed", roles=frozenset({"analyst"})),
            subject_id=world["one"],
            predicate="known_as",
            object_value="A sensitive alias",
            record_id=world["record"],
            handling_code="sensitive",
            event_time_earliest=MARCH,
            event_time_latest=MARCH,
            collection_method="curated",
        )
        session.commit()

    cleared = _timeline(client, CLEARED)
    limited = _timeline(client, ANALYST)
    def aliases(body: dict) -> set[str]:
        return {str(item["object_value"]) for item in body["items"]}

    assert "A sensitive alias" in aliases(cleared)
    assert "A sensitive alias" not in aliases(limited)


def test_an_inverted_window_is_a_422(client, world) -> None:
    response = client.get(
        "/v1/timeline",
        headers=CLEARED,
        params={"from": "2021-01-01T00:00:00Z", "to": "2019-01-01T00:00:00Z"},
    )
    assert response.status_code == 422


def test_the_route_requires_authentication(client, world) -> None:
    response = client.get("/v1/timeline")
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_every_response_carries_the_as_of_stamp(client, world) -> None:
    body = _timeline(client)
    assert body["stamp"]["ontology_version"]
    assert body["stamp"]["identity_revision_id"] is not None
