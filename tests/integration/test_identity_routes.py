"""ER candidates and identity decisions over HTTP (T23b; spec 06 §2.2).

The three suites spec 06 names — ``test_identity_candidates``,
``test_batch_confirm``, ``test_concurrency`` — plus the invariant that sits
under all of them: **a candidate never moves identity by itself**. Every merge
in this file is traceable to one human decision with a note, and the tests that
matter most are the ones proving the machine could not have done it alone.

Fictional deterministic fixtures throughout; this layer needs PostgreSQL only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
import sqlalchemy as sa
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.actions import new_id
from aegis.api import create_app
from aegis.api.auth import OIDCAuthenticator
from aegis.er.ledger import active_entity_for_mention, active_revision_id, open_membership
from aegis.store import (
    AuditLog,
    Entity,
    ErCandidate,
    IdentityDecision,
    IdentityMembership,
    Mention,
    Source,
    SourceRecord,
)
from tests.support.database import configured_test_database, truncate_domain_data

ISSUER = "http://localhost:8180/realms/aegis"
AUDIENCE = "aegis-api"

pytestmark = pytest.mark.requirement(
    "Article-V", "Article-VI", "Article-VII", "ADR-027", "ADR-031", "spec-06-2.2", "T23b"
)

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
LOW_CLEARANCE = auth("user:junior", "analyst", clearance=0)
NO_ROLES = auth("user:outsider")


@pytest.fixture(scope="module")
def identity_db(test_database_url: str, alembic_config: Config):
    with configured_test_database(test_database_url, alembic_config):
        yield test_database_url


@pytest.fixture(scope="module")
def client(identity_db: str) -> TestClient:
    app = create_app()
    app.state.authenticator = OIDCAuthenticator(app.state.settings, jwks_client=_StubJWKS())
    return TestClient(app)


@pytest.fixture(scope="module")
def engine(identity_db: str) -> sa.Engine:
    return sa.create_engine(identity_db)


def _pair(left: str, right: str) -> tuple[str, str]:
    """Canonical pair order — the table's own CHECK requires ``a < b``."""
    return (left, right) if left < right else (right, left)


@pytest.fixture()
def world(engine: sa.Engine):
    """Four people, one mention each, and two candidate pairs over them.

    ``a``/``b`` is pre-verified (an identifier rule matched); ``c``/``d`` is a
    probabilistic Splink pair carrying a real per-feature waterfall. Two bands,
    because the whole point of the batch flow is that only one of them is
    eligible for it.
    """
    truncate_domain_data(engine)
    session = Session(engine)
    ids: dict[str, str] = {"source": new_id("src"), "record": new_id("rec")}
    with session.begin():
        session.add(Source(source_id=ids["source"], source_type="open_source", name="T23b"))
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="b" * 64,
                storage_uri="test://t23b",
            )
        )
        session.flush()
        for name in ("a", "b", "c", "d"):
            entity_id, mention_id = new_id("ent"), new_id("men")
            ids[f"entity_{name}"] = entity_id
            ids[f"mention_{name}"] = mention_id
            session.add(
                Entity(entity_id=entity_id, entity_type="person", label=f"Fictional {name.upper()}")
            )
            session.add(
                Mention(
                    mention_id=mention_id,
                    record_id=ids["record"],
                    raw_text=f"Fictional {name.upper()}",
                    norm_key=f"fictional_{name}",
                )
            )
        session.flush()
        for name in ("a", "b", "c", "d"):
            open_membership(
                session, mention_id=ids[f"mention_{name}"], entity_id=ids[f"entity_{name}"]
            )

        verified_a, verified_b = _pair(ids["mention_a"], ids["mention_b"])
        ids["candidate_verified"] = new_id("cnd")
        session.add(
            ErCandidate(
                candidate_id=ids["candidate_verified"],
                mention_a=verified_a,
                mention_b=verified_b,
                producer="rule:identifier:has_passport_number",
                producer_version="1.0.0",
                score=None,  # rule producers compute no probability
                features={
                    "rule": "identifier_match",
                    "predicate": "has_passport_number",
                    "claim_ids": ["clm_one", "clm_two"],
                },
                pre_verified=True,
            )
        )
        scored_a, scored_b = _pair(ids["mention_c"], ids["mention_d"])
        ids["candidate_scored"] = new_id("cnd")
        session.add(
            ErCandidate(
                candidate_id=ids["candidate_scored"],
                mention_a=scored_a,
                mention_b=scored_b,
                producer="splink",
                producer_version="4.0.0",
                graph_snapshot_id="snap_t23b",
                score=0.94,
                features={
                    "rule": "splink",
                    "gamma_name": 3,
                    "bf_name": 12.5,
                    "tf_name": 0.8,
                    "gamma_dob": 0,
                    "bf_dob": 0.3,
                },
                pre_verified=False,
            )
        )
    try:
        yield {**ids, "session": session}
    finally:
        session.close()


