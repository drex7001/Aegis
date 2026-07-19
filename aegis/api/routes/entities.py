"""Entity routes (spec 06 Knowledge)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from aegis.api.deps import AuthContext, DbSession, OntologyDep, authorize
from aegis.api.mappers import claim_provenance_out
from aegis.api.schemas import ClaimProvenanceOut, EntityDetail, EntityOut
from aegis.authz.filters import claim_filters, hidden_entity_types
from aegis.queries.provenance import entity_provenance
from aegis.store import Entity

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
    """One entity's claims, grouped by predicate, each with its evidence.

    Grouping is what renders two disagreeing claims about the same property
    side by side; ``contradicted_by`` on each entry is what names the
    disagreement rather than leaving the reader to spot it (Article VIII).
    """
    entity = session.get(Entity, entity_id)
    if entity is None or entity.entity_type in hidden_entity_types(
        ontology, auth.user.clearance
    ):
        raise HTTPException(404, "not found")
    result = entity_provenance(
        session,
        entity_id=entity_id,
        filters=claim_filters(session, auth.user, ontology, as_of=as_of),
    )
    # `entity_provenance` re-checks existence and returns None only when the
    # entity is gone; it was loaded above, so this is unreachable in practice
    # and asserted rather than branched on.
    assert result is not None

    grouped: dict[str, list[ClaimProvenanceOut]] = defaultdict(list)
    for entry in result.claims:
        grouped[entry.claim.predicate].append(claim_provenance_out(entry))
    return EntityDetail(
        entity=EntityOut.model_validate(entity),
        claims_by_predicate=grouped,
        resolved_entity_id=result.resolved_entity_id,
        truncated=result.truncated,
    )
