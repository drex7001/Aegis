"""Task and lead routes (spec 09 §4).

A *task* is work to do; a *lead* is a line of enquiry worth pursuing. One table,
one `kind`, because the only difference is the word.

**No transition graph and no approval chain.** Any status may follow any other,
and what makes the history answerable is that every change is an audited action
carrying the old value beside the new one. A state machine here would be a rule
with no rule-maker, and plan §2's workflow-engine trigger stays untouched.

Authorization derives from the case, exactly as for hypotheses: a non-member
gets 404 from reads and writes alike.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService
from aegis.api.deps import (
    AuthContext,
    DbSession,
    OntologyDep,
    authorize,
    fga_check_or_404,
    get_fga,
)
from aegis.api.schemas import TaskIn, TaskListOut, TaskOut, TaskUpdateIn
from aegis.store import InvestigationTask

router = APIRouter(tags=["tasks"])


def _task_or_404(session: Session, task_id: str) -> InvestigationTask:
    row = session.get(InvestigationTask, task_id)
    if row is None:
        raise HTTPException(404, "not found")
    return row


@router.post("/tasks", response_model=TaskOut, status_code=201, operation_id="openTask")
def open_task(
    body: TaskIn,
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize("analyst", "investigator")),
) -> InvestigationTask:
    fga_check_or_404(fga, auth.user, "can_edit", f"case:{body.case_id}")
    row = ActionService(session, ontology).open_task(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose, roles=auth.user.roles),
        case_id=body.case_id,
        title=body.title,
        kind=body.kind,
        detail=body.detail,
        owner=body.owner,
        due_date=body.due_date,
        hypothesis_id=body.hypothesis_id,
    )
    session.commit()
    return row


@router.get("/tasks", response_model=TaskListOut, operation_id="listTasks")
def list_tasks(
    case: Annotated[str, Query(min_length=1)],
    session: DbSession,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize()),
) -> TaskListOut:
    """Scoped to one case, always — the case is the resource being authorized."""
    fga_check_or_404(fga, auth.user, "can_view", f"case:{case}")
    rows = list(
        session.scalars(
            select(InvestigationTask)
            .where(InvestigationTask.case_id == case)
            .order_by(InvestigationTask.task_id)
        )
    )
    return TaskListOut(items=[TaskOut.model_validate(row) for row in rows])


@router.post("/tasks/{task_id}", response_model=TaskOut, operation_id="updateTask")
def update_task(
    task_id: str,
    body: TaskUpdateIn,
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize("analyst", "investigator")),
) -> InvestigationTask:
    row = _task_or_404(session, task_id)
    fga_check_or_404(fga, auth.user, "can_edit", f"case:{row.case_id}")
    updated = ActionService(session, ontology).update_task(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose, roles=auth.user.roles),
        task_id=task_id,
        status=body.status,
        owner=body.owner,
        due_date=body.due_date,
        detail=body.detail,
        note=body.note,
    )
    session.commit()
    return updated
