"""The second domain is served over the API, not just the action layer (T31, T40).

The Phase 3 charter's second exit criterion asks that the fixture module
"loads, validates, **serves object/claim routes**, and appears in the client
types — with zero core-code change". `test_second_domain.py` covers loading,
validation and the projection; this covers the routes, because a domain the
core can validate but not serve would not be a domain anyone could use.

The app is built normally and its registry swapped: routes read the ontology
from `app.state.ontology` (`aegis/api/deps.py`), so pointing an otherwise
untouched application at `border-cargo` is the whole setup. That is the claim
being tested — the API has no domain knowledge to replace.
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from aegis.actions import new_id
from aegis.api import create_app
from aegis.api.auth import OIDCAuthenticator
from aegis.ontology import load
from aegis.store import Entity, Source, SourceRecord
from tests.integration.test_api import AUDIENCE, _StubJWKS, auth
from tests.support.database import configured_test_database, truncate_domain_data
from tests.support.paths import REPO_ROOT

pytestmark = pytest.mark.requirement("Article-XIV", "ADR-037", "T31", "T40")

COMPOSITION = REPO_ROOT / "tests" / "fixtures" / "ontology" / "border-cargo-composition.yaml"


@pytest.fixture(scope="module")
def cargo_db(test_database_url: str, alembic_config: Config) -> str:
    os.environ.setdefault("AEGIS_API_AUDIENCE", AUDIENCE)
    with configured_test_database(test_database_url, alembic_config):
        yield test_database_url


@pytest.fixture(scope="module")
def cargo_client(cargo_db: str) -> TestClient:
    app = create_app()
    app.state.authenticator = OIDCAuthenticator(app.state.settings, jwks_client=_StubJWKS())
    # The only line that differs from a criminal-network app.
    app.state.ontology = load(COMPOSITION)
    return TestClient(app)


@pytest.fixture()
def seeded(cargo_db: str) -> dict:
    engine = sa.create_engine(cargo_db)
    truncate_domain_data(engine)
    ids = {
        "source": new_id("src"),
        "record": new_id("rec"),
        "consignment": new_id("ent"),
        "port": new_id("ent"),
    }
    with Session(engine) as session, session.begin():
        session.add(
            Source(source_id=ids["source"], source_type="open_source", name="T31 routes")
        )
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="f" * 64,
                storage_uri="test://t31-routes",
            )
        )
        session.add_all(
            [
                Entity(
                    entity_id=ids["consignment"],
                    entity_type="consignment",
                    label="CN-ROUTE-001",
                ),
                Entity(
                    entity_id=ids["port"], entity_type="port_of_entry", label="Port Fictitious"
                ),
            ]
        )
    engine.dispose()
    yield ids
    engine = sa.create_engine(cargo_db)
    truncate_domain_data(engine)
    engine.dispose()


def test_the_vocabulary_route_serves_the_fixture_composition(cargo_client) -> None:
    response = cargo_client.get("/v1/ontology/vocabulary", headers=auth("u1", "analyst"))
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "1.0.0"          # the fixture composition's own
    assert body["handling_codes"] == ["open", "restricted", "sensitive"]


def test_a_claim_route_accepts_the_fixture_vocabulary(cargo_client, seeded) -> None:
    response = cargo_client.post(
        "/v1/claims",
        headers=auth("u1", "analyst"),
        json={
            "subject_id": seeded["consignment"],
            "predicate": "cleared_at",
            "object_id": seeded["port"],
            "record_id": seeded["record"],
            "collection_method": "curated",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["predicate"] == "cleared_at"


def test_a_criminal_network_predicate_is_rejected_here(cargo_client, seeded) -> None:
    """Loading a different domain really does change what the API accepts."""
    response = cargo_client.post(
        "/v1/claims",
        headers=auth("u1", "analyst"),
        json={
            "subject_id": seeded["consignment"],
            "predicate": "member_of",
            "object_id": seeded["port"],
            "record_id": seeded["record"],
            "collection_method": "curated",
        },
    )
    assert response.status_code == 422
    assert response.json()["path"] == "predicates.member_of"


def test_the_entity_route_serves_a_fixture_object_type(cargo_client, seeded) -> None:
    response = cargo_client.get(
        f"/v1/entities/{seeded['consignment']}", headers=auth("u1", "analyst")
    )
    assert response.status_code == 200
    body = response.json()
    assert body["entity"]["entity_type"] == "consignment"
    assert body["resolved_entity_id"] == seeded["consignment"]


def test_the_error_envelope_is_served_as_problem_json(cargo_client, seeded) -> None:
    """T36's contract holds for a domain it has never seen."""
    response = cargo_client.post(
        "/v1/claims",
        headers=auth("u1", "analyst"),
        json={
            "subject_id": seeded["consignment"],
            "predicate": "not_a_predicate",
            "object_id": seeded["port"],
            "record_id": seeded["record"],
        },
    )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "validation failed"
