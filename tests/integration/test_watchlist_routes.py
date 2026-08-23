"""Watchlists over HTTP (T75, spec 06 §2.9, ADR-056, ADR-060).

The property this layer has to prove that the service layer cannot: **no route
sweeps.** Creating a watchlist does not evaluate it and reading one does not
either, so a detection can only come from `aegis watchlists evaluate`. That is
ADR-056's whole point, and a route that quietly swept would make the sweep
command decorative while leaving the latency guarantee untrue.

The second is that an alert is read at the caller's clearance on its **own**
handling rank — the reason alerts are not review-queue rows, which are filtered
on the source record's handling code instead (ADR-060).

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
from aegis.api.auth import OIDCAuthenticator, UserContext
from aegis.er.ledger import active_revision_id
from aegis.ids import new_id
from aegis.ontology import load
from aegis.sets.service import create_set
from aegis.store import AuditLog, Claim, Entity, Source, SourceRecord, WatchlistAlert
from aegis.watchlists.service import create_watchlist, evaluate_watchlist
from tests.support.database import configured_test_database, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

ISSUER = "http://localhost:8180/realms/aegis"
AUDIENCE = "aegis-api"

pytestmark = pytest.mark.requirement(
    "Article-VI", "Article-X", "H-24", "ADR-056", "ADR-060", "spec-06-2.9", "T75"
)

WATCHED = "+94-70-000-0000"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _StubKey:
    key = _KEY.public_key()


class _StubJWKS:
    def get_signing_key_from_jwt(self, token: str) -> _StubKey:
        return _StubKey()


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


def _context(sub: str = "user:analyst", clearance: int = 2) -> UserContext:
    return UserContext(
        sub=sub,
        username=sub,
        roles=frozenset({"analyst"}),
        clearance=clearance,
        claims={},
    )


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def watchlist_db(test_database_url: str, alembic_config: Config):
    with configured_test_database(test_database_url, alembic_config):
        yield test_database_url


@pytest.fixture(scope="module")
def engine(watchlist_db: str) -> sa.Engine:
    return sa.create_engine(watchlist_db)


@pytest.fixture()
def client(watchlist_db: str) -> TestClient:
    app = create_app()
    app.state.authenticator = OIDCAuthenticator(
        app.state.settings, jwks_client=_StubJWKS()
    )
    app.state.fga = None
    return TestClient(app)


@pytest.fixture()
def world(engine: sa.Engine, ontology):
    truncate_domain_data(engine)
    session = Session(engine)
    ids: dict = {"source": new_id("src"), "record": new_id("rec")}
    with session.begin():
        session.add(
            Source(source_id=ids["source"], source_type="open_source", name="T75")
        )
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="f" * 64,
                storage_uri="test://t75-routes",
            )
        )
        session.flush()
        for key, label in (
            ("watched", "Fictional YANKEE"), ("other", "Fictional ZULU")
        ):
            ids[key] = new_id("ent")
            session.add(Entity(entity_id=ids[key], entity_type="person", label=label))
        session.flush()
        session.add(
            Claim(
                claim_id=new_id("clm"),
                subject_id=ids["watched"],
                predicate="reachable_on",
                object_value=WATCHED,
                assertion_type="reported",
                handling_code="sensitive",
                record_id=ids["record"],
                identity_revision_id=active_revision_id(session),
                ontology_version=ontology.version,
                credibility_normalized="possibly_true",
                verification_status="unverified",
            )
        )
        session.add(
            Claim(
                claim_id=new_id("clm"),
                subject_id=ids["watched"],
                predicate="allied_with",
                object_id=ids["other"],
                assertion_type="reported",
                handling_code="open",
                record_id=ids["record"],
                identity_revision_id=active_revision_id(session),
                ontology_version=ontology.version,
                credibility_normalized="possibly_true",
                verification_status="unverified",
            )
        )
        session.flush()
        obj, _ = create_set(
            session,
            name="Allies of ZULU",
            ast={
                "kind": "predicate",
                "predicate": "allied_with",
                "target": ids["other"],
            },
            actor="user:analyst",
            ontology=ontology,
        )
        ids["set_id"] = obj.set_id

    try:
        yield {**ids, "session": session}
    finally:
        session.close()


def _swept_alert(world, ontology):
    """A real alert, produced the only way one can be: by a sweep."""
    session: Session = world["session"]
    session.rollback()
    with session.begin():
        watchlist = create_watchlist(
            session,
            name="Harbour numbers",
            set_id=world["set_id"],
            rule="exact_identifier",
            user=_context(),
        )
        _, alerts = evaluate_watchlist(session, watchlist, ontology=ontology)
    return watchlist, alerts


# ── no route sweeps ─────────────────────────────────────────────────────────


def test_creating_a_watchlist_does_not_evaluate_it(client, world) -> None:
    """ADR-056's whole point, asserted rather than assumed.

    A route that quietly swept would make `aegis watchlists evaluate`
    decorative and the stated latency guarantee untrue.
    """
    response = client.post(
        "/v1/watchlists",
        json={"name": "Harbour numbers", "set_id": world["set_id"]},
        headers=ANALYST,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rule"] == "exact_identifier"
    assert body["set_version"] == 1
    # The tell: never swept, so there is no watermark.
    assert body["evaluated_through"] is None

    assert client.get("/v1/alerts", headers=ANALYST).json()["items"] == []


def test_an_unswept_watchlist_reads_as_a_gap_not_a_quiet_zero(client, world) -> None:
    created = client.post(
        "/v1/watchlists",
        json={"name": "Harbour numbers", "set_id": world["set_id"]},
        headers=ANALYST,
    ).json()
    listed = client.get("/v1/watchlists", headers=ANALYST).json()
    row = next(w for w in listed["items"] if w["watchlist_id"] == created["watchlist_id"])
    assert row["evaluated_through"] is None


def test_the_watermark_appears_once_a_sweep_has_run(client, world, ontology) -> None:
    watchlist, _ = _swept_alert(world, ontology)
    listed = client.get("/v1/watchlists", headers=ANALYST).json()
    row = next(
        w for w in listed["items"] if w["watchlist_id"] == watchlist.watchlist_id
    )
    assert row["evaluated_through"] is not None


def test_creating_a_watchlist_over_a_set_that_does_not_exist_is_422(
    client, world
) -> None:
    response = client.post(
        "/v1/watchlists",
        json={"name": "Nothing", "set_id": "oset_nothing"},
        headers=ANALYST,
    )
    assert response.status_code == 422


def test_creating_a_watchlist_is_audited(client, world) -> None:
    session: Session = world["session"]
    created = client.post(
        "/v1/watchlists",
        json={"name": "Harbour numbers", "set_id": world["set_id"]},
        headers=ANALYST,
    ).json()
    session.expire_all()
    row = session.scalars(
        sa.select(AuditLog).where(AuditLog.resource_id == created["watchlist_id"])
    ).one()
    assert row.action == "watchlist.create"
    assert row.detail["set_version"] == 1


def test_creating_requires_the_analyst_role(client, world) -> None:
    response = client.post(
        "/v1/watchlists",
        json={"name": "Harbour numbers", "set_id": world["set_id"]},
        headers=auth("user:auditor", "auditor"),
    )
    assert response.status_code == 403


# ── alerts are read at the caller's clearance ───────────────────────────────


def test_an_alert_over_restricted_evidence_is_absent_for_a_narrower_caller(
    client, world, ontology
) -> None:
    """The alert's whole content is "this exact value appeared on this entity",
    which is the content of the `sensitive` claim it came from."""
    _, alerts = _swept_alert(world, ontology)
    assert alerts and all(a.handling_code == "sensitive" for a in alerts)

    assert client.get("/v1/alerts", headers=JUNIOR).json()["items"] == []
    visible = client.get("/v1/alerts", headers=ANALYST).json()
    assert {a["alert_id"] for a in visible["items"]} == {a.alert_id for a in alerts}


def test_an_alert_carries_everything_h24_asks_for(client, world, ontology) -> None:
    _swept_alert(world, ontology)
    alert = client.get("/v1/alerts", headers=ANALYST).json()["items"][0]
    assert alert["rule"] == "exact_identifier"
    assert alert["rule_version"]
    assert alert["matched_value"] == WATCHED
    assert alert["entity_id"] == world["watched"]
    assert alert["claim_ids"]
    assert alert["dedupe_key"]
    assert alert["exactness"] == "exact"
    assert alert["authority_ref"] is None
    assert alert["status"] == "new"


def test_alerts_filter_by_watchlist_and_status(client, world, ontology) -> None:
    watchlist, _ = _swept_alert(world, ontology)
    assert client.get(
        f"/v1/alerts?watchlist={watchlist.watchlist_id}&status=new", headers=ANALYST
    ).json()["items"]
    assert (
        client.get(
            f"/v1/alerts?watchlist={watchlist.watchlist_id}&status=closed",
            headers=ANALYST,
        ).json()["items"]
        == []
    )


def test_the_alert_list_carries_no_total(client, world, ontology) -> None:
    _swept_alert(world, ontology)
    listed = client.get("/v1/alerts", headers=ANALYST).json()
    assert set(listed) == {"items", "next_cursor"}


# ── triage ──────────────────────────────────────────────────────────────────


def test_closing_without_a_reason_is_422(client, world, ontology) -> None:
    _, alerts = _swept_alert(world, ontology)
    response = client.post(
        f"/v1/alerts/{alerts[0].alert_id}/triage",
        json={"status": "closed"},
        headers=ANALYST,
    )
    assert response.status_code == 422
    assert "reason" in response.text


def test_closing_with_a_reason_is_recorded_and_audited(
    client, world, ontology
) -> None:
    session: Session = world["session"]
    _, alerts = _swept_alert(world, ontology)
    alert_id = alerts[0].alert_id

    moved = client.post(
        f"/v1/alerts/{alert_id}/triage",
        json={"status": "reviewing"},
        headers=ANALYST,
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "reviewing"

    closed = client.post(
        f"/v1/alerts/{alert_id}/triage",
        json={"status": "closed", "reason": "the number was reassigned in 2019"},
        headers=ANALYST,
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["closed_reason"]

    session.expire_all()
    rows = list(
        session.scalars(
            sa.select(AuditLog)
            .where(AuditLog.resource_id == alert_id)
            .order_by(AuditLog.id)
        )
    )
    assert [(r.detail["from"], r.detail["to"]) for r in rows] == [
        ("new", "reviewing"),
        ("reviewing", "closed"),
    ]


def test_an_unknown_status_is_422(client, world, ontology) -> None:
    _, alerts = _swept_alert(world, ontology)
    response = client.post(
        f"/v1/alerts/{alerts[0].alert_id}/triage",
        json={"status": "dismissed"},
        headers=ANALYST,
    )
    assert response.status_code == 422


def test_triaging_an_alert_above_clearance_is_404_not_403(
    client, world, ontology
) -> None:
    """Learning that an alert exists is most of what an alert says."""
    _, alerts = _swept_alert(world, ontology)
    response = client.post(
        f"/v1/alerts/{alerts[0].alert_id}/triage",
        json={"status": "reviewing"},
        headers=JUNIOR,
    )
    assert response.status_code == 404


def test_triaging_an_alert_that_does_not_exist_is_404(client, world) -> None:
    response = client.post(
        "/v1/alerts/alrt_nothing/triage",
        json={"status": "reviewing"},
        headers=ANALYST,
    )
    assert response.status_code == 404


def test_the_alert_is_not_a_review_queue_row(client, world, ontology) -> None:
    """ADR-060, asserted at the boundary.

    If a detection were queued as a suggestion, it would show up here — and it
    would be filtered on the *source record's* handling code rather than on the
    claims that fired it, which is the leak the separation prevents.
    """
    _swept_alert(world, ontology)
    queue = client.get("/v1/review-queue", headers=ANALYST).json()
    assert all(
        item["suggestion_kind"] != "watchlist_hit" for item in queue["items"]
    )
    session: Session = world["session"]
    session.expire_all()
    assert session.scalar(
        sa.select(sa.func.count()).select_from(WatchlistAlert)
    ) > 0
