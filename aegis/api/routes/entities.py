"""Entity routes (spec 06 Knowledge)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select

from aegis.api.deps import (
    AuthContext,
    DbSession,
    OntologyDep,
    authorize,
    get_fga,
)
from aegis.api.mappers import claim_provenance_out
from aegis.api.schemas import (
    AsOfStampOut,
    ClaimProvenanceOut,
    EntityCaseOut,
    EntityDetail,
    EntityOut,
)
from aegis.authz.fga import FGAClient, FGAError
from aegis.authz.filters import claim_filters, hidden_entity_types
from aegis.er.ledger import active_revision_id
from aegis.queries.provenance import entity_provenance
from aegis.store import CaseFile, CaseReference, Claim, Entity

router = APIRouter(tags=["entities"])


@router.get(
    "/entities/{entity_id}", response_model=EntityDetail, operation_id="getEntity"
)
def get_entity(
    entity_id: str,
    session: DbSession,
    ontology: OntologyDep,
    as_of: Annotated[datetime | None, Query(alias="asOf")] = None,
    as_of_revision: Annotated[int | None, Query(alias="asOfRevision", ge=0)] = None,
    auth: AuthContext = Depends(authorize()),
) -> EntityDetail:
    """One entity's claims, grouped by predicate, each with its evidence.

    Grouping is what renders two disagreeing claims about the same property
    side by side; ``contradicted_by`` on each entry is what names the
    disagreement rather than leaving the reader to spot it (Article VIII).

    ``inbound_claims_by_predicate`` is the same question from the other end —
    what *others* assert about this entity (T57). Separate rather than merged,
    because a reader has to be able to tell who asserted what about whom; and
    filtered identically, so an inbound claim can never appear on a page where
    the outbound one would have been hidden.

    **As-of is a claim-recording snapshot and nothing more** (B-11, spec 09 §7).
    ``asOf`` filters to what had been recorded and not retracted at that
    instant; ``asOfRevision`` pins the identity revision entity arguments
    resolve through. Passing ``asOf`` alone resolves identity as it is *now*,
    which is usually not what a historical question means — so the response
    always carries the revision it actually used, whether pinned or active.

    What as-of does **not** restore: labels, source evaluations, grading,
    policy, projections, or the ontology. Those are current-state, and the
    banner in the workspace says so.
    """
    entity = session.get(Entity, entity_id)
    if entity is None or entity.entity_type in hidden_entity_types(
        ontology, auth.user.clearance
    ):
        raise HTTPException(404, "not found")
    if as_of_revision is not None and as_of_revision > active_revision_id(session):
        # A revision that has not happened cannot be pinned. 422 rather than
        # clamping to the head: silently answering about *now* under a heading
        # that says otherwise is the failure mode this parameter exists against.
        raise HTTPException(422, "identity revision does not exist")
    result = entity_provenance(
        session,
        entity_id=entity_id,
        filters=claim_filters(session, auth.user, ontology, as_of=as_of),
        at_revision_id=as_of_revision,
    )
    # `entity_provenance` re-checks existence and returns None only when the
    # entity is gone; it was loaded above, so this is unreachable in practice
    # and asserted rather than branched on.
    assert result is not None

    grouped: dict[str, list[ClaimProvenanceOut]] = defaultdict(list)
    for entry in result.claims:
        grouped[entry.claim.predicate].append(claim_provenance_out(entry))
    inbound: dict[str, list[ClaimProvenanceOut]] = defaultdict(list)
    for entry in result.inbound_claims:
        inbound[entry.claim.predicate].append(claim_provenance_out(entry))
    return EntityDetail(
        entity=EntityOut.model_validate(entity),
        claims_by_predicate=grouped,
        inbound_claims_by_predicate=inbound,
        resolved_entity_id=result.resolved_entity_id,
        truncated=result.truncated,
        inbound_truncated=result.inbound_truncated,
        stamp=AsOfStampOut(
            as_of=as_of,
            # Echoed whether pinned or not: a caller must never have to re-read
            # its own request to know which identity produced this answer.
            identity_revision_id=(
                as_of_revision
                if as_of_revision is not None
                else active_revision_id(session)
            ),
            ontology_version=ontology.version,
        ),
    )


@router.get(
    "/entities/{entity_id}/cases",
    response_model=list[EntityCaseOut],
    operation_id="listEntityCases",
)
def list_entity_cases(
    entity_id: str,
    session: DbSession,
    ontology: OntologyDep,
    fga=Depends(get_fga),
    auth: AuthContext = Depends(authorize()),
) -> list[CaseFile]:
    """Cases this entity appears in — and no trace of the ones it does not (H-18).

    The naive implementation is to find every case touching the entity and then
    filter. That leaves a timing and ordering signal: how long the filtering
    took, and where the gaps in a ranking are. So the answer is **derived only
    from rows the caller can already read**, and then intersected with
    ``can_view`` on each surviving case (spec 09 §6.5):

    1. distinct ``case_id`` from claims about the entity **through**
       ``claim_filters``, which already drops case-scoped claims the caller is
       not a member of;
    2. plus cases whose ``case_reference`` names this entity — the step that can
       surface a case the caller is *not* in, because a reference may point at
       an entity everybody can see;
    3. ``can_view`` on each, dropping failures.

    Step 3 is not redundant with step 1. Without it, an open entity referenced
    from a restricted case would advertise that case's existence, which is
    exactly the finding.

    What this never does: return a total, a "N more", a relevance ordering, or a
    different status code for "in no cases" and "in cases you cannot see". Both
    are an empty array from a 200.
    """
    entity = session.get(Entity, entity_id)
    if entity is None or entity.entity_type in hidden_entity_types(
        ontology, auth.user.clearance
    ):
        raise HTTPException(404, "not found")

    filters = claim_filters(session, auth.user, ontology)
    from_claims = select(Claim.case_id).where(
        Claim.case_id.is_not(None),
        or_(Claim.subject_id == entity_id, Claim.object_id == entity_id),
        *filters,
    )
    from_references = select(CaseReference.case_id).where(
        CaseReference.target_type == "entity",
        CaseReference.target_id == entity_id,
        CaseReference.detached_at.is_(None),
    )
    candidates = set(session.scalars(from_claims)) | set(session.scalars(from_references))
    if not candidates:
        return []

    rows = list(
        session.scalars(
            # Ordered by primary key, never by activity or claim count: a
            # ranking is a place for a hidden row to leave a detectable gap.
            select(CaseFile)
            .where(CaseFile.case_id.in_(candidates))
            .order_by(CaseFile.case_id)
        )
    )
    return [row for row in rows if _can_view_case(fga, auth, row.case_id)]


def _can_view_case(fga: FGAClient | None, auth: AuthContext, case_id: str) -> bool:
    """`can_view`, as a boolean rather than as a 404.

    `fga_check_or_404` is right when the case *is* the resource being asked
    for. Here it is one row among several, and a failure means "leave it out",
    not "this request was about something you may not have".
    """
    if fga is None:
        # No authorization backend configured (dev without bootstrap). Fail
        # closed: an unauthorized-by-default empty list is a worse answer than
        # a leak is a bug.
        return False
    try:
        return fga.check(f"user:{auth.user.sub}", "can_view", f"case:{case_id}")
    except FGAError as exc:
        raise HTTPException(503, f"authorization backend unavailable: {exc}") from exc
