"""One search route over entities, claims and documents (spec 11 §1, ADR-050).

BREAKING API CHANGE: `GET /v1/search/entities` (operation `searchEntities`) is
removed. It was P2's first implementation of this route under a narrower name;
M-11 asks for one endpoint with an additive backend, and the honest expression
of "additive backend, same endpoint" is that the endpoint stops naming one of
its backends. Two routes would have meant two ranking models, two pagination
implementations, and two places to close B-17's leak surface independently.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from aegis.api.deps import AuthContext, DbSession, OntologyDep, authorize
from aegis.api.pagination import decode_cursor, encode_cursor, page_limit
from aegis.api.schemas import (
    AsOfStampOut,
    SearchGroupOut,
    SearchHitOut,
    SearchResultsOut,
)
from aegis.er.ledger import active_revision_id
from aegis.search.entities import MAX_QUERY
from aegis.search.service import MAX_LIMIT, available_groups, into_groups, search

router = APIRouter(tags=["search"])

CURSOR_SCOPE = "search"


@router.get(
    "/search",
    response_model=SearchResultsOut,
    operation_id="search",
)
def search_everything(
    session: DbSession,
    ontology: OntologyDep,
    q: Annotated[str, Query(max_length=MAX_QUERY, description="Free-text query")],
    types: Annotated[
        list[str] | None,
        Query(description="Restrict to these result groups; omit for all"),
    ] = None,
    as_of: Annotated[datetime | None, Query(alias="asOf")] = None,
    as_of_revision: Annotated[int | None, Query(alias="asOfRevision", ge=0)] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1)] = 20,
    auth: AuthContext = Depends(authorize()),
) -> SearchResultsOut:
    """Find entities, claims and documents by name, alias, excerpt or text.

    Authorization is applied while candidates are chosen, not after they are
    hydrated (ADR-012, B-17): a row the caller's filters exclude is absent from
    the scan, so neither the result *count* nor a gap in the sequence can be
    used to infer that it exists. There is no total for the same reason, and an
    empty group is omitted rather than returned empty.

    Result groups are enumerated from the ontology (Article XIV), so a new
    domain module's object types are searchable the day they are declared.
    """
    limit = min(page_limit(limit), MAX_LIMIT)
    _reject_unknown_types(ontology, types)
    stamp = _stamp(session, ontology, as_of, as_of_revision)
    after = _decode_after(cursor)

    hits, has_more = search(
        session,
        query=q,
        user=auth.user,
        ontology=ontology,
        types=types,
        limit=limit,
        as_of=as_of,
        after=after,
    )

    next_cursor = None
    if has_more and hits:
        last = hits[-1]
        next_cursor = encode_cursor(CURSOR_SCOPE, [last.score, last.label, last.id])

    return SearchResultsOut(
        query=q,
        groups=[
            SearchGroupOut(
                group=group.group,
                label=group.label,
                hits=[
                    SearchHitOut(
                        kind=hit.kind,
                        id=hit.id,
                        group=hit.group,
                        label=hit.label,
                        detail=hit.detail,
                        parent_id=hit.parent_id,
                        score=hit.score,
                        matched=hit.matched,
                    )
                    for hit in group.hits
                ],
            )
            for group in into_groups(ontology, hits)
        ],
        next_cursor=next_cursor,
        stamp=stamp,
    )


def _reject_unknown_types(ontology, types: list[str] | None) -> None:
    """A group name nobody declares is a typo, and a typo must not widen.

    Silently ignoring it would return *every* group under a request that asked
    for one — the same failure mode `case_id` has on the graph route, where an
    ignored filter returns the caller's whole readable graph under a heading
    saying otherwise (spec 06 §2.6).
    """
    if not types:
        return
    unknown = sorted(set(types) - set(available_groups(ontology)))
    if unknown:
        raise HTTPException(422, f"unknown result group(s): {', '.join(unknown)}")


def _decode_after(cursor: str | None) -> tuple[float, str, str] | None:
    key = decode_cursor(cursor, CURSOR_SCOPE, 3)
    if key is None:
        return None
    try:
        return (float(key[0]), str(key[1]), str(key[2]))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "invalid cursor") from exc


def _stamp(
    session, ontology, as_of: datetime | None, as_of_revision: int | None
) -> AsOfStampOut:
    """Carried on every response, not only on as-of ones (spec 06 §3).

    A revision above the head is **422, never clamped**: answering about *now*
    under a heading that says otherwise is the failure the parameter exists
    against.
    """
    if as_of_revision is not None and as_of_revision > active_revision_id(session):
        raise HTTPException(422, "identity revision does not exist")
    return AsOfStampOut(
        as_of=as_of,
        identity_revision_id=(
            as_of_revision if as_of_revision is not None else active_revision_id(session)
        ),
        ontology_version=ontology.version,
    )
