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
from aegis.api.routes import graph
from aegis.store import AuthzOutbox, Entity, Source, SourceRecord
from tests.support.database import configured_test_database, truncate_domain_data

REPO_ROOT = Path(__file__).resolve().parents[2]
ISSUER = "http://localhost:8180/realms/aegis"
AUDIENCE = "aegis-api"

pytestmark = pytest.mark.requirement("Article-VI", "T13", "T14")

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _StubKey:
    key = _KEY.public_key()


class _StubJWKS:
    def get_signing_key_from_jwt(self, token: str) -> _StubKey:
        return _StubKey()


class _FakeFGA:
    """Small relation evaluator for request-path revocation tests."""

    def __init__(self) -> None:
        self.tuples: set[tuple[str, str, str]] = set()
        self.deleted: list[tuple[str, str, str]] = []

    def add(self, user: str, relation: str, object_: str) -> None:
        self.tuples.add((user, relation, object_))

    def delete(self, tuple_: dict[str, str]) -> None:
        key = (tuple_["user"], tuple_["relation"], tuple_["object"])
        self.tuples.discard(key)
        self.deleted.append(key)

    def check(self, user: str, relation: str, object_: str) -> bool:
        if (user, relation, object_) in self.tuples:
            return True
        if object_.startswith("case:"):
            memberships = {
                tuple_relation
                for tuple_user, tuple_relation, tuple_object in self.tuples
                if tuple_user == user and tuple_object == object_
            }
            if relation == "can_approve":
                return "supervisor" in memberships
            if relation in {"can_view", "can_edit"}:
                return bool(
                    memberships
                    & {"analyst", "investigator", "supervisor", "auditor_grant"}
                )
        if object_.startswith("evidence_item:"):
            if relation == "can_transfer" and (user, "custodian", object_) in self.tuples:
                return True
            parent_cases = {
                tuple_user
                for tuple_user, tuple_relation, tuple_object in self.tuples
                if tuple_relation == "case" and tuple_object == object_
            }
            inherited = "can_approve" if relation == "can_transfer" else relation
            return any(self.check(user, inherited, parent_case) for parent_case in parent_cases)
        return False


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
def api_db(test_database_url: str, alembic_config: Config) -> str:
    database_url = test_database_url
    os.environ.setdefault("AEGIS_API_AUDIENCE", AUDIENCE)
    with configured_test_database(database_url, alembic_config):
        yield database_url


@pytest.fixture(autouse=True)
def clean_api_database(api_db: str):
    engine = sa.create_engine(api_db)
    truncate_domain_data(engine)
    yield
    truncate_domain_data(engine)
    engine.dispose()


@pytest.fixture(scope="module")
def client(api_db: str) -> TestClient:
    app = create_app()
    app.state.authenticator = OIDCAuthenticator(app.state.settings, jwks_client=_StubJWKS())
    return TestClient(app)


@pytest.fixture()
def fake_fga(client: TestClient):
    previous = client.app.state.fga
    fake = _FakeFGA()
    client.app.state.fga = fake
    client.app.state.authz_dispatcher_task = None
    yield fake
    client.app.state.fga = previous


@pytest.fixture()
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


# ── revocations: commit first, then inline FGA delete (T16b) ───────────────


