"""Geo routes: authorized GeoJSON, never tiles (T59, ADR-049, spec 10 §8).

Martin was evaluated at T54 and declined. A vector tile is a cache keyed by
z/x/y and shared across viewers; read authorization here is per claim — handling
code × clearance × case membership × as-of revision — so a correct tile cache
would have to be keyed by authorization context, which is a cache of one. What
remains is the failure mode: a mis-keyed tile serves sensitive geometry to the
wrong viewer, silently, where no response-level test would see it.

So these are **ordinary routes**. They inherit the authz matrix, the
no-anonymous-surface sweep, cursor pagination, the problem+json envelope and the
as-of stamp, and they are tested by the same machinery as everything else. That
is the point of the decision, not a consolation for it.

`next_cursor` rides as a foreign member of the `FeatureCollection`, which
RFC 7946 §6.1 permits.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query

from aegis.api.deps import AuthContext, DbSession, OntologyDep, authorize
from aegis.api.pagination import (
    DEFAULT_LIMIT,
    decode_cursor,
    encode_cursor,
    page_limit,
)
from aegis.api.schemas import (
    AsOfStampOut,
    FeatureCollectionOut,
    TimelineItemOut,
    TimelinePageOut,
)
from aegis.authz.filters import claim_filters
from aegis.er.ledger import active_revision_id
from aegis.queries.geo import event_features, place_features
from aegis.queries.timeline import timeline_items

router = APIRouter(tags=["geo"])

_PLACE_CURSOR = "geo.locations"
_EVENT_CURSOR = "geo.events"
_TIMELINE_CURSOR = "timeline"


def _bbox(raw: str | None) -> list[float] | None:
    """`west,south,east,north` in WGS84, or a 422 naming what is wrong.

    A malformed box is **not** an empty collection. An empty map is
    indistinguishable from "you may see nothing", and one of those is a lie
    (spec 10 §8.2).
    """
    if raw is None:
        return None
    parts = raw.split(",")
    if len(parts) != 4:
        raise HTTPException(422, "bbox must be west,south,east,north")
    try:
        west, south, east, north = (float(part) for part in parts)
    except ValueError:
        raise HTTPException(422, "bbox values must be numbers") from None
    for value, name in ((west, "west"), (east, "east")):
        if not -180 <= value <= 180:
            raise HTTPException(422, f"bbox {name} is outside [-180, 180]")
    for value, name in ((south, "south"), (north, "north")):
        if not -90 <= value <= 90:
            raise HTTPException(422, f"bbox {name} is outside [-90, 90]")
    if south > north:
        raise HTTPException(422, "bbox south is above north")
    if west > east:
        # An antimeridian-crossing viewport is a real thing and this refuses it
        # rather than guessing, for the same reason §4.3 rule 4 refuses a ring
        # that wraps: the two readings differ by most of the planet.
        raise HTTPException(
            422, "bbox west is east of east — split a viewport that crosses ±180"
        )
    return [west, south, east, north]


def _stamp(
    session, ontology, as_of: datetime | None, as_of_revision: int | None
) -> AsOfStampOut:
    if as_of_revision is not None and as_of_revision > active_revision_id(session):
        raise HTTPException(422, "identity revision does not exist")
    return AsOfStampOut(
        as_of=as_of,
        identity_revision_id=(
            as_of_revision if as_of_revision is not None else active_revision_id(session)
        ),
        ontology_version=ontology.version,
    )


def _collection(
    features: Sequence[Any], stamp: AsOfStampOut, next_cursor: str | None
) -> FeatureCollectionOut:
    return FeatureCollectionOut(
        features=[feature.to_feature() for feature in features],
        next_cursor=next_cursor,
        stamp=stamp,
    )


@router.get(
    "/geo/locations",
    response_model=FeatureCollectionOut,
    operation_id="geoLocations",
)
def geo_locations(
    session: DbSession,
    ontology: OntologyDep,
    bbox: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query()] = None,
    as_of: Annotated[datetime | None, Query(alias="asOf")] = None,
    as_of_revision: Annotated[int | None, Query(alias="asOfRevision", ge=0)] = None,
    auth: AuthContext = Depends(authorize()),
) -> FeatureCollectionOut:
    """Every place the caller may see, with the finest geometry they may read.

    **Authorized generalization, not a runtime blur** (M-18, spec 10 §7.2). A
    location may carry a `sensitive` building polygon and an `open` district
    polygon; the ordinary claim filter removes the first for a low-clearance
    viewer and the district is what comes back. Nothing is synthesized, so no
    viewer is ever shown a shape no source asserted — and the coarse geometry
    keeps its own source and grading, because in practice it came from a
    different, more public document.

    A place with no readable geometry is **listed, never placed**:
    `geometry: null` with a `geometry_state` of `none_permitted`,
    `none_recorded` or `invalid`.
    """
    stamp = _stamp(session, ontology, as_of, as_of_revision)
    after = decode_cursor(cursor, _PLACE_CURSOR, 1)
    size = page_limit(limit)
    features, truncated = place_features(
        session,
        ontology,
        filters=claim_filters(session, auth.user, ontology, as_of=as_of),
        bbox=_bbox(bbox),
        after_id=after[0] if after else None,
        limit=size,
    )
    next_cursor = (
        encode_cursor(_PLACE_CURSOR, [features[-1].entity_id])
        if truncated and features
        else None
    )
    return _collection(features, stamp, next_cursor)


@router.get(
    "/geo/events",
    response_model=FeatureCollectionOut,
    operation_id="geoEvents",
)
def geo_events(
    session: DbSession,
    ontology: OntologyDep,
    bbox: Annotated[str | None, Query()] = None,
    since: Annotated[datetime | None, Query(alias="from")] = None,
    until: Annotated[datetime | None, Query(alias="to")] = None,
    event_type: Annotated[str | None, Query(alias="eventType")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query()] = None,
    as_of: Annotated[datetime | None, Query(alias="asOf")] = None,
    as_of_revision: Annotated[int | None, Query(alias="asOfRevision", ge=0)] = None,
    auth: AuthContext = Depends(authorize()),
) -> FeatureCollectionOut:
    """Occurrences that have a place the caller may see.

    **One feature per (event, place, role)**, not per event: travel has an
    origin and a destination, and a journey drawn as one point at its origin
    would be a lie of omission.

    `time_intervals` carries every interval the event's claims assert, each with
    the claim that asserts it. Never collapsed to one span — two disjoint
    reports are two intervals, and min/max would turn them into a single
    continuous occurrence (spec 10 §6.3, the B-12 discipline).
    """
    stamp = _stamp(session, ontology, as_of, as_of_revision)
    after = decode_cursor(cursor, _EVENT_CURSOR, 1)
    size = page_limit(limit)
    if since is not None and until is not None and since > until:
        raise HTTPException(422, "`from` is after `to`")
    features, truncated = event_features(
        session,
        ontology,
        filters=claim_filters(session, auth.user, ontology, as_of=as_of),
        bbox=_bbox(bbox),
        since=since,
        until=until,
        event_type=event_type,
        after_id=after[0] if after else None,
        limit=size,
    )
    next_cursor = (
        encode_cursor(_EVENT_CURSOR, [features[-1].entity_id])
        if truncated and features
        else None
    )
    return _collection(features, stamp, next_cursor)


@router.get(
    "/timeline",
    response_model=TimelinePageOut,
    operation_id="getTimeline",
)
def get_timeline(
    session: DbSession,
    ontology: OntologyDep,
    entity_id: Annotated[str | None, Query(alias="entityId")] = None,
    case_id: Annotated[str | None, Query(alias="caseId")] = None,
    since: Annotated[datetime | None, Query(alias="from")] = None,
    until: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query()] = None,
    as_of: Annotated[datetime | None, Query(alias="asOf")] = None,
    as_of_revision: Annotated[int | None, Query(alias="asOfRevision", ge=0)] = None,
    auth: AuthContext = Depends(authorize()),
) -> TimelinePageOut:
    """Claims on one timeline, with the certainty their sources actually stated.

    In the geo router rather than a module of its own because it answers the
    same question the map does — *what happened, where and when* — through the
    same filters and the same window rule. Splitting them would be two places
    for "a claim is in the window when its interval intersects it" to drift.

    An **undated** claim is not in a bounded window (§11.2) and is not silently
    dropped either: `undated_count` says how many there are, so a narrow window
    can never look like a complete account of everything known.
    """
    stamp = _stamp(session, ontology, as_of, as_of_revision)
    if since is not None and until is not None and since > until:
        raise HTTPException(422, "`from` is after `to`")
    after = decode_cursor(cursor, _TIMELINE_CURSOR, 2)
    items, truncated, undated = timeline_items(
        session,
        filters=claim_filters(session, auth.user, ontology, as_of=as_of),
        entity_id=entity_id,
        case_id=case_id,
        since=since,
        until=until,
        after=(after[0], after[1]) if after else None,
        limit=page_limit(limit),
    )
    next_cursor = (
        encode_cursor(
            _TIMELINE_CURSOR,
            [
                (items[-1].earliest or items[-1].latest or "").isoformat()
                if (items[-1].earliest or items[-1].latest)
                else "",
                items[-1].claim_id,
            ],
        )
        if truncated and items
        else None
    )
    return TimelinePageOut(
        items=[TimelineItemOut(**item.to_dict()) for item in items],
        next_cursor=next_cursor,
        undated_count=undated,
        stamp=stamp,
    )
