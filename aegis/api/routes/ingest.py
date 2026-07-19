"""Ingestion routes: raw landing, derivatives, extraction triggers (spec 04, T23a).

**Landing and extraction run synchronously.** That is a decision, not a
default. A job queue buys asynchrony at the cost of a status model, a worker
deployment and a whole class of "stuck job" failures, and it buys nothing an
operator can feel until the work is slow enough to outlast a request. What
keeps synchronous honest is a bound, and there are two, for two different
reasons: ``ingest_max_bytes`` refuses a body we will not buffer (transport),
and ``ingest_oversize_bytes`` quarantines an artifact that lands but should not
be read yet (governance, spec 04 §3). When the corpus outgrows them, the
trigger to revisit is the connector/watch-folder path in plan §2 — a scheduled
poll has no request to hold open, so it is where a job model actually earns
its complexity.

Every route here is gated and audited. Landing itself audits inside
:func:`aegis.ingestion.land_bytes`; extraction audits here, because "who ran
which producer over what" is the question Article VII makes someone answer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import and_, or_, select

from aegis.api.deps import AuthContext, DbSession, OntologyDep, VaultDep, authorize
from aegis.api.pagination import decode_cursor, encode_cursor, page_limit, split_page
from aegis.api.schemas import (
    DerivativeOut,
    ExtractIn,
    ExtractionOut,
    LandingOut,
    LandTextIn,
    SourceRecordOut,
    SourceRecordPageOut,
)
from aegis.audit import append as append_audit
from aegis.authz.filters import allowed_handling_codes
from aegis.config import get_settings
from aegis.ingestion import (
    IngestionError,
    LandingResult,
    ensure_text,
    land_bytes,
    run_semantic_pass,
    run_structural_pass,
)
from aegis.ontology import Ontology
from aegis.store import Derivative, SourceRecord

router = APIRouter(tags=["ingestion"])

_READ_CHUNK = 1024 * 1024
PASTE_MEDIA_TYPE = "text/plain"


def _check_handling(ontology: Ontology, auth: AuthContext, handling_code: str) -> None:
    """Reject an undeclared code, then one above the caller's clearance.

    Landing above your own clearance is refused rather than allowed-and-hidden:
    it would let an analyst create evidence they cannot afterwards see, read or
    correct, which is a way to lose material, not to protect it.
    """
    if handling_code not in ontology.handling_codes:
        raise HTTPException(422, f"unknown handling code {handling_code!r}")
    if handling_code not in allowed_handling_codes(ontology, auth.user.clearance):
        raise HTTPException(403, f"handling code {handling_code!r} is above your clearance")


def _outcome(result: LandingResult) -> str:
    if not result.created:
        return "already_landed"
    return "quarantined" if result.quarantined else "landed"


def _check_authority_window(start: datetime | None, end: datetime | None) -> None:
    if start is not None and end is not None and end < start:
        raise HTTPException(422, "authority_valid_to must not precede authority_valid_from")


def _landing_response(result: LandingResult) -> LandingOut:
    return LandingOut(
        outcome=_outcome(result), record=SourceRecordOut.model_validate(result.record)
    )


def _visible_record(
    session: DbSession, ontology: Ontology, auth: AuthContext, record_id: str
) -> SourceRecord:
    """404 rather than 403 when the handling code is out of reach (no existence leak)."""
    record = session.get(SourceRecord, record_id)
    if record is None or record.handling_code not in allowed_handling_codes(
        ontology, auth.user.clearance
    ):
        raise HTTPException(404, "not found")
    return record


def _read_bounded(upload: UploadFile, limit: int) -> bytes:
    """Read the body in chunks, aborting past ``limit``.

    Reading first and measuring after would mean the sender chooses how much
    memory we allocate; Content-Length is not checked instead of this because
    it is a claim by the sender, not a fact.

    Synchronous, over the spooled file Starlette has already filled, so this
    route can stay a ``def`` — see the note on the handler.
    """
    chunks: list[bytes] = []
    total = 0
    while chunk := upload.file.read(_READ_CHUNK):
        total += len(chunk)
        if total > limit:
            raise HTTPException(413, f"upload exceeds the {limit}-byte ingest bound")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/ingest/file",
    response_model=LandingOut,
    status_code=201,
    operation_id="landFile",
)
def land_upload(
    session: DbSession,
    ontology: OntologyDep,
    vault: VaultDep,
    file: Annotated[UploadFile, File(description="The artifact to land.")],
    source_id: Annotated[str | None, Form()] = None,
    handling_code: Annotated[str, Form()] = "open",
    source_url: Annotated[str | None, Form()] = None,
    collection_policy: Annotated[str | None, Form()] = None,
    retention_class: Annotated[str | None, Form()] = None,
    authority_ref: Annotated[str | None, Form()] = None,
    authority_valid_from: Annotated[datetime | None, Form()] = None,
    authority_valid_to: Annotated[datetime | None, Form()] = None,
    notes: Annotated[str | None, Form()] = None,
    auth: AuthContext = Depends(authorize("analyst", "investigator")),
) -> LandingOut:
    """Land an uploaded artifact (spec 04 §1 stage 1)."""
    # Deliberately `def`, not `async def`, even though the body arrives as an
    # upload. Landing writes to the vault and the database and both are
    # blocking: on the event loop, one large upload to object storage would
    # stall every other request in the process. A sync handler runs in the
    # threadpool instead — which is what every other route here does — and
    # Starlette has already spooled the body, so nothing needs awaiting.
    _check_handling(ontology, auth, handling_code)
    _check_authority_window(authority_valid_from, authority_valid_to)
    settings = get_settings()
    data = _read_bounded(file, settings.ingest_max_bytes)
    filename = file.filename or "upload"
    try:
        result = land_bytes(
            session,
            vault,
            data=data,
            original_filename=filename,
            operator=auth.user.sub,
            source_id=source_id or None,
            media_type=file.content_type or None,
            source_url=source_url or None,
            collection_policy=collection_policy or None,
            retention_class=retention_class or None,
            authority_ref=authority_ref or None,
            authority_valid_from=authority_valid_from,
            authority_valid_to=authority_valid_to,
            notes=notes or None,
            handling_code=handling_code,
            oversize_bytes=settings.ingest_oversize_bytes,
        )
    except IngestionError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _landing_response(result)


@router.post(
    "/ingest/text",
    response_model=LandingOut,
    status_code=201,
    operation_id="landText",
)
def land_text(
    body: LandTextIn,
    session: DbSession,
    ontology: OntologyDep,
    vault: VaultDep,
    auth: AuthContext = Depends(authorize("analyst", "investigator")),
) -> LandingOut:
    """Land pasted text (spec 04 §1 — "File / paste / curated entry")."""
    _check_handling(ontology, auth, body.handling_code)
    _check_authority_window(body.authority_valid_from, body.authority_valid_to)
    data = body.text.encode("utf-8")
    settings = get_settings()
    if len(data) > settings.ingest_max_bytes:
        raise HTTPException(
            413, f"pasted text exceeds the {settings.ingest_max_bytes}-byte ingest bound"
        )
    try:
        result = land_bytes(
            session,
            vault,
            data=data,
            original_filename=body.filename,
            operator=auth.user.sub,
            source_id=body.source_id,
            media_type=PASTE_MEDIA_TYPE,
            source_url=body.source_url,
            collection_policy=body.collection_policy,
            retention_class=body.retention_class,
            authority_ref=body.authority_ref,
            authority_valid_from=body.authority_valid_from,
            authority_valid_to=body.authority_valid_to,
            notes=body.notes,
            handling_code=body.handling_code,
            source_time=body.source_time,
            oversize_bytes=settings.ingest_oversize_bytes,
        )
    except IngestionError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _landing_response(result)


@router.get(
    "/source-records",
    response_model=SourceRecordPageOut,
    operation_id="listSourceRecords",
)
def list_source_records(
    session: DbSession,
    ontology: OntologyDep,
    status: Annotated[str | None, Query()] = None,
    source_id: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1)] = 50,
    auth: AuthContext = Depends(authorize("analyst")),
) -> SourceRecordPageOut:
    """Landed records the caller may see, newest first.

    Rows above the caller's clearance are absent, not counted (specs/03 §4).
    """
    limit = page_limit(limit)
    key = decode_cursor(cursor, "source-records", 2)
    query = (
        select(SourceRecord)
        .where(
            SourceRecord.handling_code.in_(
                allowed_handling_codes(ontology, auth.user.clearance)
            )
        )
        # received_at ties are broken by the primary key so paging is stable
        # once T24c puts a cursor on it.
        .order_by(SourceRecord.received_at.desc(), SourceRecord.record_id.desc())
        .limit(limit + 1)
    )
    if key is not None:
        try:
            received_at = datetime.fromisoformat(str(key[0]))
            record_id = str(key[1])
        except ValueError as exc:
            raise HTTPException(422, "invalid cursor") from exc
        query = query.where(
            or_(
                SourceRecord.received_at < received_at,
                and_(
                    SourceRecord.received_at == received_at,
                    SourceRecord.record_id < record_id,
                ),
            )
        )
    if status is not None:
        query = query.where(SourceRecord.status == status)
    if source_id is not None:
        query = query.where(SourceRecord.source_id == source_id)
    rows = list(session.scalars(query))
    items, next_cursor = split_page(
        rows,
        limit,
        lambda row: encode_cursor(
            "source-records", [row.received_at, row.record_id]
        ),
    )
    return SourceRecordPageOut(
        items=[SourceRecordOut.model_validate(row) for row in items],
        next_cursor=next_cursor,
    )


@router.get(
    "/source-records/{record_id}/derivatives",
    response_model=list[DerivativeOut],
    operation_id="listDerivatives",
)
def list_derivatives(
    record_id: str,
    session: DbSession,
    ontology: OntologyDep,
    auth: AuthContext = Depends(authorize("analyst")),
) -> list[Derivative]:
    """The transformations recorded for a record (spec 04 §1 stage 3)."""
    record = _visible_record(session, ontology, auth, record_id)
    return list(
        session.scalars(
            select(Derivative)
            .where(Derivative.parent_record == record.record_id)
            .order_by(Derivative.created_at)
        )
    )


@router.post(
    "/source-records/{record_id}/extract",
    response_model=ExtractionOut,
    operation_id="extractRecord",
)
def extract_record(
    record_id: str,
    body: ExtractIn,
    session: DbSession,
    ontology: OntologyDep,
    vault: VaultDep,
    auth: AuthContext = Depends(authorize("analyst")),
) -> ExtractionOut:
    """Run an extraction pass over a record → review-queue suggestions.

    Writes no claims (Article VII): everything produced here waits for
    ``review_suggestion``.
    """
    record = _visible_record(session, ontology, auth, record_id)
    if record.status == "quarantined":
        raise HTTPException(
            409,
            f"record is quarantined ({record.quarantine_reason}); release it before extracting",
        )

    try:
        extraction = ensure_text(session, vault, record=record, operator=auth.user.sub)
        if body.producer == "structural":
            suggestions = run_structural_pass(
                session,
                record=record,
                text=extraction.text,
                actor=auth.user.sub,
                ontology=ontology,
            )
        else:
            suggestions = run_semantic_pass(
                session,
                vault,
                record=record,
                text=extraction.text,
                actor=auth.user.sub,
                ontology=ontology,
                mock=body.mock,
            )
    except IngestionError as exc:
        raise HTTPException(422, str(exc)) from exc

    append_audit(
        session,
        actor=auth.user.sub,
        purpose=auth.purpose,
        action="ingest.extract",
        resource_type="source_record",
        resource_id=record.record_id,
        decision="allow",
        detail={
            "producer": body.producer,
            "mock": body.mock,
            "suggestions_created": len(suggestions),
            "derivative_id": (
                extraction.derivative.derivative_id if extraction.derivative else None
            ),
        },
    )
    session.commit()
    return ExtractionOut(
        record_id=record.record_id,
        producer=body.producer,
        suggestions_created=len(suggestions),
        derivative=(
            DerivativeOut.model_validate(extraction.derivative)
            if extraction.derivative
            else None
        ),
        derivative_created=extraction.created,
    )