def _open_authorized_case(client: TestClient, fake_fga: _FakeFGA, owner: str) -> str:
    created = client.post(
        "/v1/cases",
        json={"title": "Revocation case", "purpose": "T16b verification"},
        headers=auth(owner, "analyst", "supervisor"),
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["case_id"]
    fake_fga.add(f"user:{owner}", "supervisor", f"case:{case_id}")
    return case_id


def test_revoked_member_is_denied_with_dispatcher_paused(
    client: TestClient, fake_fga: _FakeFGA
) -> None:
    owner = f"owner-{new_id('u')}"
    member = f"member-{new_id('u')}"
    case_id = _open_authorized_case(client, fake_fga, owner)

    assigned = client.post(
        f"/v1/cases/{case_id}/members",
        json={"user_id": member, "role": "analyst"},
        headers=auth(owner, "supervisor"),
    )
    assert assigned.status_code == 201, assigned.text
    member_tuple = (f"user:{member}", "analyst", f"case:{case_id}")
    fake_fga.add(*member_tuple)
    assert client.get(
        f"/v1/cases/{case_id}", headers=auth(member, "analyst")
    ).status_code == 200

    revoked = client.delete(
        f"/v1/cases/{case_id}/members/{member}",
        headers=auth(owner, "supervisor"),
    )
    assert revoked.status_code == 204, revoked.text
    assert member_tuple in fake_fga.deleted
    assert client.app.state.authz_dispatcher_task is None
    assert client.get(
        f"/v1/cases/{case_id}", headers=auth(member, "analyst")
    ).status_code == 404

    with client.app.state.sessionmaker() as session:
        pending_delete = session.scalar(
            sa.select(AuthzOutbox).where(
                AuthzOutbox.op == "delete",
                AuthzOutbox.processed_at.is_(None),
                AuthzOutbox.fga_tuple == {
                    "user": member_tuple[0],
                    "relation": member_tuple[1],
                    "object": member_tuple[2],
                },
            )
        )
    assert pending_delete is not None


def test_role_and_custody_changes_delete_old_grants_inline(
    client: TestClient, fake_fga: _FakeFGA
) -> None:
    owner = f"owner-{new_id('u')}"
    member = f"member-{new_id('u')}"
    case_id = _open_authorized_case(client, fake_fga, owner)

    assert client.post(
        f"/v1/cases/{case_id}/members",
        json={"user_id": member, "role": "analyst"},
        headers=auth(owner, "supervisor"),
    ).status_code == 201
    old_member_tuple = (f"user:{member}", "analyst", f"case:{case_id}")
    fake_fga.add(*old_member_tuple)
    changed = client.post(
        f"/v1/cases/{case_id}/members",
        json={"user_id": member, "role": "investigator"},
        headers=auth(owner, "supervisor"),
    )
    assert changed.status_code == 201, changed.text
    assert old_member_tuple in fake_fga.deleted

    evidence = client.post(
        "/v1/evidence",
        json={"description": "T16b evidence", "case_id": case_id},
        headers=auth(owner, "investigator"),
    )
    assert evidence.status_code == 201, evidence.text
    evidence_id = evidence.json()["evidence_id"]
    fake_fga.add(f"case:{case_id}", "case", f"evidence_item:{evidence_id}")

    first_at = datetime.now(timezone.utc)
    first = client.post(
        f"/v1/evidence/{evidence_id}/custody-events",
        json={
            "to_actor": member,
            "occurred_at": first_at.isoformat(),
            "purpose": "intake",
        },
        headers=auth(owner, "investigator"),
    )
    assert first.status_code == 201, first.text
    old_custodian_tuple = (f"user:{member}", "custodian", f"evidence_item:{evidence_id}")
    fake_fga.add(*old_custodian_tuple)

    second = client.post(
        f"/v1/evidence/{evidence_id}/custody-events",
        json={
            "to_actor": owner,
            "from_actor": member,
            "occurred_at": (first_at + timedelta(minutes=1)).isoformat(),
            "purpose": "return",
        },
        headers=auth(member, "investigator"),
    )
    assert second.status_code == 201, second.text
    assert old_custodian_tuple in fake_fga.deleted


# ── legacy projection surface: public, unchanged shape (T13/T14) ────────────


def test_legacy_graph_is_public_and_shaped(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        graph,
        "_load_graph",
        lambda: {
            "nodes": [{"node_id": "fictional-person", "name": "Fictional Person"}],
            "edges": [],
            "cells": [],
            "meta": {"fixture": True},
        },
    )
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
