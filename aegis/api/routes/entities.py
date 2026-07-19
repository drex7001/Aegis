"""Entity routes (spec 06 Knowledge)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from aegis.api.deps import AuthContext, DbSession, OntologyDep, authorize
from aegis.api.schemas import ClaimOut, EntityDetail, EntityOut
from aegis.authz.filters import claim_filters
from aegis.store import Claim, Entity

router = APIRouter(tags=["entities"])


@router.get(
    "/entities/{entity_id}", response_model=EntityDetail, operation_id="getEntity"
)
def get_entity(
    entity_id: str,
    session: DbSession,
    ontology: OntologyDep,
    as_of: Annotated[datetime | None, Query(alias="asOf")] = None,
    auth: AuthContext = Depends(authorize()),
) -> EntityDetail:
    entity = session.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(404, "not found")
    filters = claim_filters(session, auth.user, ontology, as_of=as_of)
    rows = session.scalars(
        select(Claim)
        .where(Claim.subject_id == entity_id, *filters)
        .order_by(Claim.predicate, Claim.claim_id)
    ).all()
    grouped: dict[str, list[ClaimOut]] = defaultdict(list)
    for row in rows:
        grouped[row.predicate].append(ClaimOut.model_validate(row))
    return EntityDetail(entity=EntityOut.model_validate(entity), claims_by_predicate=grouped)
