"""The investigation's operational plane, at the actions layer (T43, spec 09).

Hypotheses, tasks and case references round-tripping through the service with
their audit, plus the four properties spec 09 argues for and which are easy to
lose:

1. A hypothesis revision is a **snapshot**, not a diff — one row answers "what
   did this say" without replaying the ones before it (§3.1).
2. A **blank** missing-information note is refused, and the refusal is audited
   (§3.3). `required: true` accepts `"   "`; the rule with the strongest reason
   to exist was the one with no mechanism behind it.
3. The same claim may be linked to one hypothesis as **both** supporting and
   contradicting (§3.2, Article VIII).
4. A case reference **grants nothing** and never re-scopes a claim (ADR-044).

The HTTP half — authorization, 404-not-403, both arrays always present — is
`tests/integration/test_investigation_routes.py`.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, ActionValidationError, new_id
from aegis.er.ledger import open_membership
from aegis.er.normalize import norm_key
from aegis.ontology import load
from aegis.store import (
    AuditLog,
    CaseMember,
    CaseReference,
    Claim,
    Entity,
    Hypothesis,
    HypothesisClaim,
    HypothesisRevision,
    InvestigationTask,
    Mention,
    Source,
    SourceRecord,
)
from tests.support.database import migrated_test_engine, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement(
    "Article-VIII", "Article-IX", "Article-X", "ADR-044", "H-17", "T43"
)

ANALYST = frozenset({"analyst"})
SUPERVISOR = frozenset({"supervisor"})
ACTOR = "user:analyst"


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


@pytest.fixture()
def world(engine: sa.Engine, ontology):
    """One case the analyst is a member of, one entity, and one claim about it.

    Fictional throughout. A hypothesis is the one place someone writes down what
    they suspect, so no fixture here names a real person (`data/real/README.md`).
    """
    truncate_domain_data(engine)
    session = Session(engine)
    service = ActionService(session, ontology)
    context = ActionContext(actor=ACTOR, purpose="T43 fixture", roles=ANALYST)
    ids: dict[str, str] = {}
    with session.begin():
        session.add(Source(source_id=(sid := new_id("src")), source_type="open_source", name="T43"))
        session.add(
            SourceRecord(
                record_id=(rid := new_id("rec")),
                source_id=sid,
                ingest_key=new_id("key"),
                content_hash="d" * 64,
                storage_uri="test://t43",
            )
        )
        session.flush()
        ids["record"] = rid
        for key, label in (("person", "Fictional Suspect"), ("org", "Fictional Holdings")):
            entity_id, mention_id = new_id("ent"), new_id("men")
            ids[key] = entity_id
            session.add(
                Entity(
                    entity_id=entity_id,
                    entity_type="person" if key == "person" else "organization",
                    label=label,
                )
            )
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

    case = service.open_case(
        ActionContext(actor=ACTOR, purpose="T43", roles=frozenset({"analyst"})),
        title="Fictional case",
        purpose="testing",
    )
    session.add(CaseMember(case_id=case.case_id, user_id=ACTOR, role="analyst"))
    claim = service.record_claim(
        context,
        subject_id=ids["person"],
        predicate="member_of",
        object_id=ids["org"],
        record_id=ids["record"],
        collection_method="curated",
    )
    session.commit()
    ids["case"] = case.case_id
    ids["claim"] = claim.claim_id
    try:
        yield {**ids, "session": session, "service": service, "context": context}
    finally:
        session.close()


def _open(world, **overrides) -> HypothesisRevision:
    kwargs = {
        "case_id": world["case"],
        "statement": "The two fictional parties are the same enterprise.",
        "missing_info": "No registry filing has been checked.",
    }
    kwargs.update(overrides)
    return world["service"].open_hypothesis(world["context"], **kwargs)


def _denials(session: Session, action: str) -> list[AuditLog]:
    return list(
        session.scalars(
            sa.select(AuditLog)
            .where(AuditLog.action == action, AuditLog.decision == "deny")
            .order_by(AuditLog.id)
        )
    )


# ── hypotheses: opening, revising, history ──────────────────────────────────


def test_opening_a_hypothesis_writes_identity_and_a_first_revision(world) -> None:
    session: Session = world["session"]
    revision = _open(world)
    session.commit()

    hypothesis = session.get(Hypothesis, revision.hypothesis_id)
    assert hypothesis is not None
    assert hypothesis.case_id == world["case"]
    assert hypothesis.opened_by == ACTOR
    assert revision.version == 1
    assert revision.status == "open"
    # No note on the first revision: a hypothesis needs no justification for
    # existing, only for changing.
    assert revision.note is None


def test_a_hypothesis_is_never_a_claim(world) -> None:
    """Article IX in its structural form: a suspicion cannot become an edge.

    A hypothesis has no source record and no grading, so it cannot be recorded
    as a claim even by accident — there is no column for it to occupy.
    """
    session: Session = world["session"]
    before = session.scalar(sa.select(sa.func.count()).select_from(Claim))
    _open(world)
    session.commit()
    assert session.scalar(sa.select(sa.func.count()).select_from(Claim)) == before
    assert not hasattr(Hypothesis, "record_id")
    assert not hasattr(Hypothesis, "credibility_normalized")


def test_a_revision_is_a_snapshot_not_a_diff(world) -> None:
    session: Session = world["session"]
    first = _open(world)
    session.commit()

    second = world["service"].revise_hypothesis(
        world["context"],
        hypothesis_id=first.hypothesis_id,
        note="A filing was found.",
        status="supported",
    )
    session.commit()

    assert second.version == 2
    assert second.status == "supported"
    # Carried forward, not left null: reading this row alone answers what the
    # hypothesis said at version 2.
    assert second.statement == first.statement
    assert second.missing_info == first.missing_info
    assert second.note == "A filing was found."


def test_the_history_returns_every_version_in_order(world) -> None:
    session: Session = world["session"]
    first = _open(world)
    session.commit()
    for status in ("supported", "refuted", "withdrawn"):
        world["service"].revise_hypothesis(
            world["context"],
            hypothesis_id=first.hypothesis_id,
            note=f"moved to {status}",
            status=status,
        )
    session.commit()

    versions = list(
        session.scalars(
            sa.select(HypothesisRevision)
            .where(HypothesisRevision.hypothesis_id == first.hypothesis_id)
            .order_by(HypothesisRevision.version)
        )
    )
    assert [r.version for r in versions] == [1, 2, 3, 4]
    assert [r.status for r in versions] == ["open", "supported", "refuted", "withdrawn"]
    # The earlier statement is a row, not an audit payload to be parsed.
    assert versions[0].status == "open"


# ── the missing-information note (spec 09 §3.3) ─────────────────────────────


def test_a_blank_missing_info_note_is_refused_and_audited(world) -> None:
    """The gap `required: true` leaves open, closed by the fourth criterion.

    GOAL.md §18 requires a hypothesis to say what would change it, and a string
    of spaces satisfies "the field is present" while saying nothing.
    """
    session: Session = world["session"]
    with pytest.raises(ActionValidationError) as exc:
        _open(world, missing_info="   ")
    assert "required_text_is_substantive" in str(exc.value)
    assert "missing_info" in str(exc.value)

    session.rollback()
    denials = _denials(session, "open_hypothesis")
    assert len(denials) == 1
    assert denials[0].actor == ACTOR
    assert denials[0].detail["criterion"] == "required_text_is_substantive"
    # Nothing was written.
    assert session.scalar(sa.select(sa.func.count()).select_from(Hypothesis)) == 0


def test_the_denial_survives_the_callers_rollback(world) -> None:
    """The denial is written in its own session, as T34 established for roles."""
    session: Session = world["session"]
    with pytest.raises(ActionValidationError):
        _open(world, missing_info="")
    session.rollback()
    assert len(_denials(session, "open_hypothesis")) == 1


def test_a_revision_cannot_blank_the_note_either(world) -> None:
    session: Session = world["session"]
    first = _open(world)
    session.commit()
    with pytest.raises(ActionValidationError) as exc:
        world["service"].revise_hypothesis(
            world["context"],
            hypothesis_id=first.hypothesis_id,
            note="clearing it",
            missing_info="  ",
        )
    assert "missing_info" in str(exc.value)
    session.rollback()


def test_the_database_refuses_a_blank_note_as_well(world) -> None:
    """The rule is enforced in two layers on purpose.

    A governance rule that holds in exactly one place is a governance rule with
    a bypass — anything writing the table directly would slip past the action.
    """
    session: Session = world["session"]
    first = _open(world)
    session.commit()
    session.add(
        HypothesisRevision(
            hypothesis_id=first.hypothesis_id,
            version=99,
            statement="bypassing the action",
            status="open",
            missing_info="   ",
            authored_by=ACTOR,
        )
    )
    with pytest.raises(sa.exc.IntegrityError):
        session.commit()
    session.rollback()


# ── the evidence basis (spec 09 §3.2) ───────────────────────────────────────


def test_a_claim_can_be_linked_under_both_stances(world) -> None:
    """Article VIII: a claim that cuts both ways is not a conflict to resolve."""
    session: Session = world["session"]
    first = _open(world)
    session.commit()

    for stance in ("supports", "contradicts"):
        world["service"].link_hypothesis_claim(
            world["context"],
            hypothesis_id=first.hypothesis_id,
            claim_id=world["claim"],
            stance=stance,
            note=f"reads as {stance}",
        )
    session.commit()

    links = list(
        session.scalars(
            sa.select(HypothesisClaim).where(
                HypothesisClaim.hypothesis_id == first.hypothesis_id
            )
        )
    )
    assert sorted(link.stance for link in links) == ["contradicts", "supports"]


def test_the_same_stance_cannot_be_linked_twice(world) -> None:
    session: Session = world["session"]
    first = _open(world)
    session.commit()
    world["service"].link_hypothesis_claim(
        world["context"],
        hypothesis_id=first.hypothesis_id,
        claim_id=world["claim"],
        stance="supports",
    )
    session.commit()
    with pytest.raises(ActionValidationError, match="already linked"):
        world["service"].link_hypothesis_claim(
            world["context"],
            hypothesis_id=first.hypothesis_id,
            claim_id=world["claim"],
            stance="supports",
        )
    session.rollback()


def test_unlinking_tombstones_rather_than_deletes(world) -> None:
    session: Session = world["session"]
    first = _open(world)
    session.commit()
    world["service"].link_hypothesis_claim(
        world["context"],
        hypothesis_id=first.hypothesis_id,
        claim_id=world["claim"],
        stance="supports",
    )
    session.commit()
    world["service"].unlink_hypothesis_claim(
        world["context"],
        hypothesis_id=first.hypothesis_id,
        claim_id=world["claim"],
        stance="supports",
        reason="the filing turned out to be a different company",
    )
    session.commit()

    row = session.get(HypothesisClaim, (first.hypothesis_id, world["claim"], "supports"))
    # The row survives: somebody once thought this claim supported this
    # hypothesis, and that is a fact the case may need to explain.
    assert row is not None
    assert row.detached_at is not None


# ── case references (ADR-044) ───────────────────────────────────────────────


def test_a_reference_does_not_rescope_the_claim(world) -> None:
    """The whole reason references exist as a separate table.

    `claim.case_id` is an access predicate — reassigning it would widen or
    narrow who can read a recorded claim. Referring to it must leave it alone.
    """
    session: Session = world["session"]
    before = session.get(Claim, world["claim"]).case_id
    world["service"].link_case_reference(
        world["context"],
        case_id=world["case"],
        target_type="claim",
        target_id=world["claim"],
        note="mentioned in the filing",
    )
    session.commit()

    assert session.get(Claim, world["claim"]).case_id == before
    reference = session.get(CaseReference, (world["case"], "claim", world["claim"]))
    assert reference is not None
    assert reference.linked_by == ACTOR


def test_a_reference_to_something_that_does_not_exist_is_refused(world) -> None:
    session: Session = world["session"]
    with pytest.raises(ActionValidationError, match="does not exist"):
        world["service"].link_case_reference(
            world["context"],
            case_id=world["case"],
            target_type="entity",
            target_id="ent_not_real",
        )
    session.rollback()


def test_unlinking_a_reference_tombstones_it(world) -> None:
    session: Session = world["session"]
    world["service"].link_case_reference(
        world["context"], case_id=world["case"], target_type="entity", target_id=world["person"]
    )
    session.commit()
    world["service"].unlink_case_reference(
        world["context"],
        case_id=world["case"],
        target_type="entity",
        target_id=world["person"],
        reason="wrong person",
    )
    session.commit()
    row = session.get(CaseReference, (world["case"], "entity", world["person"]))
    assert row is not None and row.detached_at is not None

    # ...and it can be re-linked, which clears the tombstone rather than
    # inserting a second row.
    world["service"].link_case_reference(
        world["context"], case_id=world["case"], target_type="entity", target_id=world["person"]
    )
    session.commit()
    row = session.get(CaseReference, (world["case"], "entity", world["person"]))
    assert row.detached_at is None


def test_a_non_member_cannot_link_a_reference(world) -> None:
    """`actor_is_case_member` reads the canonical row inside the transaction."""
    session: Session = world["session"]
    outsider = ActionContext(actor="user:outsider", purpose="T43", roles=ANALYST)
    with pytest.raises(ActionValidationError, match="actor_is_case_member"):
        world["service"].link_case_reference(
            outsider, case_id=world["case"], target_type="entity", target_id=world["person"]
        )
    session.rollback()
    assert len(_denials(session, "link_case_reference")) == 1


# ── tasks and leads (spec 09 §4) ────────────────────────────────────────────


def test_a_lead_moves_through_its_statuses_with_the_old_value_audited(world) -> None:
    session: Session = world["session"]
    task = world["service"].open_task(
        world["context"],
        case_id=world["case"],
        title="Check the registry filing",
        kind="lead",
    )
    session.commit()
    assert task.status == "open"
    assert task.owner is None  # unassigned is a real state

    for status in ("in_progress", "blocked", "done"):
        world["service"].update_task(
            world["context"], task_id=task.task_id, status=status, note=f"-> {status}"
        )
    session.commit()

    row = session.get(InvestigationTask, task.task_id)
    assert row.status == "done"
    assert row.closed_at is not None

    moves = list(
        session.scalars(
            sa.select(AuditLog)
            .where(AuditLog.action == "update_task", AuditLog.decision == "allow")
            .order_by(AuditLog.id)
        )
    )
    assert [m.detail["status"] for m in moves] == ["in_progress", "blocked", "done"]
    # The old value beside the new one is what makes the history answerable
    # without a transition table.
    assert [m.detail["old_status"] for m in moves] == ["open", "in_progress", "blocked"]


def test_reopening_a_task_clears_its_closing_time(world) -> None:
    session: Session = world["session"]
    task = world["service"].open_task(
        world["context"], case_id=world["case"], title="Reopenable"
    )
    session.commit()
    world["service"].update_task(world["context"], task_id=task.task_id, status="done")
    session.commit()
    assert session.get(InvestigationTask, task.task_id).closed_at is not None

    world["service"].update_task(world["context"], task_id=task.task_id, status="open")
    session.commit()
    # A reopened task carrying a closing time reads as finished.
    assert session.get(InvestigationTask, task.task_id).closed_at is None


def test_any_status_may_follow_any_other(world) -> None:
    """No transition graph — plan §2's workflow-engine trigger stays untouched."""
    session: Session = world["session"]
    task = world["service"].open_task(world["context"], case_id=world["case"], title="Free")
    session.commit()
    for status in ("done", "open", "dropped", "in_progress"):
        world["service"].update_task(world["context"], task_id=task.task_id, status=status)
    session.commit()
    assert session.get(InvestigationTask, task.task_id).status == "in_progress"


