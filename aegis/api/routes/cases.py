"""Case routes (spec 06 §2.5, spec 09 §2.4).

Two rules govern every read here and are worth stating once:

* **Non-membership is 404, never 403.** `fga_check_or_404` is the only
  acceptable gate on a case-scoped read; a 403 tells the caller the case exists.
* **No list route returns a total.** A count over an authorization-filtered
  collection is an existence leak (spec 06 §4 default 4), and ordering is by
  primary key so hidden rows cannot be detected as gaps in a ranking.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select

from aegis.actions import ActionContext, ActionService
from aegis.actions.service import CASE_MEMBER_RELATIONS
from aegis.api.deps import (
    AuthContext,
    DbSession,
    FGADep,
    OntologyDep,
    authorize,
    fga_check_or_404,
    get_fga,
)
from aegis.api.schemas import (
    CaseCloseIn,
    CaseIn,
    CaseMemberIn,
    CaseMemberOut,
    CaseOut,
    CasePageOut,
    CaseReferenceIn,
    CaseReferenceOut,
)
from aegis.api.pagination import decode_cursor, encode_cursor, page_limit, split_page
from aegis.authz.filters import member_case_ids
from aegis.authz.outbox import delete_inline_best_effort
from aegis.store import CaseFile, CaseMember, CaseReference

router = APIRouter(tags=["cases"])


@router.post(
    "/cases", response_model=CaseOut, status_code=201, operation_id="openCase"
)
def open_case(
    body: CaseIn,
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(
        authorize("analyst", "investigator", purpose_required=True)
    ),
) -> CaseFile:
    service = ActionService(session, ontology)
    row = service.open_case(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose, roles=auth.user.roles),
        title=body.title,
        purpose=body.purpose,
        handling_code=body.handling_code,
    )
    # The opener becomes a supervisor of the case so they can view/manage it.
    service.assign_case_member(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose, roles=auth.user.roles),
        case_id=row.case_id,
        user_id=auth.user.sub,
        role="supervisor",
    )
    session.commit()
    return row


@router.get("/cases", response_model=CasePageOut, operation_id="listCases")
def list_cases(
    session: DbSession,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1)] = 50,
    auth: AuthContext = Depends(authorize()),
) -> CasePageOut:
    """The caller's own cases.

    Built from canonical `case_member` rows rather than from every case filtered
    afterwards — the list is *derived* from what the caller may see, which is
    the same construction the object view's case list uses (spec 09 §6.5) and
    the reason there is no timing signal to measure. `case_member` is the fact
    and OpenFGA is its projection (ADR-014), so reading it here is not a bypass.

    Ordered by `case_id`, never by activity: a ranking is a place for a hidden
    row to leave a gap.
    """
    limit = page_limit(limit)
    key = decode_cursor(cursor, "cases", 1)
    mine = member_case_ids(session, auth.user)
    if not mine:
        return CasePageOut(items=[], next_cursor=None)
    query = (
        select(CaseFile)
        .where(CaseFile.case_id.in_(mine))
        .order_by(CaseFile.case_id)
        .limit(limit + 1)
    )
    if key is not None:
        query = query.where(CaseFile.case_id > str(key[0]))
    rows = list(session.scalars(query))
    items, next_cursor = split_page(
        rows, limit, lambda row: encode_cursor("cases", [row.case_id])
    )
    return CasePageOut(
        items=[CaseOut.model_validate(row) for row in items], next_cursor=next_cursor
    )


@router.get("/cases/{case_id}", response_model=CaseOut, operation_id="getCase")
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


@router.post(
    "/cases/{case_id}/close", response_model=CaseOut, operation_id="closeCase"
)
def close_case(
    case_id: str,
    body: CaseCloseIn,
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize("supervisor")),
) -> CaseFile:
    """Close a case. Never deletes: `status` moves and `closed_at` is set."""
    fga_check_or_404(fga, auth.user, "can_approve", f"case:{case_id}")
    row = ActionService(session, ontology).close_case(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose, roles=auth.user.roles),
        case_id=case_id,
        reason=body.reason,
    )
    session.commit()
    return row


@router.get(
    "/cases/{case_id}/members",
    response_model=list[CaseMemberOut],
    operation_id="listCaseMembers",
)
def list_members(
    case_id: str,
    session: DbSession,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize()),
) -> list[CaseMember]:
    fga_check_or_404(fga, auth.user, "can_view", f"case:{case_id}")
    return list(
        session.scalars(
            select(CaseMember)
            .where(CaseMember.case_id == case_id)
            .order_by(CaseMember.user_id)
        )
    )


@router.get(
    "/cases/{case_id}/references",
    response_model=list[CaseReferenceOut],
    operation_id="listCaseReferences",
)
def list_references(
    case_id: str,
    session: DbSession,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize()),
) -> list[CaseReference]:
    """What this investigation refers to — attached, not detached.

    A reference grants nothing (ADR-044), so this returns the links; whether
    the caller can read a target is answered by that target's own route, which
    applies `claim_filters` like every other read.
    """
    fga_check_or_404(fga, auth.user, "can_view", f"case:{case_id}")
    return list(
        session.scalars(
            select(CaseReference)
            .where(
                CaseReference.case_id == case_id,
                CaseReference.detached_at.is_(None),
            )
            .order_by(CaseReference.target_type, CaseReference.target_id)
        )
    )


@router.post(
    "/cases/{case_id}/references",
    response_model=CaseReferenceOut,
    status_code=201,
    operation_id="linkCaseReference",
)
def link_reference(
    case_id: str,
    body: CaseReferenceIn,
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize("analyst", "investigator")),
) -> CaseReference:
    fga_check_or_404(fga, auth.user, "can_edit", f"case:{case_id}")
    row = ActionService(session, ontology).link_case_reference(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose, roles=auth.user.roles),
        case_id=case_id,
        target_type=body.target_type,
        target_id=body.target_id,
        note=body.note,
    )
    session.commit()
    return row


@router.delete(
    "/cases/{case_id}/references/{target_type}/{target_id}",
    response_model=CaseReferenceOut,
    operation_id="unlinkCaseReference",
)
def unlink_reference(
    case_id: str,
    target_type: str,
    target_id: str,
    reason: Annotated[str, Query(min_length=1)],
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize("analyst", "investigator")),
) -> CaseReference:
    """Detach a reference. Tombstoned, never deleted — somebody once thought
    these two were connected, and that is a fact the case may need to explain."""
    fga_check_or_404(fga, auth.user, "can_edit", f"case:{case_id}")
    row = ActionService(session, ontology).unlink_case_reference(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose, roles=auth.user.roles),
        case_id=case_id,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
    )
    session.commit()
    return row


@router.post(
    "/cases/{case_id}/members", status_code=201, operation_id="addCaseMember"
)
def add_member(
    case_id: str,
    body: CaseMemberIn,
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize("supervisor")),
) -> dict:
    fga_check_or_404(fga, auth.user, "can_approve", f"case:{case_id}")
    existing = session.get(CaseMember, (case_id, body.user_id))
    revoked_tuple = None
    if existing is not None and existing.role != body.role:
        revoked_tuple = {
            "user": f"user:{body.user_id}",
            "relation": CASE_MEMBER_RELATIONS[existing.role],
            "object": f"case:{case_id}",
        }
    service = ActionService(session, ontology)
    row = service.assign_case_member(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose, roles=auth.user.roles),
        case_id=case_id,
        user_id=body.user_id,
        role=body.role,
    )
    session.commit()
    if revoked_tuple is not None:
        delete_inline_best_effort(fga, revoked_tuple)
    return {"case_id": row.case_id, "user_id": row.user_id, "role": row.role}


@router.delete(
    "/cases/{case_id}/members/{user_id}",
    status_code=204,
    response_class=Response,
    operation_id="removeCaseMember",
)
def remove_member(
    case_id: str,
    user_id: str,
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize("supervisor")),
) -> Response:
    fga_check_or_404(fga, auth.user, "can_approve", f"case:{case_id}")
    member = session.get(CaseMember, (case_id, user_id))
    if member is None:
        raise HTTPException(404, "not found")
    revoked_tuple = {
        "user": f"user:{user_id}",
        "relation": CASE_MEMBER_RELATIONS[member.role],
        "object": f"case:{case_id}",
    }
    ActionService(session, ontology).remove_case_member(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose, roles=auth.user.roles),
        case_id=case_id,
        user_id=user_id,
    )
    session.commit()
    delete_inline_best_effort(fga, revoked_tuple)
    return Response(status_code=204)
