"""The object view's case list leaks nothing (T44, H-18, spec 09 §6.5).

The finding: an entity-360 page lists "cases the entity appears in", and a
viewer may be allowed to see an open entity but not a restricted case that
mentions it.

The naive fix — compute every case touching the entity, then filter — leaves a
timing and an ordering signal behind. The construction here is stronger: the
answer is *derived* from rows the caller can already read, then intersected with
`can_view` on each case. So the strongest test in this file is not "the
restricted case is absent" but **"the response is identical to the response for
an entity in no cases at all"**: absent, not filtered, not counted, not ranked
around.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, new_id
from aegis.er.ledger import open_membership
from aegis.er.normalize import norm_key
from aegis.store import CaseMember, Claim, Entity, Mention, Source, SourceRecord
from tests.integration.test_api import (  # noqa: F401
    _FakeFGA,
    api_db,
    auth,
    clean_api_database,
    client,
    fake_fga,
)

pytestmark = pytest.mark.requirement("Article-VI", "H-18", "T44")

INSIDER = "insider-t44"
OUTSIDER = "outsider-t44"


@pytest.fixture()
def world(client: TestClient, fake_fga: _FakeFGA) -> dict:
    """An open entity, a restricted case that refers to it, and a lonely entity.

    `subject` is mentioned by an open claim anybody may read, and referenced
    from `secret`, a case only the insider belongs to. `lonely` is in no case at
    all and exists to be the baseline the outsider's answer must equal.
    """
    engine = sa.create_engine(client.app.state.settings.database_url)
    ids: dict[str, str] = {}
    with Session(engine) as session, session.begin():
        session.add(Source(source_id=(sid := new_id("src")), source_type="open_source", name="T44"))
        session.add(
            SourceRecord(
                record_id=(rid := new_id("rec")),
                source_id=sid,
                ingest_key=new_id("key"),
                content_hash="a" * 64,
                storage_uri="test://t44",
            )
        )
        session.flush()
        ids["record"] = rid
        for key, label, entity_type in (
            ("subject", "Fictional Subject", "person"),
            ("org", "Fictional Co", "organization"),
            ("lonely", "Fictional Bystander", "person"),
        ):
            entity_id, mention_id = new_id("ent"), new_id("men")
            ids[key] = entity_id
            session.add(Entity(entity_id=entity_id, entity_type=entity_type, label=label))
            session.add(
                Mention(
                    mention_id=mention_id,
                    record_id=rid,
                    raw_text=label,
                    norm_key=f"{norm_key(label)}-{mention_id[-6:].lower()}",
                )
            )
            session.flush()
            open_membership(session, mention_id=mention_id, entity_id=entity_id)

        service = ActionService(session, client.app.state.ontology)
        insider = ActionContext(actor=INSIDER, purpose="T44", roles=frozenset({"analyst"}))
        secret = service.open_case(insider, title="Restricted enquiry", purpose="T44")
        session.add(CaseMember(case_id=secret.case_id, user_id=INSIDER, role="analyst"))
        ids["secret"] = secret.case_id
        session.flush()

        # An open claim about the subject: no case scope, so everybody sees it.
        session.add(
            Claim(
                claim_id=new_id("clm"),
                subject_id=ids["subject"],
                predicate="member_of",
                object_id=ids["org"],
                assertion_type="reported",
                record_id=rid,
                identity_revision_id=0,
                ontology_version=client.app.state.ontology.version,
            )
        )
        session.flush()
        service.link_case_reference(
            insider,
            case_id=secret.case_id,
            target_type="entity",
            target_id=ids["subject"],
            note="named in the filing",
        )
    engine.dispose()
    fake_fga.add(f"user:{INSIDER}", "analyst", f"case:{ids['secret']}")
    return ids


def _cases(client: TestClient, entity_id: str, who: str) -> object:
    return client.get(f"/v1/entities/{entity_id}/cases", headers=auth(who, "analyst"))


# ── the finding ─────────────────────────────────────────────────────────────


def test_a_member_sees_the_case_that_refers_to_the_entity(
    client: TestClient, world: dict
) -> None:
    response = _cases(client, world["subject"], INSIDER)
    assert response.status_code == 200, response.text
    assert [c["case_id"] for c in response.json()] == [world["secret"]]
    assert response.json()[0]["title"] == "Restricted enquiry"


def test_a_non_member_gets_the_same_answer_as_for_an_entity_in_no_case(
    client: TestClient, world: dict
) -> None:
    """The H-18 assertion, in its strongest form.

    Not "the restricted case is absent" — that would pass for an implementation
    that filtered a computed list and left a timing signal. Identical responses
    mean there is nothing to compare.
    """
    referenced = _cases(client, world["subject"], OUTSIDER)
    lonely = _cases(client, world["lonely"], OUTSIDER)

    assert referenced.status_code == lonely.status_code == 200
    assert referenced.json() == lonely.json() == []
    assert referenced.headers.get("content-type") == lonely.headers.get("content-type")


def test_the_response_carries_no_count_and_no_hidden_marker(
    client: TestClient, world: dict
) -> None:
    """Restricted data is absent, not teased (spec 03 §4, spec 07 §5)."""
    body = _cases(client, world["subject"], OUTSIDER).text
    assert world["secret"] not in body
    for tell in ("hidden", "total", "count", "more", "restricted"):
        assert tell not in body.lower()


def test_a_case_scoped_claim_never_names_its_case_to_an_outsider(
    client: TestClient, world: dict, fake_fga: _FakeFGA
) -> None:
    """The other half of the derivation: step 1 is filtered before it is read.

    A claim recorded *into* the secret case mentions the entity, and
    `claim_filters` drops it for a non-member — so the case never becomes a
    candidate in the first place, rather than being removed afterwards.
    """
    engine = sa.create_engine(client.app.state.settings.database_url)
    with Session(engine) as session, session.begin():
        session.add(
            Claim(
                claim_id=new_id("clm"),
                subject_id=world["subject"],
                predicate="member_of",
                object_id=world["org"],
                assertion_type="reported",
                record_id=world["record"],
                identity_revision_id=0,
                ontology_version=client.app.state.ontology.version,
                case_id=world["secret"],
            )
        )
    engine.dispose()

    assert _cases(client, world["subject"], OUTSIDER).json() == []
    assert [c["case_id"] for c in _cases(client, world["subject"], INSIDER).json()] == [
        world["secret"]
    ]


def test_an_entity_in_no_case_returns_an_empty_list_not_a_404(
    client: TestClient, world: dict
) -> None:
    response = _cases(client, world["lonely"], INSIDER)
    assert response.status_code == 200
    assert response.json() == []


def test_an_unknown_entity_is_404(client: TestClient, world: dict) -> None:
    assert _cases(client, "ent_does_not_exist", INSIDER).status_code == 404


def test_the_route_requires_a_token(client: TestClient, world: dict) -> None:
    assert client.get(f"/v1/entities/{world['subject']}/cases").status_code == 401


def test_a_detached_reference_stops_listing_its_case(
    client: TestClient, world: dict
) -> None:
    """Unlinking tombstones the row; the case must leave the list all the same."""
    unlinked = client.delete(
        f"/v1/cases/{world['secret']}/references/entity/{world['subject']}",
        params={"reason": "wrong entity"},
        headers=auth(INSIDER, "analyst"),
    )
    assert unlinked.status_code == 200, unlinked.text
    assert _cases(client, world["subject"], INSIDER).json() == []
