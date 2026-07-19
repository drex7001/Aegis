"""The reversal test plan (T20; spec 05 §8, ADR-028 §6 — blocking).

Wrong merges are the most dangerous failure mode in the platform, so the gate
criterion is **exact reversal**, and these are the cases spec 05 §8 enumerates.
The recurring assertion is that a split restores mention-attributable state
*with zero claim-row rewrites*: identity moves memberships, never claims.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, ActionValidationError, new_id
from aegis.er.adjudication import StaleRevisionError
from aegis.er.canonical import CanonicalMapError, canonical_entity, rebuild_canonical_map
from aegis.er.ledger import active_entity_for_mention, active_revision_id, open_membership
from aegis.store import (
    Claim,
    Entity,
    EntityCanonicalMap,
    IdentityDecision,
    IdentityMembership,
    IdentityNegativeConstraint,
    Mention,
    ReviewQueue,
    Source,
    SourceRecord,
)
from tests.support.database import migrated_test_engine, truncate_domain_data

pytestmark = pytest.mark.requirement(
    "Article-V", "Article-VII", "Article-VIII", "ADR-028", "ADR-029", "T20"
)

ANALYST = frozenset({"analyst"})


@pytest.fixture(scope="module")
def adjudication_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


@pytest.fixture()
def world(adjudication_engine: sa.Engine):
    """Three entities, one mention each, in one record."""
    truncate_domain_data(adjudication_engine)
    session = Session(adjudication_engine)
    ids = {"source": new_id("src"), "record": new_id("rec")}
    with session.begin():
        session.add(
            Source(source_id=ids["source"], source_type="open_source", name="T20 source")
        )
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="a" * 64,
                storage_uri="test://t20",
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
                    record_id=ids["record"],
                    raw_text=f"Person {name}",
                    norm_key=f"person_{name}",
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
                actor="user:analyst", purpose="T20 test", roles=ANALYST
            ),
        }
    finally:
        session.close()


def _state(session: Session) -> set[tuple[str, str]]:
    """Mention → entity, as it stands now."""
    return {
        (mention_id, entity_id)
        for mention_id, entity_id in session.execute(
            select(IdentityMembership.mention_id, IdentityMembership.entity_id).where(
                IdentityMembership.closed_revision_id.is_(None)
            )
        )
    }


def _claim_rows(session: Session) -> set[tuple]:
    """Every field an identity decision must never touch."""
    return {
        row
        for row in session.execute(
            select(
                Claim.claim_id,
                Claim.subject_id,
                Claim.object_id,
                Claim.subject_mention_id,
                Claim.identity_revision_id,
            )
        )
    }


def _confirm(world, left: str, right: str, note: str = "same person"):
    return world["service"].adjudicate_identity(
        world["context"],
        mode="confirm_match",
        parent_revision_id=active_revision_id(world["session"]),
        note=note,
        mention_a=left,
        mention_b=right,
    )


def _split(world, entity_id: str, mention_ids: list[str], note: str = "distinct people"):
    return world["service"].adjudicate_identity(
        world["context"],
        mode="split_entity",
        parent_revision_id=active_revision_id(world["session"]),
        note=note,
        entity_id=entity_id,
        mention_ids=mention_ids,
    )


# ── the seven cases of spec 05 §8 ────────────────────────────────────────────


@pytest.mark.integration
def test_multi_merge_chain_splits_back_to_the_intermediate_state(world) -> None:
    """A←B, then (A+B)←C, then split C out: A+B survives, C's mentions return."""
    session: Session = world["session"]
    _confirm(world, world["mention_a"], world["mention_b"])
    session.commit()
    after_first_merge = _state(session)

    _confirm(world, world["mention_a"], world["mention_c"])
    session.commit()
    assert active_entity_for_mention(session, world["mention_c"]) == world["entity_a"]

    result = _split(world, world["entity_a"], [world["mention_c"]])
    session.commit()

    # A+B is restored exactly; C stands alone again.
    assert active_entity_for_mention(session, world["mention_a"]) == world["entity_a"]
    assert active_entity_for_mention(session, world["mention_b"]) == world["entity_a"]
    assert active_entity_for_mention(session, world["mention_c"]) == result.new_entity_id
    assert {m for m, _ in after_first_merge} == {m for m, _ in _state(session)}


@pytest.mark.integration
def test_partial_split_leaves_the_remainder_untouched(world) -> None:
    session: Session = world["session"]
    _confirm(world, world["mention_a"], world["mention_b"])
    _confirm(world, world["mention_a"], world["mention_c"])
    session.commit()

    result = _split(world, world["entity_a"], [world["mention_b"]])
    session.commit()

    assert active_entity_for_mention(session, world["mention_b"]) == result.new_entity_id
    # the remainder keeps its membership, unchanged
    assert active_entity_for_mention(session, world["mention_a"]) == world["entity_a"]
    assert active_entity_for_mention(session, world["mention_c"]) == world["entity_a"]


