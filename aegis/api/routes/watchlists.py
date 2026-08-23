"""Watchlist and alert routes (spec 06 §2.9, spec 12 §11, ADR-056, ADR-060).

Three properties hold here, and each is a decision rather than a convention.

**No route sweeps.** Creating a watchlist does not evaluate it and neither does
reading one. Evaluation is `aegis watchlists evaluate` (ADR-056), so detection
latency is the sweep interval — stated, rather than implied by a hook that fires
somewhere on the write path. What it buys is that a window nobody evaluated is a
visible gap in `analytic_run` rather than silence, which is why `WatchlistOut`
carries `evaluated_through` and lets it be null.

**An alert is read at the caller's clearance**, on its own `handling_rank`,
which is derived from the claims that triggered it. That is one comparison
rather than a join back through the run to the evidence — and it is the reason
alerts are not review-queue rows, which are filtered on the *source record's*
handling code instead (ADR-060). A `sensitive` claim can sit in an `open`
record, so reusing the queue would have keyed alert visibility on the wrong
thing, quietly, in the direction that discloses.

**Triage is audited on every transition**, including the ones that look like
nothing happened, because "who looked at this and decided it was noise" is the
question an alert queue exists to answer.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select

from aegis.api.deps import AuthContext, DbSession, OntologyDep, authorize
from aegis.api.pagination import encode_cursor, page_limit, split_page
from aegis.api.schemas import (
    AlertTriageIn,
    WatchlistAlertOut,
    WatchlistAlertPageOut,
    WatchlistIn,
    WatchlistOut,
    WatchlistPageOut,
)
from aegis.audit import append as append_audit
from aegis.store import AnalyticRun, Watchlist, WatchlistAlert
from aegis.watchlists.service import METHOD, WatchlistError, create_watchlist, triage_alert

router = APIRouter(tags=["watchlists"])


def _watchlist_out(session, watchlist: Watchlist) -> WatchlistOut:
    """The watchlist plus the watermark, read from the runs.

    The watermark is not a column on `watchlist` on purpose: "a window nobody
    evaluated is a gap in the runs" is only literally true when the runs are
    where the answer lives.
    """
    out = WatchlistOut.model_validate(watchlist, from_attributes=True)
    out.evaluated_through = session.scalar(
        select(AnalyticRun.evaluated_through)
        .where(
            AnalyticRun.method == METHOD,
            AnalyticRun.parameters["watchlist_id"].astext == watchlist.watchlist_id,
            AnalyticRun.evaluated_through.is_not(None),
        )
        .order_by(AnalyticRun.evaluated_through.desc())
        .limit(1)
    )
    return out


@router.post(
    "/watchlists",
    response_model=WatchlistOut,
    operation_id="createWatchlist",
)
def create(
    body: WatchlistIn,
    session: DbSession,
    auth: AuthContext = Depends(authorize("analyst")),
) -> WatchlistOut:
    """Save a standing question. **Does not evaluate it** (ADR-056).

    The sweep will run under *this* caller's clearance, snapshotted now, because
    there is no user table to look one up from when the sweep runs offline. It
    therefore cannot exceed what the creator has — but it does not follow them
    down either, which `Watchlist.owner_clearance` states in full.
    """
    try:
        watchlist = create_watchlist(
            session,
            name=body.name,
            set_id=body.set_id,
            rule=body.rule,
            user=auth.user,
            set_version=body.set_version,
        )
    except WatchlistError as exc:
        raise HTTPException(422, str(exc)) from exc

    append_audit(
        session,
        actor=auth.user.sub,
        action="watchlist.create",
        decision="allow",
        purpose=auth.purpose,
        resource_type="watchlist",
        resource_id=watchlist.watchlist_id,
        detail={
            "set_id": watchlist.set_id,
            "set_version": watchlist.set_version,
            "rule": watchlist.rule,
            "rule_version": watchlist.rule_version,
        },
    )
    session.commit()
    return _watchlist_out(session, watchlist)


@router.get(
    "/watchlists",
    response_model=WatchlistPageOut,
    operation_id="listWatchlists",
)
def list_watchlists(
    session: DbSession,
    auth: AuthContext = Depends(authorize("analyst")),
    limit: Annotated[int, Query(le=50, ge=1)] = 25,
    cursor: str | None = None,
) -> WatchlistPageOut:
    """Watchlists this caller owns.

    Owner-scoped rather than shared: a watchlist runs with its owner's
    clearance, so lending one out would lend the clearance with it. Sharing
    arrives with a grant that says what it means, not by widening a list route.
    """
    limit = min(page_limit(limit), 50)
    statement = select(Watchlist).where(Watchlist.owner == auth.user.sub)
    if cursor:
        statement = statement.where(Watchlist.watchlist_id > cursor)
    rows = list(session.scalars(statement.order_by(Watchlist.watchlist_id)))
    items, next_cursor = split_page(rows, limit, lambda row: row.watchlist_id)
    return WatchlistPageOut(
        items=[_watchlist_out(session, row) for row in items],
        next_cursor=encode_cursor(next_cursor) if next_cursor else None,
    )


@router.get(
    "/alerts",
    response_model=WatchlistAlertPageOut,
    operation_id="listAlerts",
)
def list_alerts(
    session: DbSession,
    ontology: OntologyDep,
    auth: AuthContext = Depends(authorize("analyst")),
    watchlist: str | None = None,
    status: str | None = None,
    limit: Annotated[int, Query(le=50, ge=1)] = 25,
    cursor: str | None = None,
) -> WatchlistAlertPageOut:
    """Detections, filtered on the alert's own handling rank.

    Derived from the claims that fired it, so an alert over evidence the caller
    cannot read is **absent** rather than redacted — the alert's whole content
    is "this exact value appeared on this entity", which is the content of the
    claim it came from.
    """
    limit = min(page_limit(limit), 50)
    statement = select(WatchlistAlert).where(
        WatchlistAlert.handling_rank <= auth.user.clearance
    )
    if watchlist is not None:
        statement = statement.where(WatchlistAlert.watchlist_id == watchlist)
    if status is not None:
        statement = statement.where(WatchlistAlert.status == status)
    if cursor:
        statement = statement.where(WatchlistAlert.alert_id > cursor)
    rows = list(session.scalars(statement.order_by(WatchlistAlert.alert_id)))
    items, next_cursor = split_page(rows, limit, lambda row: row.alert_id)
    return WatchlistAlertPageOut(
        items=[
            WatchlistAlertOut.model_validate(row, from_attributes=True)
            for row in items
        ],
        next_cursor=encode_cursor(next_cursor) if next_cursor else None,
    )


@router.post(
    "/alerts/{alert_id}/triage",
    response_model=WatchlistAlertOut,
    operation_id="triageAlert",
)
def triage(
    alert_id: Annotated[str, Path(description="The alert to move")],
    body: AlertTriageIn,
    session: DbSession,
    auth: AuthContext = Depends(authorize("analyst")),
) -> WatchlistAlert:
    """`new → reviewing → closed`. Every transition audited; `closed` needs a reason.

    An alert above the caller's clearance is **404, not 403**: the same rule
    reading one follows, because learning that an alert exists is most of what
    an alert says.
    """
    alert = session.get(WatchlistAlert, alert_id)
    if alert is None or alert.handling_rank > auth.user.clearance:
        raise HTTPException(404, "not found")

    try:
        alert = triage_alert(
            session,
            alert_id=alert_id,
            status=body.status,
            actor=auth.user.sub,
            purpose=auth.purpose,
            reason=body.reason,
        )
    except WatchlistError as exc:
        raise HTTPException(422, str(exc)) from exc

    session.commit()
    return alert