def _parent(session: Session) -> int:
    session.expire_all()
    return active_revision_id(session)


# --------------------------------------------------------------------------
# test_identity_candidates
# --------------------------------------------------------------------------


def _candidates(client, **params) -> list[dict]:
    response = client.get("/v1/identity/candidates", params=params, headers=ANALYST)
    assert response.status_code == 200, response.text
    return response.json()["candidates"]


def test_identity_candidates_report_the_revision_they_were_read_at(client, world) -> None:
    """The parent revision travels with the list, not from a separate lookup.

    A decision's ``parent_revision_id`` is meant to be the state the analyst was
    looking at. Fetching it independently would let a client send a revision
    newer than the screen it decided from — the exact race the check exists for.
    """
    body = client.get("/v1/identity/candidates", headers=ANALYST).json()
    assert body["revision_id"] == active_revision_id(world["session"])


def test_identity_candidates_returns_both_bands_with_their_explanation(client, world) -> None:
    body = _candidates(client)

    assert len(body) == 2
    # Pre-verified first: it is the band an analyst can act on in bulk, so it
    # is the band the screen has to open on.
    assert body[0]["candidate_id"] == world["candidate_verified"]
    assert body[0]["pre_verified"] is True
    assert body[0]["score"] is None, "a rule producer must not invent a probability"
    assert body[0]["features"]["predicate"] == "has_passport_number"

    scored = body[1]
    assert scored["score"] == pytest.approx(0.94)
    assert scored["graph_snapshot_id"] == "snap_t23b"
    # The waterfall survives verbatim — this is what the reviewer reads to
    # decide, and a summarised score would be exactly the thing they cannot
    # check (GOAL.md §10.4).
    assert scored["features"]["bf_name"] == pytest.approx(12.5)
    assert scored["features"]["gamma_dob"] == 0


@pytest.mark.requirement("Article-VI", "T24a")
def test_identifier_candidate_above_field_clearance_is_absent(client, world) -> None:
    session: Session = world["session"]
    with session.begin():
        candidate = session.get(ErCandidate, world["candidate_verified"])
        assert candidate is not None
        candidate.producer = "rule:has_nic"
        candidate.features = {**candidate.features, "predicate": "has_nic"}

    high = _candidates(client)
    low_response = client.get("/v1/identity/candidates", headers=LOW_CLEARANCE)
    assert low_response.status_code == 200
    low = low_response.json()
    assert world["candidate_verified"] in {row["candidate_id"] for row in high}
    assert world["candidate_verified"] not in {
        row["candidate_id"] for row in low["candidates"]
    }
    assert "total" not in low


def test_identity_candidates_carry_each_side_s_current_entity(client, world) -> None:
    verified = _candidates(client)[0]

    sides = {verified["mention_a"]["entity_id"], verified["mention_b"]["entity_id"]}
    assert sides == {world["entity_a"], world["entity_b"]}
    assert verified["mention_a"]["raw_text"].startswith("Fictional")
    assert verified["mention_a"]["entity_label"] is not None


