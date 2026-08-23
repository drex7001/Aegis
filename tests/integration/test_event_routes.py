"""`POST /v1/events` and the object view's inbound region (T57, spec 10 §13).

Two things under test at the API boundary. The route is gated exactly as
recording a claim is — an event *is* claims, so an occurrence must not be
assertable by someone who may not assert its parts. And the inbound set is
filtered by the same predicates as the outbound one, which is the property that
stops "Referenced by" becoming a way to read a claim through the back door.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from aegis.actions import new_id
from aegis.store import Entity, Source, SourceRecord
from tests.integration.test_api import (  # noqa: F401
    _FakeFGA,
    api_db,
    auth,
    clean_api_database,
    client,
    fake_fga,
)

pytestmark = pytest.mark.requirement(
    "Article-I", "Article-VI", "ADR-046", "T57"
)

#: Clearance 0 — `open` only. The default in `auth` is 2, which would make
#: the sensitive-claim case below assert nothing.
ANALYST = auth("analyst-t57", "analyst", clearance=0)
CLEARED = auth("cleared-t57", "analyst", clearance=2)


@pytest.fixture()
def world(client: TestClient, api_db: str) -> dict:
    ids = {"source": new_id("src"), "record": new_id("rec")}
    engine = sa.create_engine(api_db)
    with Session(engine) as session, session.begin():
        session.add(
            Source(
                source_id=ids["source"],
                source_type="open_source",
                name="T57 route source",
                reliability_normalized="generally_reliable",
            )
        )
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="e" * 64,
                storage_uri="test://t57/routes",
            )
        )
        session.flush()
        for slot, label, kind in (
            ("one", "Nimal Perera", "person"),
            ("two", "Kamala Silva", "person"),
            ("three", "Ranjan Fernando", "person"),
            ("place", "Negombo", "location"),
        ):
            entity_id = new_id("ent")
            ids[slot] = entity_id
            session.add(Entity(entity_id=entity_id, entity_type=kind, label=label))
    return ids


def _body(world: dict, **overrides) -> dict:
    body = {
        "event_type": "arrest",
        "record_id": world["record"],
        "summary": "Three men arrested at Negombo",
        "event_time_earliest": "2019-03-12T00:00:00Z",
        "event_time_latest": "2019-03-12T23:59:59Z",
        "participants": [
            {"role": "has_arrestee", "entity_id": world["one"]},
            {"role": "has_arrestee", "entity_id": world["two"]},
            {"role": "has_arrestee", "entity_id": world["three"]},
        ],
        "places": [{"role": "took_place_at", "entity_id": world["place"]}],
    }
    body.update(overrides)
    return body


def test_an_analyst_records_an_event_and_is_told_what_it_created(client, world) -> None:
    response = client.post("/v1/events", json=_body(world), headers=ANALYST)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["entity_type"] == "arrest"
    # The claim ids, not just the entity: every assertion the call made has its
    # own provenance, and returning the entity alone would suggest the
    # occurrence itself was the record.
    assert len(body["claim_ids"]) == 5
    for claim_id in body["claim_ids"]:
        assert client.get(f"/v1/claims/{claim_id}", headers=ANALYST).status_code == 200


def test_the_event_renders_through_the_generic_object_view(client, world) -> None:
    """No type-specific route and no type-specific response (Article XIV)."""
    created = client.post("/v1/events", json=_body(world), headers=ANALYST).json()
    response = client.get(f"/v1/entities/{created['entity_id']}", headers=ANALYST)
    assert response.status_code == 200
    detail = response.json()
    assert detail["entity"]["entity_type"] == "arrest"
    assert set(detail["claims_by_predicate"]) == {
        "summarized_as",
        "has_arrestee",
        "took_place_at",
    }
    assert len(detail["claims_by_predicate"]["has_arrestee"]) == 3


def test_each_participant_page_shows_the_arrest(client, world) -> None:
    """Charter exit №2's other half: one claim set, one answer from both ends."""
    created = client.post("/v1/events", json=_body(world), headers=ANALYST).json()
    detail = client.get(f"/v1/entities/{world['one']}", headers=ANALYST).json()

    assert detail["claims_by_predicate"] == {}
    inbound = detail["inbound_claims_by_predicate"]
    assert set(inbound) == {"has_arrestee"}
    assert inbound["has_arrestee"][0]["claim"]["subject_id"] == created["entity_id"]
    # The source travels with it, so the provenance panel opens from either end.
    assert inbound["has_arrestee"][0]["record"]["record_id"] == world["record"]


def test_the_inbound_set_is_filtered_like_the_outbound_one(client, world) -> None:
    """"Referenced by" must not become a back door.

    A claim recorded above the caller's clearance is absent from both
    directions — not merely from the one the caller happens to ask about.
    """
    client.post(
        "/v1/events",
        json=_body(world, handling_code="sensitive"),
        headers=CLEARED,
    )
    detail = client.get(f"/v1/entities/{world['one']}", headers=ANALYST).json()
    assert detail["inbound_claims_by_predicate"] == {}

    cleared = client.get(f"/v1/entities/{world['one']}", headers=CLEARED).json()
    assert set(cleared["inbound_claims_by_predicate"]) == {"has_arrestee"}


def test_the_route_requires_authentication(client, world) -> None:
    response = client.post("/v1/events", json=_body(world))
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_a_role_without_the_action_is_refused(client, world) -> None:
    response = client.post(
        "/v1/events", json=_body(world), headers=auth("auditor-t57", "auditor")
    )
    assert response.status_code == 403


def test_an_undeclared_role_is_a_422_naming_it(client, world) -> None:
    response = client.post(
        "/v1/events",
        json=_body(world, participants=[{"role": "has_ringleader", "entity_id": world["one"]}]),
        headers=ANALYST,
    )
    assert response.status_code == 422
    assert "has_ringleader" in response.text


def test_an_undeclared_field_on_a_participant_is_refused(client, world) -> None:
    """`extra="forbid"` on the link model: a field nobody reads is a field a
    caller believes is being honoured."""
    response = client.post(
        "/v1/events",
        json=_body(
            world,
            participants=[
                {"role": "has_arrestee", "entity_id": world["one"], "confidence": 0.9}
            ],
        ),
        headers=ANALYST,
    )
    assert response.status_code == 422
    assert "confidence" in response.text
