"""The "why connected?" API (T21; GOAL.md §18, specs/06 §2.1).

A graph that draws a line between two people without being able to say why is
an accusation with no evidence behind it. These tests hold the answer to the
standard the constitution sets: every claim reachable, all three grading
dimensions separate (Article III), disagreement visible rather than netted
(Article VIII), identity decisions on the record (Article V), and nothing
returned that the caller is not cleared to read (Article VI).
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

from aegis.actions import ActionContext, ActionService, new_id
from aegis.api import create_app
from aegis.api.auth import OIDCAuthenticator
from aegis.er.ledger import active_revision_id, open_membership
from aegis.store import Entity, Mention, Source, SourceRecord
from tests.support.database import configured_test_database, truncate_domain_data

ISSUER = "http://localhost:8180/realms/aegis"
AUDIENCE = "aegis-api"
ANALYST = frozenset({"analyst"})

pytestmark = pytest.mark.requirement(
    "Article-III", "Article-V", "Article-VI", "Article-VIII", "B-14", "T21"
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


@pytest.fixture(scope="module")
def why_db(test_database_url: str, alembic_config: Config):
    with configured_test_database(test_database_url, alembic_config):
        yield test_database_url


@pytest.fixture(scope="module")
def client(why_db: str) -> TestClient:
    app = create_app()
    app.state.authenticator = OIDCAuthenticator(
        app.state.settings, jwks_client=_StubJWKS()
    )
    return TestClient(app)


@pytest.fixture()
def world(why_db: str):
    """Two people connected by two claims from two records, plus a bystander."""
    engine = sa.create_engine(why_db)
    truncate_domain_data(engine)
    session = Session(engine)
    ids = {"source": new_id("src")}
    with session.begin():
        session.add(
            Source(
                source_id=ids["source"],
                source_type="open_source",
                name="T21b source",
                reliability_normalized="generally_reliable",
            )
        )
        for slot in ("one", "two"):
            record_id = new_id("rec")
            ids[f"record_{slot}"] = record_id
            session.add(
                SourceRecord(
                    record_id=record_id,
                    source_id=ids["source"],
                    ingest_key=new_id("key"),
                    content_hash=slot[0] * 64,
                    storage_uri=f"test://t21b/{slot}",
                )
            )
        session.flush()
        for name in ("a", "b", "c"):
            entity_id, mention_id = new_id("ent"), new_id("men")
            ids[f"entity_{name}"] = entity_id
            ids[f"mention_{name}"] = mention_id
            session.add(
                Entity(entity_id=entity_id, entity_type="person", label=f"Person {name}")
            )
            session.add(
                Mention(
                    mention_id=mention_id,
                    record_id=ids["record_one"],
                    raw_text=f"Person {name}",
                    norm_key=f"t21b_person_{name}",
                    char_start=0,
                    char_end=8,
                    script="Latn",
                )
            )
        session.flush()
        for name in ("a", "b", "c"):
            open_membership(
                session,
                mention_id=ids[f"mention_{name}"],
                entity_id=ids[f"entity_{name}"],
            )
    service = ActionService(session)
    context = ActionContext(actor="user:analyst", purpose="T21b", roles=ANALYST)
    try:
        yield {**ids, "session": session, "service": service, "context": context}
    finally:
        session.close()
        engine.dispose()


def _claim(world, *, subject: str, obj: str, record: str = "record_one", **kwargs) -> str:
    claim = world["service"].record_claim(
        world["context"],
        subject_id=world[f"entity_{subject}"],
        predicate="allied_with",
        object_id=world[f"entity_{obj}"],
        assertion_type="assessed",
        record_id=world[record],
        **kwargs,
    )
    return claim.claim_id


def _why(client, world, left="entity_a", right="entity_b", **kw):
    return client.get(
        f"/v1/entities/{world[left]}/why-connected/{world[right]}",
        headers=auth("u1", "analyst", **kw),
    )


# ── the answer itself ────────────────────────────────────────────────────────


def test_every_supporting_claim_reaches_its_source_record(client, world) -> None:
    """Article I: no edge without a source behind it, and the panel proves it."""
    _claim(world, subject="a", obj="b")
    _claim(world, subject="a", obj="b", record="record_two")
    world["session"].commit()

    body = _why(client, world).json()

    assert len(body["claims"]) == 2
    assert body["record_count"] == 2
    for entry in body["claims"]:
        assert entry["record"] is not None
        assert entry["source"]["name"] == "T21b source"
        assert entry["claim"]["excerpt"] is None or isinstance(
            entry["claim"]["excerpt"], str
        )


def test_the_three_grading_dimensions_come_back_separately(client, world) -> None:
    """Article III — and there is deliberately no combined score to read."""
    _claim(world, subject="a", obj="b")
    world["session"].commit()

    entry = _why(client, world).json()["claims"][0]

    assert entry["grading"] == {
        # reliability is graded on the *source*, and is reported as such
        "reliability": "generally_reliable",
        "credibility": "cannot_judge",
        "verification": "unverified",
        "analytic_confidence": None,
    }
    assert "score" not in entry["grading"] and "weight" not in entry["grading"]


def test_contradiction_is_reported_beside_corroboration_not_netted(
    client, world
) -> None:
    """Article VIII: the reader sees the disagreement, not a net verdict."""
    first = _claim(world, subject="a", obj="b")
    second = _claim(world, subject="a", obj="b", record="record_two")
    world["service"].link_claims(
        world["context"], from_claim=first, to_claim=second, relation="contradicts"
    )
    world["session"].commit()

    body = _why(client, world).json()

    # one disagreement between two claims is *one* disagreement
    assert body["contradiction_count"] == 1
    assert body["corroboration_count"] == 0
    by_id = {entry["claim"]["claim_id"]: entry for entry in body["claims"]}
    # and each side knows about the other, whichever way the row was written
    assert by_id[first]["contradicted_by"] == [second]
    assert by_id[second]["contradicted_by"] == [first]


def test_mention_anchors_are_returned_so_the_words_can_be_found(client, world) -> None:
    """ADR-029: the panel can point at the text, not just cite the document."""
    _claim(
        world,
        subject="a",
        obj="b",
        subject_mention_id=world["mention_a"],
        object_mention_id=world["mention_b"],
    )
    world["session"].commit()

    entry = _why(client, world).json()["claims"][0]

    anchors = [entry["subject_mention"], entry["object_mention"]]
    assert all(a is not None for a in anchors)
    assert {a["mention_id"] for a in anchors} == {world["mention_a"], world["mention_b"]}
    assert all(a["char_start"] == 0 and a["script"] == "Latn" for a in anchors)


def test_the_edge_is_undirected(client, world) -> None:
    """Asking B-to-A must answer the same as A-to-B."""
    _claim(world, subject="a", obj="b")
    world["session"].commit()

    forward = _why(client, world, "entity_a", "entity_b").json()
    backward = _why(client, world, "entity_b", "entity_a").json()

    assert [c["claim"]["claim_id"] for c in forward["claims"]] == [
        c["claim"]["claim_id"] for c in backward["claims"]
    ]


def test_unconnected_entities_answer_emptily_rather_than_404(client, world) -> None:
    """"No evidence" is a real answer; 404 would mean "no such entity"."""
    _claim(world, subject="a", obj="b")
    world["session"].commit()

    body = _why(client, world, "entity_a", "entity_c").json()

    assert body["claims"] == [] and body["record_count"] == 0


def test_a_missing_entity_is_404(client, world) -> None:
    response = client.get(
        f"/v1/entities/{world['entity_a']}/why-connected/ent_does_not_exist",
        headers=auth("u1", "analyst"),
    )
    assert response.status_code == 404


# ── identity is part of the provenance ───────────────────────────────────────


def test_a_merge_puts_its_decision_in_the_identity_line(client, world) -> None:
    """Article V: if two nodes are one because a human said so, show who."""
    _claim(world, subject="a", obj="c")
    world["session"].commit()
    world["service"].adjudicate_identity(
        world["context"],
        mode="confirm_match",
        parent_revision_id=active_revision_id(world["session"]),
        note="same person, per the court record",
        mention_a=world["mention_a"],
        mention_b=world["mention_b"],
    )
    world["session"].commit()

    body = _why(client, world, "entity_a", "entity_c").json()

    assert body["identity_line"], "a merged edge must explain its identity"
    decision = body["identity_line"][-1]
    assert decision["kind"] == "confirm"
    assert decision["decided_by"] == "user:analyst"
    assert decision["decision_note"] == "same person, per the court record"


def test_claims_written_against_an_absorbed_id_still_answer(client, world) -> None:
    """The merge case that would otherwise report "no evidence".

    A claim recorded before a merge names the entity that was absorbed. Asking
    about the surviving entity must still find it, or the panel contradicts the
    graph that is actively drawing the edge.
    """
    _claim(world, subject="b", obj="c")  # written against B, before the merge
    world["session"].commit()
    world["service"].adjudicate_identity(
        world["context"],
        mode="confirm_match",
        parent_revision_id=active_revision_id(world["session"]),
        note="same person",
        mention_a=world["mention_a"],
        mention_b=world["mention_b"],
    )
    world["session"].commit()

    body = _why(client, world, "entity_a", "entity_c").json()

    assert len(body["claims"]) == 1, "the absorbed entity's claim must be found"


def test_identity_history_lists_the_decision_line(client, world) -> None:
    world["service"].adjudicate_identity(
        world["context"],
        mode="confirm_match",
        parent_revision_id=active_revision_id(world["session"]),
        note="same person",
        mention_a=world["mention_a"],
        mention_b=world["mention_b"],
    )
    world["session"].commit()

    response = client.get(
        f"/v1/entities/{world['entity_a']}/identity-history",
        headers=auth("u1", "analyst"),
    )

    assert response.status_code == 200
    line = response.json()
    assert line and line[-1]["decision_note"] == "same person"
    assert line[-1]["parent_revision_id"] < line[-1]["result_revision_id"]


# ── generic claim provenance (B-14) ──────────────────────────────────────────


def test_any_claim_resolves_its_own_provenance(client, world) -> None:
    """Property values need provenance too, not just edges."""
    claim_id = _claim(world, subject="a", obj="b")
    world["session"].commit()

    response = client.get(
        f"/v1/claims/{claim_id}/provenance", headers=auth("u1", "analyst")
    )

    assert response.status_code == 200
    body = response.json()
    assert body["claim"]["claim_id"] == claim_id
    assert body["source"]["name"] == "T21b source"
    assert body["grading"]["reliability"] == "generally_reliable"


# ── authorization is applied in the query (Article VI) ───────────────────────


def test_claims_above_a_callers_clearance_never_enter_the_answer(
    client, world
) -> None:
    """Not filtered from the response — filtered from the query.

    The counts are computed over what this caller can see, so the panel cannot
    report evidence it then refuses to show, which would leak its existence.
    """
    _claim(world, subject="a", obj="b")
    _claim(world, subject="a", obj="b", record="record_two", handling_code="sensitive")
    world["session"].commit()

    cleared = _why(client, world).json()
    restricted = client.get(
        f"/v1/entities/{world['entity_a']}/why-connected/{world['entity_b']}",
        headers=auth("u2", "analyst", clearance=0),
    ).json()

    assert len(cleared["claims"]) == 2 and cleared["record_count"] == 2
    assert len(restricted["claims"]) == 1, "the sensitive claim must not appear"
    assert restricted["record_count"] == 1, "counts must reflect the filtered set"


def test_a_claim_above_clearance_is_404_not_403(client, world) -> None:
    """No existence leak: unauthorized and absent look identical (specs/06)."""
    claim_id = _claim(world, subject="a", obj="b", handling_code="sensitive")
    world["session"].commit()

    response = client.get(
        f"/v1/claims/{claim_id}/provenance", headers=auth("u2", "analyst", clearance=0)
    )

    assert response.status_code == 404


def test_the_routes_require_a_token(client, world) -> None:
    for path in (
        f"/v1/entities/{world['entity_a']}/why-connected/{world['entity_b']}",
        f"/v1/claims/{new_id('clm')}/provenance",
        f"/v1/entities/{world['entity_a']}/identity-history",
    ):
        assert client.get(path).status_code == 401, path


def test_retracted_claims_do_not_support_an_edge(client, world) -> None:
    """Retraction is soft in the store and absent from the answer (Article VIII)."""
    claim_id = _claim(world, subject="a", obj="b")
    world["session"].commit()
    world["service"].retract_claim(
        world["context"], claim_id=claim_id, reason="withdrawn by the source"
    )
    world["session"].commit()

    assert _why(client, world).json()["claims"] == []
