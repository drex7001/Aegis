"""Transactional action-layer acceptance tests (speckit T7)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import os

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, ActionValidationError, new_id
from aegis.audit import verify
from aegis.store import (
    AuditLog,
    AuthzOutbox,
    CaseFile,
    CaseMember,
    Claim,
    ClaimRelation,
    CustodyEvent,
    Entity,
    EvidenceItem,
    ReviewQueue,
    Source,
    SourceRecord,
)
from tests.support.database import migrated_test_engine


pytestmark = pytest.mark.requirement("Article-VII", "Article-X", "T7")


@pytest.fixture(scope="module")
def action_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


@pytest.fixture()
def seeded(action_engine: sa.Engine) -> dict[str, object]:
    ids = {
        "source": new_id("src"),
        "record": new_id("rec"),
        "person_a": new_id("ent"),
        "person_b": new_id("ent"),
        "organization": new_id("ent"),
    }
    session = Session(action_engine)
    with session.begin():
        session.add(
            Source(
                source_id=ids["source"], source_type="open_source", name="T7 test source"
            )
        )
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="b" * 64,
                storage_uri="test://record",
            )
        )
        session.add_all(
            [
                Entity(entity_id=ids["person_a"], entity_type="person", label="A"),
                Entity(entity_id=ids["person_b"], entity_type="person", label="B"),
                Entity(
                    entity_id=ids["organization"],
                    entity_type="organization",
                    label="Org",
                ),
            ]
        )
    yield {
        **ids,
        "session": session,
        "service": ActionService(session),
        "context": ActionContext(actor="test:analyst", purpose="T7 tests"),
    }
    session.rollback()
    session.close()


def _claim_args(seed: dict[str, object], **overrides: object) -> dict[str, object]:
    args: dict[str, object] = {
        "subject_id": seed["person_a"],
        "predicate": "member_of",
        "object_id": seed["organization"],
        "record_id": seed["record"],
        "assertion_type": "reported",
    }
    args.update(overrides)
    return args


@pytest.mark.integration
def test_record_claim_validates_ontology_and_invariants(seeded: dict[str, object]) -> None:
    service: ActionService = seeded["service"]  # type: ignore[assignment]
    context: ActionContext = seeded["context"]  # type: ignore[assignment]
    claim = service.record_claim(
        context,
        **_claim_args(
            seeded,
            subject_id=seeded["person_b"],
            predicate="sibling_of",
            object_id=seeded["person_a"],
            credibility_normalized="probably_true",
            verification_status="partially_corroborated",
        ),
    )
    service.session.commit()
    service.session.refresh(claim)
    assert claim.subject_id < claim.object_id  # symmetric predicates canonicalize
    assert claim.ontology_version == service.ontology.version

    with pytest.raises(ActionValidationError, match=r"^predicates\.unknown_predicate:"):
        service.record_claim(
            context, **_claim_args(seeded, predicate="unknown_predicate")
        )
    with pytest.raises(ActionValidationError, match=r"^grading\.credibility\.bogus:"):
        service.record_claim(
            context, **_claim_args(seeded, credibility_normalized="bogus")
        )
    with pytest.raises(ActionValidationError, match=r"^handling_codes\.secret:"):
        service.record_claim(context, **_claim_args(seeded, handling_code="secret"))
    unknown_type_id = new_id("ent")
    service.session.add(Entity(entity_id=unknown_type_id, entity_type="alien", label="Unknown"))
    service.session.commit()
    with pytest.raises(ActionValidationError, match=r"^object_types\.alien:"):
        service.record_claim(
            context, **_claim_args(seeded, subject_id=unknown_type_id)
        )
    with pytest.raises(ActionValidationError, match="self-claims are forbidden"):
        service.record_claim(
            context,
            **_claim_args(
                seeded,
                predicate="sibling_of",
                object_id=seeded["person_a"],
            ),
        )
    with pytest.raises(ActionValidationError, match="must be on or after valid_from"):
        service.record_claim(
            context,
            **_claim_args(
                seeded,
                valid_from=date(2026, 2, 1),
                valid_to=date(2026, 1, 1),
            ),
        )
    now = datetime.now(timezone.utc)
    with pytest.raises(ActionValidationError, match="must be on or after event_time_earliest"):
        service.record_claim(
            context,
            **_claim_args(
                seeded,
                event_time_earliest=now,
                event_time_latest=now - timedelta(seconds=1),
            ),
        )


@pytest.mark.integration
def test_retract_claim(seeded: dict[str, object]) -> None:
    service: ActionService = seeded["service"]  # type: ignore[assignment]
    context: ActionContext = seeded["context"]  # type: ignore[assignment]
    claim = service.record_claim(context, **_claim_args(seeded))
    service.session.commit()
    claim = service.retract_claim(context, claim_id=claim.claim_id, reason="superseded")
    service.session.commit()
    assert claim.retracted_at is not None
    assert claim.retraction_reason == "superseded"


@pytest.mark.integration
def test_link_claims(seeded: dict[str, object]) -> None:
    service: ActionService = seeded["service"]  # type: ignore[assignment]
    context: ActionContext = seeded["context"]  # type: ignore[assignment]
    first = service.record_claim(context, **_claim_args(seeded))
    second = service.record_claim(
        context,
        **_claim_args(seeded, predicate="known_as", object_id=None, object_value="Alias"),
    )
    service.session.commit()
    relation = service.link_claims(
        context,
        from_claim=first.claim_id,
        to_claim=second.claim_id,
        relation="contradicts",
    )
    service.session.commit()
    assert service.session.get(
        ClaimRelation, (relation.from_claim, relation.to_claim, relation.relation)
    )


@pytest.mark.integration
def test_submit_and_review_suggestion(seeded: dict[str, object]) -> None:
    service: ActionService = seeded["service"]  # type: ignore[assignment]
    context: ActionContext = seeded["context"]  # type: ignore[assignment]
    payload = _claim_args(
        seeded, predicate="known_as", object_id=None, object_value="Review alias"
    )
    suggestion = service.submit_suggestion(
        context, payload=payload, producer="semantic_pass", producer_meta={"model": "test"}
    )
    service.session.commit()
    decided = service.review_suggestion(
        context, suggestion_id=suggestion.suggestion_id, decision="accepted", note="checked"
    )
    service.session.commit()
    assert decided.status == "accepted"
    assert decided.result_claim is not None
    assert service.session.get(Claim, decided.result_claim) is not None

    rejected = service.submit_suggestion(
        context, payload=payload, producer="structural_pass", producer_meta={"rule": "test"}
    )
    service.session.commit()
    rejected = service.review_suggestion(
        context, suggestion_id=rejected.suggestion_id, decision="rejected"
    )
    service.session.commit()
    assert rejected.result_claim is None


@pytest.mark.integration
def test_register_evidence_and_custody_outbox(seeded: dict[str, object]) -> None:
    service: ActionService = seeded["service"]  # type: ignore[assignment]
    context: ActionContext = seeded["context"]  # type: ignore[assignment]
    case = service.open_case(context, title="Evidence case", purpose="test")
    service.session.commit()
    evidence = service.register_evidence(
        context, description="sealed notebook", case_id=case.case_id
    )
    service.session.commit()
    assert service.session.get(EvidenceItem, evidence.evidence_id) is not None

    first_at = datetime.now(timezone.utc)
    first = service.add_custody_event(
        context,
        evidence_id=evidence.evidence_id,
        to_actor="officer-1",
        occurred_at=first_at,
        purpose="intake",
    )
    service.session.commit()
    second = service.add_custody_event(
        context,
        evidence_id=evidence.evidence_id,
        from_actor="officer-1",
        to_actor="lab-1",
        occurred_at=first_at + timedelta(minutes=1),
        purpose="analysis",
    )
    service.session.commit()
    assert (first.seq, second.seq) == (1, 2)
    tuples = service.session.execute(
        sa.select(AuthzOutbox.op, AuthzOutbox.fga_tuple).where(
            AuthzOutbox.fga_tuple["object"].astext
            == f"evidence_item:{evidence.evidence_id}"
        )
    ).all()
    assert ("delete", {
        "user": "user:officer-1",
        "relation": "custodian",
        "object": f"evidence_item:{evidence.evidence_id}",
    }) in tuples
    assert any(op == "write" and tuple_["relation"] == "case" for op, tuple_ in tuples)


@pytest.mark.integration
def test_open_case_and_assign_member_outbox(seeded: dict[str, object]) -> None:
    service: ActionService = seeded["service"]  # type: ignore[assignment]
    context: ActionContext = seeded["context"]  # type: ignore[assignment]
    case = service.open_case(
        context, title="Case assignment", purpose="investigation", handling_code="restricted"
    )
    service.session.commit()
    member = service.assign_case_member(
        context, case_id=case.case_id, user_id="user-7", role="analyst"
    )
    service.session.commit()
    assert service.session.get(CaseMember, (case.case_id, "user-7")) == member
    tuple_ = service.session.scalar(
        sa.select(AuthzOutbox.fga_tuple)
        .where(AuthzOutbox.fga_tuple["object"].astext == f"case:{case.case_id}")
        .order_by(AuthzOutbox.outbox_id.desc())
    )
    assert tuple_ == {
        "user": "user:user-7",
        "relation": "analyst",
        "object": f"case:{case.case_id}",
    }

    removed = service.remove_case_member(
        context, case_id=case.case_id, user_id="user-7"
    )
    service.session.commit()
    assert removed.role == "analyst"
    assert service.session.get(CaseMember, (case.case_id, "user-7")) is None
    delete_tuple = service.session.scalar(
        sa.select(AuthzOutbox.fga_tuple)
        .where(
            AuthzOutbox.op == "delete",
            AuthzOutbox.fga_tuple["object"].astext == f"case:{case.case_id}",
        )
        .order_by(AuthzOutbox.outbox_id.desc())
    )
    assert delete_tuple == {
        "user": "user:user-7",
        "relation": "analyst",
        "object": f"case:{case.case_id}",
    }


@pytest.mark.integration
def test_action_write_rolls_back_when_audit_append_fails(
    seeded: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    import aegis.actions.service as service_module

    service: ActionService = seeded["service"]  # type: ignore[assignment]
    context: ActionContext = seeded["context"]  # type: ignore[assignment]
    case_id = new_id("cas")

    def fail_audit(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated audit failure")

    monkeypatch.setattr(service_module, "append_audit", fail_audit)
    with pytest.raises(RuntimeError, match="simulated audit failure"):
        service.open_case(
            context, case_id=case_id, title="Must roll back", purpose="atomicity test"
        )
    assert service.session.get(CaseFile, case_id) is None


@pytest.mark.integration
def test_every_successful_action_leaves_chain_valid(action_engine: sa.Engine) -> None:
    with Session(action_engine) as session:
        assert verify(session).valid
        assert session.scalar(sa.select(sa.func.count()).select_from(AuditLog)) > 0
