"""Claims routes (spec 06 Knowledge)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from aegis.actions import ActionContext, ActionService
from aegis.api.auth import UserContext
from aegis.api.deps import (
    AuthContext,
    DbSession,
    OntologyDep,
    authorize,
    fga_check_or_404,
    get_fga,
)
from aegis.api.schemas import ClaimIn, ClaimOut, EventIn, EventOut, RelationIn, RetractIn
from aegis.authz.filters import claim_filters
from aegis.store import Claim

router = APIRouter(tags=["claims"])


def _context(auth: AuthContext) -> ActionContext:
    return ActionContext(actor=auth.user.sub, purpose=auth.purpose, roles=auth.user.roles)


def _visible_claim(session, user: UserContext, ontology, claim_id: str, *, as_of=None) -> Claim:
    row = session.scalar(
        select(Claim).where(
            Claim.claim_id == claim_id,
            *claim_filters(session, user, ontology, as_of=as_of),
        )
    )
    if row is None:
        raise HTTPException(404, "not found")  # unauthorized and absent are indistinguishable
    return row


@router.post(
    "/events", response_model=EventOut, status_code=201, operation_id="recordEvent"
)
def record_event(
    body: EventIn,
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize("analyst", "investigator")),
) -> EventOut:
    """Record an occurrence and the claims that assert it, in one transaction.

    Under `/v1/events` rather than a section of its own, and in the claims
    router deliberately: an event *is* claims. The route creates an entity and
    writes every participant, place and summary through the ordinary claim
    validator — there is no second write path around `record_claim`, and no
    canonical event table for one to write to (ADR-046, Article I).
    """
    if body.case_id is not None:
        fga_check_or_404(fga, auth.user, "can_edit", f"case:{body.case_id}")
    service = ActionService(session, ontology)
    payload = body.model_dump(exclude_none=True)
    result = service.record_event(_context(auth), **payload)
    session.commit()
    return EventOut(
        entity_id=result.entity_id,
        entity_type=result.entity_type,
        claim_ids=result.claim_ids,
    )


@router.post(
    "/claims", response_model=ClaimOut, status_code=201, operation_id="createClaim"
)
def create_claim(
    body: ClaimIn,
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize("analyst", "investigator")),
) -> Claim:
    if body.case_id is not None:
        fga_check_or_404(fga, auth.user, "can_edit", f"case:{body.case_id}")
    service = ActionService(session, ontology)
    row = service.record_claim(_context(auth), **body.model_dump(exclude_none=False))
    session.commit()
    return row


@router.post(
    "/claims/{claim_id}/retract",
    response_model=ClaimOut,
    operation_id="retractClaim",
)
def retract_claim(
    claim_id: str,
    body: RetractIn,
    session: DbSession,
    ontology: OntologyDep,
    auth: AuthContext = Depends(authorize("analyst", "supervisor")),
) -> Claim:
    service = ActionService(session, ontology)
    row = service.retract_claim(_context(auth), claim_id=claim_id, reason=body.reason)
    session.commit()
    return row


@router.post(
    "/claims/{claim_id}/relations", status_code=201, operation_id="linkClaim"
)
def link_claim(
    claim_id: str,
    body: RelationIn,
    session: DbSession,
    ontology: OntologyDep,
    auth: AuthContext = Depends(authorize("analyst")),
) -> dict:
    service = ActionService(session, ontology)
    row = service.link_claims(
        _context(auth), from_claim=claim_id, to_claim=body.to_claim, relation=body.relation
    )
    session.commit()
    return {"from_claim": row.from_claim, "to_claim": row.to_claim, "relation": row.relation}


@router.get("/claims/{claim_id}", response_model=ClaimOut, operation_id="getClaim")
def get_claim(
    claim_id: str,
    session: DbSession,
    ontology: OntologyDep,
    as_of: Annotated[datetime | None, Query(alias="asOf")] = None,
    auth: AuthContext = Depends(authorize()),
) -> Claim:
    return _visible_claim(session, auth.user, ontology, claim_id, as_of=as_of)
