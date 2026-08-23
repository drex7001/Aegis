"""Opening a restricted record records why (T67; spec 11 §7, Article X).

Purpose is captured **at the open, not at the search**. Requiring a reason to
type a name trains people to supply a meaningless one, and the audit value is in
knowing why a *specific* restricted record was read — which is a discrete act
with a discrete moment, unlike a claim rendered as one row among forty on an
object view.

"Restricted" is an index, not a name: any handling code above the least
restrictive one the ontology declares. A deployment that renames its ladder
keeps the rule (Article XIV), and the test asserts that by reading the ladder
rather than hard-coding `open`.

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

from aegis.actions import new_id
from aegis.api import create_app
from aegis.api.auth import OIDCAuthenticator
from aegis.ontology import load
from aegis.store import AuditLog, Source, SourceRecord
from tests.support.database import configured_test_database, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

ISSUER = "http://localhost:8180/realms/aegis"
AUDIENCE = "aegis-api"

pytestmark = pytest.mark.requirement("Article-X", "Article-XIV", "spec-11-7", "T67")

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _StubKey:
    key = _KEY.public_key()


class _StubJWKS:
    def get_signing_key_from_jwt(self, token: str) -> _StubKey:
        return _StubKey()


def _auth(sub: str, *roles: str, clearance: int = 2) -> dict:
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


ANALYST = _auth("user:analyst", "analyst")


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def purpose_db(test_database_url: str, alembic_config: Config):
    with configured_test_database(test_database_url, alembic_config):
        yield test_database_url


@pytest.fixture(scope="module")
def engine(purpose_db: str) -> sa.Engine:
    return sa.create_engine(purpose_db)


@pytest.fixture(scope="module")
def client(purpose_db: str) -> TestClient:
    app = create_app()
    app.state.authenticator = OIDCAuthenticator(app.state.settings, jwks_client=_StubJWKS())
    return TestClient(app)


@pytest.fixture()
def world(engine: sa.Engine, ontology):
    """One record at the least restrictive code, one above it."""
    truncate_domain_data(engine)
    open_code, restricted_code = ontology.handling_codes[0], ontology.handling_codes[1]
    session = Session(engine)
    ids = {"source": new_id("src"), "open_code": open_code, "restricted_code": restricted_code}
    with session.begin():
        session.add(Source(source_id=ids["source"], source_type="open_source", name="T67"))
        session.flush()
        for key, handling in (("open", open_code), ("restricted", restricted_code)):
            ids[key] = new_id("rec")
            session.add(
                SourceRecord(
                    record_id=ids[key],
                    source_id=ids["source"],
                    ingest_key=new_id("key"),
                    content_hash="c" * 64,
                    storage_uri=f"test://purpose/{key}",
                    handling_code=handling,
                )
            )
    try:
        yield {**ids, "session": session}
    finally:
        session.close()


def _open(client, record_id: str, **params):
    return client.get(f"/v1/source-records/{record_id}", params=params, headers=ANALYST)


def _audit_rows(session, record_id: str) -> list[AuditLog]:
    return list(
        session.scalars(
            sa.select(AuditLog).where(AuditLog.resource_id == record_id)
        )
    )


def test_an_open_record_needs_no_purpose(world, client) -> None:
    """The common case stays frictionless, which is what keeps the rare one meaningful."""
    assert _open(client, world["open"]).status_code == 200


def test_a_restricted_record_without_a_purpose_is_refused(world, client) -> None:
    """422, not 403: the caller is permitted, the request is incomplete.

    A 403 would also say something different about existence than the 404 a
    caller above their clearance already gets.
    """
    response = _open(client, world["restricted"])
    assert response.status_code == 422
    assert "purpose" in response.text


def test_a_blank_purpose_is_not_a_purpose(world, client) -> None:
    assert _open(client, world["restricted"], purpose="   ").status_code == 422


def test_a_restricted_record_with_a_purpose_is_returned_and_audited(world, client) -> None:
    session: Session = world["session"]
    response = _open(client, world["restricted"], purpose="checking the harbour lead")
    assert response.status_code == 200

    session.expire_all()
    rows = _audit_rows(session, world["restricted"])
    assert rows, "opening a restricted record left no audit row"
    row = rows[-1]
    assert row.purpose == "checking the harbour lead"
    assert row.decision == "allow"
    assert row.actor == "user:analyst"
    assert world["restricted_code"] in row.action


def test_opening_an_open_record_writes_no_purpose_row(world, client) -> None:
    """Non-vacuity: the audit row above must be caused by the handling code.

    Without this, a test suite that audited *every* read would pass the case
    above while proving nothing about restricted records specifically.
    """
    session: Session = world["session"]
    _open(client, world["open"])
    session.expire_all()
    assert not [row for row in _audit_rows(session, world["open"]) if row.purpose]


def test_the_rule_reads_the_ladder_rather_than_the_name_open(world, ontology) -> None:
    """Article XIV: a deployment that renames its handling codes keeps the rule.

    The route asks whether the record's code ranks above the *first* one, so
    nothing depends on that code being called `open`.
    """
    assert ontology.handling_rank(ontology.handling_codes[0]) == 0
    assert all(
        ontology.handling_rank(code) > 0 for code in ontology.handling_codes[1:]
    )
