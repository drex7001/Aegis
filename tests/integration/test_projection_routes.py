"""The admin projection rebuild route (T23c, spec 06 §2.6, Articles X + XIII).

Spec 06 gates this on **admin** and caps it at **1 concurrent**, and both halves
are load-bearing for different reasons. The role gate is because a full rebuild
reads every claim in the store, so it is an operator action rather than an
analyst capability. The concurrency cap is not about correctness — the rebuild
is idempotent, so two of them produce the same table — it is because two full
scans contending over the same rows is a denial of service an authenticated
admin can trigger by double-clicking.

Fictional deterministic fixtures throughout.
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
from aegis.api.routes.projections import _REBUILD_LOCK_KEY
from aegis.er.ledger import active_revision_id
from aegis.store import AuditLog, Claim, Entity, Source, SourceRecord
from tests.support.database import configured_test_database, truncate_domain_data

ISSUER = "http://localhost:8180/realms/aegis"
AUDIENCE = "aegis-api"

pytestmark = pytest.mark.requirement(
    "Article-X", "Article-XIII", "spec-06-2.6", "T23c", "T24b"
)

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _StubKey:
    key = _KEY.public_key()


class _StubJWKS:
    def get_signing_key_from_jwt(self, token: str) -> _StubKey:
        return _StubKey()


def auth(sub: str, *roles: str) -> dict:
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
            "clearance": 2,
        },
        _KEY,
        algorithm="RS256",
    )
    return {"Authorization": f"Bearer {encoded}"}


ADMIN = auth("user:admin", "admin")
ANALYST = auth("user:analyst", "analyst")
SUPERVISOR = auth("user:supervisor", "supervisor")


@pytest.fixture(scope="module")
def rebuild_db(test_database_url: str, alembic_config: Config):
    with configured_test_database(test_database_url, alembic_config):
        yield test_database_url


@pytest.fixture(scope="module")
def client(rebuild_db: str) -> TestClient:
    app = create_app()
    app.state.authenticator = OIDCAuthenticator(app.state.settings, jwks_client=_StubJWKS())
    return TestClient(app)


@pytest.fixture(scope="module")
def engine(rebuild_db: str) -> sa.Engine:
    return sa.create_engine(rebuild_db)


@pytest.fixture()
def world(engine: sa.Engine):
    """Two people and one relation claim — enough for the projection to have work."""
    truncate_domain_data(engine)
    session = Session(engine)
    ids = {"source": new_id("src"), "record": new_id("rec")}
    with session.begin():
        session.add(
            Source(source_id=ids["source"], source_type="open_source", name="T23c rebuild")
        )
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="f" * 64,
                storage_uri="test://t23c-rebuild",
            )
        )
        ids["a"] = new_id("ent")
        ids["b"] = new_id("ent")
        session.add(Entity(entity_id=ids["a"], entity_type="person", label="Fictional INDIA"))
        session.add(Entity(entity_id=ids["b"], entity_type="person", label="Fictional JULIET"))
        session.flush()
        session.add(
            Claim(
                claim_id=new_id("clm"),
                subject_id=ids["a"],
                predicate="known_as",
                object_value="Fictional I",
                assertion_type="reported",
                handling_code="open",
                record_id=ids["record"],
                identity_revision_id=active_revision_id(session),
                ontology_version="1.2.0",
                credibility_normalized="possibly_true",
                verification_status="unverified",
            )
        )
    try:
        yield {**ids, "session": session}
    finally:
        session.close()


def test_an_admin_can_rebuild_and_is_told_what_was_built(client, world) -> None:
    response = client.post("/v1/projections/rebuild", headers=ADMIN)
    assert response.status_code == 200, response.text
    body = response.json()
    # "It rebuilt" is not the useful answer: the anchor/map split is a live
    # measure of how reversible the projected graph currently is.
    assert {"anchor_resolved", "map_resolved", "built_at_revision_id"} <= set(body)
    assert body["builder_version"]
    # The stamp is the revision the projection was actually built against, not
    # a timestamp: that is what makes staleness decidable later (Article XIII).
    # Zero is a real value here — an empty ledger has taken no decisions.
    assert body["built_at_revision_id"] == active_revision_id(world["session"])
    # The geometry projection rebuilds in the same pass (T56). `rejected` is
    # reported rather than swallowed: a projection is a cache, so one geometry
    # claim this build could not read must not make the rest unavailable, and
    # the count is the only way anyone would notice it happened.
    assert {"geometry_rows", "geometry_invalid", "geometry_rejected"} <= set(body)
    assert body["geometry_builder_version"]


def test_the_rebuild_is_idempotent(client, world) -> None:
    """Article XIII: the projection is a cache, so running it twice is safe."""
    first = client.post("/v1/projections/rebuild", headers=ADMIN).json()
    second = client.post("/v1/projections/rebuild", headers=ADMIN).json()
    assert first["edges"] == second["edges"]
    assert first["segments"] == second["segments"]


def test_an_analyst_may_not_rebuild(client, world) -> None:
    """A full scan of the claim store is an operator action, not analysis."""
    assert client.post("/v1/projections/rebuild", headers=ANALYST).status_code == 403


def test_a_supervisor_may_not_rebuild(client, world) -> None:
    """Seniority is not the axis: the gate is the admin role, not rank."""
    assert client.post("/v1/projections/rebuild", headers=SUPERVISOR).status_code == 403


def test_rebuild_requires_authentication(client, world) -> None:
    assert client.post("/v1/projections/rebuild").status_code == 401


def test_the_rebuild_is_audited(client, world, engine: sa.Engine) -> None:
    """Article X: an operator action that rewrites a whole table leaves a row."""
    client.post("/v1/projections/rebuild", headers=ADMIN)
    with Session(engine) as session:
        row = session.scalars(
            sa.select(AuditLog)
            .where(AuditLog.action == "projections.rebuild")
            .order_by(AuditLog.id.desc())
            .limit(1)
        ).first()
    assert row is not None
    assert row.actor == "user:admin"
    assert row.decision == "allow"
    # Both projections rebuild in one pass under one lock (T56), so the audit
    # row names both. A row naming only the edge projection would understate
    # what an operator just rewrote.
    assert row.resource_id == "edge_projection,location_geometry_projection"
    # The report is the audit detail, so the record says what the rebuild did
    # and not merely that one happened.
    assert "edges" in row.detail
    assert "geometry" in row.detail
    assert "rows" in row.detail["geometry"]


def test_a_denied_rebuild_is_audited_too(client, world, engine: sa.Engine) -> None:
    client.post("/v1/projections/rebuild", headers=ANALYST)
    with Session(engine) as session:
        row = session.scalars(
            sa.select(AuditLog)
            .where(AuditLog.action == "authz.deny", AuditLog.actor == "user:analyst")
            .order_by(AuditLog.id.desc())
            .limit(1)
        ).first()
    assert row is not None
    assert row.decision == "deny"


def test_a_second_concurrent_rebuild_is_refused(client, world, engine: sa.Engine) -> None:
    """The "1 concurrent" cap in spec 06 §2.6, proven against a real lock.

    Session-level and transaction-level advisory locks share one lock space in
    Postgres, so holding the session form on another connection is exactly what
    a rebuild already in flight looks like to this route.
    """
    holder = engine.connect()
    try:
        holder.execute(
            sa.text("SELECT pg_advisory_lock(hashtext(:key))"), {"key": _REBUILD_LOCK_KEY}
        )
        holder.commit()
        blocked = client.post("/v1/projections/rebuild", headers=ADMIN)
        assert blocked.status_code == 409
    finally:
        holder.execute(
            sa.text("SELECT pg_advisory_unlock(hashtext(:key))"), {"key": _REBUILD_LOCK_KEY}
        )
        holder.commit()
        holder.close()

    # And the lock is released with the transaction, so the route recovers
    # rather than staying wedged until the process restarts.
    assert client.post("/v1/projections/rebuild", headers=ADMIN).status_code == 200
