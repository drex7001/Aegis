"""Governed graph routes (T22; specs/06 §2.6, ADR-026, ADR-030).

These replace the anonymous ``/api/graph``, ``/api/stats``, ``/api/cells`` and
``/api/query/{name}`` surface that ADR-019 introduced and ADR-026 retired. The
old routes served an entire projection of a real-person corpus to anyone who
could reach the port, recording no actor, no purpose, and no decision; the
interim rate and size caps T16a added were exposure controls, not
authorization, and they are gone with the routes they contained.

What replaces them is smaller on purpose. There is no "give me the graph" call:
expansion takes seeds and a hop bound, and the one seedless mode — the bounded
overview — is capped by the same element budget as everything else. Both routes
are authenticated, audited by the gate, and filtered to the claims the caller
may actually read.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from aegis.api.deps import (
    AuthContext,
    DbSession,
    OntologyDep,
    authorize,
    fga_check_or_404,
    get_fga,
)
from aegis.api.schemas import (
    GraphExpandIn,
    GraphPathsIn,
    GraphPathsOut,
    GraphViewOut,
)
from aegis.authz.filters import claim_filters
from aegis.queries import graph as graph_query
from aegis.store import Claim

router = APIRouter(tags=["graph"])


@router.post(
    "/graph/expand",
    response_model=GraphViewOut,
    operation_id="expandGraph",
)
def expand_graph(
    body: GraphExpandIn,
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize()),
) -> GraphViewOut:
    """Breadth-first expansion from seeds, or the bounded overview without them.

    POST rather than GET because the request is a query object — seed sets,
    category filters and time windows — not a resource address, and putting a
    hundred entity ids in a query string is how URL-length limits become silent
    truncation of an authorization-relevant input.

    ``case_id`` narrows to the evidence that case recorded. It is threaded in as
    an extra **claim filter** rather than applied to the result, which is what
    makes "the case graph never renders out-of-case data" a property of the
    query: edge visibility and every support summary are computed from the same
    narrowed set (spec 09 §2.4).
    """
    filters = list(claim_filters(session, auth.user, ontology))
    if body.case_id is not None:
        # 404-not-403, like every other case-scoped read: asking must not
        # confirm that a case exists.
        fga_check_or_404(fga, auth.user, "can_view", f"case:{body.case_id}")
        filters.append(Claim.case_id == body.case_id)

    view = graph_query.expand(
        session,
        ontology,
        filters=filters,
        seed_ids=body.seed_ids,
        max_hops=body.max_hops,
        categories=body.categories,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        max_elements=body.max_elements,
    )
    return GraphViewOut.model_validate(view)


@router.post(
    "/graph/paths",
    response_model=GraphPathsOut,
    operation_id="graphPaths",
)
def graph_paths(
    body: GraphPathsIn,
    session: DbSession,
    ontology: OntologyDep,
    auth: AuthContext = Depends(authorize()),
) -> GraphPathsOut:
    """Shortest routes between two entities, bounded by hops and count.

    A path here is a claim about *what the evidence connects*, not about what
    anyone did: every edge on it opens onto its claims, and none of them is
    graded by its position on the path (Article IX).
    """
    result = graph_query.paths(
        session,
        ontology,
        filters=claim_filters(session, auth.user, ontology),
        from_id=body.from_id,
        to_id=body.to_id,
        max_hops=body.max_hops,
        max_paths=body.max_paths,
        categories=body.categories,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
    )
    return GraphPathsOut.model_validate(result)
