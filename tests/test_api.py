"""API v1 tests (speckit T13/T14, spec 06).

The app is built against the test database with its OIDC authenticator swapped
for a locally-signed one (same validation path as production, no live
Keycloak).  The legacy ``/api/graph`` surface is exercised without a token to
prove the UI keeps working unchanged (T13/T14 AC).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

import jwt
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from aegis.actions import new_id
from aegis.api import create_app
from aegis.api.auth import OIDCAuthenticator
from aegis.api.deps import find_ungated_routes
from aegis.store import Entity, Source, SourceRecord

REPO_ROOT = Path(__file__).resolve().parents[1]
ISSUER = "http://localhost:8180/realms/aegis"
AUDIENCE = "aegis-api"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _StubKey:
    key = _KEY.public_key()


class _StubJWKS:
    def get_signing_key_from_jwt(self, token: str) -> _StubKey:
        return _StubKey()


def token(sub: str, *roles: str, clearance: int = 2) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": sub,
            "preferred_username": sub,
            "iat": now,
            "exp": now + timedelta(minutes=10),
            "realm_access": {"roles": list(roles)},
            "clearance": clearance,
        },
        _KEY,
        algorithm="RS256",
    )


def auth(sub: str, *roles: str, clearance: int = 2) -> dict:
    return {"Authorization": f"Bearer {token(sub, *roles, clearance=clearance)}"}


@pytest.fixture(scope="module")
def api_db() -> str:
    database_url = os.getenv("AEGIS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("set AEGIS_TEST_DATABASE_URL to run API tests")
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    previous = os.environ.get("AEGIS_DATABASE_URL")
    os.environ["AEGIS_DATABASE_URL"] = database_url
    os.environ.setdefault("AEGIS_API_AUDIENCE", AUDIENCE)
    from aegis.config import get_settings

    get_settings.cache_clear()
    command.upgrade(config, "head")
    yield database_url
    if previous is None:
        os.environ.pop("AEGIS_DATABASE_URL", None)
    else:
        os.environ["AEGIS_DATABASE_URL"] = previous
    get_settings.cache_clear()


@pytest.fixture(scope="module")
def client(api_db: str) -> TestClient:
    app = create_app()
    app.state.authenticator = OIDCAuthenticator(app.state.settings, jwks_client=_StubJWKS())
    return TestClient(app)


@pytest.fixture(scope="module")
def seeded(api_db: str) -> dict:
    engine = sa.create_engine(api_db)
    ids = {"source": new_id("src"), "record": new_id("rec"), "p": new_id("ent"), "o": new_id("ent")}
    with Session(engine) as session, session.begin():
        session.add(Source(source_id=ids["source"], source_type="open_source", name="API test"))
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="d" * 64,
                storage_uri="test://api",
            )
        )
        session.add_all(
            [
                Entity(entity_id=ids["p"], entity_type="person", label="API Person"),
                Entity(entity_id=ids["o"], entity_type="organization", label="API Org"),
            ]
        )
    engine.dispose()
    return ids


# ── deny-by-default lint (the T12 CI gate) ──────────────────────────────────


def test_no_ungated_routes(client: TestClient) -> None:
    assert find_ungated_routes(client.app) == []


# ── AuthN at the HTTP boundary ───────────────────────────────────────────────


def test_protected_route_requires_token(client: TestClient) -> None:
    assert client.get(f"/v1/claims/{new_id('clm')}").status_code == 401


def test_wrong_audience_401(client: TestClient) -> None:
    bad = jwt.encode(
        {
            "iss": ISSUER,
            "aud": "someone-else",
            "sub": "u",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        _KEY,
        algorithm="RS256",
    )
    resp = client.get(f"/v1/claims/{new_id('clm')}", headers={"Authorization": f"Bearer {bad}"})
    assert resp.status_code == 401


# ── claims: create, read (with row filters), retract ────────────────────────


def test_claim_lifecycle_and_rbac(client: TestClient, seeded: dict) -> None:
    body = {
        "subject_id": seeded["p"],
        "predicate": "member_of",
        "object_id": seeded["o"],
        "record_id": seeded["record"],
        "assertion_type": "reported",
        "credibility_normalized": "probably_true",
    }
    # evidence_officer cannot record claims (role gate → 403)
    denied = client.post("/v1/claims", json=body, headers=auth("eo", "evidence_officer"))
    assert denied.status_code == 403

    created = client.post("/v1/claims", json=body, headers=auth("ana", "analyst"))
    assert created.status_code == 201, created.text
    claim_id = created.json()["claim_id"]

    got = client.get(f"/v1/claims/{claim_id}", headers=auth("ana", "analyst"))
    assert got.status_code == 200
    assert got.json()["predicate"] == "member_of"

    # retract, then it is invisible to a normal analyst but visible to an auditor
    retracted = client.post(
        f"/v1/claims/{claim_id}/retract",
        json={"reason": "test retraction"},
        headers=auth("suP", "supervisor"),
    )
    assert retracted.status_code == 200
    assert client.get(f"/v1/claims/{claim_id}", headers=auth("ana", "analyst")).status_code == 404
    assert client.get(f"/v1/claims/{claim_id}", headers=auth("aud", "auditor")).status_code == 200


def test_handling_floor_hides_high_claims(client: TestClient, seeded: dict) -> None:
    created = client.post(
        "/v1/claims",
        json={
            "subject_id": seeded["p"],
            "predicate": "member_of",
            "object_id": seeded["o"],
            "record_id": seeded["record"],
            "assertion_type": "reported",
            "handling_code": "sensitive",
        },
        headers=auth("ana", "analyst"),
    )
    assert created.status_code == 201
    claim_id = created.json()["claim_id"]
    # clearance 0 cannot see a sensitive claim (404, not "hidden")
    low = client.get(f"/v1/claims/{claim_id}", headers=auth("ana", "analyst", clearance=0))
    assert low.status_code == 404
    high = client.get(f"/v1/claims/{claim_id}", headers=auth("ana", "analyst", clearance=2))
    assert high.status_code == 200


def test_unknown_predicate_is_422_with_path(client: TestClient, seeded: dict) -> None:
    resp = client.post(
        "/v1/claims",
        json={
            "subject_id": seeded["p"],
            "predicate": "owns_a_yacht",
            "object_id": seeded["o"],
            "record_id": seeded["record"],
            "assertion_type": "reported",
        },
        headers=auth("ana", "analyst"),
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["title"] == "validation failed"
    assert body["path"].startswith("predicates.owns_a_yacht")


# ── entity detail groups claims by predicate ────────────────────────────────


def test_entity_detail(client: TestClient, seeded: dict) -> None:
    client.post(
        "/v1/claims",
        json={
            "subject_id": seeded["p"],
            "predicate": "known_as",
            "object_value": "The Tester",
            "record_id": seeded["record"],
            "assertion_type": "reported",
        },
        headers=auth("ana", "analyst"),
    )
    resp = client.get(f"/v1/entities/{seeded['p']}", headers=auth("ana", "analyst"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["entity"]["label"] == "API Person"
    assert "known_as" in body["claims_by_predicate"]


# ── sources ──────────────────────────────────────────────────────────────────


def test_create_and_list_sources(client: TestClient) -> None:
    created = client.post(
        "/v1/sources",
        json={"source_type": "open_source", "name": "Reuters"},
        headers=auth("ana", "analyst"),
    )
    assert created.status_code == 201
    listed = client.get("/v1/sources", headers=auth("ana", "analyst"))
    assert listed.status_code == 200
    assert any(s["name"] == "Reuters" for s in listed.json())


def test_unknown_source_type_rejected(client: TestClient) -> None:
    resp = client.post(
        "/v1/sources",
        json={"source_type": "telepathy", "name": "X"},
        headers=auth("ana", "analyst"),
    )
    assert resp.status_code == 422


# ── legacy projection surface: public, unchanged shape (T13/T14) ────────────


def test_legacy_graph_is_public_and_shaped(client: TestClient) -> None:
    # ensure the projection file exists (committed baseline is fine for shape)
    graph_path = REPO_ROOT / "output" / "real_graph.json"
    if not graph_path.exists():
        pytest.skip("output/real_graph.json missing — run `aegis projections rebuild`")
    resp = client.get("/api/graph")  # no Authorization header
    assert resp.status_code == 200
    body = resp.json()
    assert {"nodes", "edges", "cells", "meta"} <= set(body)
    stats = client.get("/api/stats")
    assert stats.status_code == 200
    assert stats.json()["nodes"] == len(body["nodes"])
    assert client.get("/api/cells").status_code == 200
    assert client.get("/api/query/brokers").status_code == 200


def test_openapi_renders(client: TestClient) -> None:
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    assert "/v1/claims" in schema.json()["paths"]
