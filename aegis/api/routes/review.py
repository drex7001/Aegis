"""Review-queue routes (Article VII, spec 06)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from aegis.actions import ActionContext, ActionService
from aegis.api.deps import AuthContext, DbSession, OntologyDep, authorize
from aegis.api.schemas import AcceptIn, RejectIn, SuggestionOut
from aegis.store import ReviewQueue

router = APIRouter(tags=["review-queue"])


@router.get("/review-queue", response_model=list[SuggestionOut])
def list_suggestions(
    session: DbSession,
    status: Annotated[str | None, Query()] = None,
    producer: Annotated[str | None, Query()] = None,
    record: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=500)] = 100,
    auth: AuthContext = Depends(authorize("analyst")),
) -> list[ReviewQueue]:
    query = select(ReviewQueue).order_by(ReviewQueue.created_at.desc()).limit(limit)
    if status is not None:
        query = query.where(ReviewQueue.status == status)
    if producer is not None:
        query = query.where(ReviewQueue.producer == producer)
    if record is not None:
        query = query.where(ReviewQueue.payload["record_id"].astext == record)
    return list(session.scalars(query))


@router.post("/review-queue/{suggestion_id}/accept", response_model=SuggestionOut)
def accept_suggestion(
    suggestion_id: str,
    body: AcceptIn,
    session: DbSession,
    ontology: OntologyDep,
    auth: AuthContext = Depends(authorize("analyst")),
) -> ReviewQueue:
    service = ActionService(session, ontology)
    row = service.review_suggestion(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose),
        suggestion_id=suggestion_id,
        decision="accepted",
        edits=body.edits,
        note=body.note,
    )
    session.commit()
    return row


@router.post("/review-queue/{suggestion_id}/reject", response_model=SuggestionOut)
def reject_suggestion(
    suggestion_id: str,
    body: RejectIn,
    session: DbSession,
    ontology: OntologyDep,
    auth: AuthContext = Depends(authorize("analyst")),
) -> ReviewQueue:
    service = ActionService(session, ontology)
    row = service.review_suggestion(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose),
        suggestion_id=suggestion_id,
        decision="rejected",
        note=body.reason,
    )
    session.commit()
    return row
