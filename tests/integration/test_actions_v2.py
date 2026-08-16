"""Submission criteria are enforced at the write, and denials are audited (T34).

The Phase 3 charter's fourth exit criterion: *an action with declared
`submission_criteria` rejects a non-qualifying actor in a test, and the
rejection is audited.* ADR-040 found two reasons that was not achievable as
written — the ontology's `roles` list fired for one action out of thirteen, and
`ActionService._audit` could only ever write `decision="allow"`. Both are closed
here, and this file is what proves it.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, ActionValidationError, new_id
from aegis.store import AuditLog, CaseFile, CaseMember, Entity, Source, SourceRecord
from tests.support.database import migrated_test_engine, truncate_domain_data

pytestmark = pytest.mark.requirement("Article-X", "ADR-040", "T34")

ANALYST = frozenset({"analyst"})
SUPERVISOR = frozenset({"supervisor"})
AUDITOR = frozenset({"auditor"})


@pytest.fixture(scope="module")
def actions_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


@pytest.fixture()
def world(actions_engine: sa.Engine):
    truncate_domain_data(actions_engine)
    ids = {"case": new_id("cas"), "source": new_id("src"), "record": new_id("rec")}
    session = Session(actions_engine)
    with session.begin():
        session.add(
            CaseFile(
                case_id=ids["case"],
                title="T34 fictional case",
                purpose="testing declared criteria",
                handling_code="open",
                opened_by="user:supervisor",
            )
        )
        session.add(
            Source(source_id=ids["source"], source_type="open_source", name="T34 source")
        )
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="e" * 64,
                storage_uri="test://t34",
            )
        )
    try:
        yield {**ids, "session": session, "service": ActionService(session)}
    finally:
        session.close()


def _denials(session: Session, action: str) -> list[AuditLog]:
    return list(
        session.scalars(
            sa.select(AuditLog)
            .where(AuditLog.decision == "deny", AuditLog.action == action)
            .order_by(AuditLog.id)
        )
    )


# ── actor_holds_action_role ─────────────────────────────────────────────────


def test_a_non_qualifying_actor_is_refused_and_the_denial_is_audited(world) -> None:
    """The charter's exit criterion, in one test."""
    service: ActionService = world["service"]
    session: Session = world["session"]
    context = ActionContext(actor="user:auditor", purpose="T34", roles=AUDITOR)

    with pytest.raises(ActionValidationError) as excinfo:
        service.open_case(context, title="Nope", purpose="Nope")

    assert excinfo.value.path == (
        "actions.open_case.submission_criteria.actor_holds_action_role"
    )
    assert "requires one of ['analyst', 'investigator']" in excinfo.value.message

    denials = _denials(session, "open_case")
    assert len(denials) == 1
    assert denials[0].actor == "user:auditor"
    assert denials[0].detail["criterion"] == "actor_holds_action_role"
    assert "auditor" in denials[0].detail["reason"]
    # Nothing was written.
    assert session.scalar(sa.select(sa.func.count()).select_from(CaseFile)) == 1


def test_the_denial_survives_a_rolled_back_caller_transaction(world) -> None:
    """A refused write must be reviewable even when the request that made it fails.

    Written in its own session for the same reason `aegis/api/deps.py` does it
    for `authz.deny`: the audit row is about the *attempt*, and an attempt that
    only exists inside a transaction nobody committed leaves no trace.
    """
    service: ActionService = world["service"]
    session: Session = world["session"]
    context = ActionContext(actor="user:auditor", roles=AUDITOR)

    with session.begin():
        with pytest.raises(ActionValidationError):
            service.open_case(context, title="Nope", purpose="Nope")
        session.rollback()

    with Session(session.get_bind()) as fresh:
        assert len(_denials(fresh, "open_case")) == 1


