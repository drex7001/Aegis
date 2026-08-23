"""Co-arrest edges become arrest events, losing nothing (T63, spec 10 §2.4).

The acceptance criterion is *"migrated incidents lose no sources or gradings"*,
and the strongest form of it is the one asserted here: **every envelope field on
the original claim is present on every claim that replaces it**, enumerated
rather than spot-checked, so a field added to the claim model later cannot be
silently dropped by this migration.

The second property is that nothing is deleted. The original is **retracted**
with a reason naming the event it became — so an auditor still reads it, and the
record says why it stopped being the current answer.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, new_id
from aegis.migration.arrests import (
    ARRESTEE_ROLE,
    SOURCE_PREDICATE,
    migrate_co_arrests,
)
from aegis.ontology import load
from aegis.store import AuditLog, Claim, Entity, Source, SourceRecord
from tests.support.database import migrated_test_engine, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement(
    "Article-I", "Article-VII", "Article-VIII", "Article-X", "ADR-046", "T63"
)

DUBAI = datetime(2019, 2, 4, tzinfo=timezone.utc)
MADAGASCAR = datetime(2023, 3, 15, tzinfo=timezone.utc)

#: Every envelope field the migration must carry. Enumerated so a field added to
#: the claim model later fails this test until someone decides whether it
#: travels — which is the point of writing it out rather than spot-checking.
CARRIED = (
    "assertion_type",
    "excerpt",
    "credibility_normalized",
    "verification_status",
    "event_time_earliest",
    "event_time_latest",
    "handling_code",
    "case_id",
)


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def migration_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


@pytest.fixture()
def world(migration_engine: sa.Engine, ontology):
    """Two arrests from two reports, and one claim that is not an arrest."""
    truncate_domain_data(migration_engine)
    session = Session(migration_engine)
    ids: dict[str, str] = {}
    with session.begin():
        ids["source"] = new_id("src")
        session.add(
            Source(
                source_id=ids["source"],
                source_type="open_source",
                name="Fictional Wire",
                reliability_normalized="generally_reliable",
            )
        )
        for slot in ("dubai", "madagascar"):
            ids[f"record_{slot}"] = new_id("rec")
            session.add(
                SourceRecord(
                    record_id=ids[f"record_{slot}"],
                    source_id=ids["source"],
                    ingest_key=new_id("key"),
                    content_hash=f"{slot[0]}" * 64,
                    storage_uri=f"test://t63/{slot}",
                )
            )
        session.flush()
        for slot, label in (
            ("a", "Fictional A"),
            ("b", "Fictional B"),
            ("c", "Fictional C"),
            ("d", "Fictional D"),
        ):
            ids[slot] = new_id("ent")
            session.add(Entity(entity_id=ids[slot], entity_type="person", label=label))

    service = ActionService(session, ontology)
    context = ActionContext(
        actor="user:analyst", purpose="T63 seed", roles=frozenset({"analyst"})
    )
    ids["claim_dubai"] = service.record_claim(
        context,
        subject_id=ids["a"],
        predicate=SOURCE_PREDICATE,
        object_id=ids["b"],
        record_id=ids["record_dubai"],
        assertion_type="reported",
        excerpt="A was arrested in Dubai; B was among those arrested with him.",
        credibility_normalized="probably_true",
        verification_status="partially_corroborated",
        event_time_earliest=DUBAI,
        event_time_latest=DUBAI,
        handling_code="restricted",
        jurisdiction="AE",
        location_text="Dubai, UAE",
        collection_method="curated",
    ).claim_id
    ids["claim_madagascar"] = service.record_claim(
        context,
        subject_id=ids["c"],
        predicate=SOURCE_PREDICATE,
        object_id=ids["d"],
        record_id=ids["record_madagascar"],
        assertion_type="reported",
        excerpt="C and D were arrested in Madagascar.",
        event_time_earliest=MADAGASCAR,
        event_time_latest=MADAGASCAR,
        location_text="Madagascar",
        collection_method="curated",
    ).claim_id
    # Not an occurrence: a standing relation the rule says stays a predicate.
    ids["claim_kept"] = service.record_claim(
        context,
        subject_id=ids["a"],
        predicate="sibling_of",
        object_id=ids["c"],
        record_id=ids["record_dubai"],
        collection_method="curated",
    ).claim_id
    session.commit()

    try:
        yield {**ids, "session": session, "service": service, "context": context}
    finally:
        session.close()


def _migrate(world, ontology, *, dry_run: bool = False):
    report = migrate_co_arrests(
        world["session"],
        context=ActionContext(
            actor="operator:t63", purpose="T63 migration", roles=frozenset()
        ),
        ontology=ontology,
        dry_run=dry_run,
    )
    world["session"].commit()
    return report


def _events(session: Session) -> list[Entity]:
    return list(
        session.scalars(
            select(Entity).where(Entity.entity_type == "arrest").order_by(Entity.label)
        )
    )


# ── the migration ───────────────────────────────────────────────────────────


def test_two_reports_become_two_arrests(world, ontology) -> None:
    """Two claims are two arrests unless a human says otherwise.

    Grouping is by (record, time, place). Merging two occurrences that were not
    the same one is an identity decision a machine must not make (Article VII),
    so the conservative split is the correct default.
    """
    report = _migrate(world, ontology)
    session: Session = world["session"]

    assert report.claims_considered == 2
    assert len(report.events) == 2
    events = _events(session)
    assert len(events) == 2
    assert {entity.entity_type for entity in events} == {"arrest"}


def test_every_participant_becomes_an_arrestee(world, ontology) -> None:
    report = _migrate(world, ontology)
    session: Session = world["session"]

    for migrated in report.events:
        arrestees = list(
            session.scalars(
                select(Claim).where(
                    Claim.subject_id == migrated.event_id,
                    Claim.predicate == ARRESTEE_ROLE,
                )
            )
        )
        assert len(arrestees) == 2
        assert all(claim.retracted_at is None for claim in arrestees)


def test_no_source_or_grading_is_lost(world, ontology) -> None:
    """The acceptance criterion, enumerated rather than spot-checked.

    Every envelope field on the original is asserted present on every claim that
    replaced it — so a field added to the claim model later fails here until
    someone decides whether it travels.
    """
    session: Session = world["session"]
    before = {
        name: getattr(session.get(Claim, world["claim_dubai"]), name) for name in CARRIED
    }
    report = _migrate(world, ontology)

    dubai = next(
        event for event in report.events if world["claim_dubai"] in event.source_claim_ids
    )
    replacements = [session.get(Claim, claim_id) for claim_id in dubai.new_claim_ids]
    assert replacements

    for claim in replacements:
        for name in CARRIED:
            assert getattr(claim, name) == before[name], name
        # The record is the whole point: a migrated occurrence must still say
        # which report it came from (Article I).
        assert claim.record_id == world["record_dubai"]
        # `restricted` travels, so the migration cannot declassify an incident
        # by moving it.
        assert claim.handling_code == "restricted"


def test_the_original_is_retracted_not_deleted(world, ontology) -> None:
    """Nothing is deleted. An auditor still reads it, and the reason says why."""
    session: Session = world["session"]
    report = _migrate(world, ontology)

    original = session.get(Claim, world["claim_dubai"])
    assert original is not None
    assert original.retracted_at is not None
    dubai = next(
        event for event in report.events if world["claim_dubai"] in event.source_claim_ids
    )
    # The reason names the event it became, so the transformation is answerable
    # from the record rather than from the migration's source code.
    assert dubai.event_id in original.retraction_reason
    assert "spec 10" in original.retraction_reason


def test_a_standing_relation_is_untouched(world, ontology) -> None:
    """`sibling_of` names no occurrence — the rule says it stays a predicate."""
    session: Session = world["session"]
    _migrate(world, ontology)
    kept = session.get(Claim, world["claim_kept"])
    assert kept.retracted_at is None
    assert kept.predicate == "sibling_of"


def test_the_migration_is_idempotent(world, ontology) -> None:
    """A re-run after a partial migration finishes it rather than duplicating."""
    first = _migrate(world, ontology)
    second = _migrate(world, ontology)

    assert len(first.events) == 2
    assert second.claims_considered == 0
    assert second.events == []
    assert len(_events(world["session"])) == 2


def test_a_dry_run_writes_nothing(world, ontology) -> None:
    """A one-time transformation over a real corpus should have to be asked for
    twice — once to see it, once to mean it."""
    session: Session = world["session"]
    report = _migrate(world, ontology, dry_run=True)

    assert len(report.events) == 2
    assert all(event.event_id == "(not created)" for event in report.events)
    assert _events(session) == []
    assert session.get(Claim, world["claim_dubai"]).retracted_at is None


def test_every_write_is_audited_under_the_operator(world, ontology) -> None:
    session: Session = world["session"]
    _migrate(world, ontology)

    rows = list(
        session.scalars(
            select(AuditLog).where(AuditLog.actor == "operator:t63").order_by(AuditLog.id)
        )
    )
    actions = {row.action for row in rows}
    assert "record_event" in actions
    assert "retract_claim" in actions
    # Article X: an operator rewriting part of the corpus leaves a row per write,
    # not one summary row that says a migration happened.
    assert len([row for row in rows if row.action == "record_event"]) == 2
    assert len([row for row in rows if row.action == "retract_claim"]) == 2


def test_the_summary_says_only_what_the_claim_already_carried(world, ontology) -> None:
    """A derived description. Writing anything the source did not support would
    be the migration inventing content; the excerpt is what a reader trusts, and
    it travels with every claim."""
    report = _migrate(world, ontology)
    dubai = next(
        event for event in report.events if world["claim_dubai"] in event.source_claim_ids
    )
    assert "Fictional A" in dubai.summary
    assert "Fictional B" in dubai.summary
    assert "Dubai, UAE" in dubai.summary
    assert "2019-02-04" in dubai.summary


def test_location_text_is_not_resolved_to_a_place(world, ontology) -> None:
    """Turning a source's words into a place is an analyst act with its own
    grading (spec 02 §9.3). Doing it here would manufacture geography the report
    never asserted."""
    session: Session = world["session"]
    _migrate(world, ontology)

    assert session.scalars(
        select(Claim).where(Claim.predicate == "took_place_at")
    ).all() == []
    assert session.scalars(
        select(Entity).where(Entity.entity_type == "location")
    ).all() == []
