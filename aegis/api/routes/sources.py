"""Sources & source-record routes (spec 06 Sources & ingestion)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from aegis.actions import ActionContext, new_id
from aegis.api.deps import AuthContext, DbSession, OntologyDep, authorize
from aegis.api.schemas import SourceIn, SourceOut, SourceRecordOut
from aegis.audit import append as append_audit
from aegis.authz.filters import allowed_handling_codes
from aegis.store import Source, SourceRecord

router = APIRouter(tags=["sources"])


@router.post("/sources", response_model=SourceOut, status_code=201)
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


@router.get("/sources", response_model=list[SourceOut])
def list_sources(
    session: DbSession,
    auth: AuthContext = Depends(authorize("analyst")),
) -> list[Source]:
    return list(session.scalars(select(Source).order_by(Source.created_at)))


@router.get("/source-records/{record_id}", response_model=SourceRecordOut)
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


@router.post("/source-records/{record_id}/release", response_model=SourceRecordOut)
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
