"""Grouped search over three backends, and the leak surfaces it must close (T67).

`test_search.py` covers the entity backend, unchanged from T23c. This covers
what T67 added: claims and documents as searchable kinds, groups taken from the
ontology, the identifier rule (ADR-053), the versioned index (ADR-052), as-of,
and the B-17 obligations that are about the *response shape* rather than about
any one row — no totals, no empty groups, no pagination gaps.

The governance cases are the point of the file. M-13's correction is honoured
explicitly: two users get the **same** results when everything matching is
`open`, and a **strict** subset only once a restricted matching row is seeded.
Asserting "strictly fewer" unconditionally would be asserting something false.

Fictional deterministic fixtures throughout. The identifier values are invented
strings, never a real national identifier (`data/real/README.md`).
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
from aegis.er.ledger import active_revision_id
from aegis.search.pipeline import NORMALIZATION_VERSION
from aegis.store import (
    Claim,
    DocumentTextProjection,
    Entity,
    Source,
    SourceRecord,
)
from tests.support.database import configured_test_database, truncate_domain_data

ISSUER = "http://localhost:8180/realms/aegis"
AUDIENCE = "aegis-api"

pytestmark = pytest.mark.requirement(
    "Article-VI", "Article-XIV", "B-17", "M-13", "ADR-050", "ADR-052", "ADR-053", "T67"
)

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

#: Invented, and shaped so nobody can mistake it for a real identifier.
FICTIONAL_NIC = "FICTIONAL-NIC-0001"


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


@pytest.fixture(scope="module")
def search_db(test_database_url: str, alembic_config: Config):
    with configured_test_database(test_database_url, alembic_config):
        yield test_database_url


@pytest.fixture(scope="module")
def engine(search_db: str) -> sa.Engine:
    return sa.create_engine(search_db)


@pytest.fixture(scope="module")
def client(search_db: str) -> TestClient:
    app = create_app()
    app.state.authenticator = OIDCAuthenticator(app.state.settings, jwks_client=_StubJWKS())
    return TestClient(app)


def _claim(session: Session, subject: str, record: str, handling: str, **kwargs) -> str:
    claim_id = new_id("clm")
    session.add(
        Claim(
            claim_id=claim_id,
            subject_id=subject,
            predicate=kwargs.pop("predicate", "has_role"),
            object_value=kwargs.pop("object_value", "person of interest"),
            assertion_type="reported",
            handling_code=handling,
            record_id=record,
            identity_revision_id=active_revision_id(session),
            ontology_version="2.1.0",
            credibility_normalized="possibly_true",
            verification_status="unverified",
            **kwargs,
        )
    )
    return claim_id


def _document(
    session: Session,
    record_id: str,
    text: str,
    handling: str,
    rank: int,
    *,
    version: str | None = None,
) -> str:
    projection_id = new_id("dtp")
    session.add(
        DocumentTextProjection(
            projection_id=projection_id,
            record_id=record_id,
            derivative_id=None,
            content_hash="d" * 64,
            text_body=text,
            handling_code=handling,
            handling_rank=rank,
            normalization_version=version or NORMALIZATION_VERSION,
            builder_version="document-text-v1",
        )
    )
    return projection_id


@pytest.fixture()
def world(engine: sa.Engine):
    """One person, one organisation, claims of three kinds, two documents."""
    truncate_domain_data(engine)
    session = Session(engine)
    ids: dict[str, str] = {"source": new_id("src")}
    with session.begin():
        session.add(Source(source_id=ids["source"], source_type="open_source", name="T67"))
        for key, handling in (("record", "open"), ("record_sensitive", "sensitive")):
            ids[key] = new_id("rec")
            session.add(
                SourceRecord(
                    record_id=ids[key],
                    source_id=ids["source"],
                    ingest_key=new_id("key"),
                    content_hash="c" * 64,
                    storage_uri=f"test://t67/{key}",
                    handling_code=handling,
                )
            )
        session.flush()

        ids["person"] = new_id("ent")
        session.add(
            Entity(entity_id=ids["person"], entity_type="person", label="Fictional ECHO")
        )
        ids["org"] = new_id("ent")
        session.add(
            Entity(
                entity_id=ids["org"], entity_type="organization", label="Fictional Holdings"
            )
        )
        session.flush()

        # An excerpt only the claim backend can find.
        ids["claim_excerpt"] = _claim(
            session,
            ids["person"],
            ids["record"],
            "open",
            excerpt="the harbour meeting was arranged by telephone",
        )
        # An identifier: exact-match only, never trigram (ADR-053).
        ids["claim_nic"] = _claim(
            session,
            ids["person"],
            ids["record"],
            "open",
            predicate="has_nic",
            object_value=FICTIONAL_NIC,
        )
        _claim(session, ids["org"], ids["record"], "open")

        ids["doc_open"] = _document(
            session,
            ids["record"],
            "A fictional report about the harbour meeting and Fictional Holdings.",
            "open",
            0,
        )
        ids["doc_sensitive"] = _document(
            session,
            ids["record_sensitive"],
            "A fictional restricted annex about the harbour meeting.",
            "sensitive",
            2,
        )
    try:
        yield {**ids, "session": session}
    finally:
        session.close()


def _page(client, headers, q: str, **params) -> dict:
    response = client.get("/v1/search", params={"q": q, **params}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _hits(client, headers, q: str, **params) -> list[dict]:
    return [hit for group in _page(client, headers, q, **params)["groups"] for hit in group["hits"]]


def _ids(client, headers, q: str, **params) -> set[str]:
    return {hit["id"] for hit in _hits(client, headers, q, **params)}


# ── groups follow the ontology ──────────────────────────────────────────────


def test_groups_are_ontology_types_plus_claims_and_documents(client, world) -> None:
    groups = {group["group"] for group in _page(client, ANALYST, "Fictional")["groups"]}
    assert {"person", "organization"} <= groups
    assert "claim" in groups or "document" in groups


def test_a_group_label_comes_from_the_ontology(client, world) -> None:
    """Article XIV: nothing in the route names a domain type.

    The label is the one the module declares, so a second domain's types arrive
    with their own names and no code change.
    """
    page = _page(client, ANALYST, "Fictional Holdings")
    org = next(group for group in page["groups"] if group["group"] == "organization")
    assert org["label"] == "Organization"


def test_an_empty_group_is_omitted_not_returned_empty(client, world) -> None:
    """A present group with no hits *is* a count of zero (spec 11 §5.1)."""
    page = _page(client, ANALYST, "Fictional Holdings")
    assert all(group["hits"] for group in page["groups"])


def test_an_unknown_group_is_refused_rather_than_ignored(client, world) -> None:
    """An ignored filter returns everything under a heading that says otherwise."""
    response = client.get(
        "/v1/search", params={"q": "Fictional", "types": ["nonesuch"]}, headers=ANALYST
    )
    assert response.status_code == 422
    assert "nonesuch" in response.text


def test_restricting_to_a_group_returns_only_that_group(client, world) -> None:
    page = _page(client, ANALYST, "Fictional", types=["organization"])
    assert {group["group"] for group in page["groups"]} == {"organization"}


# ── the claim backend ───────────────────────────────────────────────────────


def test_a_claim_is_found_by_its_excerpt(client, world) -> None:
    hits = _hits(client, ANALYST, "harbour meeting was arranged", types=["claim"])
    assert world["claim_excerpt"] in {hit["id"] for hit in hits}
    match = next(hit for hit in hits if hit["id"] == world["claim_excerpt"])
    assert match["matched"] == "excerpt"


def test_a_claim_hit_points_at_the_entity_it_is_about(client, world) -> None:
    """A claim's page is the page of the thing it is about."""
    hits = _hits(client, ANALYST, "harbour meeting was arranged", types=["claim"])
    match = next(hit for hit in hits if hit["id"] == world["claim_excerpt"])
    assert match["parent_id"] == world["person"]
    assert match["detail"] == "has_role"