@pytest.mark.integration
def test_intervening_claim_edits_survive_a_merge_and_split_unchanged(world) -> None:
    """THE gate criterion: exact reversal with **zero claim-row rewrites**."""
    session: Session = world["session"]
    service: ActionService = world["service"]
    context: ActionContext = world["context"]

    _confirm(world, world["mention_a"], world["mention_b"])
    session.commit()

    # claims recorded and retracted *while merged*
    kept = service.record_claim(
        context,
        subject_id=world["entity_a"],
        predicate="known_as",
        object_value="Recorded while merged",
        assertion_type="reported",
        collection_method="curated",
        record_id=world["record"],
        subject_mention_id=world["mention_b"],
    )
    doomed = service.record_claim(
        context,
        subject_id=world["entity_a"],
        predicate="known_as",
        object_value="Retracted while merged",
        assertion_type="reported",
        collection_method="curated",
        record_id=world["record"],
        subject_mention_id=world["mention_a"],
    )
    session.commit()
    service.retract_claim(context, claim_id=doomed.claim_id, reason="superseded")
    session.commit()
    before_split = _claim_rows(session)

    _split(world, world["entity_a"], [world["mention_b"]])
    session.commit()

    # Not one claim row changed: identity moved memberships, not claims.
    assert _claim_rows(session) == before_split
    # Attribution still follows the mention, which is what makes the state
    # "mention-attributable" rather than merely restored.
    assert kept.subject_mention_id == world["mention_b"]
    assert active_entity_for_mention(session, world["mention_b"]) != world["entity_a"]


@pytest.mark.integration
def test_a_stale_decision_in_scope_is_rejected_and_re_presented(world) -> None:
    session: Session = world["session"]
    stale_parent = active_revision_id(session)
    _confirm(world, world["mention_a"], world["mention_b"])
    session.commit()

    # Not an ActionValidationError: the decision was well-formed and was valid
    # when it was computed — what changed is the world, so it surfaces as a
    # conflict (409) rather than a 422.
    with pytest.raises(StaleRevisionError) as excinfo:
        world["service"].adjudicate_identity(
            world["context"],
            mode="confirm_match",
            parent_revision_id=stale_parent,  # computed before the merge above
            note="also the same person",
            mention_a=world["mention_a"],
            mention_b=world["mention_c"],
        )
    session.rollback()
    # Re-presented, not silently retried: the message names what intervened.
    assert "later decision" in str(excinfo.value)
    assert "confirm" in str(excinfo.value)
    # And it survives as *data*, not only prose. Matching a message string is
    # how a caller ends up unable to show the analyst what actually happened.
    assert excinfo.value.parent_revision_id == stale_parent
    assert [decision.kind for decision in excinfo.value.intervening] == ["confirm"]


@pytest.mark.integration
def test_an_unrelated_concurrent_decision_is_not_rejected(world) -> None:
    """The check is *scoped*.

    A global head check would make every unrelated adjudication conflict, and
    analysts would learn to retry blindly — the opposite of the care this check
    exists to enforce (spec 05 §2).
    """
    session: Session = world["session"]
    extra_entity, extra_mention = new_id("ent"), new_id("men")
    session.add(Entity(entity_id=extra_entity, entity_type="person", label="Person d"))
    session.add(
        Mention(
            mention_id=extra_mention,
            record_id=world["record"],
            raw_text="Person d",
            norm_key="person_d",
        )
    )
    session.flush()
    open_membership(session, mention_id=extra_mention, entity_id=extra_entity)
    session.commit()

    parent = active_revision_id(session)
    _confirm(world, world["mention_a"], world["mention_b"])
    session.commit()

    # Same stale parent revision, but a disjoint entity scope — allowed.
    result = world["service"].adjudicate_identity(
        world["context"],
        mode="confirm_match",
        parent_revision_id=parent,
        note="unrelated pair, decided concurrently",
        mention_a=world["mention_c"],
        mention_b=extra_mention,
    )
    session.commit()
    assert result.decision.kind == "confirm"


@pytest.mark.integration
def test_a_late_mention_attaches_at_the_current_revision(world) -> None:
    """It is not retroactively attributed to a pre-merge revision."""
    session: Session = world["session"]
    _confirm(world, world["mention_a"], world["mention_b"])
    session.commit()
    head = active_revision_id(session)

    late = Mention(
        mention_id=new_id("men"),
        record_id=world["record"],
        raw_text="Person a (late)",
        norm_key="person_a_late",
    )
    session.add(late)
    session.flush()
    membership = open_membership(
        session, mention_id=late.mention_id, entity_id=world["entity_a"]
    )
    session.commit()
    assert membership.opened_revision_id == head
    assert membership.opened_revision_id > 0


