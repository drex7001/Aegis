"""The case graph renders the case's evidence and nothing else (T46).

The charter's third exit criterion has two halves, and only one of them is
about authorization.

**Authorization**: a non-member asking for a case's graph gets 404, like every
other case-scoped read — asking must not confirm the case exists.

**Scope**: for a member, the filter is threaded into `claim_filters` rather than
applied to the result, so it narrows *edge visibility* and *every support
summary* together. That is the half a filtered-afterwards implementation gets
wrong: it would render the right edges with the open graph's tallies, which
overstates what the investigation has and is exactly the sort of quiet
inflation Article IX exists against.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, new_id
from aegis.er.ledger import open_membership
from aegis.er.normalize import norm_key
from aegis.projections import rebuild_edge_projection
from aegis.store import CaseMember, Claim, Entity, Mention, Source, SourceRecord
from tests.integration.test_api import (  # noqa: F401
    _FakeFGA,
    api_db,
    auth,
    clean_api_database,
    client,
    fake_fga,
)

pytestmark = pytest.mark.requirement("Article-VI", "Article-IX", "H-18", "T46")

MEMBER = "member-t46"
OUTSIDER = "outsider-t46"


@pytest.fixture()
def world(client: TestClient, fake_fga: _FakeFGA) -> dict:
    """One edge supported by two claims: one inside the case, one open.

    The mix is the point. Both claims say the same thing about the same pair, so
    the open graph counts two records and the case graph must count one.
    """
    engine = sa.create_engine(client.app.state.settings.database_url)
    ids: dict[str, str] = {}
    with Session(engine) as session, session.begin():
        session.add(Source(source_id=(sid := new_id("src")), source_type="open_source", name="T46"))
        session.add(
            SourceRecord(
                record_id=(rid := new_id("rec")),
                source_id=sid,
                ingest_key=new_id("key"),
                content_hash="b" * 64,
                storage_uri="test://t46",
            )
        )
        session.add(
            SourceRecord(
                record_id=(rid2 := new_id("rec")),
                source_id=sid,
                ingest_key=new_id("key"),
                content_hash="c" * 64,
                storage_uri="test://t46-2",
            )
        )
        session.flush()
        ids.update({"record": rid, "record2": rid2})
        for key, label, entity_type in (
            ("person", "Fictional Suspect", "person"),
            ("org", "Fictional Co", "organization"),
            ("other", "Fictional Bystander", "person"),
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
        context = ActionContext(actor=MEMBER, purpose="T46", roles=frozenset({"analyst"}))
        case = service.open_case(context, title="Fictional case", purpose="T46")
        session.add(CaseMember(case_id=case.case_id, user_id=MEMBER, role="analyst"))
        ids["case"] = case.case_id
        session.flush()

        for record, case_id in ((rid, case.case_id), (rid2, None)):
            session.add(
                Claim(
                    claim_id=new_id("clm"),
                    subject_id=ids["person"],
                    predicate="member_of",
                    object_id=ids["org"],
                    assertion_type="reported",
                    record_id=record,
                    identity_revision_id=0,
                    ontology_version=client.app.state.ontology.version,
                    case_id=case_id,
                )
            )
        # A second edge with no case scope at all: it must not appear in the
        # case graph, and must appear in the open one.
        session.add(
            Claim(
                claim_id=new_id("clm"),
                subject_id=ids["other"],
                predicate="member_of",
                object_id=ids["org"],
                assertion_type="reported",
                record_id=rid2,
                identity_revision_id=0,
                ontology_version=client.app.state.ontology.version,
            )
        )
    with Session(engine) as session:
        rebuild_edge_projection(session, ontology=client.app.state.ontology)
        session.commit()
    engine.dispose()
    fake_fga.add(f"user:{MEMBER}", "analyst", f"case:{ids['case']}")
    return ids


def _expand(client: TestClient, who: str, **body) -> dict:
    response = client.post("/v1/graph/expand", json=body, headers=auth(who, "analyst"))
    return {"status": response.status_code, "body": response.json()}


def test_the_case_graph_holds_only_claims_recorded_into_the_case(
    client: TestClient, world: dict
) -> None:
    scoped = _expand(client, MEMBER, case_id=world["case"], max_hops=1)
    assert scoped["status"] == 200
    subjects = {edge["subject_id"] for edge in scoped["body"]["edges"]}
    assert subjects == {world["person"]}
    # The out-of-case edge is absent, not faint.
    assert world["other"] not in {node["entity_id"] for node in scoped["body"]["nodes"]}


def test_the_open_graph_still_sees_everything_the_member_may_read(
    client: TestClient, world: dict
) -> None:
    """The narrowing is a parameter, not a new default."""
    everything = _expand(client, MEMBER, max_hops=1)
    subjects = {edge["subject_id"] for edge in everything["body"]["edges"]}
    assert subjects == {world["person"], world["other"]}


def test_the_tally_counts_only_the_cases_own_evidence(
    client: TestClient, world: dict
) -> None:
    """The half a filtered-afterwards implementation gets wrong.

    The same edge is supported by two records — one recorded into the case, one
    open. Rendering it with the open graph's tally would overstate what the
    investigation has.
    """
    scoped = _expand(client, MEMBER, case_id=world["case"], max_hops=1)
    everything = _expand(client, MEMBER, max_hops=1)

    scoped_edge = next(
        edge for edge in scoped["body"]["edges"] if edge["subject_id"] == world["person"]
    )
    open_edge = next(
        edge for edge in everything["body"]["edges"] if edge["subject_id"] == world["person"]
    )
    assert scoped_edge["record_count"] == 1
    assert open_edge["record_count"] == 2
    assert len(scoped_edge["support"]["claims"]) == 1
    assert len(open_edge["support"]["claims"]) == 2


def test_a_non_member_asking_for_a_case_graph_gets_404(
    client: TestClient, world: dict
) -> None:
    """404, not 403 — and not an empty graph either.

    An empty 200 would say "that case exists and holds nothing you can see",
    which is one bit more than the caller is entitled to.
    """
    refused = _expand(client, OUTSIDER, case_id=world["case"], max_hops=1)
    assert refused["status"] == 404
    assert world["case"] not in str(refused["body"])


def test_an_unknown_case_and_a_hidden_one_answer_identically(
    client: TestClient, world: dict
) -> None:
    hidden = _expand(client, OUTSIDER, case_id=world["case"], max_hops=1)
    absent = _expand(client, OUTSIDER, case_id="cas_does_not_exist", max_hops=1)
    assert hidden == absent


def test_the_case_filter_does_not_widen_what_a_member_may_read(
    client: TestClient, world: dict
) -> None:
    """A narrowing parameter must never become a way in.

    Passing another case's id (which the caller is not in) is refused rather
    than silently ignored — an ignored filter would return the caller's *whole*
    readable graph under a heading that says otherwise.
    """
    engine = sa.create_engine(client.app.state.settings.database_url)
    with Session(engine) as session, session.begin():
        service = ActionService(session, client.app.state.ontology)
        other = service.open_case(
            ActionContext(actor=OUTSIDER, purpose="T46", roles=frozenset({"analyst"})),
            title="Someone else's case",
            purpose="T46",
        )
        session.add(CaseMember(case_id=other.case_id, user_id=OUTSIDER, role="analyst"))
        other_id = other.case_id
    engine.dispose()

    refused = _expand(client, MEMBER, case_id=other_id, max_hops=1)
    assert refused["status"] == 404