def test_identity_candidates_filter_by_disposition_and_producer(client, world) -> None:
    by_producer = _candidates(client, producer="splink")
    assert [row["candidate_id"] for row in by_producer] == [world["candidate_scored"]]

    assert len(_candidates(client, disposition="open")) == 2
    assert _candidates(client, disposition="confirmed") == []


def test_identity_candidates_require_a_role(client, world) -> None:
    assert client.get("/v1/identity/candidates", headers=NO_ROLES).status_code == 403
    assert client.get("/v1/identity/candidates").status_code == 401


def test_listing_candidates_moves_no_identity(client, world) -> None:
    """Reading the inbox is not deciding (Article VII)."""
    session: Session = world["session"]
    before = _state(session)

    client.get("/v1/identity/candidates", headers=ANALYST)

    session.expire_all()
    assert _state(session) == before
    assert session.scalar(select(sa.func.count()).select_from(IdentityDecision)) == 0


def _state(session: Session) -> set[tuple[str, str]]:
    return {
        row
        for row in session.execute(
            select(IdentityMembership.mention_id, IdentityMembership.entity_id).where(
                IdentityMembership.closed_revision_id.is_(None)
            )
        )
    }


# --------------------------------------------------------------------------
# decisions
# --------------------------------------------------------------------------


