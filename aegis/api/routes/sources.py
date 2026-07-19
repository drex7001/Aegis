"""Sources & source-record routes (spec 06 Sources & ingestion)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select

from aegis.actions import ActionContext, new_id
from aegis.api.deps import AuthContext, DbSession, OntologyDep, authorize
from aegis.api.pagination import decode_cursor, encode_cursor, page_limit, split_page
from aegis.api.schemas import SourceIn, SourceOut, SourcePageOut, SourceRecordOut
from aegis.audit import append as append_audit
from aegis.authz.filters import allowed_handling_codes
from aegis.store import Source, SourceRecord

router = APIRouter(tags=["sources"])


@router.post(
    "/sources", response_model=SourceOut, status_code=201, operation_id="createSource"
)
def create_source(
    body: SourceIn,
    session: DbSession,
    ontology: OntologyDep,
    auth: AuthContext = Depends(authorize("analyst")),
) -> Source:
    if body.source_type not in ontology.source_types:
        raise HTTPException(422, f"unknown source_type {body.source_type!r}")
    row = Source(source_id=new_id("src"), **body.model_dump())
    session.add(row)
    append_audit(
        session,
        actor=auth.user.sub,
        purpose=auth.purpose,
        action="create_source",
        resource_type="source",
        resource_id=row.source_id,
        decision="allow",
        detail={"name": body.name, "source_type": body.source_type},
    )
    session.commit()
    return row


@router.get(
    "/sources", response_model=SourcePageOut, operation_id="listSources"
)
def list_sources(
    session: DbSession,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1)] = 50,
    auth: AuthContext = Depends(authorize("analyst")),
) -> SourcePageOut:
    limit = page_limit(limit)
    key = decode_cursor(cursor, "sources", 2)
    query = select(Source).order_by(Source.created_at, Source.source_id).limit(limit + 1)
    if key is not None:
        try:
            created_at = datetime.fromisoformat(str(key[0]))
            source_id = str(key[1])
        except ValueError as exc:
            raise HTTPException(422, "invalid cursor") from exc
        query = query.where(
            or_(
                Source.created_at > created_at,
                and_(Source.created_at == created_at, Source.source_id > source_id),
            )
        )
    rows = list(session.scalars(query))
    items, next_cursor = split_page(
        rows,
        limit,
        lambda row: encode_cursor("sources", [row.created_at, row.source_id]),
    )
    return SourcePageOut(
        items=[SourceOut.model_validate(row) for row in items],
        next_cursor=next_cursor,
    )


@router.get(
    "/source-records/{record_id}",
    response_model=SourceRecordOut,
    operation_id="getSourceRecord",
)
def get_source_record(
    record_id: str,
    session: DbSession,
    ontology: OntologyDep,
    auth: AuthContext = Depends(authorize()),
) -> SourceRecord:
    record = session.get(SourceRecord, record_id)
    # handling floor applies to provenance too (no existence leaks)
    if record is None or record.handling_code not in allowed_handling_codes(
        ontology, auth.user.clearance
    ):
        raise HTTPException(404, "not found")
    return record


@router.post(
    "/source-records/{record_id}/release",
    response_model=SourceRecordOut,
    operation_id="releaseSourceRecord",
)
def release_record(
    record_id: str,
    session: DbSession,
    ontology: OntologyDep,
    note: str = "",
    auth: AuthContext = Depends(authorize("supervisor")),
) -> SourceRecord:
    from aegis.actions import ActionService

    service = ActionService(session, ontology)
    row = service.release_quarantine(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose),
        record_id=record_id,
        note=note or "released via API",
    )
    session.commit()
    return row
