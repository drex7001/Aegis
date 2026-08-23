"""`record_event`: an occurrence and its claims, in one transaction (T57).

The charter's second exit criterion lives here — an event with 3+ participants
round-trips — but the cases that matter most are the ones proving the action is
**not** a second write path. Every participant is an ordinary claim, validated
by the ordinary predicate rules, carrying its own source and grading. What the
action adds is atomicity: an entity with no claim would be a fact with no
provenance (Article I, ADR-046).

The inbound-claims case is the other half. Participation claims are subjected to
the *event*, so without §13 an arrest would list its participants and each
participant's page would show no arrest at all — one claim set, two
contradictory pages.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, ActionValidationError, new_id
from aegis.ontology import load
from aegis.queries.provenance import entity_provenance
from aegis.store import AuditLog, Claim, Entity, Source, SourceRecord
from tests.support.database import migrated_test_engine, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement(
    "Article-I", "Article-VIII", "Article-X", "Article-XIV", "ADR-046", "T57"
)

ANALYST = frozenset({"analyst"})
MARCH = datetime(2019, 3, 12, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def event_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


@pytest.fixture()
def world(event_engine: sa.Engine, ontology):
    """Three people, one officer, one location, one source record."""
    truncate_domain_data(event_engine)
    session = Session(event_engine)
    ids = {"source": new_id("src"), "record": new_id("rec")}
    with session.begin():
        session.add(
            Source(
                source_id=ids["source"],
                source_type="open_source",
                name="T57 press report",
                reliability_normalized="generally_reliable",
            )
        )
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="c" * 64,
                storage_uri="test://t57/one",
            )
        )
        session.flush()
        for slot, label, kind in (
            ("one", "Nimal Perera", "person"),
            ("two", "Kamala Silva", "person"),
            ("three", "Ranjan Fernando", "person"),
            ("officer", "Inspector Alwis", "person"),
            ("place", "Negombo", "location"),
            ("org", "Harbour Traders", "organization"),
        ):
            entity_id = new_id("ent")
            ids[slot] = entity_id
            session.add(Entity(entity_id=entity_id, entity_type=kind, label=label))
    service = ActionService(session, ontology)
    try:
        yield {
            **ids,
            "session": session,
            "service": service,
            "context": ActionContext(
                actor="user:analyst", purpose="T57 test", roles=ANALYST
            ),
        }
    finally:
        session.close()


def _arrest(world, **overrides):
    payload = {
        "event_type": "arrest",
        "record_id": world["record"],
        "summary": "Three men arrested at Negombo on 12 March 2019",
        "event_time_earliest": MARCH,
        "event_time_latest": MARCH,
        "participants": [
            {"role": "has_arrestee", "entity_id": world["one"]},
            {"role": "has_arrestee", "entity_id": world["two"]},
            {"role": "has_arrestee", "entity_id": world["three"]},
            {"role": "has_arresting_officer", "entity_id": world["officer"]},
        ],
        "places": [{"role": "took_place_at", "entity_id": world["place"]}],
    }
    payload.update(overrides)
    return world["service"].record_event(world["context"], **payload)


def _claims(session: Session, event_id: str) -> list[Claim]:
    return list(
        session.scalars(
            select(Claim).where(Claim.subject_id == event_id).order_by(Claim.claim_id)
        )
    )


# ── the criterion ───────────────────────────────────────────────────────────


def test_an_event_with_more_than_three_participants_round_trips(world) -> None:
    """Charter exit №2, at the action layer.

    Four participants and a place become five claims plus the summary — each
    one an ordinary claim carrying the source, the grading and the interval the
    call supplied.
    """
    result = _arrest(world)
    session: Session = world["session"]
    session.commit()

    event = session.get(Entity, result.entity_id)
    assert event.entity_type == "arrest"
    claims = _claims(session, result.entity_id)
    assert len(claims) == 6 == len(result.claim_ids)

    by_predicate = {}
    for claim in claims:
        by_predicate.setdefault(claim.predicate, []).append(claim)
    assert len(by_predicate["has_arrestee"]) == 3
    assert len(by_predicate["has_arresting_officer"]) == 1
    assert len(by_predicate["took_place_at"]) == 1
    assert by_predicate["summarized_as"][0].object_value.startswith("Three men")

    # Every claim carries the envelope, so a participation is as attributable
    # and as gradable as any other assertion.
    for claim in claims:
        assert claim.record_id == world["record"]
        assert claim.event_time_earliest == MARCH
        assert claim.credibility_normalized == "cannot_judge"
        assert claim.retracted_at is None


def test_each_participant_sees_the_event_on_its_own_page(world, ontology) -> None:
    """Spec 10 §13 — the reason the inbound set exists.

    Participation claims are subjected to the event, so without this an arrest
    lists its participants and each participant's page shows no arrest at all:
    one claim set, two contradictory pages.
    """
    result = _arrest(world)
    session: Session = world["session"]
    session.commit()

    person = entity_provenance(session, entity_id=world["one"])
    assert person.claims == []                       # Nimal asserts nothing
    inbound = {entry.claim.predicate for entry in person.inbound_claims}
    assert inbound == {"has_arrestee"}
    assert person.inbound_claims[0].claim.subject_id == result.entity_id
    # ...and the source travels with it, so the panel opens from either end.
    assert person.inbound_claims[0].record.record_id == world["record"]

    event = entity_provenance(session, entity_id=result.entity_id)
    assert len(event.claims) == 6
    assert event.inbound_claims == []


def test_the_inbound_set_is_generic_not_event_shaped(world) -> None:
    """The same hole existed for `member_of` and is closed by the same field."""
    session: Session = world["session"]
    world["service"].record_claim(
        world["context"],
        subject_id=world["one"],
        predicate="member_of",
        object_id=world["org"],
        record_id=world["record"],
        collection_method="curated",
    )
    session.commit()

    org = entity_provenance(session, entity_id=world["org"])
    assert [entry.claim.predicate for entry in org.inbound_claims] == ["member_of"]


# ── the action is not a second write path ───────────────────────────────────


def test_an_undeclared_role_is_refused_with_the_vocabulary_that_exists(world) -> None:
    with pytest.raises(ActionValidationError) as exc:
        _arrest(world, participants=[{"role": "has_ringleader", "entity_id": world["one"]}])
    assert "has_ringleader" in str(exc.value)
    assert "has_arrestee" in str(exc.value)


def test_a_role_from_another_kind_of_occurrence_is_refused(world) -> None:
    """An arrestee at a meeting is a validation error, not a convention."""
    with pytest.raises(ActionValidationError) as exc:
        world["service"].record_event(
            world["context"],
            event_type="meeting",
            record_id=world["record"],
            summary="A meeting",
            participants=[{"role": "has_arrestee", "entity_id": world["one"]}],
        )
    assert "has_arrestee" in str(exc.value)


def test_an_object_type_that_is_not_an_event_is_refused(world) -> None:
    """The core checks the *interface*, so the message names what qualifies."""
    with pytest.raises(ActionValidationError) as exc:
        _arrest(world, event_type="person")
    assert "event" in str(exc.value)
    assert "arrest" in str(exc.value)


def test_a_participant_of_the_wrong_type_is_refused_by_the_claim_validator(world) -> None:
    """`has_arrestee` targets `person`; a location is not one.

    Caught by the ordinary predicate rules rather than by anything this action
    added, which is the point of the role being a predicate.
    """
    with pytest.raises(ActionValidationError) as exc:
        _arrest(world, participants=[{"role": "has_arrestee", "entity_id": world["place"]}])
    assert "location" in str(exc.value)


def test_nothing_is_written_when_one_participant_fails(world) -> None:
    """Atomicity is the whole reason this action exists.

    A half-recorded arrest — the event and two of its three arrestees — is worse
    than none: it reads as a complete account of a smaller incident.
    """
    session: Session = world["session"]
    before = session.scalar(select(sa.func.count()).select_from(Entity))
    with pytest.raises(ActionValidationError):
        _arrest(
            world,
            participants=[
                {"role": "has_arrestee", "entity_id": world["one"]},
                {"role": "has_arrestee", "entity_id": "ent_does_not_exist"},
            ],
        )
    session.rollback()
    assert session.scalar(select(sa.func.count()).select_from(Entity)) == before
    assert session.scalars(
        select(Claim).where(Claim.predicate == "has_arrestee")
    ).all() == []


def test_an_event_always_carries_at_least_its_summary_claim(world) -> None:
    """An entity row is not an assertion (spec 10 §3.4)."""
    result = world["service"].record_event(
        world["context"],
        event_type="meeting",
        record_id=world["record"],
        summary="Two men met at the harbour",
    )
    session: Session = world["session"]
    session.commit()
    claims = _claims(session, result.entity_id)
    assert [claim.predicate for claim in claims] == ["summarized_as"]


# ── extending an occurrence, rather than merging one ────────────────────────


def test_a_second_report_can_be_attached_to_the_same_event(world) -> None:
    """The reviewer's move — there is no automatic occurrence merging (§3.5)."""
    first = _arrest(world)
    session: Session = world["session"]
    session.commit()

    second_record = new_id("rec")
    with session.begin():
        session.add(
            SourceRecord(
                record_id=second_record,
                source_id=world["source"],
                ingest_key=new_id("key"),
                content_hash="d" * 64,
                storage_uri="test://t57/two",
            )
        )
    again = world["service"].record_event(
        world["context"],
        event_type="arrest",
        event_id=first.entity_id,
        record_id=second_record,
        summary="A fourth man was also held",
    )
    session.commit()

    assert again.entity_id == first.entity_id
    claims = _claims(session, first.entity_id)
    # Both summaries survive: two sources describing one occurrence disagree
    # visibly rather than one overwriting the other (Article VIII).
    summaries = [c for c in claims if c.predicate == "summarized_as"]
    assert len(summaries) == 2
    assert {c.record_id for c in summaries} == {world["record"], second_record}


