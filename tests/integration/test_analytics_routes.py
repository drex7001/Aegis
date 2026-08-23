"""Analytics over HTTP: recording an answer needs a reason (T72, ADR-057).

`/v1/graph/*` answers a question and writes nothing. These routes **record**,
and recording is what demands a purpose, a manifest and an actor — a recorded
answer outlives the question and gets forwarded to people who never saw the
query.

The set-driven path is the one worth testing at this layer rather than below
it: an analytic run over somebody's shared set must evaluate that set **under
the caller's own filters**, so a shared set drives a metric without lending its
owner's clearance.

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
from aegis.er.canonical import rebuild_canonical_map
from aegis.er.ledger import active_revision_id
from aegis.ids import new_id
from aegis.ontology import load
from aegis.projections import rebuild_edge_projection
from aegis.store import AuditLog, Claim, Entity, Source, SourceRecord
from tests.support.database import configured_test_database, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

ISSUER = "http://localhost:8180/realms/aegis"
AUDIENCE = "aegis-api"

pytestmark = pytest.mark.requirement("Article-X", "ADR-057", "spec-06-2.6", "T72")

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _StubKey:
    key = _KEY.public_key()


class _StubJWKS:
    def get_signing_key_from_jwt(self, token: str) -> _StubKey:
        return _StubKey()


class _StubFGA:
    def __init__(self) -> None:
        self.granted: set[tuple[str, str, str]] = set()

    def grant(self, user: str, relation: str, object_: str) -> None:
        self.granted.add((f"user:{user}", relation, object_))

    def check(self, user: str, relation: str, object_: str) -> bool:
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


ANALYST = auth("user:analyst", "analyst")
JUNIOR = auth("user:junior", "analyst", clearance=0)


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def analytics_db(test_database_url: str, alembic_config: Config):
    with configured_test_database(test_database_url, alembic_config):
        yield test_database_url


@pytest.fixture(scope="module")
def engine(analytics_db: str) -> sa.Engine:
    return sa.create_engine(analytics_db)


@pytest.fixture()
def fga() -> _StubFGA:
    return _StubFGA()


@pytest.fixture()
def client(analytics_db: str, fga: _StubFGA) -> TestClient:
    app = create_app()
    app.state.authenticator = OIDCAuthenticator(app.state.settings, jwks_client=_StubJWKS())
    app.state.fga = fga
    return TestClient(app)


@pytest.fixture()
def world(engine: sa.Engine, ontology):
    truncate_domain_data(engine)
    session = Session(engine)
    ids = {"source": new_id("src"), "record": new_id("rec")}
    with session.begin():
        session.add(Source(source_id=ids["source"], source_type="open_source", name="T72"))
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="c" * 64,
                storage_uri="test://t72",
            )
        )
        session.flush()
        for key, label in (("a", "Fictional PAPA"), ("b", "Fictional QUEBEC")):
            ids[key] = new_id("ent")
            session.add(Entity(entity_id=ids[key], entity_type="person", label=label))
        session.flush()
        session.add(
            Claim(
                claim_id=new_id("clm"),
                subject_id=ids["a"],
                predicate="allied_with",
                object_id=ids["b"],
                assertion_type="reported",
                handling_code="sensitive",
                record_id=ids["record"],
                identity_revision_id=active_revision_id(session),
                ontology_version="2.1.0",
                credibility_normalized="possibly_true",
                verification_status="unverified",
            )
        )

    with Session(engine) as builder:
        rebuild_canonical_map(builder)
        rebuild_edge_projection(builder, ontology=ontology)
        builder.commit()

    try:
        yield {**ids, "session": session}
    finally:
        session.close()


# ── recording needs a reason ────────────────────────────────────────────────


def test_running_a_metric_without_a_purpose_is_refused(client, world) -> None:
    """Unlike opening a document, there is no "just looking" version of this."""
    response = client.post("/v1/analytics/degree", json={}, headers=ANALYST)
    assert response.status_code == 422
    assert "purpose" in response.text


def test_running_a_metric_records_the_run_and_its_findings(client, world) -> None:
    response = client.post(
        "/v1/analytics/degree?purpose=mapping the harbour network",
        json={},
        headers=ANALYST,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run"]["method"] == "degree"
    assert body["run"]["purpose"] == "mapping the harbour network"
    assert body["findings"]
    assert all(finding["caveat_text"] for finding in body["findings"])


def test_the_run_is_audited(client, world) -> None:
    session: Session = world["session"]
    body = client.post(
        "/v1/analytics/degree?purpose=checking", json={}, headers=ANALYST
    ).json()
    session.expire_all()
    row = session.scalars(
        sa.select(AuditLog).where(AuditLog.resource_id == body["run"]["run_id"])
    ).one()
    assert row.action == "analytics.degree"
    assert row.purpose == "checking"


def test_an_unknown_metric_is_422(client, world) -> None:
    response = client.post(
        "/v1/analytics/influence?purpose=x", json={}, headers=ANALYST
    )
    assert response.status_code == 422


def test_running_requires_the_analyst_role(client, world) -> None:
    response = client.post(
        "/v1/analytics/degree?purpose=x", json={}, headers=auth("user:auditor", "auditor")
    )
    assert response.status_code == 403


# ── findings are read at the caller's clearance ─────────────────────────────


def test_a_finding_over_restricted_evidence_is_hidden_from_a_narrower_caller(
    client, world
) -> None:
    body = client.post(
        "/v1/analytics/degree?purpose=x", json={}, headers=ANALYST
    ).json()
    assert body["findings"]
    assert all(f["handling_code"] == "sensitive" for f in body["findings"])

    listed = client.get("/v1/findings", headers=JUNIOR).json()
    assert listed["items"] == []

    visible = client.get("/v1/findings", headers=ANALYST).json()
    assert {f["finding_id"] for f in visible["items"]} == {
        f["finding_id"] for f in body["findings"]
    }


def test_the_finding_list_carries_no_total(client, world) -> None:
    client.post("/v1/analytics/degree?purpose=x", json={}, headers=ANALYST)
    listed = client.get("/v1/findings", headers=ANALYST).json()
    assert set(listed) == {"items", "next_cursor"}


def test_one_finding_comes_back_with_its_manifest(client, world) -> None:
    """Together, always.

    A finding without its manifest is a number whose provenance the reader has
    to go and look for — and the going and looking is what does not happen.
    """
    body = client.post(
        "/v1/analytics/degree?purpose=x", json={}, headers=ANALYST
    ).json()
    finding_id = body["findings"][0]["finding_id"]

    one = client.get(f"/v1/findings/{finding_id}", headers=ANALYST).json()
    assert one["run"]["run_id"] == body["run"]["run_id"]
    assert one["run"]["edge_digest"]
    assert one["findings"][0]["finding_id"] == finding_id


def test_a_finding_above_clearance_is_404_not_403(client, world) -> None:
    body = client.post(
        "/v1/analytics/degree?purpose=x", json={}, headers=ANALYST
    ).json()
    finding_id = body["findings"][0]["finding_id"]
    assert client.get(f"/v1/findings/{finding_id}", headers=JUNIOR).status_code == 404


# ── driving a metric from a shared set ──────────────────────────────────────


def test_an_analytic_over_a_set_evaluates_it_as_the_caller(client, world, fga) -> None:
    """A shared set drives a metric without lending its owner's clearance.

    The route asks for `evaluator` — running somebody's question, not reading
    it — and the evaluation digest that lands in the manifest is the caller's,
    so two callers running one set produce two different manifests.
    """
    created = client.post(
        "/v1/object-sets",
        json={"name": "People", "ast": {"kind": "type", "object_type": "person"}},
        headers=ANALYST,
    ).json()
    set_id = created["set_id"]
    fga.grant("user:analyst", "evaluator", f"object_set:{set_id}")

    body = client.post(
        "/v1/analytics/degree?purpose=x",
        json={"object_set_id": set_id},
        headers=ANALYST,
    ).json()
    assert body["run"]["input_kind"] == "object_set"
    assert body["run"]["object_set_id"] == set_id
    assert body["run"]["object_set_version"] == 1
    assert len(body["run"]["evaluation_digest"]) == 64


def test_a_set_you_may_not_evaluate_is_404(client, world, fga) -> None:
    created = client.post(
        "/v1/object-sets",
        json={"name": "People", "ast": {"kind": "type", "object_type": "person"}},
        headers=ANALYST,
    ).json()
    response = client.post(
        "/v1/analytics/degree?purpose=x",
        json={"object_set_id": created["set_id"]},
        headers=auth("user:stranger", "analyst"),
    )
    assert response.status_code == 404