# ── the identifier rule (ADR-053) ───────────────────────────────────────────


def test_an_exact_identifier_matches(client, world) -> None:
    hits = _hits(client, ANALYST, FICTIONAL_NIC, types=["claim"])
    match = next(hit for hit in hits if hit["id"] == world["claim_nic"])
    assert match["matched"] == "identifier"
    assert match["score"] == 1.0


def test_a_near_miss_identifier_returns_nothing(client, world) -> None:
    """The trade ADR-053 makes, asserted rather than described.

    One character off. A trigram engine would score this ~0.9 and return a
    person; the correct answer is nothing, because a confident wrong person is
    worse than no answer at any recall (Article IX).
    """
    near = FICTIONAL_NIC[:-1] + "2"
    assert world["claim_nic"] not in _ids(client, ANALYST, near, types=["claim"])


def test_the_near_miss_control_is_close_enough_to_matter(client, world) -> None:
    """Non-vacuity: the near miss must be one a fuzzy matcher *would* have hit."""
    near = FICTIONAL_NIC[:-1] + "2"
    with Session(world["session"].get_bind()) as session:
        similarity = session.execute(
            sa.text("SELECT similarity(:a, :b)"), {"a": FICTIONAL_NIC, "b": near}
        ).scalar()
    assert similarity > 0.8, "the control is too far off to prove anything"


# ── the document backend ────────────────────────────────────────────────────


def test_a_document_is_found_by_its_text(client, world) -> None:
    hits = _hits(client, ANALYST, "harbour meeting", types=["document"])
    assert world["doc_open"] in {hit["id"] for hit in hits}
    match = next(hit for hit in hits if hit["id"] == world["doc_open"])
    assert match["matched"] == "text"
    assert match["parent_id"] == world["record"]