@pytest.mark.integration
def test_an_unanchored_claim_on_a_split_goes_to_the_review_queue(world) -> None:
    """Never silently reassigned, never dropped (spec 02 §3.1 rule 4)."""
    session: Session = world["session"]
    service: ActionService = world["service"]
    _confirm(world, world["mention_a"], world["mention_b"])
    session.commit()

    orphan = service.record_claim(
        world["context"],
        subject_id=world["entity_a"],
        predicate="known_as",
        object_value="Analyst judgement, no mention",
        assertion_type="inferred",  # legitimately unanchored
        collection_method="manual",
        record_id=world["record"],
    )
    session.commit()
    before = _claim_rows(session)

    result = _split(world, world["entity_a"], [world["mention_b"]])
    session.commit()

    assert orphan.claim_id in result.unattributable_claims
    # The original claim is untouched; the correction is a *draft* of a
    # superseding claim that a human must accept.
    assert _claim_rows(session) == before
    queued = session.scalar(
        select(ReviewQueue).where(ReviewQueue.producer == "split-readjudication")
    )
    assert queued is not None
    assert queued.suggestion_kind == "claim_draft"
    assert queued.payload["supersedes"] == orphan.claim_id
    assert queued.payload["subject_id"] == result.new_entity_id
    assert queued.producer_meta["candidate_entities"] == [
        result.surviving_entity_id,
        result.new_entity_id,
    ]


@pytest.mark.integration
def test_canonical_map_rebuilds_byte_identically_from_the_ledger_alone(world) -> None:
    """Article XIII: dropping the whole table loses nothing."""
    session: Session = world["session"]
    _confirm(world, world["mention_a"], world["mention_b"])
    session.commit()

    before = {
        (row.entity_id, row.canonical_entity_id)
        for row in session.scalars(select(EntityCanonicalMap))
    }
    assert (world["entity_b"], world["entity_a"]) in before

    session.execute(sa.delete(EntityCanonicalMap))
    session.commit()
    rebuild_canonical_map(session)
    session.commit()

    after = {
        (row.entity_id, row.canonical_entity_id)
        for row in session.scalars(select(EntityCanonicalMap))
    }
    assert after == before


# ── decision discipline ──────────────────────────────────────────────────────


@pytest.mark.integration
def test_every_decision_carries_a_human_actor_and_a_note(world) -> None:
    session: Session = world["session"]
    _confirm(world, world["mention_a"], world["mention_b"], note="matching NIC + DOB")
    session.commit()

    decision = session.scalar(select(IdentityDecision))
    assert decision.decided_by == "user:analyst"
    assert not decision.decided_by.startswith("rule:")
    assert decision.decision_note == "matching NIC + DOB"
    assert decision.parent_revision_id < decision.result_revision_id

    audit = session.execute(
        sa.text(
            "SELECT actor, detail FROM audit_log WHERE action = 'adjudicate_identity'"
        )
    ).one()
    assert audit.actor == "user:analyst"
    assert audit.detail["note"] == "matching NIC + DOB"


@pytest.mark.integration
def test_a_decision_without_a_note_is_refused(world) -> None:
    """A merge nobody explained is a merge nobody can review later."""
    with pytest.raises(ActionValidationError, match="evidence note is required"):
        _confirm(world, world["mention_a"], world["mention_b"], note="   ")
    world["session"].rollback()


@pytest.mark.integration
def test_reject_writes_a_versioned_constraint_and_supersedes_never_erases(world) -> None:
    session: Session = world["session"]
    service: ActionService = world["service"]
    for attempt, basis in enumerate(("conflicting DOB", "newly landed passport"), start=1):
        service.adjudicate_identity(
            world["context"],
            mode="reject_match",
            parent_revision_id=active_revision_id(session),
            note=f"different people ({basis})",
            mention_a=world["mention_a"],
            mention_b=world["mention_b"],
            evidence_basis=basis,
        )
        session.commit()
        assert (
            session.scalar(
                select(func.count()).select_from(IdentityNegativeConstraint)
            )
            == attempt
        )

    constraints = list(
        session.scalars(
            select(IdentityNegativeConstraint).order_by(
                IdentityNegativeConstraint.version
            )
        )
    )
    assert [c.version for c in constraints] == [1, 2]
    # both readings survive (Article VIII)
    assert constraints[0].superseded_by == constraints[1].constraint_id
    assert constraints[1].superseded_by is None
    # a reject moves no membership
    assert active_entity_for_mention(session, world["mention_a"]) == world["entity_a"]
    assert active_entity_for_mention(session, world["mention_b"]) == world["entity_b"]


