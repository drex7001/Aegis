"""Audit query routes (auditor only; querying audit is itself audited)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from aegis.api.deps import AuthContext, DbSession, authorize
from aegis.api.pagination import decode_cursor, encode_cursor, page_limit, split_page
from aegis.api.schemas import AuditOut, AuditPageOut
from aegis.audit import verify
from aegis.store import AuditLog

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=AuditPageOut, operation_id="queryAudit")
def query_audit(
    session: DbSession,
    actor: Annotated[str | None, Query()] = None,
    case: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1)] = 50,
    auth: AuthContext = Depends(authorize("auditor", purpose_required=True)),
) -> AuditPageOut:
    limit = page_limit(limit)
    key = decode_cursor(cursor, "audit", 1)
    query = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit + 1)
    if key is not None:
        try:
            audit_id = int(key[0])
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, "invalid cursor") from exc
        query = query.where(AuditLog.id < audit_id)
    if actor is not None:
        query = query.where(AuditLog.actor == actor)
    if case is not None:
        query = query.where(AuditLog.case_id == case)
    if action is not None:
        query = query.where(AuditLog.action == action)
    if from_ is not None:
        query = query.where(AuditLog.at >= from_)
    if to is not None:
        query = query.where(AuditLog.at <= to)
    rows = list(session.scalars(query))
    # the authorize gate already audited this sensitive read (purpose captured)
    items, next_cursor = split_page(
        rows,
        limit,
        lambda row: encode_cursor("audit", [row.id]),
    )
    return AuditPageOut(
        items=[AuditOut.model_validate(row) for row in items],
        next_cursor=next_cursor,
    )


@router.post("/audit/verify", operation_id="verifyAudit")
def verify_audit(
    session: DbSession,
    auth: AuthContext = Depends(authorize("auditor", "admin")),
) -> dict:
    report = verify(session)
    return {
        "valid": report.valid,
        "checked": report.checked,
        "failed_id": report.failed_id,
        "reason": report.reason,
    }