def test_a_qualifying_actor_passes_and_writes_an_allow_row(world) -> None:
    service: ActionService = world["service"]
    session: Session = world["session"]
    case = service.open_case(
        ActionContext(actor="user:analyst", roles=ANALYST),
        title="Fine",
        purpose="Also fine",
    )
    session.commit()
    assert case.title == "Fine"
    assert _denials(session, "open_case") == []


def test_a_system_caller_without_roles_is_not_gated(world) -> None:
    """The migration adapter and the CLI are not people and hold no roles."""
    service: ActionService = world["service"]
    session: Session = world["session"]
    case = service.open_case(
        ActionContext(actor="migration", purpose="phase-1 legacy migration"),
        title="Migrated",
        purpose="Backfill",
    )
    session.commit()
    assert case.opened_by == "migration"
    assert _denials(session, "open_case") == []


def test_every_action_is_gated_not_just_adjudicate_identity(world) -> None:
    """The regression ADR-040 was written about.

    Before T34 the ontology's `roles` list was enforced at the write for
    `adjudicate_identity` alone; every other action passed no context and the
    check was skipped. A supervisor may open a case only through the analyst or
    investigator roles, so this is a real refusal for each one.
    """
    service: ActionService = world["service"]
    session: Session = world["session"]
    context = ActionContext(actor="user:auditor", roles=AUDITOR)

    with pytest.raises(ActionValidationError, match="actor_holds_action_role"):
        service.record_claim(
            context, predicate="known_as", record_id=world["record"], subject_id="ent_x"
        )
    with pytest.raises(ActionValidationError, match="actor_holds_action_role"):
        service.release_quarantine(context, record_id=world["record"], note="n")
    with pytest.raises(ActionValidationError, match="actor_holds_action_role"):
        service.assign_case_member(
            context, case_id=world["case"], user_id="user:x", role="analyst"
        )
    assert {row.action for row in _denials(session, "record_claim")} == {"record_claim"}
    assert len(_denials(session, "release_quarantine")) == 1
    assert len(_denials(session, "assign_case_member")) == 1


# ── actor_is_case_member ────────────────────────────────────────────────────


def test_a_case_scoped_write_by_a_non_member_is_refused_and_audited(world) -> None:
    """Checked against the canonical `case_member` table, not OpenFGA (ADR-014)."""
    service: ActionService = world["service"]
    session: Session = world["session"]
    context = ActionContext(actor="user:outsider", roles=ANALYST)

    with pytest.raises(ActionValidationError) as excinfo:
        service.record_claim(
            context,
            predicate="known_as",
            record_id=world["record"],
            subject_id="ent_x",
            object_value="Nickname",
            case_id=world["case"],
        )
    assert excinfo.value.path.endswith("actor_is_case_member")
    assert world["case"] in excinfo.value.message

    denials = _denials(session, "record_claim")
    assert denials[-1].detail["criterion"] == "actor_is_case_member"


def test_a_member_passes_the_case_criterion(world) -> None:
    service: ActionService = world["service"]
    session: Session = world["session"]
    with session.begin():
        session.add(
            CaseMember(case_id=world["case"], user_id="user:insider", role="analyst")
        )

    # Reaches claim validation rather than the criterion: the criterion passed,
    # and the subject entity legitimately does not exist in this fixture.
    with pytest.raises(ActionValidationError) as excinfo:
        service.record_claim(
            ActionContext(actor="user:insider", roles=ANALYST),
            predicate="known_as",
            record_id=world["record"],
            subject_id="ent_missing",
            object_value="Nickname",
            case_id=world["case"],
        )
    assert "actor_is_case_member" not in excinfo.value.path
    assert excinfo.value.path == "claim.subject_id"


def test_a_write_with_no_case_skips_the_case_criterion(world) -> None:
    service: ActionService = world["service"]
    with pytest.raises(ActionValidationError) as excinfo:
        service.record_claim(
            ActionContext(actor="user:outsider", roles=ANALYST),
            predicate="known_as",
            record_id=world["record"],
            subject_id="ent_missing",
            object_value="Nickname",
        )
    assert excinfo.value.path == "claim.subject_id"


