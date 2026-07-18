"""Edge projection v2 — the blocking cases of spec 02 §7.1 (T21).

Every case here exists because the Phase-1 materialized view failed it.  The
view collapsed disjoint intervals into one span, reduced contradictions to a
single `max(weight)`, and grouped by raw entity id so identity decisions could
not reach it.  ADR-030 calls the result an "authoritative rumor engine"; these
tests are what stop it coming back.

The recurring assertion, inherited from T20, is that **no claim row changes**.
A merge collapses the projection and a split restores it because the
projection resolves identity at build time — not because anything rewrote
history.
"""

from __future__ import annotations

from datetime import date

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, new_id
from aegis.er.canonical import rebuild_canonical_map
from aegis.er.ledger import active_revision_id, open_membership
from aegis.ontology import load
from aegis.projections import (
    AGGREGATION_METHOD,
    BUILDER_VERSION,
    is_stale,
    rebuild_edge_projection,
)
from aegis.store import (
    Claim,
    EdgeProjection,
    Entity,
    Mention,
    ReviewQueue,
    Source,
    SourceRecord,
)
from tests.support.database import migrated_test_engine, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement(
    "Article-I", "Article-III", "Article-VIII", "Article-XIII", "ADR-029", "ADR-030", "T21"
)

ANALYST = frozenset({"analyst"})


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def projection_v2_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


