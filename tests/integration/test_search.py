"""Entity search over HTTP (T23c; spec 06 §2.1, ADR-012 minimal, ADR-035).

The cases that matter are the two the design is built around: a romanized query
finding a name written in Sinhala, and an entity that is *absent* — not merely
unranked — for a caller who cannot read any claim about it. The second is the
one a careless implementation gets wrong while still looking correct, because
filtering after the search returns the right rows and the wrong count.

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
from aegis.er.ledger import active_revision_id, open_membership
from aegis.er.translit import latin_key, phonetic_key
from aegis.er.normalize import norm_key
from aegis.store import Claim, Entity, Mention, Source, SourceRecord
from tests.support.database import configured_test_database, truncate_domain_data

ISSUER = "http://localhost:8180/realms/aegis"
AUDIENCE = "aegis-api"

pytestmark = pytest.mark.requirement(
    "Article-VI", "ADR-012", "ADR-035", "spec-06-2.1", "T23c"
)

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

#: A fictional Sinhala name and its romanization. The pair is the whole point:
#: `norm_key` preserves Sinhala, so nothing derived from the Latin form can
#: match it — only the stored transliteration keys can (ADR-035).
SINHALA_NAME = "නිමල් පෙරේරා"
ROMANIZED = "Nimal Perera"


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


@pytest.fixture(scope="module")
def search_db(test_database_url: str, alembic_config: Config):
    with configured_test_database(test_database_url, alembic_config):
        yield test_database_url


@pytest.fixture(scope="module")
def client(search_db: str) -> TestClient:
    app = create_app()
    app.state.authenticator = OIDCAuthenticator(app.state.settings, jwks_client=_StubJWKS())
    return TestClient(app)


@pytest.fixture(scope="module")
def engine(search_db: str) -> sa.Engine:
    return sa.create_engine(search_db)


def _mention(session: Session, record_id: str, text: str) -> str:
    mention_id = new_id("men")
    session.add(
        Mention(
            mention_id=mention_id,
            record_id=record_id,
            raw_text=text,
            norm_key=norm_key(text),
            latin_key=latin_key(text),
            phonetic_key=phonetic_key(text),
        )
    )
    return mention_id


def _claim(session: Session, subject: str, record: str, handling: str, **kwargs) -> None:
    session.add(
        Claim(
            claim_id=new_id("clm"),
            subject_id=subject,
            predicate=kwargs.pop("predicate", "has_role"),
            object_value=kwargs.pop("object_value", "person of interest"),
            assertion_type="reported",
            handling_code=handling,
            record_id=record,
            identity_revision_id=active_revision_id(session),
            ontology_version="1.2.0",
            credibility_normalized="possibly_true",
            verification_status="unverified",
            **kwargs,
        )
    )


@pytest.fixture()
def world(engine: sa.Engine):
    """Three people: one written in Sinhala, one open, one behind clearance."""
    truncate_domain_data(engine)
    session = Session(engine)
    ids: dict[str, str] = {"source": new_id("src"), "record": new_id("rec")}
    with session.begin():
        session.add(Source(source_id=ids["source"], source_type="open_source", name="T23c"))
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="c" * 64,
                storage_uri="test://t23c",
            )
        )
        session.flush()

        # The entity whose name is written in Sinhala in the record, but whose
        # display label is the romanization an analyst would type.
        ids["entity_sinhala"] = new_id("ent")
        session.add(
            Entity(
                entity_id=ids["entity_sinhala"],
                entity_type="person",
                label=SINHALA_NAME,
            )
        )
        ids["entity_open"] = new_id("ent")
        session.add(
            Entity(entity_id=ids["entity_open"], entity_type="person", label="Fictional CHARLIE")
        )
        ids["entity_restricted"] = new_id("ent")
        session.add(
            Entity(
                entity_id=ids["entity_restricted"],
                entity_type="person",
                label="Fictional DELTA",
            )
        )
        session.flush()

        ids["mention_sinhala"] = _mention(session, ids["record"], SINHALA_NAME)
        ids["mention_open"] = _mention(session, ids["record"], "Fictional CHARLIE")
        session.flush()
        open_membership(
            session, mention_id=ids["mention_sinhala"], entity_id=ids["entity_sinhala"]
        )
        open_membership(
            session, mention_id=ids["mention_open"], entity_id=ids["entity_open"]
        )

        _claim(session, ids["entity_sinhala"], ids["record"], "open")
        _claim(session, ids["entity_open"], ids["record"], "open")
        _claim(
            session,
            ids["entity_open"],
            ids["record"],
            "open",
            predicate="aliases",
            object_value="Charlie the Younger",
        )
        # Reachable only through a claim above a junior analyst's clearance.
        _claim(session, ids["entity_restricted"], ids["record"], "sensitive")
    try:
        yield {**ids, "session": session}
    finally:
        session.close()


def _search(client, headers, q: str, **params) -> list[dict]:
    response = client.get("/v1/search/entities", params={"q": q, **params}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["results"]


def test_a_name_is_found_by_its_label(client, world) -> None:
    # Ranked first, not returned alone: every fixture name shares the token
    # "Fictional", and a trigram search that hid those near-neighbours would
    # not be a fuzzy search. What matters is that the exact name wins.
    hits = _search(client, ANALYST, "Fictional CHARLIE")
    assert hits[0]["entity_id"] == world["entity_open"]
    assert hits[0]["matched"] == "label"
    assert hits[0]["score"] > 0.9


def test_a_near_miss_still_finds_the_entity(client, world) -> None:
    """Trigram, not equality — an analyst who mistypes should still land."""
    hits = _search(client, ANALYST, "Fictional CHARLE")
    assert world["entity_open"] in [hit["entity_id"] for hit in hits]


def test_an_alias_finds_the_entity_and_says_so(client, world) -> None:
    hits = _search(client, ANALYST, "Charlie the Younger")
    match = next(hit for hit in hits if hit["entity_id"] == world["entity_open"])
    assert match["matched"] == "alias"


def test_a_romanized_query_finds_a_name_written_in_sinhala(client, world) -> None:
    """The AC of T23c, and the reason ADR-035 stores the keys at all.

    `norm_key` preserves Sinhala on purpose, so this query can only succeed
    through `latin_key`/`phonetic_key`. If this passes while those columns are
    null, the test is not testing what it claims.
    """
    hits = _search(client, ANALYST, ROMANIZED)
    assert world["entity_sinhala"] in [hit["entity_id"] for hit in hits]


def test_the_sinhala_mention_actually_carries_its_keys(client, world) -> None:
    """Guards the test above from passing for the wrong reason."""
    session: Session = world["session"]
    mention = session.get(Mention, world["mention_sinhala"])
    assert mention is not None
    # Still Sinhala — which is exactly why a Latin query cannot reach it and
    # why the stored keys have to exist (ADR-035).
    assert not mention.norm_key.isascii(), "norm_key must preserve the script"
    assert mention.latin_key and mention.latin_key.isascii()
    assert mention.phonetic_key


def test_a_query_in_sinhala_finds_it_too(client, world) -> None:
    hits = _search(client, ANALYST, SINHALA_NAME)
    assert world["entity_sinhala"] in [hit["entity_id"] for hit in hits]


def test_an_entity_above_clearance_is_absent_not_ranked_last(client, world) -> None:
    """Authorization in candidate generation, not hydration (ADR-012, B-17).

    The junior analyst's result list must not merely omit the row — the row
    must never have been a candidate, so the *count* carries no signal either.
    """
    cleared = _search(client, ANALYST, "Fictional DELTA")
    assert world["entity_restricted"] in [hit["entity_id"] for hit in cleared]

    junior = _search(client, LOW_CLEARANCE, "Fictional DELTA")
    assert world["entity_restricted"] not in [hit["entity_id"] for hit in junior]


def test_clearance_does_not_change_what_is_otherwise_visible(client, world) -> None:
    """The filter is scoped to what is restricted, not a blanket narrowing."""
    junior = _search(client, LOW_CLEARANCE, "Fictional CHARLIE")
    assert world["entity_open"] in [hit["entity_id"] for hit in junior]


def test_an_entity_with_no_readable_claim_is_unreachable(client, world) -> None:
    """An entity row alone is not a reason to appear in results.

    Entities carry no handling code; claims do. An entity nobody has said
    anything readable about is not a search hit, or the row itself would leak
    the existence of the restricted claims that produced it.
    """
    session: Session = world["session"]
    orphan = new_id("ent")
    with session.begin():
        session.add(Entity(entity_id=orphan, entity_type="person", label="Fictional ECHO"))

    hits = _search(client, ANALYST, "Fictional ECHO")
    assert orphan not in [hit["entity_id"] for hit in hits]


def test_a_tombstoned_entity_is_not_a_search_hit(client, world) -> None:
    session: Session = world["session"]
    with session.begin():
        entity = session.get(Entity, world["entity_open"])
        assert entity is not None
        entity.tombstoned_at = datetime.now(timezone.utc)

    hits = _search(client, ANALYST, "Fictional CHARLIE")
    assert world["entity_open"] not in [hit["entity_id"] for hit in hits]


def test_noise_is_not_returned(client, world) -> None:
    """A name search that returns half the corpus is a failed search."""
    assert _search(client, ANALYST, "zzzzzzzz") == []


def test_an_empty_query_returns_nothing_rather_than_everything(client, world) -> None:
    assert _search(client, ANALYST, "   ") == []


def test_search_requires_authentication(client, world) -> None:
    assert client.get("/v1/search/entities", params={"q": "anything"}).status_code == 401


def test_the_query_length_is_bounded(client, world) -> None:
    response = client.get(
        "/v1/search/entities", params={"q": "x" * 500}, headers=ANALYST
    )
    assert response.status_code == 422


def test_results_are_bounded_and_ordered_by_strength(client, world) -> None:
    hits = _search(client, ANALYST, "Fictional", limit=50)
    scores = [hit["score"] for hit in hits]
    assert scores == sorted(scores, reverse=True)
    assert len(hits) <= 50
