"""Travel reaches canon only through a human (T58, charter exit №4).

The criterion: "a travel event ingested from a press report carries its source
and appears only after review (Article VII unchanged for events)."

Both halves are asserted here, and the second is the one that matters. Between
`run_travel_pass` and `review_suggestion` there is **no event, no claim and no
canonical row** — the pass creates place entities and mentions, which are
evidence rather than assertions, and nothing else. Rejection leaves the queue row
decided and the graph untouched.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, new_id
from aegis.ingestion.travel import PRODUCER, PRODUCER_VERSION, run_travel_pass
from aegis.ontology import load
from aegis.store import AuditLog, Claim, Entity, ReviewQueue, Source, SourceRecord
from tests.support.database import migrated_test_engine, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH, REPO_ROOT

pytestmark = pytest.mark.requirement(
    "Article-I", "Article-VII", "Article-X", "ADR-027", "ADR-031", "T58"
)

ANALYST = frozenset({"analyst"})
FIXTURE = REPO_ROOT / "data" / "sample" / "mvp" / "border-report.txt"


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def travel_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


@pytest.fixture()
def world(travel_engine: sa.Engine, ontology):
    truncate_domain_data(travel_engine)
    session = Session(travel_engine)
    ids = {"source": new_id("src"), "record": new_id("rec")}
    with session.begin():
        session.add(
            Source(
                source_id=ids["source"],
                source_type="open_source",
                name="Fictional Border Bulletin",
                reliability_normalized="generally_reliable",
            )
        )
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="f" * 64,
                storage_uri="test://t58/bulletin",
            )
        )
    service = ActionService(session, ontology)
    try:
        yield {
            **ids,
            "session": session,
            "service": service,
            "text": FIXTURE.read_text(encoding="utf-8"),
            "context": ActionContext(
                actor="user:analyst", purpose="T58 test", roles=ANALYST
            ),
        }
    finally:
        session.close()


def _run(world) -> object:
    return run_travel_pass(
        world["session"],
        record=world["session"].get(SourceRecord, world["record"]),
        text=world["text"],
        actor="producer:travel_pass",
    )


def _events(session: Session) -> list[Entity]:
    return list(
        session.scalars(select(Entity).where(Entity.entity_type == "travel"))
    )


# ── the pass proposes; nothing else happens ─────────────────────────────────


def test_the_pass_proposes_journeys_and_writes_no_canon(world) -> None:
    """Charter exit №4's first half, and the Article VII half of the second.

    Three attributed journeys in the fixture become three suggestions. No event
    entity and no claim exists until a human decides — the assertion that would
    fail if a producer ever gained a write path.
    """
    report = _run(world)
    session: Session = world["session"]
    session.commit()

    assert len(report.suggestions) == 3
    assert report.journeys == 4          # one is unattributed
    assert len(report.unattributed) == 1
    assert "Mannar" in report.unattributed[0]

    assert _events(session) == []
    assert session.scalars(
        select(Claim).where(Claim.predicate.in_(["has_traveller", "travelled_to"]))
    ).all() == []

    for row in report.suggestions:
        assert row.status == "suggested"
        assert row.suggestion_kind == "event_draft"
        assert row.target_action == "record_event"
        assert row.producer == PRODUCER
        assert row.producer_version == PRODUCER_VERSION
        # The source travels with the proposal: a reviewer must never have to
        # ask where a suggestion came from (Article I).
        assert row.record_id == world["record"]
        assert row.payload["excerpt"]


def test_places_are_created_without_coordinates(world) -> None:
    """A press report supports a name, not a position (spec 10 §10).

    Geocoding is manual or assisted, and a locality string turned silently into
    a point is the false precision this phase is built against.
    """
    _run(world)
    session: Session = world["session"]
    session.commit()

    places = {
        entity.label
        for entity in session.scalars(
            select(Entity).where(Entity.entity_type == "location")
        )
    }
    assert {"Colombo", "Chennai", "Dubai", "Katunayake"} <= places
    assert session.scalars(
        select(Claim).where(Claim.predicate == "has_geometry")
    ).all() == []


def test_an_undated_journey_is_undated_not_guessed(world) -> None:
    """Never `recorded_at`: when we learned something is not when it happened."""
    report = _run(world)
    world["session"].commit()

    undated = [
        row for row in report.suggestions if row.payload["event_time_earliest"] is None
    ]
    assert len(undated) == 1
    assert "Chennai to Colombo" in undated[0].payload["summary"]


def test_a_stated_month_becomes_the_month_not_its_midpoint(world) -> None:
    report = _run(world)
    world["session"].commit()

    june = next(
        row for row in report.suggestions if "Dubai" in row.payload["summary"]
    )
    assert june.payload["event_time_earliest"].startswith("2019-06-01")
    assert june.payload["event_time_latest"].startswith("2019-06-30")


def test_replaying_the_pass_proposes_nothing_new(world) -> None:
    """The idempotency key digests the proposal, so a re-run is a no-op."""
    first = _run(world)
    world["session"].commit()
    second = _run(world)
    world["session"].commit()

    assert len(second.suggestions) == 0
    assert second.skipped_replays == len(first.suggestions) == 3


# ── acceptance is the only path to canon ────────────────────────────────────


def test_acceptance_creates_the_event_through_record_event(world) -> None:
    """Charter exit №4's second half.

    Acceptance dispatches through the kind's declared action with the *reviewer*
    as actor (ADR-031 §2), so the event and its claims are recorded by a human
    decision and nothing else.
    """
    report = _run(world)
    session: Session = world["session"]
    session.commit()

    suggestion = next(
        row for row in report.suggestions if "Chennai" in row.payload["summary"]
    )
    decided = world["service"].review_suggestion(
        world["context"], suggestion_id=suggestion.suggestion_id, decision="accepted"
    )
    session.commit()

    assert decided.status == "accepted"
    assert decided.decided_by == "user:analyst"
    assert decided.result_entity_id is not None

    event = session.get(Entity, decided.result_entity_id)
    assert event.entity_type == "travel"
    claims = list(
        session.scalars(select(Claim).where(Claim.subject_id == event.entity_id))
    )
    predicates = {claim.predicate for claim in claims}
    assert predicates == {"summarized_as", "has_traveller", "travelled_from", "travelled_to"}
    # Every claim carries the record the producer read it from.
    assert {claim.record_id for claim in claims} == {world["record"]}
    assert {claim.assertion_type for claim in claims} == {"reported"}


def test_the_travellers_become_entities_from_their_mentions(world) -> None:
    """No `entity_draft` kind: an unadjudicated name rides as its mention anchor
    and acceptance creates the entity from it (spec 02 §3.2)."""
    report = _run(world)
    session: Session = world["session"]
    session.commit()

    suggestion = next(
        row for row in report.suggestions if "Chennai" in row.payload["summary"]
    )
    # The producer proposed mentions, never entity ids it invented.
    assert all(
        "mention_id" in participant and "entity_id" not in participant
        for participant in suggestion.payload["participants"]
    )

    decided = world["service"].review_suggestion(
        world["context"], suggestion_id=suggestion.suggestion_id, decision="accepted"
    )
    session.commit()

    travellers = list(
        session.scalars(
            select(Claim).where(
                Claim.subject_id == decided.result_entity_id,
                Claim.predicate == "has_traveller",
            )
        )
    )
    assert len(travellers) == 2
    for claim in travellers:
        person = session.get(Entity, claim.object_id)
        assert person.entity_type == "person"
        assert claim.object_mention_id is not None


def test_rejection_leaves_no_canonical_trace(world) -> None:
    """Charter exit №4: "rejection leaves no canonical trace"."""
    report = _run(world)
    session: Session = world["session"]
    session.commit()
    before = {entity.entity_id for entity in _events(session)}

    decided = world["service"].review_suggestion(
        world["context"],
        suggestion_id=report.suggestions[0].suggestion_id,
        decision="rejected",
        note="the bulletin was withdrawn",
    )
    session.commit()

    assert decided.status == "rejected"
    assert decided.result_entity_id is None
    assert {entity.entity_id for entity in _events(session)} == before == set()
    # The decision itself is recorded, which is not a canonical *trace of the
    # event* — it is the audit of a human saying no (Article X).
    row = session.scalars(
        select(AuditLog)
        .where(AuditLog.action == "review_suggestion")
        .order_by(AuditLog.id.desc())
        .limit(1)
    ).first()
    assert row.detail["decision"] == "rejected"
    assert row.detail["suggestion_kind"] == "event_draft"


def test_a_reviewer_may_edit_the_draft_before_accepting(world) -> None:
    """The reviewer's edits are what gets recorded (spec 04 §4)."""
    report = _run(world)
    session: Session = world["session"]
    session.commit()

    suggestion = next(
        row for row in report.suggestions if "Chennai" in row.payload["summary"]
    )
    decided = world["service"].review_suggestion(
        world["context"],
        suggestion_id=suggestion.suggestion_id,
        decision="accepted",
        edits={"summary": "Two travellers left Colombo for Chennai (corrected)"},
    )
    session.commit()

    summary = session.scalar(
        select(Claim).where(
            Claim.subject_id == decided.result_entity_id,
            Claim.predicate == "summarized_as",
        )
    )
    assert "corrected" in summary.object_value


def test_an_accepted_draft_is_validated_like_a_direct_call(world) -> None:
    """The queue must not be a way around `record_event`'s refusals."""
    report = _run(world)
    session: Session = world["session"]
    session.commit()

    from aegis.actions import ActionValidationError

    with pytest.raises(ActionValidationError) as exc:
        world["service"].review_suggestion(
            world["context"],
            suggestion_id=report.suggestions[0].suggestion_id,
            decision="accepted",
            edits={"event_type": "person"},
        )
    assert "event" in str(exc.value)
    session.rollback()
