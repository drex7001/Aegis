"""Entity search (spec 06 §2.1, T23c)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from aegis.api.deps import AuthContext, DbSession, OntologyDep, authorize
from aegis.api.pagination import decode_cursor, encode_cursor, page_limit, split_page
from aegis.api.schemas import EntityHitOut, SearchResultsOut
from aegis.search.entities import MAX_QUERY, search_entities

router = APIRouter(tags=["search"])


@router.get(
    "/search/entities",
    response_model=SearchResultsOut,
    operation_id="searchEntities",
)
def search(
    session: DbSession,
    ontology: OntologyDep,
    q: Annotated[str, Query(max_length=MAX_QUERY, description="Free-text name query")],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1)] = 20,
    auth: AuthContext = Depends(authorize()),
) -> SearchResultsOut:
    """Find entities by name, alias or the names they were mentioned under.

    Authorization is applied while candidates are chosen, not after they are
    hydrated (ADR-012, B-17): an entity reachable only through claims above the
    caller's clearance is absent from the scan, so the result *count* cannot be
    used to infer that it exists.
    """
    limit = min(page_limit(limit), 50)
    key = decode_cursor(cursor, "entity-search", 3)
    after = None
    if key is not None:
        try:
            after = (float(key[0]), str(key[1]), str(key[2]))
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, "invalid cursor") from exc
    hits = search_entities(
        session,
        query=q,
        user=auth.user,
        ontology=ontology,
        limit=limit + 1,
        after=after,
    )
    items, next_cursor = split_page(
        hits,
        limit,
        lambda hit: encode_cursor(
            "entity-search", [hit.score, hit.label, hit.entity_id]
        ),
    )
    return SearchResultsOut(
        query=q,
        results=[
            EntityHitOut(
                entity_id=hit.entity_id,
                label=hit.label,
                entity_type=hit.entity_type,
                score=hit.score,
                matched=hit.matched,
            )
            for hit in items
        ],
        next_cursor=next_cursor,
    )
