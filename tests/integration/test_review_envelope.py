"""Typed suggestion envelope (T17; ADR-031, spec 02 §3.2).

The Phase-1 queue could *hold* a suggestion that no code path could accept.
These tests pin the two structural rules that fixed it: every row declares its
kind, and acceptance dispatches through the action that kind names.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, ActionValidationError, new_id
from aegis.actions.service import SUGGESTION_KINDS, suggestion_idempotency_key
from aegis.store import Claim, ClaimRelation, Entity, ReviewQueue, Source, SourceRecord
from tests.support.database import migrated_test_engine

pytestmark = pytest.mark.requirement("Article-VII", "Article-VIII", "ADR-031", "T17")


@pytest.fixture(scope="module")
def queue_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


@pytest.fixture()
def seeded(queue_engine: sa.Engine):
    ids = {
        "source": new_id("src"),
        "record": new_id("rec"),
        "entity": new_id("ent"),
    }
    session = Session(queue_engine)
    with session.begin():
        session.add(
            Source(source_id=ids["source"], source_type="open_source", name="T17 queue")
        )
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="d" * 64,
                storage_uri="test://queue",
            )
        )
        session.add(
            Entity(entity_id=ids["entity"], entity_type="person", label="Queue subject")
        )
    service = ActionService(session)
    try:
        yield {
            **ids,
            "session": session,
            "service": service,
            "context": ActionContext(actor="user:analyst", purpose="T17 queue test"),
        }
    finally:
        session.close()


def _claim_draft(seeded, value: str = "Alias one") -> dict:
    return {
        "subject_id": seeded["entity"],
        "predicate": "known_as",
        "object_value": value,
        "assertion_type": "reported",
        "record_id": seeded["record"],
    }


@pytest.mark.integration
def test_every_kind_declares_its_target_action() -> None:
    """The list is closed and code-owned — adding a kind is a mapping change."""
    assert set(SUGGESTION_KINDS) == {
        "claim_draft",
        "identity_candidate",
        "claim_relation",
        "event_draft",
    }
    assert SUGGESTION_KINDS["claim_draft"] == "record_claim"
    assert SUGGESTION_KINDS["identity_candidate"] == "adjudicate_identity"
    assert SUGGESTION_KINDS["claim_relation"] == "link_claims"
    # T58. The travel path's kind: a producer proposes an occurrence and
    # acceptance dispatches to `record_event`, so Article VII holds for events
    # through the mechanism it already held for claims.
    assert SUGGESTION_KINDS["event_draft"] == "record_event"

    # The code-owned list and the ontology's declared enum must agree, or a
    # producer could send a kind nothing can accept — or a kind could exist that
    # no caller is permitted to name (ADR-031 §1).
    from aegis.ontology import load
    from tests.support.paths import ONTOLOGY_PATH

    declared = load(ONTOLOGY_PATH).action("submit_suggestion").parameters["suggestion_kind"]
    assert set(declared.values or ()) == set(SUGGESTION_KINDS)


@pytest.mark.integration
def test_unknown_kind_is_refused_before_it_reaches_the_table(seeded) -> None:
    with pytest.raises(ActionValidationError, match="not a known kind"):
        seeded["service"].submit_suggestion(
            seeded["context"],
            payload=_claim_draft(seeded),
            suggestion_kind="entity_draft",  # retired by ADR-031 §1
            producer="semantic_pass",
            producer_version="mock+abc",
            producer_meta={},
        )


@pytest.mark.integration
def test_claim_draft_acceptance_produces_a_typed_claim_result(seeded) -> None:
    service: ActionService = seeded["service"]
    suggestion = service.submit_suggestion(
        seeded["context"],
        payload=_claim_draft(seeded),
        suggestion_kind="claim_draft",
        producer="semantic_pass",
        producer_version="mock+abc123",
        producer_meta={"model": "mock"},
    )
    seeded["session"].commit()
    assert suggestion.target_action == "record_claim"
    assert suggestion.record_id == seeded["record"]

    decided = service.review_suggestion(
        seeded["context"],
        suggestion_id=suggestion.suggestion_id,
        decision="accepted",
        note="verified against the record",
    )
    seeded["session"].commit()
    assert decided.result_claim_id is not None
    assert decided.result_decision_id is None
    assert decided.result_relation is None
    assert seeded["session"].get(Claim, decided.result_claim_id) is not None


@pytest.mark.integration
def test_claim_relation_acceptance_writes_a_relation_not_a_claim(seeded) -> None:
    """A second kind, dispatched to a different action from the same route."""
    service: ActionService = seeded["service"]
    context: ActionContext = seeded["context"]
    first = service.record_claim(context, **_claim_draft(seeded, "Alias A"))
    second = service.record_claim(context, **_claim_draft(seeded, "Alias B"))
    seeded["session"].commit()

    suggestion = service.submit_suggestion(
        context,
        payload={
            "from_claim": first.claim_id,
            "to_claim": second.claim_id,
            "relation": "contradicts",
        },
        suggestion_kind="claim_relation",
        producer="split-readjudication",
        producer_version="v1",
        producer_meta={"reason": "unanchored claim on split"},
    )
    seeded["session"].commit()
    decided = service.review_suggestion(
        context,
        suggestion_id=suggestion.suggestion_id,
        decision="accepted",
        note="both readings stand",
    )
    seeded["session"].commit()

    assert decided.result_claim_id is None
    assert decided.result_relation == {
        "from_claim": first.claim_id,
        "to_claim": second.claim_id,
        "relation": "contradicts",
    }
    assert (
        seeded["session"].get(
            ClaimRelation, (first.claim_id, second.claim_id, "contradicts")
        )
        is not None
    )


@pytest.mark.integration
def test_identity_candidate_acceptance_names_the_task_that_implements_it(seeded) -> None:
    """No kind may be silently unacceptable — the Phase-1 defect this replaces."""
    service: ActionService = seeded["service"]
    suggestion = service.submit_suggestion(
        seeded["context"],
        payload={"candidate_id": "cnd_x", "kind": "confirm"},
        suggestion_kind="identity_candidate",
        producer="rule:nic",
        producer_version="v1",
        producer_meta={},
    )
    seeded["session"].commit()
    with pytest.raises(ActionValidationError, match="not implemented until T20"):
        service.review_suggestion(
            seeded["context"],
            suggestion_id=suggestion.suggestion_id,
            decision="accepted",
        )
    seeded["session"].rollback()


@pytest.mark.integration
def test_replaying_a_producer_cannot_duplicate_a_suggestion(seeded) -> None:
    """Idempotency is a database guarantee, not a pre-check (spec 04 §5)."""
    service: ActionService = seeded["service"]
    payload = _claim_draft(seeded, "Replayed alias")
    service.submit_suggestion(
        seeded["context"],
        payload=payload,
        producer="structural_pass",
        producer_version="v1",
        producer_meta={},
    )
    seeded["session"].commit()
    with pytest.raises(IntegrityError, match="uq_review_queue_idempotency_key"):
        service.submit_suggestion(
            seeded["context"],
            payload=payload,
            producer="structural_pass",
            producer_version="v1",
            producer_meta={},
        )
    seeded["session"].rollback()


@pytest.mark.integration
def test_accepted_row_must_carry_exactly_one_typed_result(seeded) -> None:
    """The DB owns this: 'accepted' with no result is a lie about what happened."""
    session: Session = seeded["session"]
    session.add(
        ReviewQueue(
            suggestion_id=new_id("sug"),
            suggestion_kind="claim_draft",
            schema_version=1,
            payload={},
            target_action="record_claim",
            producer="test",
            producer_version="v1",
            producer_meta={},
            idempotency_key=new_id("idem"),
            status="accepted",
        )
    )
    with pytest.raises(IntegrityError, match="ck_review_queue_accepted_result"):
        session.flush()
    session.rollback()


@pytest.mark.integration
def test_superseded_and_expired_are_representable(seeded) -> None:
    """Article VIII: output nobody could act on is closed, never deleted."""
    session: Session = seeded["session"]
    for status in ("superseded", "expired"):
        session.add(
            ReviewQueue(
                suggestion_id=new_id("sug"),
                suggestion_kind="claim_draft",
                schema_version=1,
                payload={},
                target_action="record_claim",
                producer="test",
                producer_version="v1",
                producer_meta={},
                idempotency_key=new_id("idem"),
                status=status,
                decision_note="closed by test",
            )
        )
    session.flush()
    kept = session.scalars(
        select(ReviewQueue.status).where(
            ReviewQueue.status.in_(["superseded", "expired"])
        )
    ).all()
    assert sorted(kept) == ["expired", "superseded"]
    session.rollback()
