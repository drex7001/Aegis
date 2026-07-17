"""Evidence & custody routes (spec 06 Evidence & custody)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from aegis.actions import ActionContext, ActionService
from aegis.api.deps import (
    AuthContext,
    DbSession,
    OntologyDep,
    authorize,
    fga_check_or_404,
    get_fga,
)
from aegis.api.schemas import CustodyEventIn, EvidenceIn, EvidenceOut
from aegis.store import CustodyEvent, EvidenceItem

router = APIRouter(tags=["evidence"])


@router.post("/evidence", response_model=EvidenceOut, status_code=201)
def register_evidence(
    body: EvidenceIn,
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize("investigator", "evidence_officer")),
) -> EvidenceItem:
    if body.case_id is not None:
        fga_check_or_404(fga, auth.user, "can_edit", f"case:{body.case_id}")
    service = ActionService(session, ontology)
    row = service.register_evidence(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose),
        **body.model_dump(),
    )
    session.commit()
    return row


@router.get("/evidence/{evidence_id}", response_model=dict)
def get_evidence(
    evidence_id: str,
    session: DbSession,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize()),
) -> dict:
    fga_check_or_404(fga, auth.user, "can_view", f"evidence_item:{evidence_id}")
    item = session.get(EvidenceItem, evidence_id)
    if item is None:
        raise HTTPException(404, "not found")
    custody = session.scalars(
        select(CustodyEvent)
        .where(CustodyEvent.evidence_id == evidence_id)
        .order_by(CustodyEvent.seq)
    ).all()
    return {
        "evidence": EvidenceOut.model_validate(item).model_dump(),
        "custody_chain": [
            {
                "seq": e.seq,
                "from_actor": e.from_actor,
                "to_actor": e.to_actor,
                "occurred_at": e.occurred_at.isoformat(),
                "purpose": e.purpose,
                "hash_checked": e.hash_checked,
            }
            for e in custody
        ],
    }


@router.post("/evidence/{evidence_id}/custody-events", status_code=201)
def add_custody_event(
    evidence_id: str,
    body: CustodyEventIn,
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize()),
) -> dict:
    fga_check_or_404(fga, auth.user, "can_transfer", f"evidence_item:{evidence_id}")
    service = ActionService(session, ontology)
    row = service.add_custody_event(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose),
        evidence_id=evidence_id,
        **body.model_dump(),
    )
    session.commit()
    return {"evidence_id": row.evidence_id, "seq": row.seq, "to_actor": row.to_actor}
