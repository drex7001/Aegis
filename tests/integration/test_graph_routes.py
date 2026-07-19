"""Governed graph traversal (T22; specs/06 §2.6, ADR-026, ADR-030).

These routes replace an anonymous bulk dump, so the cases that matter are the
ones the dump could not have passed: is the traversal bounded, is authorization
computed inside the query rather than trimmed off the answer, and does the
response say what it left out.

Every fixture is fictional (data-ethics rubric) and every assertion goes through
HTTP, because the filters under test are only real once the token is.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

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
from aegis.er.canonical import rebuild_canonical_map
from aegis.er.ledger import active_revision_id, open_membership
from aegis.ontology import load
from aegis.projections import rebuild_edge_projection
from aegis.store import Entity, Mention, Source, SourceRecord
from tests.support.database import configured_test_database, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

ISSUER = "http://localhost:8180/realms/aegis"
AUDIENCE = "aegis-api"
ANALYST = frozenset({"analyst"})

pytestmark = pytest.mark.requirement(
    "Article-VI", "Article-VIII", "Article-XIII", "ADR-026", "ADR-030", "T22"
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
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def graph_db(test_database_url: str, alembic_config: Config):
    with configured_test_database(test_database_url, alembic_config):
        yield test_database_url


@pytest.fixture(scope="module")
def client(graph_db: str) -> TestClient:
    app = create_app()
    app.state.authenticator = OIDCAuthenticator(
        app.state.settings, jwks_client=_StubJWKS()
    )
    return TestClient(app)


@pytest.fixture()
def world(graph_db: str, ontology):
    """A→B→C→D chain plus an isolated E, all anchored to their own mentions."""
    engine = sa.create_engine(graph_db)
    truncate_domain_data(engine)
    session = Session(engine)
    ids: dict[str, str] = {"source": new_id("src"), "record": new_id("rec")}
    with session.begin():
        session.add(
            Source(
                source_id=ids["source"],
                source_type="open_source",
                name="T22 fixture publication",
                reliability_normalized="generally_reliable",
            )
        )
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="e" * 64,
                storage_uri="test://t22/one",
            )
        )
        session.flush()
        for name in "abcde":
            entity_id, mention_id = new_id("ent"), new_id("men")
            ids[f"entity_{name}"] = entity_id
            ids[f"mention_{name}"] = mention_id
            session.add(
                Entity(
                    entity_id=entity_id,
                    entity_type="person",
                    label=f"Fictional {name.upper()}",
                )
            )
            session.add(
                Mention(
                    mention_id=mention_id,
                    record_id=ids["record"],
                    raw_text=f"Fictional {name.upper()}",
                    norm_key=f"t22_fictional_{name}",
                )
            )
        session.flush()
        for name in "abcde":
            open_membership(
                session,
                mention_id=ids[f"mention_{name}"],
                entity_id=ids[f"entity_{name}"],
            )

    service = ActionService(session)
    context = ActionContext(actor="user:analyst", purpose="T22 test", roles=ANALYST)

    def link(subject: str, obj: str, **kwargs) -> str:
        claim = service.record_claim(
            context,
            subject_id=ids[f"entity_{subject}"],
            predicate="allied_with",
            object_id=ids[f"entity_{obj}"],
            subject_mention_id=ids[f"mention_{subject}"],
            object_mention_id=ids[f"mention_{obj}"],
            assertion_type="assessed",
            record_id=ids["record"],
            **kwargs,
        )
        return claim.claim_id

    try:
        yield {
            **ids,
            "session": session,
            "service": service,
            "context": context,
            "link": link,
            "ontology": ontology,
        }
    finally:
        session.close()
        engine.dispose()


def _rebuild(world) -> None:
    session: Session = world["session"]
    rebuild_canonical_map(session)
    rebuild_edge_projection(session, ontology=world["ontology"])
    session.commit()


def _chain(world) -> None:
    """A—B—C—D, and E connected to nothing."""
    world["link"]("a", "b")
    world["link"]("b", "c")
    world["link"]("c", "d")
    _rebuild(world)


def expand(client: TestClient, headers: dict, **body) -> dict:
    response = client.post("/v1/graph/expand", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _labels(payload: dict) -> set[str]:
    return {node["label"] for node in payload["nodes"]}


# ── bounded traversal ────────────────────────────────────────────────────────


def test_one_hop_reaches_only_the_neighbours(client: TestClient, world) -> None:
    _chain(world)

    payload = expand(
        client, auth("analyst", "analyst"), seed_ids=[world["entity_a"]], max_hops=1
    )

    assert _labels(payload) == {"Fictional A", "Fictional B"}
    assert payload["truncated"] is False


def test_hops_accumulate_along_the_chain(client: TestClient, world) -> None:
    _chain(world)

    payload = expand(
        client, auth("analyst", "analyst"), seed_ids=[world["entity_a"]], max_hops=2
    )

    assert _labels(payload) == {"Fictional A", "Fictional B", "Fictional C"}


def test_hop_limit_is_clamped_not_rejected(client: TestClient, world) -> None:
    """specs/06 §4: over-asking gets the maximum, not a 422.

    Nine hops must behave exactly like three — and must not quietly reach D's
    neighbours beyond the cap.
    """
    _chain(world)
    headers = auth("analyst", "analyst")

    nine = expand(client, headers, seed_ids=[world["entity_a"]], max_hops=9)
    three = expand(client, headers, seed_ids=[world["entity_a"]], max_hops=3)

    assert _labels(nine) == _labels(three)
    assert _labels(nine) == {f"Fictional {c}" for c in "ABCD"}


def test_element_budget_truncates_and_says_so(client: TestClient, world) -> None:
    """A partial answer is fine; a partial answer that looks complete is not."""
    _chain(world)

    payload = expand(
        client,
        auth("analyst", "analyst"),
        seed_ids=[world["entity_a"]],
        max_hops=3,
        max_elements=3,
    )

    assert payload["truncated"] is True
    assert len(payload["nodes"]) + len(payload["edges"]) <= 3


def test_a_seed_with_no_visible_edges_still_comes_back(client: TestClient, world) -> None:
    """"Nothing connects to this person" and "no such person" are different
    answers, and an empty response gives the reader the wrong one."""
    _chain(world)

    payload = expand(
        client, auth("analyst", "analyst"), seed_ids=[world["entity_e"]], max_hops=3
    )

    assert _labels(payload) == {"Fictional E"}
    assert payload["edges"] == []


def test_seedless_overview_is_bounded_like_any_expansion(
    client: TestClient, world
) -> None:
    """The one seedless mode is still capped — that is what separates it from
    the ``/api/graph`` dump ADR-026 retired."""
    _chain(world)

    payload = expand(client, auth("analyst", "analyst"), max_elements=2)

    assert payload["truncated"] is True
    assert len(payload["nodes"]) + len(payload["edges"]) <= 2


# ── authorization is computed in the query ───────────────────────────────────


def test_an_edge_held_up_only_by_restricted_support_is_absent(
    client: TestClient, world
) -> None:
    world["link"]("a", "b")
    world["link"]("c", "d", handling_code="restricted")
    _rebuild(world)

    payload = expand(
        client, auth("low", "analyst", clearance=0), seed_ids=[world["entity_c"]]
    )

    assert payload["edges"] == []
    assert _labels(payload) == {"Fictional C"}  # the seed, and nothing inferred


def test_restricted_support_is_absent_from_a_visible_edge_not_counted(
    client: TestClient, world
) -> None:
    """The core no-leak case (specs/03 §4, specs/07 §5).

    Two claims support A—B; one is restricted. A cleared caller sees both. A
    low-clearance caller sees the edge — their open claim justifies it — and
    must see *no trace* of the other: not the claim, not a "1 hidden", and not
    a record count that adds up to two.
    """
    open_claim = world["link"]("a", "b")
    world["link"]("a", "b", handling_code="restricted")
    _rebuild(world)

    cleared = expand(
        client, auth("high", "analyst", clearance=2), seed_ids=[world["entity_a"]]
    )
    low = expand(
        client, auth("low", "analyst", clearance=0), seed_ids=[world["entity_a"]]
    )

    assert len(cleared["edges"][0]["support"]["claims"]) == 2
    (edge,) = low["edges"]
    assert [c["claim_id"] for c in edge["support"]["claims"]] == [open_claim]
    assert edge["support"]["record_count"] == 1
    assert edge["record_count"] == 1


def test_contradiction_counts_cover_only_visible_relations(
    client: TestClient, world
) -> None:
    """A relation to a claim the caller cannot read would otherwise report that
    claim's existence as a number.

    This is the deliberate cost of specs/03 §4's "absent, not counted": the
    low-clearance reader sees an edge that looks uncontested. P7's
    marked-redaction mode (H-25) is where that gets revisited.
    """
    visible = world["link"]("a", "b")
    hidden = world["link"]("a", "b", handling_code="restricted")
    world["service"].link_claims(
        world["context"],
        from_claim=hidden,
        to_claim=visible,
        relation="contradicts",
    )
    _rebuild(world)

    cleared = expand(
        client, auth("high", "analyst", clearance=2), seed_ids=[world["entity_a"]]
    )
    low = expand(
        client, auth("low", "analyst", clearance=0), seed_ids=[world["entity_a"]]
    )

    assert cleared["edges"][0]["support"]["contradiction_count"] == 1
    assert low["edges"][0]["support"]["contradiction_count"] == 0
    assert low["edges"][0]["support"]["claims"][0]["contradicted_by"] == 0


def test_no_aggregate_weight_anywhere_in_the_response(
    client: TestClient, world
) -> None:
    """ADR-030: the projection carries a summary, never a fused score."""
    _chain(world)

    payload = expand(client, auth("analyst", "analyst"), seed_ids=[world["entity_a"]])

    edge = payload["edges"][0]
    assert "weight" not in edge
    assert "weight" not in edge["support"]
    assert {"reliability", "credibility", "verification"} <= set(
        edge["support"]["claims"][0]
    )


# ── identity, time, and stamps ───────────────────────────────────────────────


def test_a_seed_naming_an_absorbed_id_answers_about_the_survivor(
    client: TestClient, world
) -> None:
    """A link written before a merge still names the id it was written against.

    Answering "no such entity" for an id the graph is actively drawing an edge
    for would be technically true and practically a lie.
    """
    _chain(world)
    session: Session = world["session"]
    result = world["service"].adjudicate_identity(
        world["context"],
        mode="confirm_match",
        parent_revision_id=active_revision_id(session),
        note="Fictional D and E are one person (T22 fixture).",
        mention_a=world["mention_d"],
        mention_b=world["mention_e"],
    )
    session.commit()
    _rebuild(world)
    survivor = result.surviving_entity_id
    absorbed = next(
        world[f"entity_{c}"] for c in "de" if world[f"entity_{c}"] != survivor
    )

    payload = expand(
        client, auth("analyst", "analyst"), seed_ids=[absorbed], max_hops=1
    )

    assert payload["seed_ids"] == [absorbed]
    assert payload["resolved_seed_ids"] == [survivor]
    assert "Fictional C" in _labels(payload)


def test_disjoint_intervals_come_back_as_separate_edges(
    client: TestClient, world
) -> None:
    """Nobody claimed anything about 2021, and the response must not either."""
    world["link"]("a", "b", valid_from=date(2019, 1, 1), valid_to=date(2019, 12, 31))
    world["link"]("a", "b", valid_from=date(2023, 1, 1), valid_to=date(2023, 12, 31))
    _rebuild(world)

    payload = expand(client, auth("analyst", "analyst"), seed_ids=[world["entity_a"]])

    assert len(payload["edges"]) == 2
    assert {e["segment_from"] for e in payload["edges"]} == {"2019-01-01", "2023-01-01"}


def test_a_time_window_selects_the_overlapping_segment(
    client: TestClient, world
) -> None:
    world["link"]("a", "b", valid_from=date(2019, 1, 1), valid_to=date(2019, 12, 31))
    world["link"]("a", "b", valid_from=date(2023, 1, 1), valid_to=date(2023, 12, 31))
    _rebuild(world)

    payload = expand(
        client,
        auth("analyst", "analyst"),
        seed_ids=[world["entity_a"]],
        valid_from="2023-01-01",
        valid_to="2023-06-30",
    )

    assert [e["segment_from"] for e in payload["edges"]] == ["2023-01-01"]


def test_category_filter_uses_the_ontology_not_a_hardcoded_list(
    client: TestClient, world
) -> None:
    """Article XIV: the core names no domain category.

    A category the ontology does declare selects its predicates; one it does not
    matches nothing rather than erroring, because categories arrive with domain
    modules the core has never heard of.
    """
    _chain(world)
    headers = auth("analyst", "analyst")
    category = world["ontology"].predicates["allied_with"].category

    matching = expand(
        client, headers, seed_ids=[world["entity_a"]], categories=[category]
    )
    unknown = expand(
        client, headers, seed_ids=[world["entity_a"]], categories=["no-such-category"]
    )

    assert matching["edges"]
    assert unknown["edges"] == []


def test_response_carries_build_stamps_and_flags_staleness(
    client: TestClient, world
) -> None:
    """A stale projection is usable; a stale projection that looks current is not."""
    _chain(world)
    headers = auth("analyst", "analyst")

    fresh = expand(client, headers, seed_ids=[world["entity_a"]])
    assert fresh["stamps"]["stale"] is False
    assert fresh["stamps"]["builder_version"]
    assert fresh["stamps"]["ontology_version"] == world["ontology"].version

    session: Session = world["session"]
    world["service"].adjudicate_identity(
        world["context"],
        mode="confirm_match",
        parent_revision_id=active_revision_id(session),
        note="A decision landing after the build (T22 fixture).",
        mention_a=world["mention_d"],
        mention_b=world["mention_e"],
    )
    session.commit()

    after = expand(client, headers, seed_ids=[world["entity_a"]])
    assert after["stamps"]["stale"] is True


# ── paths ────────────────────────────────────────────────────────────────────


def paths(client: TestClient, headers: dict, **body) -> dict:
    response = client.post("/v1/graph/paths", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_shortest_path_walks_the_chain(client: TestClient, world) -> None:
    _chain(world)

    payload = paths(
        client,
        auth("analyst", "analyst"),
        from_id=world["entity_a"],
        to_id=world["entity_d"],
    )

    (path,) = payload["paths"]
    assert path["entity_ids"] == [world[f"entity_{c}"] for c in "abcd"]
    assert len(path["edge_ids"]) == 3
    assert _labels(payload) == {f"Fictional {c}" for c in "ABCD"}


def test_a_hop_bound_below_the_distance_finds_nothing(client: TestClient, world) -> None:
    _chain(world)

    payload = paths(
        client,
        auth("analyst", "analyst"),
        from_id=world["entity_a"],
        to_id=world["entity_d"],
        max_hops=2,
    )

    assert payload["paths"] == []
    assert _labels(payload) == {"Fictional A", "Fictional D"}  # endpoints, no route


def test_a_path_cannot_be_built_through_claims_the_caller_cannot_read(
    client: TestClient, world
) -> None:
    """The sharpest form of the authorization rule: a restricted claim must not
    become a stepping stone that reveals a connection through it."""
    world["link"]("a", "b")
    world["link"]("b", "c", handling_code="restricted")
    _rebuild(world)

    cleared = paths(
        client,
        auth("high", "analyst", clearance=2),
        from_id=world["entity_a"],
        to_id=world["entity_c"],
    )
    low = paths(
        client,
        auth("low", "analyst", clearance=0),
        from_id=world["entity_a"],
        to_id=world["entity_c"],
    )

    assert len(cleared["paths"]) == 1
    assert low["paths"] == []