def test_a_confirm_merges_and_records_who_decided(client, world) -> None:
    session: Session = world["session"]
    response = client.post(
        "/v1/identity/decisions",
        headers=ANALYST,
        json={
            "mode": "confirm_match",
            "parent_revision_id": _parent(session),
            "note": "same passport number on both records",
            "mention_a": world["mention_a"],
            "mention_b": world["mention_b"],
            "candidate_id": world["candidate_verified"],
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["decision"]["decided_by"] == "user:analyst"
    assert body["decision"]["kind"] == "confirm"
    assert body["moved_mentions"]

    session.expire_all()
    assert active_entity_for_mention(session, world["mention_a"]) == active_entity_for_mention(
        session, world["mention_b"]
    )


def test_a_decision_without_a_note_is_refused(client, world) -> None:
    """A merge nobody explained is a merge nobody can review later."""
    response = client.post(
        "/v1/identity/decisions",
        headers=ANALYST,
        json={
            "mode": "confirm_match",
            "parent_revision_id": _parent(world["session"]),
            "note": "   ",
            "mention_a": world["mention_a"],
            "mention_b": world["mention_b"],
        },
    )
    assert response.status_code == 422
    assert active_entity_for_mention(
        world["session"], world["mention_a"]
    ) != active_entity_for_mention(world["session"], world["mention_b"])


def test_a_reject_without_an_evidence_basis_is_refused_by_the_schema(client, world) -> None:
    """The union types the difference: only reject carries an evidence basis."""
    response = client.post(
        "/v1/identity/decisions",
        headers=ANALYST,
        json={
            "mode": "reject_match",
            "parent_revision_id": _parent(world["session"]),
            "note": "different people",
            "mention_a": world["mention_a"],
            "mention_b": world["mention_b"],
        },
    )
    assert response.status_code == 422


def test_a_reject_writes_a_constraint_and_moves_nothing(client, world) -> None:
    session: Session = world["session"]
    before = _state(session)

    response = client.post(
        "/v1/identity/decisions",
        headers=ANALYST,
        json={
            "mode": "reject_match",
            "parent_revision_id": _parent(session),
            "note": "different dates of birth",
            "evidence_basis": "birth certificates in both records",
            "mention_a": world["mention_a"],
            "mention_b": world["mention_b"],
        },
    )

    assert response.status_code == 201
    assert response.json()["decision"]["kind"] == "reject"
    session.expire_all()
    assert _state(session) == before, "a reject is about the future, not a membership change"


def test_decisions_require_a_role(client, world) -> None:
    response = client.post(
        "/v1/identity/decisions",
        headers=NO_ROLES,
        json={
            "mode": "confirm_match",
            "parent_revision_id": _parent(world["session"]),
            "note": "same person",
            "mention_a": world["mention_a"],
            "mention_b": world["mention_b"],
        },
    )
    assert response.status_code == 403
    assert world["session"].scalar(select(sa.func.count()).select_from(IdentityDecision)) == 0


def test_a_decision_is_audited(client, world) -> None:
    session: Session = world["session"]
    client.post(
        "/v1/identity/decisions",
        headers=ANALYST,
        json={
            "mode": "confirm_match",
            "parent_revision_id": _parent(session),
            "note": "same person",
            "mention_a": world["mention_a"],
            "mention_b": world["mention_b"],
        },
    )

    session.expire_all()
    rows = list(
        session.scalars(select(AuditLog).where(AuditLog.action == "adjudicate_identity"))
    )
    assert len(rows) == 1
    assert rows[0].actor == "user:analyst"
    assert rows[0].detail["mode"] == "confirm_match"


# --------------------------------------------------------------------------
# test_concurrency
# --------------------------------------------------------------------------


def test_concurrency_a_stale_parent_revision_is_a_409_naming_what_intervened(
    client, world
) -> None:
    session: Session = world["session"]
    stale = _parent(session)

    first = client.post(
        "/v1/identity/decisions",
        headers=ANALYST,
        json={
            "mode": "confirm_match",
            "parent_revision_id": stale,
            "note": "same person",
            "mention_a": world["mention_a"],
            "mention_b": world["mention_b"],
        },
    )
    assert first.status_code == 201

    conflict = client.post(
        "/v1/identity/decisions",
        headers=ANALYST,
        json={
            "mode": "confirm_match",
            "parent_revision_id": stale,  # computed before the merge above
            "note": "and this one too",
            "mention_a": world["mention_a"],
            "mention_b": world["mention_c"],
        },
    )

    # 409, not 422: the request was well formed and was correct when it was
    # computed. What changed is the world.
    assert conflict.status_code == 409
    body = conflict.json()
    assert body["parent_revision_id"] == stale
    # Re-presented as data, so the screen can show the analyst what happened
    # rather than asking them to read a sentence and guess.
    assert [row["kind"] for row in body["intervening"]] == ["confirm"]
    assert body["intervening"][0]["decided_by"] == "user:analyst"
    assert body["intervening"][0]["result_revision_id"] > stale


def test_concurrency_a_disjoint_scope_is_not_a_conflict(client, world) -> None:
    """The check is scoped, or analysts learn to retry blindly."""
    session: Session = world["session"]
    parent = _parent(session)

    assert (
        client.post(
            "/v1/identity/decisions",
            headers=ANALYST,
            json={
                "mode": "confirm_match",
                "parent_revision_id": parent,
                "note": "same person",
                "mention_a": world["mention_a"],
                "mention_b": world["mention_b"],
            },
        ).status_code
        == 201
    )
    # Same stale parent, entirely different people — allowed.
    assert (
        client.post(
            "/v1/identity/decisions",
            headers=ANALYST,
            json={
                "mode": "confirm_match",
                "parent_revision_id": parent,
                "note": "also the same person",
                "mention_a": world["mention_c"],
                "mention_b": world["mention_d"],
            },
        ).status_code
        == 201
    )


# --------------------------------------------------------------------------
# test_batch_confirm
# --------------------------------------------------------------------------


def test_batch_confirm_writes_one_decision_per_pair(client, world) -> None:
    session: Session = world["session"]
    response = client.post(
        "/v1/identity/candidates/batch-confirm",
        headers=ANALYST,
        json={
            "candidate_ids": [world["candidate_verified"]],
            "parent_revision_id": _parent(session),
            "note": "identifier matches reviewed in bulk",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["confirmed"]) == 1
    assert body["skipped"] == []

    session.expire_all()
    decisions = list(session.scalars(select(IdentityDecision)))
    assert len(decisions) == 1, "one human action, one ledger decision per pair (ADR-027)"
    assert decisions[0].decided_by == "user:analyst"
    assert decisions[0].candidate_id == world["candidate_verified"]
    assert active_entity_for_mention(session, world["mention_a"]) == active_entity_for_mention(
        session, world["mention_b"]
    )


def test_batch_confirm_refuses_a_candidate_outside_the_pre_verified_band(client, world) -> None:
    session: Session = world["session"]
    before = _state(session)

    response = client.post(
        "/v1/identity/candidates/batch-confirm",
        headers=ANALYST,
        json={
            "candidate_ids": [world["candidate_scored"]],
            "parent_revision_id": _parent(session),
            "note": "trying to bulk-approve a probabilistic pair",
        },
    )

    body = response.json()
    assert body["confirmed"] == []
    assert body["skipped"][0]["candidate_id"] == world["candidate_scored"]
    assert "pre-verified" in body["skipped"][0]["reason"]
    session.expire_all()
    assert _state(session) == before


def test_batch_confirm_reports_the_band_it_took_and_the_one_it_did_not(client, world) -> None:
    """A mixed batch is partial, and says which half was refused."""
    session: Session = world["session"]
    response = client.post(
        "/v1/identity/candidates/batch-confirm",
        headers=ANALYST,
        json={
            "candidate_ids": [
                world["candidate_verified"],
                world["candidate_scored"],
                "cnd_does_not_exist",
            ],
            "parent_revision_id": _parent(session),
            "note": "bulk review of today's candidates",
        },
    )

    body = response.json()
    assert [row["candidate_id"] for row in body["skipped"]] == [
        world["candidate_scored"],
        "cnd_does_not_exist",
    ]
    assert len(body["confirmed"]) == 1
    session.expire_all()
    assert session.scalar(select(sa.func.count()).select_from(IdentityDecision)) == 1


def test_batch_confirm_requires_a_note(client, world) -> None:
    response = client.post(
        "/v1/identity/candidates/batch-confirm",
        headers=ANALYST,
        json={
            "candidate_ids": [world["candidate_verified"]],
            "parent_revision_id": _parent(world["session"]),
            "note": "",
        },
    )
    assert response.status_code == 422


def test_batch_confirm_is_bounded(client, world) -> None:
    """A batch nobody could read before approving is a rubber stamp."""
    response = client.post(
        "/v1/identity/candidates/batch-confirm",
        headers=ANALYST,
        json={
            "candidate_ids": [f"cnd_{index}" for index in range(101)],
            "parent_revision_id": _parent(world["session"]),
            "note": "too many",
        },
    )
    assert response.status_code == 422


def test_batch_confirm_requires_a_role(client, world) -> None:
    response = client.post(
        "/v1/identity/candidates/batch-confirm",
        headers=NO_ROLES,
        json={
            "candidate_ids": [world["candidate_verified"]],
            "parent_revision_id": _parent(world["session"]),
            "note": "not allowed",
        },
    )
    assert response.status_code == 403
    assert world["session"].scalar(select(sa.func.count()).select_from(IdentityDecision)) == 0


def test_batch_confirm_is_idempotent_against_an_already_settled_candidate(client, world) -> None:
    session: Session = world["session"]
    payload = {
        "candidate_ids": [world["candidate_verified"]],
        "parent_revision_id": _parent(session),
        "note": "identifier matches reviewed in bulk",
    }
    assert len(client.post(
        "/v1/identity/candidates/batch-confirm", headers=ANALYST, json=payload
    ).json()["confirmed"]) == 1

    session.expire_all()
    again = client.post(
        "/v1/identity/candidates/batch-confirm",
        headers=ANALYST,
        json={**payload, "parent_revision_id": _parent(session)},
    ).json()

    assert again["confirmed"] == []
    assert "already" in again["skipped"][0]["reason"]
    session.expire_all()
    assert session.scalar(select(sa.func.count()).select_from(IdentityDecision)) == 1
