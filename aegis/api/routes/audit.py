"""Audit query routes (auditor only; querying audit is itself audited)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from aegis.api.deps import AuthContext, DbSession, authorize
from aegis.api.schemas import AuditOut
from aegis.audit import append as append_audit, verify
from aegis.store import AuditLog

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=list[AuditOut], operation_id="queryAudit")
def query_audit(
    session: DbSession,
    actor: Annotated[str | None, Query()] = None,
    case: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(le=1000)] = 200,
    auth: AuthContext = Depends(authorize("auditor", purpose_required=True)),
) -> list[AuditLog]:
    query = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
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
    return rows


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
