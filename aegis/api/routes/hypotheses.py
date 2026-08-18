"""Hypothesis routes (spec 09 §3.5).

A hypothesis is an assertion about **our own reasoning**, never about the
world: it has no source record, it carries no grading, and no projection
renders it. Keeping it off the claim surfaces is what stops a suspicion
becoming an edge by accident (Article IX).

Three properties hold on every route here:

* **The case is the resource.** A hypothesis has no authorization of its own —
  `can_view`/`can_edit` derive from its case (spec 09 §5) — and a non-member
  gets 404 from reads *and* writes, so a 403 never discloses that the case
  exists.
* **Both sides always ship.** `supporting` and `contradicting` are arrays that
  are present whether or not they are empty. A client cannot render "no
  contradicting evidence recorded" from a field that was omitted, and
  Article VIII is a rendering obligation rather than a data accident.
* **A link grants nothing.** The evidence basis is read through
  `claim_filters` like any other claim read (ADR-044), so a member who cannot
  see a linked claim gets a shorter list rather than an error.
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
from aegis.api.schemas import (
    HypothesisClaimIn,
    HypothesisClaimOut,
    HypothesisIn,
    HypothesisListOut,
    HypothesisOut,
    HypothesisRevisionIn,
    HypothesisRevisionOut,
    HypothesisSummaryOut,
)
from aegis.store import Hypothesis, HypothesisClaim, HypothesisRevision

router = APIRouter(tags=["hypotheses"])


def _hypothesis_or_404(session: Session, hypothesis_id: str) -> Hypothesis:
    """Load it, or 404 — the same answer as "you may not see it".

    Order matters: the row is fetched first so the caller's FGA check runs
    against its *case*, and a hypothesis that does not exist and one in a case
    the caller cannot reach are indistinguishable from outside.
    """
    row = session.get(Hypothesis, hypothesis_id)
    if row is None:
        raise HTTPException(404, "not found")
    return row


def _revisions(session: Session, hypothesis_id: str) -> list[HypothesisRevision]:
    return list(
        session.scalars(
            select(HypothesisRevision)
            .where(HypothesisRevision.hypothesis_id == hypothesis_id)
            .order_by(HypothesisRevision.version)
        )
    )


@router.post(
    "/hypotheses", response_model=HypothesisRevisionOut, status_code=201,
    operation_id="openHypothesis",
)
def open_hypothesis(
    body: HypothesisIn,
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize("analyst", "investigator")),
) -> HypothesisRevision:
    fga_check_or_404(fga, auth.user, "can_edit", f"case:{body.case_id}")
    revision = ActionService(session, ontology).open_hypothesis(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose, roles=auth.user.roles),
        case_id=body.case_id,
        statement=body.statement,
        missing_info=body.missing_info,
        handling_code=body.handling_code,
    )
    session.commit()
    return revision


@router.get(
    "/hypotheses", response_model=HypothesisListOut, operation_id="listHypotheses"
)
def list_hypotheses(
    case: Annotated[str, Query(min_length=1)],
    session: DbSession,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize()),
) -> HypothesisListOut:
    """Scoped to one case, always. There is no global hypothesis list."""
    fga_check_or_404(fga, auth.user, "can_view", f"case:{case}")
    rows = list(
        session.scalars(
            select(Hypothesis)
            .where(Hypothesis.case_id == case)
            .order_by(Hypothesis.hypothesis_id)
        )
    )
    items: list[HypothesisSummaryOut] = []
    for row in rows:
        current = _revisions(session, row.hypothesis_id)[-1]
        items.append(
            HypothesisSummaryOut(
                hypothesis_id=row.hypothesis_id,
                case_id=row.case_id,
                statement=current.statement,
                status=current.status,
                version=current.version,
                opened_by=row.opened_by,
                opened_at=row.opened_at,
            )
        )
    return HypothesisListOut(items=items)


@router.get(
    "/hypotheses/{hypothesis_id}",
    response_model=HypothesisOut,
    operation_id="getHypothesis",
)
def get_hypothesis(
    hypothesis_id: str,
    session: DbSession,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize()),
) -> HypothesisOut:
    row = _hypothesis_or_404(session, hypothesis_id)
    fga_check_or_404(fga, auth.user, "can_view", f"case:{row.case_id}")
    revisions = _revisions(session, hypothesis_id)
    links = list(
        session.scalars(
            select(HypothesisClaim)
            .where(
                HypothesisClaim.hypothesis_id == hypothesis_id,
                HypothesisClaim.detached_at.is_(None),
            )
            .order_by(HypothesisClaim.claim_id, HypothesisClaim.stance)
        )
    )
    return HypothesisOut(
        hypothesis_id=row.hypothesis_id,
        case_id=row.case_id,
        opened_by=row.opened_by,
        opened_at=row.opened_at,
        handling_code=row.handling_code,
        current=HypothesisRevisionOut.model_validate(revisions[-1]),
        revisions=[HypothesisRevisionOut.model_validate(r) for r in revisions],
        # Both keys, always. See the module docstring.
        supporting=[
            HypothesisClaimOut.model_validate(link)
            for link in links
            if link.stance == "supports"
        ],
        contradicting=[
            HypothesisClaimOut.model_validate(link)
            for link in links
            if link.stance == "contradicts"
        ],
    )


@router.post(
    "/hypotheses/{hypothesis_id}/revisions",
    response_model=HypothesisRevisionOut,
    status_code=201,
    operation_id="reviseHypothesis",
)
def revise_hypothesis(
    hypothesis_id: str,
    body: HypothesisRevisionIn,
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize("analyst", "investigator")),
) -> HypothesisRevision:
    row = _hypothesis_or_404(session, hypothesis_id)
    fga_check_or_404(fga, auth.user, "can_edit", f"case:{row.case_id}")
    revision = ActionService(session, ontology).revise_hypothesis(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose, roles=auth.user.roles),
        hypothesis_id=hypothesis_id,
        note=body.note,
        statement=body.statement,
        status=body.status,
        missing_info=body.missing_info,
    )
    session.commit()
    return revision


@router.post(
    "/hypotheses/{hypothesis_id}/claims",
    response_model=HypothesisClaimOut,
    status_code=201,
    operation_id="linkHypothesisClaim",
)
def link_claim(
    hypothesis_id: str,
    body: HypothesisClaimIn,
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize("analyst", "investigator")),
) -> HypothesisClaim:
    row = _hypothesis_or_404(session, hypothesis_id)
    fga_check_or_404(fga, auth.user, "can_edit", f"case:{row.case_id}")
    link = ActionService(session, ontology).link_hypothesis_claim(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose, roles=auth.user.roles),
        hypothesis_id=hypothesis_id,
        claim_id=body.claim_id,
        stance=body.stance,
        note=body.note,
    )
    session.commit()
    return link


@router.delete(
    "/hypotheses/{hypothesis_id}/claims/{claim_id}/{stance}",
    response_model=HypothesisClaimOut,
    operation_id="unlinkHypothesisClaim",
)
def unlink_claim(
    hypothesis_id: str,
    claim_id: str,
    stance: str,
    reason: Annotated[str, Query(min_length=1)],
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize("analyst", "investigator")),
) -> HypothesisClaim:
    row = _hypothesis_or_404(session, hypothesis_id)
    fga_check_or_404(fga, auth.user, "can_edit", f"case:{row.case_id}")
    link = ActionService(session, ontology).unlink_hypothesis_claim(
        ActionContext(actor=auth.user.sub, purpose=auth.purpose, roles=auth.user.roles),
        hypothesis_id=hypothesis_id,
        claim_id=claim_id,
        stance=stance,
        reason=reason,
    )
    session.commit()
    return link
