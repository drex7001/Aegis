"""Analytics routes: recording an answer (T72, ADR-057, spec 06 §2.6).

`/v1/graph/expand` and `/v1/graph/paths` **answer a question** and write
nothing. These **record an answer**, and the difference is the whole reason
this module exists separately: a recorded answer outlives the question and gets
forwarded to people who never saw the query, so it needs a manifest, a caveat,
an actor and a purpose. An interactive expansion needs none of those, and
making an analyst mint a finding to look at a neighbourhood would make findings
worthless by volume.

Two rules hold on every route here.

**Purpose is required.** Recording an answer about people is the kind of act
Article X exists to keep a record of, and unlike opening a document there is no
"just looking" version of it.

**A finding is read at the caller's clearance.** `handling_rank` is on the row,
derived from the claims that contributed, so filtering is one comparison rather
than a join back through the run to the evidence.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.analytics.service import AnalyticsError, METRICS, run_metric
from aegis.api.deps import AuthContext, DbSession, FGADep, OntologyDep, authorize, fga_check_or_404
from aegis.api.pagination import page_limit, split_page
from aegis.api.schemas import (
    AnalyticFindingOut,
    AnalyticFindingPageOut,
    AnalyticRunIn,
    AnalyticRunOut,
    AnalyticRunResultOut,
)
from aegis.audit import append as append_audit
from aegis.sets.evaluation import evaluate_version
from aegis.sets.sharing import EVALUATOR, fga_object
from aegis.store import AnalyticFinding, AnalyticRun, ObjectSetVersion

router = APIRouter(tags=["analytics"])


def _run_out(run: AnalyticRun) -> AnalyticRunOut:
    return AnalyticRunOut.model_validate(run, from_attributes=True)


def _finding_out(finding: AnalyticFinding) -> AnalyticFindingOut:
    return AnalyticFindingOut.model_validate(finding, from_attributes=True)


@router.post(
    "/analytics/{metric}",
    response_model=AnalyticRunResultOut,
    operation_id="runAnalytic",
)
def run(
    metric: Annotated[str, Path(description="One of the recorded metrics")],
    body: AnalyticRunIn,
    session: DbSession,
    ontology: OntologyDep,
    fga: FGADep,
    auth: AuthContext = Depends(authorize("analyst", purpose_required=True)),
) -> AnalyticRunResultOut:
    """Run a metric and record what it found.

    When an object set is named, it is **evaluated first under the caller's own
    filters** and the metric runs over those members — so a shared set drives
    an analytic without lending its owner's clearance, and the evaluation
    digest that lands in the manifest is the caller's.
    """
    if metric not in METRICS:
        raise HTTPException(422, f"unknown metric {metric!r}")

    entity_ids = None
    evaluation_digest = None
    version_number = body.object_set_version

    if body.object_set_id:
        # `evaluator`, not `viewer`: driving an analytic from somebody's set is
        # running their question, not reading it (spec 12 §5.2).
        fga_check_or_404(fga, auth.user, EVALUATOR, fga_object(body.object_set_id))
        version = (
            session.get(ObjectSetVersion, (body.object_set_id, version_number))
            if version_number is not None
            else session.scalars(
                select(ObjectSetVersion)
                .where(ObjectSetVersion.set_id == body.object_set_id)
                .order_by(ObjectSetVersion.version.desc())
                .limit(1)
            ).first()
        )
        if version is None:
            raise HTTPException(404, "not found")
        evaluation = evaluate_version(
            session, version, user=auth.user, ontology=ontology
        )
        if evaluation.truncated:
            # A metric over a truncated set is a metric about the truncation,
            # and its caveat does not cover that (spec 12 §2.2).
            raise HTTPException(
                422,
                "the set evaluates to more members than an analytic run may "
                "consume; narrow it before running a metric over it",
            )
        entity_ids = [member.entity_id for member in evaluation.members]
        evaluation_digest = evaluation.evaluation_digest
        version_number = version.version

    try:
        recorded, findings = run_metric(
            session,
            metric=metric,
            user=auth.user,
            ontology=ontology,
            purpose=auth.purpose,
            parameters=body.parameters,
            object_set_id=body.object_set_id,
            object_set_version=version_number,
            evaluation_digest=evaluation_digest,
            entity_ids=entity_ids,
        )
    except AnalyticsError as exc:
        raise HTTPException(422, str(exc)) from exc

    append_audit(
        session,
        actor=auth.user.sub,
        action=f"analytics.{metric}",
        decision="allow",
        purpose=auth.purpose,
        resource_type="analytic_run",
        resource_id=recorded.run_id,
        detail={"findings": len(findings), "object_set_id": body.object_set_id},
    )
    session.commit()
    return AnalyticRunResultOut(
        run=_run_out(recorded), findings=[_finding_out(row) for row in findings]
    )


@router.get(
    "/findings",
    response_model=AnalyticFindingPageOut,
    operation_id="listFindings",
)
def list_findings(
    session: DbSession,
    ontology: OntologyDep,
    run_id: Annotated[str | None, Query(alias="run")] = None,
    finding_type: Annotated[str | None, Query(alias="type")] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1)] = 20,
    auth: AuthContext = Depends(authorize()),
) -> AnalyticFindingPageOut:
    """Findings the caller may read. No total — a count is an existence leak."""
    statement = select(AnalyticFinding).where(
        AnalyticFinding.handling_rank <= auth.user.clearance
    )
    if run_id:
        statement = statement.where(AnalyticFinding.run_id == run_id)
    if finding_type:
        statement = statement.where(AnalyticFinding.finding_type == finding_type)
    if cursor:
        statement = statement.where(AnalyticFinding.finding_id > cursor)

    rows = list(
        session.scalars(
            statement.order_by(AnalyticFinding.finding_id).limit(page_limit(limit) + 1)
        )
    )
    items, next_cursor = split_page(rows, min(page_limit(limit), 50), lambda row: row.finding_id)
    return AnalyticFindingPageOut(
        items=[_finding_out(row) for row in items], next_cursor=next_cursor
    )


@router.get(
    "/findings/{finding_id}",
    response_model=AnalyticRunResultOut,
    operation_id="getFinding",
)
def get_finding(
    finding_id: str,
    session: DbSession,
    auth: AuthContext = Depends(authorize()),
) -> AnalyticRunResultOut:
    """One finding **with its manifest**.

    Together, always. A finding without its manifest is a number whose
    provenance the reader has to go and look for, and the going and looking is
    exactly what does not happen.
    """
    finding = session.get(AnalyticFinding, finding_id)
    if finding is None or finding.handling_rank > auth.user.clearance:
        raise HTTPException(404, "not found")
    recorded = session.get(AnalyticRun, finding.run_id)
    return AnalyticRunResultOut(
        run=_run_out(recorded), findings=[_finding_out(finding)]
    )
