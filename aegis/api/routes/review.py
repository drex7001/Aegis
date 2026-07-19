"""Review-queue routes (Article VII, spec 06)."""

from __future__ import annotations

from typing import Annotated

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, not_, or_, select

from aegis.actions import ActionContext, ActionService
from aegis.api.deps import AuthContext, DbSession, OntologyDep, authorize
from aegis.api.pagination import decode_cursor, encode_cursor, page_limit, split_page
from aegis.api.schemas import AcceptIn, RejectIn, SuggestionOut, SuggestionPageOut
from aegis.authz.filters import (
    allowed_handling_codes,
    forbidden_field_predicates,
    member_case_ids,
)
from aegis.store import ReviewQueue, SourceRecord

router = APIRouter(tags=["review-queue"])


def _visibility_conditions(session, ontology, auth: AuthContext):
    allowed = allowed_handling_codes(ontology, auth.user.clearance)
    cases = member_case_ids(session, auth.user)
    case_scope = ReviewQueue.case_id.is_(None)
    if cases:
        case_scope = or_(case_scope, ReviewQueue.case_id.in_(cases))
    conditions = [
        case_scope,
        or_(ReviewQueue.record_id.is_(None), SourceRecord.handling_code.in_(allowed)),
    ]
    forbidden = forbidden_field_predicates(ontology, auth.user.clearance)
    if forbidden:
        predicate = ReviewQueue.payload["predicate"].astext
        conditions.append(or_(predicate.is_(None), not_(predicate.in_(forbidden))))
    return conditions


def _require_visible(session, ontology, auth: AuthContext, suggestion_id: str) -> None:
    visible = session.scalar(
        select(ReviewQueue.suggestion_id)
        .outerjoin(SourceRecord, SourceRecord.record_id == ReviewQueue.record_id)
        .where(
            ReviewQueue.suggestion_id == suggestion_id,
            *_visibility_conditions(session, ontology, auth),
        )
    )
    if visible is None:
        raise HTTPException(404, "not found")


@router.get(
    "/review-queue",
    response_model=SuggestionPageOut,
    operation_id="listSuggestions",
)
def list_suggestions(
    session: DbSession,
    ontology: OntologyDep,
    kind: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    producer: Annotated[str | None, Query()] = None,
    record: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1)] = 50,
    auth: AuthContext = Depends(authorize("analyst")),
) -> SuggestionPageOut:
    limit = page_limit(limit)
    key = decode_cursor(cursor, "review-queue", 2)
    query = (
        select(ReviewQueue)
        .outerjoin(SourceRecord, SourceRecord.record_id == ReviewQueue.record_id)
        .where(*_visibility_conditions(session, ontology, auth))
        .order_by(ReviewQueue.created_at.desc(), ReviewQueue.suggestion_id.desc())
        .limit(limit + 1)
    )
    if key is not None:
        try:
            created_at = datetime.fromisoformat(str(key[0]))
            suggestion_id = str(key[1])
        except ValueError as exc:
            raise HTTPException(422, "invalid cursor") from exc
        query = query.where(
            or_(
                ReviewQueue.created_at < created_at,
                and_(
                    ReviewQueue.created_at == created_at,
                    ReviewQueue.suggestion_id < suggestion_id,
                ),
            )
        )
    if kind is not None:
        query = query.where(ReviewQueue.suggestion_kind == kind)
    if status is not None:
        query = query.where(ReviewQueue.status == status)
    if producer is not None:
        query = query.where(ReviewQueue.producer == producer)
    if record is not None:
        # the envelope carries record_id as a column now — an indexed foreign
        # key rather than a JSON probe into an untyped payload (ADR-031)
        query = query.where(ReviewQueue.record_id == record)
    rows = list(session.scalars(query))
    items, next_cursor = split_page(
        rows,
        limit,
        lambda row: encode_cursor(
            "review-queue", [row.created_at, row.suggestion_id]
        ),
    )
    return SuggestionPageOut(
        items=[SuggestionOut.model_validate(row) for row in items],
        next_cursor=next_cursor,
    )


@router.post(
    "/review-queue/{suggestion_id}/accept",
    response_model=SuggestionOut,
    operation_id="acceptSuggestion",
)
def accept_suggestion(
    suggestion_id: str,
    body: AcceptIn,
    session: DbSession,
    ontology: OntologyDep,
    auth: AuthContext = Depends(authorize("analyst")),
) -> ReviewQueue:
    _require_visible(session, ontology, auth, suggestion_id)
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


@router.post(
    "/review-queue/{suggestion_id}/reject",
    response_model=SuggestionOut,
    operation_id="rejectSuggestion",
)
def reject_suggestion(
    suggestion_id: str,
    body: RejectIn,
    session: DbSession,
    ontology: OntologyDep,
    auth: AuthContext = Depends(authorize("analyst")),
) -> ReviewQueue:
    _require_visible(session, ontology, auth, suggestion_id)
    service = ActionService(session, ontology)
    row = service.review_suggestion(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose),
        suggestion_id=suggestion_id,
        decision="rejected",
        note=body.reason,
    )
    session.commit()
    return row
