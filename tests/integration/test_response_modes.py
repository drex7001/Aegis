"""The three response modes, where a caller can actually observe them (T79).

Spec 03 §6 is the policy; `tests/contract/test_response_modes.py` proves the
policy and the spec agree. This file proves the *routes* behave the way the
policy says, on the two surfaces T79 changed:

* the **object view** is `marked` — and marked from the ontology, never from the
  rows, which is the half of ADR-067 a naive test would miss entirely;
* an **object set** filtering on a property above the evaluator's clearance is
  refused, because evaluating it produced a wrong answer that looked right —
  that half lives in `test_object_set_routes.py`, where the set fixtures and the
  FGA stub the routes need already are.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from aegis.actions import new_id
from aegis.authz.modes import withheld_predicates
from aegis.er.ledger import open_membership
from aegis.er.normalize import norm_key
from aegis.store import Claim, Entity, Mention, Source, SourceRecord
from tests.integration.test_api import (  # noqa: F401
    _FakeFGA,
    api_db,
    auth,
    clean_api_database,
    client,
    fake_fga,
)

pytestmark = pytest.mark.requirement("Article-VI", "H-25", "ADR-061", "ADR-067", "T79")

ANALYST = "analyst-t79"

#: `has_nic` carries the shared `registered_identifier` property, which the
#: platform module declares `restricted` — "a state-issued number is never
#: `open`". A clearance-0 reader may never read one, at any handling code.
RESTRICTED_PREDICATE = "has_nic"


@pytest.fixture()
def world(client: TestClient) -> dict:
    """Two people of the same type: one **with** a restricted claim, one without.

    The pair is the whole design of this file. A marker that appeared only for
    `documented` would be data-derived, which is exactly the implementation
    ADR-067 rejects — and a test that checked only `documented` would pass on it.
    """
    engine = sa.create_engine(client.app.state.settings.database_url)
    ids: dict[str, str] = {}
    with Session(engine) as session, session.begin():
        session.add(
            Source(source_id=(sid := new_id("src")), source_type="open_source", name="T79")
        )
        session.add(
            SourceRecord(
                record_id=(rid := new_id("rec")),
                source_id=sid,
                ingest_key=new_id("key"),
                content_hash="b" * 64,
                storage_uri="test://t79",
            )
        )
        session.flush()
        for key, label in (("documented", "Fictional Documented"), ("undocumented", "Fictional Plain")):
            entity_id, mention_id = new_id("ent"), new_id("men")
            ids[key] = entity_id
            session.add(Entity(entity_id=entity_id, entity_type="person", label=label))
            session.add(
                Mention(
                    mention_id=mention_id,
                    record_id=rid,
                    raw_text=label,
                    norm_key=f"{norm_key(label)}-{mention_id[-6:].lower()}",
                )
            )
            session.flush()
            open_membership(session, mention_id=mention_id, entity_id=entity_id)

        # Deliberately `open`: the claim is withheld by the *property's*
        # sensitivity, not by a handling code, which is the distinction §6.1
        # turns on. If this were `restricted` the test would prove the older,
        # weaker thing.
        session.add(
            Claim(
                claim_id=new_id("clm"),
                subject_id=ids["documented"],
                predicate=RESTRICTED_PREDICATE,
                object_value="199012345678",
                assertion_type="reported",
                record_id=rid,
                handling_code="open",
                identity_revision_id=0,
                ontology_version=client.app.state.ontology.version,
            )
        )
    engine.dispose()
    return ids


def _view(client: TestClient, entity_id: str, clearance: int) -> dict:
    response = client.get(
        f"/v1/entities/{entity_id}",
        headers=auth(ANALYST, "analyst", clearance=clearance),
    )
    assert response.status_code == 200, response.text
    return response.json()


# ── the object view is `marked` ──────────────────────────────────────────────


def test_a_low_clearance_reader_is_told_the_predicate_is_withheld(
    client: TestClient, world: dict
) -> None:
    body = _view(client, world["documented"], clearance=0)

    assert RESTRICTED_PREDICATE not in body["claims_by_predicate"], (
        "the claim itself must still be absent — marking is not showing"
    )
    marked = {entry["predicate"] for entry in body["withheld"]}
    assert RESTRICTED_PREDICATE in marked


def test_the_marker_carries_the_predicate_and_nothing_else(
    client: TestClient, world: dict
) -> None:
    """ADR-061: not the value, not the count, not the grading, not an id."""
    body = _view(client, world["documented"], clearance=0)
    entry = next(e for e in body["withheld"] if e["predicate"] == RESTRICTED_PREDICATE)

    assert entry == {"predicate": RESTRICTED_PREDICATE, "withheld": True}
    # And the value is nowhere else in the payload either.
    assert "199012345678" not in response_text(body)


def test_the_marker_is_identical_for_an_entity_with_no_such_claim(
    client: TestClient, world: dict
) -> None:
    """ADR-067, and the assertion the whole file exists for.

    A data-derived marker would appear for `documented` and not for
    `undocumented`, which would make the marker a reliable oracle for "this
    person has a national identifier on file" — the existence leak H-25 named.
    """
    documented = _view(client, world["documented"], clearance=0)["withheld"]
    undocumented = _view(client, world["undocumented"], clearance=0)["withheld"]

    assert documented == undocumented
    assert documented, "both are empty, so this proves nothing — check the fixture"


def test_a_cleared_reader_sees_the_claim_and_no_marker(
    client: TestClient, world: dict
) -> None:
    body = _view(client, world["documented"], clearance=2)

    assert body["withheld"] == []
    assert RESTRICTED_PREDICATE in body["claims_by_predicate"]


def test_the_marker_matches_the_function_the_policy_exposes(
    client: TestClient, world: dict
) -> None:
    """The route must not compute its own answer beside `withheld_predicates`."""
    ontology = client.app.state.ontology
    body = _view(client, world["undocumented"], clearance=0)

    assert [entry["predicate"] for entry in body["withheld"]] == withheld_predicates(
        ontology, "person", clearance=0
    )


def response_text(body: dict) -> str:
    import json

    return json.dumps(body, default=str)