@pytest.mark.integration
def test_mark_unresolved_is_an_explicit_decision_not_an_absence(world) -> None:
    session: Session = world["session"]
    world["service"].adjudicate_identity(
        world["context"],
        mode="mark_unresolved",
        parent_revision_id=active_revision_id(session),
        note="records disagree; no basis to decide either way",
        mention_a=world["mention_a"],
        mention_b=world["mention_b"],
    )
    session.commit()
    decision = session.scalar(
        select(IdentityDecision).where(IdentityDecision.kind == "unresolved")
    )
    assert decision is not None
    assert _state(session) == {
        (world["mention_a"], world["entity_a"]),
        (world["mention_b"], world["entity_b"]),
        (world["mention_c"], world["entity_c"]),
    }


@pytest.mark.integration
def test_an_actor_without_the_declared_role_cannot_adjudicate(world) -> None:
    """The ontology's `roles` list is enforced at the write (spec 05 §3.4)."""
    with pytest.raises(ActionValidationError, match="requires one of"):
        world["service"].adjudicate_identity(
            ActionContext(actor="user:clerk", purpose="t", roles=frozenset({"auditor"})),
            mode="confirm_match",
            parent_revision_id=active_revision_id(world["session"]),
            note="not my call to make",
            mention_a=world["mention_a"],
            mention_b=world["mention_b"],
        )
    world["session"].rollback()


@pytest.mark.integration
def test_protected_person_requires_a_second_approver(world) -> None:
    """`dual_control_for` was declared but unenforced until now (spec 05 §3.4)."""
    session: Session = world["session"]
    with pytest.raises(ActionValidationError, match="second approver"):
        world["service"].adjudicate_identity(
            world["context"],
            mode="confirm_match",
            parent_revision_id=active_revision_id(session),
            note="merging a protected person",
            protected_person=True,
            mention_a=world["mention_a"],
            mention_b=world["mention_b"],
        )
    session.rollback()

    with pytest.raises(ActionValidationError, match="different person"):
        world["service"].adjudicate_identity(
            ActionContext(
                actor="user:analyst",
                purpose="t",
                roles=ANALYST,
                second_actor="user:analyst",  # approving oneself is not dual control
            ),
            mode="confirm_match",
            parent_revision_id=active_revision_id(session),
            note="merging a protected person",
            protected_person=True,
            mention_a=world["mention_a"],
            mention_b=world["mention_b"],
        )
    session.rollback()

    result = world["service"].adjudicate_identity(
        ActionContext(
            actor="user:analyst",
            purpose="t",
            roles=ANALYST,
            second_actor="user:supervisor",
        ),
        mode="confirm_match",
        parent_revision_id=active_revision_id(session),
        note="merging a protected person, countersigned",
        protected_person=True,
        mention_a=world["mention_a"],
        mention_b=world["mention_b"],
    )
    session.commit()
    assert result.decision.kind == "confirm"


@pytest.mark.integration
def test_a_split_that_moves_everything_is_refused(world) -> None:
    session: Session = world["session"]
    _confirm(world, world["mention_a"], world["mention_b"])
    session.commit()
    with pytest.raises(ActionValidationError, match="rename, not a split"):
        _split(world, world["entity_a"], [world["mention_a"], world["mention_b"]])
    session.rollback()


@pytest.mark.integration
def test_an_entity_with_no_memberships_and_no_lineage_is_tombstoned(world) -> None:
    """Retained forever, excluded from projections, id never reused (spec 05 §5)."""
    session: Session = world["session"]
    stranded = Entity(entity_id=new_id("ent"), entity_type="person", label="Stranded")
    session.add(stranded)
    session.commit()

    rebuild_canonical_map(session)
    session.commit()

    session.refresh(stranded)
    assert stranded.tombstoned_at is not None
    # It resolves to itself rather than disappearing: the row survives so any
    # historical reference to the id still resolves.
    assert canonical_entity(session, stranded.entity_id) == stranded.entity_id


@pytest.mark.integration
def test_a_merged_entity_resolves_to_its_survivor_and_is_not_tombstoned(world) -> None:
    """An absorbed entity has a lineage target, so it is not stranded."""
    session: Session = world["session"]
    _confirm(world, world["mention_a"], world["mention_b"])
    session.commit()

    absorbed = session.get(Entity, world["entity_b"])
    assert absorbed.tombstoned_at is None
    assert canonical_entity(session, world["entity_b"]) == world["entity_a"]
    assert canonical_entity(session, world["entity_a"]) == world["entity_a"]


@pytest.mark.integration
def test_a_cold_canonical_map_degrades_to_resolving_to_itself(world) -> None:
    """The map is a cache; a missing row must not be a failure (Article XIII)."""
    session: Session = world["session"]
    session.execute(sa.delete(EntityCanonicalMap))
    session.commit()
    assert canonical_entity(session, world["entity_a"]) == world["entity_a"]
