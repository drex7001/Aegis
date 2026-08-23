"""One set, two analysts, two honest answers (T76 — charter exit №4).

The criterion, verbatim: *an object set is created, shared case-scoped, and
drives both an analytic run and a watchlist; a second user with narrower
clearance sees a correctly narrower evaluation of the **same** set.*

It is one test because it is one claim, and the claim is the phase's whole
argument: **a set stores a question, never an answer.** If sets stored results,
sharing one would hand over its owner's clearance — and every governance
property this phase built would be a convention rather than a mechanism.

## What "correctly narrower" has to mean

M-13 warns that "strictly fewer" gets misused, and it would be easy to satisfy
this criterion vacuously. `narrow ⊆ wide` passes when `narrow` is empty. It also
passes when `narrow == wide`, if the assertion is only `⊆`. So this asserts all
three parts:

1. `narrow ⊂ wide` — a **proper** subset, so something really was withheld;
2. `narrow` is **non-empty**, so the narrower analyst still has a working view
   and the test is not measuring a broken one; and
3. the entity withheld is exactly the one whose only claim is `sensitive` —
   named, so the test fails if the *wrong* thing goes missing.

## The digest is the tell

Two analysts evaluating one set produce two different `evaluation_digest`
values, and the analytic run records the caller's. That is what makes "the
filters are applied during evaluation" checkable rather than asserted: if the
set stored members, both runs would carry the same digest and the difference
would have to appear somewhere downstream, where nobody looks.

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
from aegis.store import (
    AnalyticRun,
    CaseFile,
    CaseMember,
    Claim,
    Entity,
    Source,
    SourceRecord,
    Watchlist,
)
from aegis.watchlists.service import create_watchlist, evaluate_watchlist
from tests.support.database import configured_test_database, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

ISSUER = "http://localhost:8180/realms/aegis"
AUDIENCE = "aegis-api"

pytestmark = pytest.mark.requirement(
    "Article-VI", "Article-XIII", "B-17", "M-13", "phase-06-exit-4", "T76"
)

#: The watched number, held by the person only the cleared analyst can see.
WATCHED = "+94-70-000-0000"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _StubKey:
    key = _KEY.public_key()


class _StubJWKS:
    def get_signing_key_from_jwt(self, token: str) -> _StubKey:
        return _StubKey()


class _StubFGA:
    """Grants, as the share route writes them and the read routes check them."""

    def __init__(self) -> None:
        self.granted: set[tuple[str, str, str]] = set()

    def grant(self, user: str, relation: str, object_: str) -> None:
        self.granted.add((f"user:{user}", relation, object_))

    def write(self, user: str, relation: str, object_: str) -> None:
        self.granted.add((user, relation, object_))

    def delete(self, user: str, relation: str, object_: str) -> None:
        self.granted.discard((user, relation, object_))

    def check(self, user: str, relation: str, object_: str) -> bool:
        return (user, relation, object_) in self.granted


def token(sub: str, *roles: str, clearance: int = 2) -> dict:
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


#: Two analysts on one case. The only difference between them is clearance,
#: which is the point: everything else is held equal so the narrower answer
#: cannot be explained by anything but the filter.
WIDE = token("user:wide", "analyst", clearance=2)
NARROW = token("user:narrow", "analyst", clearance=0)


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def exit_db(test_database_url: str, alembic_config: Config):
    with configured_test_database(test_database_url, alembic_config):
        yield test_database_url


@pytest.fixture(scope="module")
def engine(exit_db: str) -> sa.Engine:
    return sa.create_engine(exit_db)


@pytest.fixture()
def fga() -> _StubFGA:
    return _StubFGA()


@pytest.fixture()
def client(exit_db: str, fga: _StubFGA) -> TestClient:
    app = create_app()
    app.state.authenticator = OIDCAuthenticator(
        app.state.settings, jwks_client=_StubJWKS()
    )
    app.state.fga = fga
    return TestClient(app)


@pytest.fixture()
def world(engine: sa.Engine, ontology):
    """Three people, one of whom exists only through a `sensitive` claim.

    Seeded so the narrower evaluation is a **proper, non-empty** subset: two
    people are reachable through `open` claims and the third is not reachable at
    all below clearance 2. An entity carries no handling code of its own, so
    "exists, for this caller" means "some claim they may read mentions it".
    """
    truncate_domain_data(engine)
    session = Session(engine)
    ids: dict = {
        "source": new_id("src"),
        "record": new_id("rec"),
        "case": new_id("case"),
    }
    with session.begin():
        session.add(
            Source(source_id=ids["source"], source_type="open_source", name="T76")
        )
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="a" * 64,
                storage_uri="test://t76",
            )
        )
        session.add(
            CaseFile(
                case_id=ids["case"],
                title="Harbour movements",
                purpose="T76 exit proof",
                handling_code="open",
                opened_by="user:wide",
            )
        )
        session.flush()
        # Both analysts are on the case. The set is shared case-scoped, so
        # membership is the precondition — and holding it equal is what makes
        # clearance the only variable.
        for member in ("user:wide", "user:narrow"):
            session.add(
                CaseMember(case_id=ids["case"], user_id=member, role="member")
            )
        for key, label in (
            ("open_a", "Fictional ALPHA"),
            ("open_b", "Fictional BRAVO"),
            ("hidden", "Fictional CHARLIE"),
        ):
            ids[key] = new_id("ent")
            session.add(Entity(entity_id=ids[key], entity_type="person", label=label))
        session.flush()

        def claim(subject, predicate, handling, *, object_id=None, value=None):
            session.add(
                Claim(
                    claim_id=new_id("clm"),
                    subject_id=subject,
                    predicate=predicate,
                    object_id=object_id,
                    object_value=value,
                    assertion_type="reported",
                    handling_code=handling,
                    record_id=ids["record"],
                    identity_revision_id=active_revision_id(session),
                    ontology_version=ontology.version,
                    credibility_normalized="possibly_true",
                    verification_status="unverified",
                )
            )

        # Reachable by everybody.
        claim(ids["open_a"], "allied_with", "open", object_id=ids["open_b"])
        # CHARLIE's *only* claims are sensitive, so below clearance 2 there is
        # no readable basis for the entity at all.
        claim(ids["hidden"], "allied_with", "sensitive", object_id=ids["open_a"])
        claim(ids["hidden"], "reachable_on", "sensitive", value=WATCHED)
        session.flush()

    try:
        yield {**ids, "session": session}
    finally:
        session.close()


def _create_and_share(client, fga, world) -> str:
    """Step 1 and 2: a case-scoped set, shared with the narrower analyst."""
    created = client.post(
        "/v1/object-sets",
        json={
            "name": "People on the case",
            "ast": {"kind": "type", "object_type": "person"},
            "case_id": world["case"],
        },
        headers=WIDE,
    )
    assert created.status_code == 200, created.text
    set_id = created.json()["set_id"]

    # The owner can act on their own set; the share route checks `editor`.
    fga.grant("user:wide", "editor", f"object_set:{set_id}")
    fga.grant("user:wide", "evaluator", f"object_set:{set_id}")

    shared = client.post(
        f"/v1/object-sets/{set_id}/share",
        json={"user_sub": "user:narrow", "relation": "evaluator"},
        headers=WIDE,
    )
    assert shared.status_code == 200, shared.text

    # The route writes the grant to the **authz outbox** (ADR-014), which a
    # projector drains into OpenFGA. That projector is not running here, so the
    # grant is reflected into the stub exactly as it would arrive — the route's
    # job is to record the intent and audit it, and that part is asserted above.
    fga.grant("user:narrow", "evaluator", f"object_set:{set_id}")
    return set_id


def test_the_whole_chain(client, fga, world, ontology) -> None:
    """Charter exit №4, end to end, in the order the criterion states it."""
    session: Session = world["session"]
    set_id = _create_and_share(client, fga, world)

    # ── it drives an analytic run ───────────────────────────────────────────
    run = client.post(
        "/v1/analytics/degree?purpose=mapping the harbour network",
        json={"object_set_id": set_id},
        headers=WIDE,
    )
    assert run.status_code == 200, run.text
    wide_run = run.json()["run"]
    assert wide_run["input_kind"] == "object_set"
    assert wide_run["object_set_id"] == set_id
    assert len(wide_run["evaluation_digest"]) == 64

    # ── and a watchlist ─────────────────────────────────────────────────────
    session.rollback()
    with session.begin():
        watchlist = create_watchlist(
            session,
            name="Harbour numbers",
            set_id=set_id,
            rule="exact_identifier",
            user=UserContext(
                sub="user:wide",
                username="user:wide",
                roles=frozenset({"analyst"}),
                clearance=2,
                claims={},
            ),
        )
    with session.begin():
        _, alerts = evaluate_watchlist(session, watchlist, ontology=ontology)
    assert [a.matched_value for a in alerts] == [WATCHED]
    assert alerts[0].handling_code == "sensitive"

    # ── the second analyst evaluates the SAME set ───────────────────────────
    wide_members = {
        m["entity_id"]
        for m in client.post(
            f"/v1/object-sets/{set_id}/evaluate", headers=WIDE
        ).json()["members"]
    }
    narrow_response = client.post(
        f"/v1/object-sets/{set_id}/evaluate", headers=NARROW
    )
    assert narrow_response.status_code == 200, narrow_response.text
    narrow_members = {m["entity_id"] for m in narrow_response.json()["members"]}

    # Three assertions, because any one alone can pass vacuously (M-13).
    assert narrow_members, "the narrower analyst must still have a working view"
    assert narrow_members < wide_members, "a proper subset, not merely a subset"
    assert wide_members - narrow_members == {world["hidden"]}, (
        "and the withheld entity is the one whose only claims are sensitive — "
        "named, so the test fails if the wrong thing goes missing"
    )


def test_two_analysts_running_one_set_record_different_digests(
    client, fga, world
) -> None:
    """The tell that the filters run during evaluation.

    If a set stored members rather than a question, both runs would carry the
    same digest and the difference would have to show up somewhere downstream,
    where nobody looks. The manifest is where it has to be visible, because a
    finding computed under a narrower clearance is a *different* finding and
    without this on the run it reads as the system contradicting itself.
    """
    session: Session = world["session"]
    set_id = _create_and_share(client, fga, world)

    wide_run = client.post(
        "/v1/analytics/degree?purpose=wide",
        json={"object_set_id": set_id},
        headers=WIDE,
    ).json()["run"]
    narrow_run = client.post(
        "/v1/analytics/degree?purpose=narrow",
        json={"object_set_id": set_id},
        headers=NARROW,
    ).json()["run"]

    assert wide_run["object_set_id"] == narrow_run["object_set_id"] == set_id
    assert wide_run["object_set_version"] == narrow_run["object_set_version"]
    assert wide_run["evaluation_digest"] != narrow_run["evaluation_digest"]
    # …and the authorization digest differs too, which is what says *why*.
    assert wide_run["authorization_digest"] != narrow_run["authorization_digest"]

    session.expire_all()
    stored = {
        row.run_id: row.evaluation_digest
        for row in session.scalars(
            sa.select(AnalyticRun).where(AnalyticRun.object_set_id == set_id)
        )
    }
    assert stored[wide_run["run_id"]] == wide_run["evaluation_digest"]
    assert stored[narrow_run["run_id"]] == narrow_run["evaluation_digest"]


def test_the_set_is_the_same_set(client, fga, world) -> None:
    """Not a copy, not a fork: one row, one version, two evaluations.

    Worth asserting on its own, because "a second user sees a narrower
    evaluation" would also be satisfied by handing them a *different* set —
    which is how this property is usually lost.
    """
    set_id = _create_and_share(client, fga, world)
    wide_view = client.post(f"/v1/object-sets/{set_id}/evaluate", headers=WIDE).json()
    narrow_view = client.post(
        f"/v1/object-sets/{set_id}/evaluate", headers=NARROW
    ).json()

    assert wide_view["set_id"] == narrow_view["set_id"] == set_id
    assert wide_view["version"] == narrow_view["version"]
    assert wide_view["evaluation_digest"] != narrow_view["evaluation_digest"]


def test_an_unshared_set_is_absent_for_the_second_analyst(client, fga, world) -> None:
    """The control on the share step: without the grant, none of this works —
    and it fails as 404, because a 403 would disclose that the set exists."""
    created = client.post(
        "/v1/object-sets",
        json={
            "name": "Private",
            "ast": {"kind": "type", "object_type": "person"},
            "case_id": world["case"],
        },
        headers=WIDE,
    ).json()
    response = client.post(
        f"/v1/object-sets/{created['set_id']}/evaluate", headers=NARROW
    )
    assert response.status_code == 404


def test_the_watchlist_runs_as_its_owner_not_as_the_sweeper(
    client, fga, world, ontology
) -> None:
    """The one place a saved artifact uses its owner's clearance (spec 12 §11.3).

    A set evaluates as the *caller*; a watchlist sweeps as its *owner*. Both are
    deliberate and they point opposite ways, so the difference is asserted here
    rather than left to be inferred from two docstrings.
    """
    session: Session = world["session"]
    set_id = _create_and_share(client, fga, world)

    session.rollback()
    with session.begin():
        watchlist = create_watchlist(
            session,
            name="Owned by the narrower analyst",
            set_id=set_id,
            rule="exact_identifier",
            user=UserContext(
                sub="user:narrow",
                username="user:narrow",
                roles=frozenset({"analyst"}),
                clearance=0,
                claims={},
            ),
        )
    with session.begin():
        run, alerts = evaluate_watchlist(session, watchlist, ontology=ontology)

    # CHARLIE's number is sensitive, so for this owner it never becomes a
    # watched value — absent from the scan, not removed from the answer.
    assert alerts == []
    assert run.actor == "user:narrow"

    session.expire_all()
    assert session.get(Watchlist, watchlist.watchlist_id).owner_clearance == 0