def test_a_lead_cannot_pursue_another_cases_hypothesis(world) -> None:
    """A foreign key across an authorization boundary is still a leak."""
    session: Session = world["session"]
    other = world["service"].open_case(
        ActionContext(actor=ACTOR, purpose="T43", roles=ANALYST),
        title="Other fictional case",
        purpose="testing",
    )
    session.add(CaseMember(case_id=other.case_id, user_id=ACTOR, role="analyst"))
    session.commit()
    elsewhere = _open(world, case_id=other.case_id)
    session.commit()

    with pytest.raises(ActionValidationError, match="different case"):
        world["service"].open_task(
            world["context"],
            case_id=world["case"],
            title="Cross-case lead",
            kind="lead",
            hypothesis_id=elsewhere.hypothesis_id,
        )
    session.rollback()


# ── closing a case ──────────────────────────────────────────────────────────


def test_closing_a_case_moves_its_status_and_never_deletes(world) -> None:
    session: Session = world["session"]
    supervisor = ActionContext(actor="user:boss", purpose="T43", roles=SUPERVISOR)
    case = world["service"].close_case(
        supervisor, case_id=world["case"], reason="enquiry concluded"
    )
    session.commit()
    assert case.status == "closed"
    assert case.closed_at is not None

    with pytest.raises(ActionValidationError, match="not open"):
        world["service"].close_case(supervisor, case_id=world["case"], reason="again")
    session.rollback()


def test_an_analyst_cannot_close_a_case(world) -> None:
    session: Session = world["session"]
    with pytest.raises(ActionValidationError, match="actor_holds_action_role"):
        world["service"].close_case(
            world["context"], case_id=world["case"], reason="not mine to close"
        )
    session.rollback()
    assert len(_denials(session, "close_case")) == 1
