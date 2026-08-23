"""Object-set routes: absent, not forbidden (T71; spec 06 §2.9, spec 12 §5).

The route-level half of Milestone B. What the service layer already guarantees
is tested in `test_object_sets.py` and `test_set_evaluation.py`; this covers
what only a route can get wrong.

The property that shapes every case here: **an unshared set is absent, never
forbidden.** A 403 discloses that a set exists, which is the same leak a
non-member 403 would be on a case — so every check is 404-on-failure, and the
list route omits rather than marks.

FGA is stubbed. The real model is exercised by the system suite; what matters
here is that the routes *ask*, and ask for the right relation — `evaluator` to
run, `viewer` to read, `editor` to write.

Fictional fixtures throughout.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
import sqlalchemy as sa
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from aegis.api import create_app
from aegis.api.auth import OIDCAuthenticator
from aegis.er.ledger import active_revision_id
from aegis.ids import new_id
from aegis.store import AuditLog, Claim, Entity, Source, SourceRecord
from tests.support.database import configured_test_database, truncate_domain_data

ISSUER = "http://localhost:8180/realms/aegis"
AUDIENCE = "aegis-api"

pytestmark = pytest.mark.requirement("Article-VI", "B-17", "spec-06-2.9", "T71")

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _StubKey:
    key = _KEY.public_key()


class _StubJWKS:
    def get_signing_key_from_jwt(self, token: str) -> _StubKey:
        return _StubKey()


class _StubFGA:
    """Grants the routes ask about, as a dictionary.

    Deliberately answers `False` for anything not granted, so "the route did
    not ask" and "the route asked and was refused" produce different outcomes
    — which is what lets the tests below distinguish a missing check from a
    passing one.
    """

    def __init__(self) -> None:
        self.granted: set[tuple[str, str, str]] = set()
        self.asked: list[tuple[str, str, str]] = []

    def grant(self, user: str, relation: str, object_: str) -> None:
        self.granted.add((f"user:{user}", relation, object_))

    def check(self, user: str, relation: str, object_: str) -> bool:
        self.asked.append((user, relation, object_))
        return (user, relation, object_) in self.granted


def auth(sub: str, *roles: str, clearance: int = 2) -> dict:
    now = datetime.now(timezone.utc)
    encoded = jwt.encode(
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
    return {"Authorization": f"Bearer {encoded}"}


OWNER = auth("user:owner", "analyst")
COLLEAGUE = auth("user:colleague", "analyst")
STRANGER = auth("user:stranger", "analyst")


@pytest.fixture(scope="module")
def sets_db(test_database_url: str, alembic_config: Config):
    with configured_test_database(test_database_url, alembic_config):
        yield test_database_url


@pytest.fixture(scope="module")
def engine(sets_db: str) -> sa.Engine:
    return sa.create_engine(sets_db)


@pytest.fixture()
def fga() -> _StubFGA:
    return _StubFGA()


@pytest.fixture()
def client(sets_db: str, fga: _StubFGA) -> TestClient:
    app = create_app()
    app.state.authenticator = OIDCAuthenticator(app.state.settings, jwks_client=_StubJWKS())
    app.state.fga = fga
    return TestClient(app)


@pytest.fixture()
def world(engine: sa.Engine):
    truncate_domain_data(engine)
    session = Session(engine)
    ids = {"source": new_id("src"), "record": new_id("rec")}
    with session.begin():
        session.add(Source(source_id=ids["source"], source_type="open_source", name="T71"))
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="c" * 64,
                storage_uri="test://t71",
            )
        )
        session.flush()
        for key, entity_type, label in (
            ("person", "person", "Fictional LIMA"),
            ("org", "organization", "Fictional Holdings"),
        ):
            ids[key] = new_id("ent")
            session.add(Entity(entity_id=ids[key], entity_type=entity_type, label=label))
            session.flush()
            session.add(
                Claim(
                    claim_id=new_id("clm"),
                    subject_id=ids[key],
                    predicate="has_role",
                    object_value="fixture subject",
                    assertion_type="reported",
                    handling_code="open",
                    record_id=ids["record"],
                    identity_revision_id=active_revision_id(session),
                    ontology_version="2.1.0",
                    credibility_normalized="possibly_true",
                    verification_status="unverified",
                )
            )
    try:
        yield {**ids, "session": session}
    finally:
        session.close()


PEOPLE = {"kind": "type", "object_type": "person"}


def _create(client, headers=OWNER, **overrides) -> dict:
    body = {"name": "People", "ast": PEOPLE, **overrides}
    response = client.post("/v1/object-sets", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# ── creating ────────────────────────────────────────────────────────────────


def test_a_set_is_created_with_its_first_version(client, world, fga) -> None:
    created = _create(client)
    assert created["latest"]["version"] == 1
    assert created["latest"]["ontology_version"]
    assert created["latest"]["track_interface_members"] is False


def test_creating_a_set_is_audited(client, world, fga) -> None:
    session: Session = world["session"]
    created = _create(client)
    session.expire_all()
    rows = list(
        session.scalars(
            sa.select(AuditLog).where(AuditLog.resource_id == created["set_id"])
        )
    )
    assert [row.action for row in rows] == ["object_set.create"]


def test_an_invalid_definition_is_422_with_its_path(client, world, fga) -> None:
    response = client.post(
        "/v1/object-sets",
        json={"name": "Bad", "ast": {"kind": "type", "object_type": "wizard"}},
        headers=OWNER,
    )
    assert response.status_code == 422
    assert "object_type" in response.text


def test_creating_requires_a_writing_role(client, world, fga) -> None:
    response = client.post(
        "/v1/object-sets",
        json={"name": "People", "ast": PEOPLE},
        headers=auth("user:auditor", "auditor"),
    )
    assert response.status_code == 403


# ── absent, not forbidden ───────────────────────────────────────────────────


def test_a_set_you_cannot_see_is_404_not_403(client, world, fga) -> None:
    """A 403 would disclose that the set exists."""
    created = _create(client)
    fga.grant("user:owner", "viewer", f"object_set:{created['set_id']}")

    assert client.get(f"/v1/object-sets/{created['set_id']}", headers=OWNER).status_code == 200
    assert (
        client.get(f"/v1/object-sets/{created['set_id']}", headers=STRANGER).status_code == 404
    )


def test_a_missing_set_and_an_unshared_one_look_identical(client, world, fga) -> None:
    created = _create(client)
    missing = client.get("/v1/object-sets/oset_nonexistent", headers=STRANGER)
    unshared = client.get(f"/v1/object-sets/{created['set_id']}", headers=STRANGER)
    assert missing.status_code == unshared.status_code == 404
    assert missing.json()["detail"] == unshared.json()["detail"]


def test_the_list_omits_rather_than_marks(client, world, fga) -> None:
    """A list with holes in it answers the question it was refusing to answer."""
    mine = _create(client, name="Mine")
    theirs = _create(client, name="Theirs")
    fga.grant("user:colleague", "viewer", f"object_set:{mine['set_id']}")

    listed = client.get("/v1/object-sets", headers=COLLEAGUE).json()
    assert [row["set_id"] for row in listed["items"]] == [mine["set_id"]]
    assert theirs["set_id"] not in listed


def test_the_list_carries_no_total(client, world, fga) -> None:
    _create(client)
    listed = client.get("/v1/object-sets", headers=OWNER).json()
    assert set(listed) == {"items", "next_cursor"}


# ── the two grants ──────────────────────────────────────────────────────────


def test_evaluating_asks_for_evaluator_not_viewer(client, world, fga) -> None:
    """Running a saved query is the weaker disclosure (spec 12 §5.2).

    A colleague granted only `evaluator` gets the answer and not the question,
    which is the whole reason the relation exists.
    """
    created = _create(client)
    fga.grant("user:colleague", "evaluator", f"object_set:{created['set_id']}")

    evaluated = client.post(
        f"/v1/object-sets/{created['set_id']}/evaluate", headers=COLLEAGUE
    )
    assert evaluated.status_code == 200
    assert {member["entity_id"] for member in evaluated.json()["members"]} == {
        world["person"]
    }

    # …and still cannot read the definition.
    assert (
        client.get(f"/v1/object-sets/{created['set_id']}", headers=COLLEAGUE).status_code
        == 404
    )


def test_reading_the_definition_asks_for_viewer(client, world, fga) -> None:
    created = _create(client)
    fga.grant("user:colleague", "viewer", f"object_set:{created['set_id']}")
    assert (
        client.get(f"/v1/object-sets/{created['set_id']}", headers=COLLEAGUE).status_code
        == 200
    )


def test_adding_a_version_asks_for_editor(client, world, fga) -> None:
    created = _create(client)
    fga.grant("user:colleague", "viewer", f"object_set:{created['set_id']}")
    refused = client.post(
        f"/v1/object-sets/{created['set_id']}/versions",
        json={"ast": {"kind": "type", "object_type": "organization"}},
        headers=COLLEAGUE,
    )
    assert refused.status_code == 404

    fga.grant("user:colleague", "editor", f"object_set:{created['set_id']}")
    allowed = client.post(
        f"/v1/object-sets/{created['set_id']}/versions",
        json={"ast": {"kind": "type", "object_type": "organization"}, "note": "widened"},
        headers=COLLEAGUE,
    )
    assert allowed.status_code == 200
    assert allowed.json()["version"] == 2


def test_the_routes_actually_ask(client, world, fga) -> None:
    """Non-vacuity: a route that never checked would pass every test above.

    `_StubFGA` answers False for anything ungranted, so the 200s prove a check
    happened *and* succeeded — but only this assertion proves the relation
    asked for was the intended one.
    """
    created = _create(client)
    fga.grant("user:owner", "evaluator", f"object_set:{created['set_id']}")
    client.post(f"/v1/object-sets/{created['set_id']}/evaluate", headers=OWNER)
    assert ("user:user:owner", "evaluator", f"object_set:{created['set_id']}") in fga.asked


# ── evaluation ──────────────────────────────────────────────────────────────


def test_an_evaluation_carries_a_digest_and_no_total(client, world, fga) -> None:
    created = _create(client)
    fga.grant("user:owner", "evaluator", f"object_set:{created['set_id']}")
    body = client.post(
        f"/v1/object-sets/{created['set_id']}/evaluate", headers=OWNER
    ).json()
    assert set(body) == {"set_id", "version", "members", "truncated", "evaluation_digest"}
    assert len(body["evaluation_digest"]) == 64


def test_an_older_version_can_be_evaluated(client, world, fga) -> None:
    """A finding names `(set_id, version)`, so that version has to stay runnable."""
    created = _create(client)
    fga.grant("user:owner", "editor", f"object_set:{created['set_id']}")
    fga.grant("user:owner", "evaluator", f"object_set:{created['set_id']}")
    client.post(
        f"/v1/object-sets/{created['set_id']}/versions",
        json={"ast": {"kind": "type", "object_type": "organization"}},
        headers=OWNER,
    )

    first = client.post(
        f"/v1/object-sets/{created['set_id']}/evaluate?version=1", headers=OWNER
    ).json()
    second = client.post(
        f"/v1/object-sets/{created['set_id']}/evaluate", headers=OWNER
    ).json()
    assert {m["entity_id"] for m in first["members"]} == {world["person"]}
    assert {m["entity_id"] for m in second["members"]} == {world["org"]}


# ── sharing ─────────────────────────────────────────────────────────────────


def test_sharing_is_audited_with_the_grant_it_made(client, world, fga) -> None:
    """An audit row saying "shared" without naming the grant answers nothing."""
    session: Session = world["session"]
    created = _create(client)
    fga.grant("user:owner", "editor", f"object_set:{created['set_id']}")

    response = client.post(
        f"/v1/object-sets/{created['set_id']}/share",
        json={"user_sub": "user:colleague", "relation": "evaluator"},
        headers=OWNER,
    )
    assert response.status_code == 200

    session.expire_all()
    row = list(
        session.scalars(
            sa.select(AuditLog)
            .where(AuditLog.resource_id == created["set_id"])
            .order_by(AuditLog.id)
        )
    )[-1]
    assert row.action == "object_set.share"
    assert row.detail["grant"]["relation"] == "evaluator"
    assert row.detail["grant"]["user"] == "user:user:colleague"


def test_an_unknown_relation_is_refused(client, world, fga) -> None:
    created = _create(client)
    fga.grant("user:owner", "editor", f"object_set:{created['set_id']}")
    response = client.post(
        f"/v1/object-sets/{created['set_id']}/share",
        json={"user_sub": "user:colleague", "relation": "owner"},
        headers=OWNER,
    )
    assert response.status_code == 422


def test_sharing_requires_editor(client, world, fga) -> None:
    created = _create(client)
    fga.grant("user:colleague", "viewer", f"object_set:{created['set_id']}")
    response = client.post(
        f"/v1/object-sets/{created['set_id']}/share",
        json={"user_sub": "user:stranger"},
        headers=COLLEAGUE,
    )
    assert response.status_code == 404
