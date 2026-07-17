"""Case routes (spec 06 Cases)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from aegis.actions import ActionContext, ActionService
from aegis.api.deps import (
    AuthContext,
    DbSession,
    OntologyDep,
    authorize,
    fga_check_or_404,
    get_fga,
)
from aegis.api.schemas import CaseIn, CaseMemberIn, CaseOut
from aegis.store import CaseFile

router = APIRouter(tags=["cases"])


@router.post("/cases", response_model=CaseOut, status_code=201)
def open_case(
    body: CaseIn,
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize("analyst", "investigator")),
) -> CaseFile:
    service = ActionService(session, ontology)
    row = service.open_case(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose),
        title=body.title,
        purpose=body.purpose,
        handling_code=body.handling_code,
    )
    # The opener becomes a supervisor of the case so they can view/manage it.
    service.assign_case_member(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose),
        case_id=row.case_id,
        user_id=auth.user.sub,
        role="supervisor",
    )
    session.commit()
    return row


@router.get("/cases/{case_id}", response_model=CaseOut)
def get_case(
    case_id: str,
    session: DbSession,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize()),
) -> CaseFile:
    fga_check_or_404(fga, auth.user, "can_view", f"case:{case_id}")
    case = session.get(CaseFile, case_id)
    if case is None:
        from fastapi import HTTPException

        raise HTTPException(404, "not found")
    return case


@router.post("/cases/{case_id}/members", status_code=201)
def add_member(
    case_id: str,
    body: CaseMemberIn,
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize("supervisor")),
) -> dict:
    fga_check_or_404(fga, auth.user, "can_approve", f"case:{case_id}")
    service = ActionService(session, ontology)
    row = service.assign_case_member(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose),
        case_id=case_id,
        user_id=body.user_id,
        role=body.role,
    )
    session.commit()
    return {"case_id": row.case_id, "user_id": row.user_id, "role": row.role}