@pytest.fixture()
def world(projection_v2_engine: sa.Engine):
    """Three people, one mention each, two source records."""
    truncate_domain_data(projection_v2_engine)
    session = Session(projection_v2_engine)
    ids = {"source": new_id("src")}
    with session.begin():
        session.add(
            Source(
                source_id=ids["source"],
                source_type="open_source",
                name="T21 source",
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
                    content_hash=f"{slot[0]}" * 64,
                    storage_uri=f"test://t21/{slot}",
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
                    norm_key=f"t21_person_{name}",
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
    try:
        yield {
            **ids,
            "session": session,
            "service": service,
            "context": ActionContext(
                actor="user:analyst", purpose="T21 test", roles=ANALYST
            ),
        }
    finally:
        session.close()


def _claim(
    world,
    *,
    subject: str,
    obj: str,
    record: str | None = None,
    anchored: bool = False,
    **kwargs,
) -> str:
    """An `allied_with` claim between two entities, dated as the caller says.

    ``anchored`` attaches the mention each argument came from.  It is off by
    default because most of these cases are about time and support rather than
    identity, and an unanchored claim is the weaker input — the one that has to
    fall back to the canonical map.
    """
    if anchored:
        kwargs["subject_mention_id"] = world[f"mention_{subject}"]
        kwargs["object_mention_id"] = world[f"mention_{obj}"]
    claim = world["service"].record_claim(
        world["context"],
        subject_id=world[f"entity_{subject}"],
        predicate="allied_with",
        object_id=world[f"entity_{obj}"],
        assertion_type="assessed",
        record_id=world[record or "record_one"],
        **kwargs,
    )
    return claim.claim_id


def _rebuild(world, ontology):
    session: Session = world["session"]
    rebuild_canonical_map(session)
    report = rebuild_edge_projection(session, ontology=ontology)
    session.commit()
    return report


def _segments(session: Session) -> list[EdgeProjection]:
    return list(
        session.scalars(
            select(EdgeProjection).order_by(
                EdgeProjection.subject_id,
                EdgeProjection.object_id,
                EdgeProjection.segment_from,
            )
        )
    )


def _endpoints(session: Session) -> set[frozenset[str]]:
    """Edges as unordered endpoint pairs.

    ``allied_with`` is symmetric, so the stored direction is a normalization
    detail rather than a fact about the edge; asserting on it would test the
    sort order of two ULIDs.
    """
    return {frozenset({s.subject_id, s.object_id}) for s in _segments(session)}


def _claim_rows(session: Session) -> set[tuple]:
    """Everything a projection rebuild must never touch."""
    return {
        row
        for row in session.execute(
            select(
                Claim.claim_id,
                Claim.subject_id,
                Claim.object_id,
                Claim.valid_from,
                Claim.valid_to,
                Claim.retracted_at,
            )
        )
    }


# ── the seven blocking cases of spec 02 §7.1 ─────────────────────────────────


@pytest.mark.integration
def test_merge_collapses_the_edge_with_zero_claim_rewrites(world, ontology) -> None:
    """A—C and B—C become one edge when A and B turn out to be one person."""
    session: Session = world["session"]
    _claim(world, subject="a", obj="c")
    _claim(world, subject="b", obj="c")
    session.commit()
    _rebuild(world, ontology)
    assert len(_segments(session)) == 2

    before = _claim_rows(session)
    world["service"].adjudicate_identity(
        world["context"],
        mode="confirm_match",
        parent_revision_id=active_revision_id(session),
        note="same person",
        mention_a=world["mention_a"],
        mention_b=world["mention_b"],
    )
    session.commit()
    _rebuild(world, ontology)

    collapsed = _segments(session)
    assert len(collapsed) == 1, "the merged pair must project as one edge"
    # both claims still support it — the merge lost no evidence
    assert len(collapsed[0].claim_ids) == 2
    assert collapsed[0].support["record_count"] == 1
    assert _claim_rows(session) == before, "identity resolution rewrote a claim"


@pytest.mark.integration
def test_split_restores_the_pre_merge_edges_with_zero_claim_rewrites(
    world, ontology
) -> None:
    """Anchored claims follow their mentions, so a split undoes a merge exactly.

    The anchors are the whole mechanism (ADR-029): the claim still names the
    entity it was written against, and the projection still puts it in the
    right place, because the *mention* moved and the claim points at that.
    """
    session: Session = world["session"]
    _claim(world, subject="a", obj="c", anchored=True)
    _claim(world, subject="b", obj="c", anchored=True)
    session.commit()
    _rebuild(world, ontology)
    before_edges = _endpoints(session)
    before_claims = _claim_rows(session)

    world["service"].adjudicate_identity(
        world["context"],
        mode="confirm_match",
        parent_revision_id=active_revision_id(session),
        note="same person",
        mention_a=world["mention_a"],
        mention_b=world["mention_b"],
    )
    session.commit()
    _rebuild(world, ontology)
    assert len(_segments(session)) == 1

    result = world["service"].adjudicate_identity(
        world["context"],
        mode="split_entity",
        parent_revision_id=active_revision_id(session),
        note="distinct after all",
        entity_id=world["entity_a"],
        mention_ids=[world["mention_b"]],
    )
    session.commit()
    _rebuild(world, ontology)

    restored = _endpoints(session)
    assert len(restored) == 2, "the split must restore both edges"
    # A—C comes back untouched; B's edge returns against the entity the split
    # created, because that is where B's *mention* now lives.  The shape is
    # restored, and no claim moved to say so.
    assert frozenset({world["entity_a"], world["entity_c"]}) in restored
    assert frozenset({result.new_entity_id, world["entity_c"]}) in restored
    assert before_edges - restored == {
        frozenset({world["entity_b"], world["entity_c"]})
    }
    assert _claim_rows(session) == before_claims, "the split rewrote a claim"


@pytest.mark.integration
def test_an_unanchored_claim_is_queued_on_split_not_silently_reassigned(
    world, ontology
) -> None:
    """Spec 02 §3.1 rule 4 — the honest failure mode of the fallback path.

    Without an anchor there is no evidence of which side of the split the
    claim belonged to.  The projection keeps resolving it through the canonical
    map (so it stays with the surviving entity) and adjudication puts a draft
    in front of a human.  Both halves matter: a projection that guessed would
    be wrong silently, and one that dropped the edge would lose a claim.
    """
    session: Session = world["session"]
    _claim(world, subject="b", obj="c")  # deliberately unanchored
    session.commit()

    world["service"].adjudicate_identity(
        world["context"],
        mode="confirm_match",
        parent_revision_id=active_revision_id(session),
        note="same person",
        mention_a=world["mention_a"],
        mention_b=world["mention_b"],
    )
    session.commit()
    result = world["service"].adjudicate_identity(
        world["context"],
        mode="split_entity",
        parent_revision_id=active_revision_id(session),
        note="distinct after all",
        entity_id=world["entity_a"],
        mention_ids=[world["mention_b"]],
    )
    session.commit()
    report = _rebuild(world, ontology)

    # resolved through the map, not through a guess: it stays on the survivor
    assert _endpoints(session) == {
        frozenset({world["entity_a"], world["entity_c"]})
    }, "an unanchored claim must stay with the surviving entity, not follow the split"
    assert report.map_resolved >= 1 and report.anchor_resolved == 0
    # and the human gets asked
    assert result.unattributable_claims, "the split must surface what it cannot attribute"
    drafts = session.scalars(
        select(ReviewQueue).where(ReviewQueue.suggestion_kind == "claim_draft")
    ).all()
    # The draft repoints whichever end named the split entity — the predicate
    # is symmetric, so it may be either.
    assert any(
        result.new_entity_id in (draft.payload.get("subject_id"), draft.payload.get("object_id"))
        for draft in drafts
    ), "an unanchored claim must reach the review queue on a split"


@pytest.mark.integration
def test_disjoint_intervals_yield_two_segments_not_one_span(world, ontology) -> None:
    """The fabrication ADR-030 exists to stop: 2019 + 2023 is not 2019–2023."""
    session: Session = world["session"]
    _claim(
        world,
        subject="a",
        obj="b",
        valid_from=date(2019, 1, 1),
        valid_to=date(2019, 12, 31),
    )
    _claim(
        world,
        subject="a",
        obj="b",
        record="record_two",
        valid_from=date(2023, 1, 1),
        valid_to=date(2023, 12, 31),
    )
    session.commit()
    report = _rebuild(world, ontology)

    segments = _segments(session)
    assert report.edges == 1 and report.segments == 2
    assert [(s.segment_from, s.segment_to) for s in segments] == [
        (date(2019, 1, 1), date(2019, 12, 31)),
        (date(2023, 1, 1), date(2023, 12, 31)),
    ]
    # 2021 is covered by neither segment: nobody claimed anything about it
    assert all(len(s.claim_ids) == 1 for s in segments)


@pytest.mark.integration
def test_overlapping_intervals_segment_at_the_boundaries(world, ontology) -> None:
    """Overlap is where the claim set changes, so it is where a segment ends."""
    session: Session = world["session"]
    _claim(
        world,
        subject="a",
        obj="b",
        valid_from=date(2019, 1, 1),
        valid_to=date(2020, 12, 31),
    )
    _claim(
        world,
        subject="a",
        obj="b",
        record="record_two",
        valid_from=date(2020, 1, 1),
        valid_to=date(2021, 12, 31),
    )
    session.commit()
    _rebuild(world, ontology)

    segments = _segments(session)
    assert [(s.segment_from, s.segment_to, len(s.claim_ids)) for s in segments] == [
        (date(2019, 1, 1), date(2019, 12, 31), 1),  # first claim alone
        (date(2020, 1, 1), date(2020, 12, 31), 2),  # both — the overlap
        (date(2021, 1, 1), date(2021, 12, 31), 1),  # second claim alone
    ]
    # the overlap segment is the only one with two records behind it
    assert [s.record_count for s in segments] == [1, 2, 1]


@pytest.mark.integration
def test_adjacent_intervals_do_not_leave_a_phantom_gap(world, ontology) -> None:
    """A claim ending 2019-12-31 and one starting 2020-01-01 are contiguous."""
    session: Session = world["session"]
    _claim(
        world,
        subject="a",
        obj="b",
        valid_from=date(2019, 1, 1),
        valid_to=date(2019, 12, 31),
    )
    _claim(
        world,
        subject="a",
        obj="b",
        record="record_two",
        valid_from=date(2020, 1, 1),
        valid_to=date(2020, 12, 31),
    )
    session.commit()
    _rebuild(world, ontology)

    segments = _segments(session)
    # Two segments, because the supporting claim set differs — but touching,
    # with no uncovered day between them.
    assert len(segments) == 2
    assert segments[0].segment_to == date(2019, 12, 31)
    assert segments[1].segment_from == date(2020, 1, 1)


@pytest.mark.integration
def test_an_open_interval_stays_open(world, ontology) -> None:
    session: Session = world["session"]
    _claim(world, subject="a", obj="b", valid_from=date(2019, 1, 1))
    session.commit()
    _rebuild(world, ontology)

    segment = _segments(session)[0]
    assert segment.segment_from == date(2019, 1, 1)
    assert segment.segment_to is None, "an open interval must not be given an end"


@pytest.mark.integration
def test_undated_claims_project_as_one_unbounded_segment(world, ontology) -> None:
    session: Session = world["session"]
    _claim(world, subject="a", obj="b")
    session.commit()
    _rebuild(world, ontology)

    segment = _segments(session)[0]
    assert segment.segment_from is None and segment.segment_to is None


@pytest.mark.integration
def test_contradiction_survives_in_the_support_summary(world, ontology) -> None:
    """No aggregate may hide either side of a disagreement (Article VIII)."""
    session: Session = world["session"]
    service: ActionService = world["service"]
    first = _claim(world, subject="a", obj="b")
    second = _claim(world, subject="a", obj="b", record="record_two")
    service.link_claims(
        world["context"], from_claim=first, to_claim=second, relation="contradicts"
    )
    session.commit()
    _rebuild(world, ontology)

    segment = _segments(session)[0]
    support = segment.support
    # One disagreement is one disagreement, however many claims it touches:
    # the segment count is of distinct relations, not a sum of per-claim counts.
    assert support["contradiction_count"] == 1
    assert support["corroboration_count"] == 0
    # Both claims are listed with their own grading, not merged into a score,
    # and each knows it is contested.
    entries = {entry["claim_id"]: entry for entry in support["claims"]}
    assert set(entries) == {first, second}
    assert entries[first]["contradicted_by"] == 1
    assert entries[second]["contradicted_by"] == 1
    assert all("credibility" in entry for entry in entries.values())
    assert support["method"] == AGGREGATION_METHOD


@pytest.mark.integration
def test_the_projection_carries_no_aggregate_weight(world, ontology) -> None:
    """ADR-030's core removal, asserted structurally rather than by inspection."""
    columns = {column.name for column in EdgeProjection.__table__.columns}
    assert "weight" not in columns
    assert "independent_records" not in columns
    assert "record_count" in columns


@pytest.mark.integration
def test_grading_dimensions_stay_separate_in_the_summary(world, ontology) -> None:
    """Article III: reliability, credibility and verification never fuse."""
    session: Session = world["session"]
    _claim(world, subject="a", obj="b")
    session.commit()
    _rebuild(world, ontology)

    entry = _segments(session)[0].support["claims"][0]
    # reliability is graded on the *source*, and is carried through as such
    assert entry["reliability"] == "generally_reliable"
    assert entry["credibility"] == "cannot_judge"
    assert entry["verification"] == "unverified"


@pytest.mark.integration
def test_every_segment_resolves_to_at_least_one_source_record(world, ontology) -> None:
    """Article I: no edge without a source record behind it."""
    session: Session = world["session"]
    _claim(world, subject="a", obj="b")
    _claim(world, subject="b", obj="c", record="record_two")
    session.commit()
    _rebuild(world, ontology)

    records = {
        record_id for (record_id,) in session.execute(select(SourceRecord.record_id))
    }
    for segment in _segments(session):
        assert segment.record_count >= 1
        assert segment.claim_ids
        for entry in segment.support["claims"]:
            assert entry["record_id"] in records


@pytest.mark.integration
def test_retracted_claims_leave_the_projection(world, ontology) -> None:
    """Retraction is soft in the store (Article VIII) and total in the cache."""
    session: Session = world["session"]
    claim_id = _claim(world, subject="a", obj="b")
    session.commit()
    _rebuild(world, ontology)
    assert len(_segments(session)) == 1

    world["service"].retract_claim(
        world["context"], claim_id=claim_id, reason="withdrawn by the source"
    )
    session.commit()
    _rebuild(world, ontology)

    assert _segments(session) == []
    # the claim itself is still there, retracted — nothing was deleted
    assert session.get(Claim, claim_id).retracted_at is not None


@pytest.mark.integration
def test_stamps_record_revision_ontology_and_builder(world, ontology) -> None:
    session: Session = world["session"]
    _claim(world, subject="a", obj="b")
    session.commit()
    report = _rebuild(world, ontology)

    segment = _segments(session)[0]
    assert segment.built_at_revision_id == report.built_at_revision_id
    assert segment.ontology_version == ontology.version
    assert segment.builder_version == BUILDER_VERSION


@pytest.mark.integration
def test_a_projection_built_before_a_decision_is_detectably_stale(
    world, ontology
) -> None:
    """Staleness must be visible, not merely absent from the docs."""
    session: Session = world["session"]
    _claim(world, subject="a", obj="c")
    session.commit()
    _rebuild(world, ontology)
    assert not is_stale(session)

    world["service"].adjudicate_identity(
        world["context"],
        mode="confirm_match",
        parent_revision_id=active_revision_id(session),
        note="same person",
        mention_a=world["mention_a"],
        mention_b=world["mention_b"],
    )
    session.commit()

    assert is_stale(session), "a decision after the build must mark it stale"
    _rebuild(world, ontology)
    assert not is_stale(session)


@pytest.mark.integration
def test_a_rebuild_is_idempotent_in_content_and_identity(world, ontology) -> None:
    """Twice is the same, ids included — otherwise builds cannot be diffed."""
    session: Session = world["session"]
    _claim(world, subject="a", obj="b", valid_from=date(2019, 1, 1))
    _claim(world, subject="b", obj="c", record="record_two")
    session.commit()

    _rebuild(world, ontology)
    first = {(s.edge_id, tuple(s.claim_ids), s.segment_from) for s in _segments(session)}
    _rebuild(world, ontology)
    second = {(s.edge_id, tuple(s.claim_ids), s.segment_from) for s in _segments(session)}

    assert first == second


@pytest.mark.integration
def test_a_merge_of_both_endpoints_drops_the_edge_rather_than_self_looping(
    world, ontology
) -> None:
    """If A and B are one person, "A allied with B" is not an edge any more."""
    session: Session = world["session"]
    _claim(world, subject="a", obj="b")
    session.commit()
    _rebuild(world, ontology)
    assert len(_segments(session)) == 1

    before = _claim_rows(session)
    world["service"].adjudicate_identity(
        world["context"],
        mode="confirm_match",
        parent_revision_id=active_revision_id(session),
        note="same person",
        mention_a=world["mention_a"],
        mention_b=world["mention_b"],
    )
    session.commit()
    report = _rebuild(world, ontology)

    assert _segments(session) == []
    assert report.collapsed_endpoints == 1
    # The claim survives untouched, so the split brings the edge back.
    assert _claim_rows(session) == before


@pytest.mark.integration
def test_handling_rank_is_the_maximum_over_supporting_claims(world, ontology) -> None:
    """A segment is as restricted as its most restricted supporting claim."""
    session: Session = world["session"]
    _claim(world, subject="a", obj="b", handling_code="open")
    _claim(world, subject="a", obj="b", record="record_two", handling_code="restricted")
    session.commit()
    _rebuild(world, ontology)

    assert _segments(session)[0].handling_rank == 1
