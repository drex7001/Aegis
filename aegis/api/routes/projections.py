"""Projection routes (spec 06 §2.6, Article XIII).

A projection is a rebuildable cache, so a rebuild destroys nothing and can be
run again — but it reads every claim in the store, which is why spec 06 gates
this on **admin** and caps it at one at a time. The cap is the point: two
concurrent full rebuilds do not corrupt the table (each is idempotent), they
just do the same expensive work twice while holding the same rows, which is a
denial of service an authenticated admin can trigger by double-clicking.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from aegis.api.deps import AuthContext, DbSession, OntologyDep, authorize
from aegis.api.schemas import ProjectionRebuildOut
from aegis.audit import append
from aegis.projections import rebuild_edge_projection, rebuild_location_geometry_projection

router = APIRouter(tags=["projections"])

#: Transaction-scoped, so it is released on commit *and* on rollback. A
#: session-level lock would survive a failed rebuild and wedge the route until
#: the connection was recycled.
_REBUILD_LOCK_KEY = "aegis.projections.rebuild.v1"


@router.post(
    "/projections/rebuild",
    response_model=ProjectionRebuildOut,
    operation_id="rebuildProjections",
)
def rebuild_projections(
    session: DbSession,
    ontology: OntologyDep,
    auth: AuthContext = Depends(authorize("admin")),
) -> ProjectionRebuildOut:
    """Rebuild the edge and geometry projections from canonical claims.

    Audited as an operator action (Article X). The report is returned rather
    than a bare 204 because "it rebuilt" is not the useful answer — how many
    endpoints were resolved through a mention anchor versus the canonical map
    is a live measure of how reversible the graph currently is.
    """
    acquired = session.scalar(
        text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"),
        {"key": _REBUILD_LOCK_KEY},
    )
    if not acquired:
        raise HTTPException(409, "a projection rebuild is already running")

    report = rebuild_edge_projection(session, ontology=ontology)
    # Both projections rebuild in one pass, under the one advisory lock, because
    # "rebuild the projections" that left one of them stale would be a worse
    # answer than refusing (Article XIII, T56).
    geometry = rebuild_location_geometry_projection(session, ontology=ontology)
    detail = {**report.to_dict(), "geometry": geometry.to_dict()}
    append(
        session,
        actor=auth.user.sub,
        action="projections.rebuild",
        decision="allow",
        purpose=auth.purpose,
        resource_type="projection",
        resource_id="edge_projection,location_geometry_projection",
        detail=detail,
    )
    session.commit()
    return ProjectionRebuildOut(
        **report.to_dict(),
        geometry_rows=geometry.rows,
        geometry_invalid=geometry.invalid,
        geometry_rejected=geometry.rejected,
        geometry_builder_version=geometry.builder_version,
    )