def test_a_document_above_clearance_is_absent(client, world) -> None:
    assert world["doc_sensitive"] in _ids(client, ANALYST, "harbour meeting")
    assert world["doc_sensitive"] not in _ids(client, JUNIOR, "harbour meeting")


def test_a_document_at_an_older_pipeline_version_is_excluded(client, world) -> None:
    """ADR-052: a key produced by other rules is not comparable to this query.

    Excluding it is the honest behaviour; `aegis search check-index` is what
    makes the exclusion visible instead of quiet under-retrieval.
    """
    session: Session = world["session"]
    stale = _document(
        session, world["record"], "A fictional note about the harbour meeting.", "open", 0,
        version="search-norm-v0",
    )
    session.commit()
    assert stale not in _ids(client, ANALYST, "harbour meeting", types=["document"])


# ── B-17: the response shape ────────────────────────────────────────────────


def test_the_response_carries_no_total_anywhere(client, world) -> None:
    page = _page(client, ANALYST, "Fictional")
    forbidden = {"total", "count", "approximate_total", "hidden_count"}
    assert not set(page) & forbidden
    for group in page["groups"]:
        assert not set(group) & forbidden


def test_a_narrower_caller_sees_a_subset_and_not_necessarily_fewer(client, world) -> None:
    """M-13, in two assertions that say different things.

    Everything matching "Fictional Holdings" is `open`, so the junior analyst
    sees exactly what the analyst sees. Asserting "strictly fewer" here would
    assert something false about a correct system.
    """
    senior = _ids(client, ANALYST, "Fictional Holdings")
    junior = _ids(client, JUNIOR, "Fictional Holdings")
    assert junior <= senior
    assert junior == senior, "nothing restricted matches this query — the control"


def test_a_seeded_restricted_row_makes_it_a_strict_subset(client, world) -> None:
    """…and here it is strict, because a restricted row does match."""
    senior = _ids(client, ANALYST, "harbour meeting")
    junior = _ids(client, JUNIOR, "harbour meeting")
    assert junior < senior
    assert world["doc_sensitive"] in senior - junior


def test_paging_leaves_no_gap_for_the_narrower_caller(client, world) -> None:
    """A restricted row leaves no hole, because it was never in the sequence.

    Both callers page the whole result set; the narrower caller's sequence must
    be a **subsequence** of the wider one — same relative order, missing only
    the rows they may not see. A gap would mean the row was generated and then
    removed, which is what B-17 says must not happen.
    """

    def walk(headers) -> list[str]:
        seen: list[str] = []
        cursor = None
        for _ in range(10):
            params = {"limit": 2}
            if cursor:
                params["cursor"] = cursor
            page = _page(client, headers, "Fictional", **params)
            seen += [hit["id"] for group in page["groups"] for hit in group["hits"]]
            cursor = page.get("next_cursor")
            if not cursor:
                break
        return seen

    wide, narrow = walk(ANALYST), walk(JUNIOR)
    remaining = iter(wide)
    assert all(item in remaining for item in narrow), (
        f"{narrow} is not a subsequence of {wide}"
    )


def test_a_cursor_carries_no_authority(client, world) -> None:
    """Handing a cursor to a narrower caller widens nothing.

    Cursors remember an ordering key, never a permission: every page rebuilds
    the caller's filters before using it.
    """
    page = _page(client, ANALYST, "harbour meeting", limit=1)
    cursor = page.get("next_cursor")
    assert cursor, "the fixture must produce more than one page for this to mean anything"
    borrowed = _page(client, JUNIOR, "harbour meeting", limit=5, cursor=cursor)
    assert world["doc_sensitive"] not in {
        hit["id"] for group in borrowed["groups"] for hit in group["hits"]
    }


# ── as-of and the stamp ─────────────────────────────────────────────────────


def test_every_response_carries_a_stamp_even_without_a_snapshot(client, world) -> None:
    """Spec 06 §3: otherwise a caller cannot tell a current answer from a past one."""
    stamp = _page(client, ANALYST, "Fictional")["stamp"]
    assert stamp["as_of"] is None
    assert stamp["identity_revision_id"] >= 0
    assert stamp["ontology_version"]


def test_as_of_excludes_a_claim_recorded_later(client, world) -> None:
    before = datetime.now(timezone.utc) - timedelta(days=1)
    found = _ids(
        client, ANALYST, "harbour meeting was arranged", types=["claim"],
        asOf=before.isoformat(),
    )
    assert world["claim_excerpt"] not in found
    assert world["claim_excerpt"] in _ids(
        client, ANALYST, "harbour meeting was arranged", types=["claim"]
    )


def test_a_revision_above_the_head_is_refused_not_clamped(client, world) -> None:
    response = client.get(
        "/v1/search",
        params={"q": "Fictional", "asOfRevision": 999_999},
        headers=ANALYST,
    )
    assert response.status_code == 422