def test_extending_an_event_of_a_different_type_is_refused(world) -> None:
    """Silently attaching an arrest's claims to a meeting would make the type a
    lie that nothing later could detect."""
    meeting = world["service"].record_event(
        world["context"],
        event_type="meeting",
        record_id=world["record"],
        summary="A meeting",
    )
    world["session"].commit()
    with pytest.raises(ActionValidationError) as exc:
        _arrest(world, event_id=meeting.entity_id)
    assert "meeting" in str(exc.value)


def test_an_unknown_event_id_is_refused(world) -> None:
    with pytest.raises(ActionValidationError) as exc:
        _arrest(world, event_id="ent_nope")
    assert "does not exist" in str(exc.value)


# ── governance ──────────────────────────────────────────────────────────────


def test_the_action_is_audited_with_what_it_created(world) -> None:
    result = _arrest(world)
    session: Session = world["session"]
    session.commit()

    row = session.scalars(
        select(AuditLog)
        .where(AuditLog.action == "record_event")
        .order_by(AuditLog.id.desc())
        .limit(1)
    ).first()
    assert row is not None
    assert row.actor == "user:analyst"
    assert row.resource_id == result.entity_id
    assert row.detail["event_type"] == "arrest"
    assert row.detail["participants"] == 4
    assert row.detail["extended"] is False
    assert sorted(row.detail["claim_ids"]) == sorted(result.claim_ids)


def test_an_actor_without_the_role_is_refused(world) -> None:
    """The ontology's `roles` list is the gate, evaluated at the write."""
    with pytest.raises(ActionValidationError) as exc:
        world["service"].record_event(
            ActionContext(actor="user:auditor", purpose="peek", roles=frozenset({"auditor"})),
            event_type="arrest",
            record_id=world["record"],
            summary="Should not be recorded",
        )
    assert "actor_holds_action_role" in str(exc.value)


def test_a_blank_summary_is_refused(world) -> None:
    """`required_text_is_substantive`: a summary that is only whitespace is not
    a summary (spec 09 §3.3's criterion, reused)."""
    with pytest.raises(ActionValidationError) as exc:
        _arrest(world, summary="   ")
    assert "required_text_is_substantive" in str(exc.value)


def test_an_undeclared_parameter_is_rejected_by_the_generated_model(world) -> None:
    with pytest.raises(ActionValidationError) as exc:
        _arrest(world, confidence_score=0.9)
    assert "confidence_score" in str(exc.value)