# ── declared parameters ─────────────────────────────────────────────────────


def test_an_undeclared_parameter_is_rejected_by_the_generated_model(world) -> None:
    """`record_claim` is the action that takes free-form keywords.

    The other twelve have typed signatures, so Python's own `TypeError` refuses
    an unknown keyword before the model is reached — an earlier and clearer
    rejection, not a weaker one. `record_claim(**claim)` is the surface a
    producer, the migration adapter, and a future SDK actually post through,
    which is where the generated model has to be the gate.
    """
    service: ActionService = world["service"]
    with pytest.raises(ActionValidationError) as excinfo:
        service.record_claim(
            ActionContext(actor="user:analyst", roles=ANALYST),
            predicate="known_as",
            record_id=world["record"],
            subject_id="ent_x",
            object_value="Nickname",
            informant_payment=500,
        )
    assert excinfo.value.path == "actions.record_claim.parameters.informant_payment"
    assert "Extra inputs are not permitted" in excinfo.value.message


def test_a_missing_required_parameter_is_rejected_by_the_generated_model(world) -> None:
    service: ActionService = world["service"]
    with pytest.raises(ActionValidationError) as excinfo:
        service.record_claim(
            ActionContext(actor="user:analyst", roles=ANALYST),
            record_id=world["record"],
            subject_id="ent_x",
            object_value="Nickname",
        )
    assert excinfo.value.path == "actions.record_claim.parameters.predicate"


def test_a_declared_default_reaches_the_write(world) -> None:
    """`assertion_type: {default: reported}` in the ontology, not in Python.

    The claim below never names an assertion type; the value it lands with
    comes from `platform.yaml`, which is the only way the declaration is worth
    writing down.
    """
    service: ActionService = world["service"]
    session: Session = world["session"]
    with session.begin():
        session.add(
            CaseMember(case_id=world["case"], user_id="user:analyst", role="analyst")
        )
        session.add(Entity(entity_id="ent_t34", entity_type="person", label="Fictional"))

    claim = service.record_claim(
        ActionContext(actor="user:analyst", roles=ANALYST),
        predicate="known_as",
        record_id=world["record"],
        subject_id="ent_t34",
        object_value="The Fictional One",
        collection_method="curated",
    )
    session.commit()
    assert claim.assertion_type == "reported"
    assert claim.credibility_normalized == "cannot_judge"
    assert claim.verification_status == "unverified"
    assert claim.handling_code == "open"


# ── second_approver_present ─────────────────────────────────────────────────


def test_dual_control_is_now_a_declared_criterion(world) -> None:
    """Same policy as Phase 2, reached through the declaration (spec 08 §6.3)."""
    service: ActionService = world["service"]
    session: Session = world["session"]
    with pytest.raises(ActionValidationError) as excinfo:
        service.adjudicate_identity(
            ActionContext(actor="user:analyst", roles=ANALYST),
            mode="confirm_match",
            parent_revision_id=0,
            note="protected",
            protected_person=True,
            mention_a="men_a",
            mention_b="men_b",
        )
    assert excinfo.value.path == (
        "actions.adjudicate_identity.submission_criteria.second_approver_present"
    )
    assert len(_denials(session, "adjudicate_identity")) == 1


def test_a_second_approver_must_be_a_different_person(world) -> None:
    service: ActionService = world["service"]
    with pytest.raises(ActionValidationError) as excinfo:
        service.adjudicate_identity(
            ActionContext(
                actor="user:analyst", roles=ANALYST, second_actor="user:analyst"
            ),
            mode="confirm_match",
            parent_revision_id=0,
            note="protected",
            protected_person=True,
            mention_a="men_a",
            mention_b="men_b",
        )
    assert "different person" in excinfo.value.message
