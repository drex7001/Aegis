"""What a viewer may see on a map (T59, spec 10 §7–§8).

The map is not a side door. Every query here composes `claim_filters` — the same
clearance, handling-code, case-membership, retraction and as-of predicates that
gate every other read — and composes them **in candidate generation**, not after
hydration. A filter applied to a result set is a filter that has already loaded
what it is hiding.

Two properties are the point of the module:

* **Authorized generalization is a recorded claim, never a runtime blur**
  (M-18, spec 10 §7.2). A location may carry a `sensitive` building polygon and
  an `open` district polygon. The ordinary filter removes the first for a
  low-clearance viewer, and the finest *remaining* row is what the map draws.
  Nothing is synthesized, so no viewer is ever shown a shape no source asserted.
* **A place with no readable geometry is listed, never placed.** It comes back
  with `geometry: null` and a `geometry_state` saying which kind of nothing it
  is, and the map does not draw it (§7.3).

Which claims carry geometry is asked of the ontology, never hardcoded — the
projection rows are keyed by claim id and the rule is "the predicate declares a
property of type `geo`" (ADR-047).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Sequence

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.orm import Session

from aegis.ontology import Ontology
from aegis.ontology.registries import GEO_ADMIN_LEVELS, GEO_NOT_ADMINISTRATIVE
from aegis.ontology.shapes import (
    event_object_types,
    event_place_predicates,
    place_object_types,
)
from aegis.queries.window import intersects_window
from aegis.store import Claim, Entity, LocationGeometryProjection

#: Coarse → fine. A viewer sees the **finest** geometry among the rows they may
#: read, which is what makes §7.2's generalization work without the server
#: computing a degraded shape.
_ADMIN_ORDER = {level: index for index, level in enumerate(GEO_ADMIN_LEVELS)}
#: Not on the ladder, and finer than any of it: an instrument fix or a coverage
#: polygon is a specific thing, not an administrative unit (spec 10 §4.2).
_NOT_ADMIN_RANK = len(GEO_ADMIN_LEVELS)

GeometryState = Literal["ok", "none_permitted", "none_recorded", "invalid"]


@dataclass
class PlaceFeature:
    """One place, as the map needs it — or as much of it as the viewer may have."""

    entity_id: str
    label: str
    entity_type: str
    geometry: dict[str, Any] | None
    geometry_state: GeometryState
    admin_level: str | None = None
    accuracy_m: float | None = None
    derivation: str | None = None
    geometry_kind: str | None = None
    claim_id: str | None = None
    handling_code: str | None = None
    invalid_reason: str | None = None

    def to_feature(self) -> dict[str, Any]:
        """RFC 7946 Feature. `geometry: null` is valid and is the honest answer."""
        return {
            "type": "Feature",
            "id": self.entity_id,
            "geometry": self.geometry,
            "properties": {
                "entity_id": self.entity_id,
                "label": self.label,
                "entity_type": self.entity_type,
                "geometry_state": self.geometry_state,
                "admin_level": self.admin_level,
                "accuracy_m": self.accuracy_m,
                "derivation": self.derivation,
                "geometry_kind": self.geometry_kind,
                "claim_id": self.claim_id,
                "handling_code": self.handling_code,
                "invalid_reason": self.invalid_reason,
            },
        }


@dataclass
class EventFeature:
    """One occurrence at one place, with the intervals its claims assert."""

    entity_id: str
    label: str
    entity_type: str
    place: PlaceFeature
    place_role: str
    #: Every asserted interval, each attributable to its claim. **Never**
    #: collapsed to one span: two disjoint reports are two intervals, and
    #: min/max would turn them into a single continuous occurrence — the exact
    #: collapse B-12 caught in the edge projection (spec 10 §6.3).
    time_intervals: list[dict[str, Any]] = field(default_factory=list)
    #: Computed over claims the caller can already read (§7.4). A count taken
    #: before filtering is an existence leak wearing a number.
    participant_count: int = 0

    def to_feature(self) -> dict[str, Any]:
        feature = self.place.to_feature()
        feature["id"] = f"{self.entity_id}:{self.place.entity_id}:{self.place_role}"
        feature["properties"] = {
            **feature["properties"],
            "event_id": self.entity_id,
            "event_label": self.label,
            "event_type": self.entity_type,
            "place_id": self.place.entity_id,
            "place_role": self.place_role,
            "time_intervals": self.time_intervals,
            "participant_count": self.participant_count,
        }
        return feature


def bbox_condition(bbox: Sequence[float]) -> ColumnElement[bool]:
    """`ST_Intersects` against the GIST index. Four finite numbers, WGS84."""
    west, south, east, north = bbox
    envelope = func.ST_MakeEnvelope(west, south, east, north, 4326)
    return func.ST_Intersects(LocationGeometryProjection.geom, envelope)


def readable_geometry(
    filters: Sequence[ColumnElement[bool]],
) -> Select:
    """Projection rows the caller may read, joined through the claim filter.

    The join is the whole authorization story: `location_geometry_projection`
    copies the governance columns, but the *claim* is what `claim_filters`
    understands, and reusing it means the map cannot drift from every other
    read surface (Article VI).
    """
    return (
        select(LocationGeometryProjection)
        .join(Claim, Claim.claim_id == LocationGeometryProjection.claim_id)
        .where(*filters)
    )


def _rank(row: LocationGeometryProjection) -> tuple[int, float]:
    """How fine a geometry is. Higher is finer; ties break on a tighter radius."""
    level = (
        _NOT_ADMIN_RANK
        if row.admin_level == GEO_NOT_ADMINISTRATIVE
        else _ADMIN_ORDER.get(row.admin_level, -1)
    )
    # A missing radius sorts as the tightest: a boundary polygon states its own
    # extent, so "no radius" there means exact rather than unbounded.
    accuracy = float(row.accuracy_m) if row.accuracy_m is not None else 0.0
    return (level, -accuracy)


def _feature_for(
    entity: Entity, rows: Sequence[LocationGeometryProjection], session: Session
) -> PlaceFeature:
    """The finest readable geometry for one place, or an honest absence."""
    base = PlaceFeature(
        entity_id=entity.entity_id,
        label=entity.label,
        entity_type=entity.entity_type,
        geometry=None,
        geometry_state="none_recorded",
    )
    if not rows:
        return base

    valid = [row for row in rows if row.is_valid and row.geom is not None]
    if not valid:
        # Every readable geometry failed ST_IsValid. Reported with its reason
        # rather than repaired: ST_MakeValid would change what a source said.
        worst = rows[0]
        base.geometry_state = "invalid"
        base.invalid_reason = worst.invalid_reason
        base.claim_id = worst.claim_id
        base.admin_level = worst.admin_level
        base.derivation = worst.derivation
        return base

    best = max(valid, key=_rank)
    geojson = session.scalar(
        select(func.ST_AsGeoJSON(LocationGeometryProjection.geom)).where(
            LocationGeometryProjection.claim_id == best.claim_id
        )
    )
    return PlaceFeature(
        entity_id=entity.entity_id,
        label=entity.label,
        entity_type=entity.entity_type,
        geometry=json.loads(geojson) if geojson else None,
        geometry_state="ok",
        admin_level=best.admin_level,
        accuracy_m=float(best.accuracy_m) if best.accuracy_m is not None else None,
        derivation=best.derivation,
        geometry_kind=best.geometry_kind,
        claim_id=best.claim_id,
        handling_code=best.handling_code,
    )


def place_features(
    session: Session,
    ontology: Ontology,
    *,
    filters: Sequence[ColumnElement[bool]],
    entity_ids: Sequence[str] | None = None,
    bbox: Sequence[float] | None = None,
    after_id: str | None = None,
    limit: int = 50,
) -> tuple[list[PlaceFeature], bool]:
    """Readable places, finest-permitted geometry each, ordered by id.

    ``bbox`` narrows to places with a **readable** geometry intersecting it: a
    place whose only geometry the caller may not read is not "outside the box",
    it is invisible, and returning it would disclose that something is there.
    """
    places = place_object_types(ontology)
    if not places:
        return [], False

    query = select(Entity).where(
        Entity.entity_type.in_(places), Entity.tombstoned_at.is_(None)
    )
    if entity_ids is not None:
        query = query.where(Entity.entity_id.in_(entity_ids))
    if after_id is not None:
        query = query.where(Entity.entity_id > after_id)
    if bbox is not None:
        inside = (
            readable_geometry(filters)
            .with_only_columns(LocationGeometryProjection.place_id)
            .where(bbox_condition(bbox), LocationGeometryProjection.is_valid.is_(True))
        )
        query = query.where(Entity.entity_id.in_(inside))
    entities = list(
        session.scalars(query.order_by(Entity.entity_id).limit(limit + 1)).all()
    )
    truncated = len(entities) > limit
    entities = entities[:limit]
    if not entities:
        return [], False

    ids = [entity.entity_id for entity in entities]
    by_place: dict[str, list[LocationGeometryProjection]] = {}
    for row in session.scalars(
        readable_geometry(filters).where(
            LocationGeometryProjection.place_id.in_(ids)
        )
    ):
        by_place.setdefault(row.place_id, []).append(row)

    features = [
        _feature_for(entity, by_place.get(entity.entity_id, []), session)
        for entity in entities
    ]
    # A place with geometry recorded that this caller may not read is a
    # different fact from a place with none recorded, and an analyst needs
    # both (§7.3). Whether the distinction should itself be withheld is a
    # response-mode question, and that policy is P7's (H-25).
    _mark_permitted(session, features, by_place)
    return features, truncated


def _mark_permitted(
    session: Session,
    features: Sequence[PlaceFeature],
    readable: dict[str, list[LocationGeometryProjection]],
) -> None:
    empty = [f.entity_id for f in features if f.geometry_state == "none_recorded"]
    if not empty:
        return
    # One unfiltered existence query, over ids the caller can already see. It
    # answers "does any geometry exist here", never "what is it".
    with_any = set(
        session.scalars(
            select(LocationGeometryProjection.place_id)
            .where(LocationGeometryProjection.place_id.in_(empty))
            .distinct()
        )
    )
    for feature in features:
        if feature.entity_id in with_any and not readable.get(feature.entity_id):
            feature.geometry_state = "none_permitted"


def event_features(
    session: Session,
    ontology: Ontology,
    *,
    filters: Sequence[ColumnElement[bool]],
    bbox: Sequence[float] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    event_type: str | None = None,
    after_id: str | None = None,
    limit: int = 50,
) -> tuple[list[EventFeature], bool]:
    """Readable occurrences that have a readable place, one feature per link.

    One feature per (event, place, role) rather than per event, because travel
    has two ends and a journey drawn as one point at its origin would be a lie
    of omission.
    """
    events = event_object_types(ontology)
    place_predicates = list(event_place_predicates(ontology))
    if not events or not place_predicates:
        return [], False
    if event_type is not None:
        if event_type not in events:
            return [], False
        events = [event_type]

    link_query = (
        select(Claim)
        .join(Entity, Entity.entity_id == Claim.subject_id)
        .where(
            Claim.predicate.in_(place_predicates),
            Entity.entity_type.in_(events),
            Entity.tombstoned_at.is_(None),
            *filters,
        )
        .order_by(Claim.subject_id, Claim.claim_id)
    )
    if after_id is not None:
        link_query = link_query.where(Claim.subject_id > after_id)
    links = list(session.scalars(link_query.limit(limit + 1)).all())
    truncated = len(links) > limit
    links = links[:limit]
    if not links:
        return [], False

    event_ids = {link.subject_id for link in links}
    place_ids = {link.object_id for link in links if link.object_id}
    entities = {
        entity.entity_id: entity
        for entity in session.scalars(
            select(Entity).where(Entity.entity_id.in_(event_ids | place_ids))
        )
    }
    places, _ = place_features(
        session, ontology, filters=filters, entity_ids=sorted(place_ids), limit=len(place_ids) or 1
    )
    place_by_id = {place.entity_id: place for place in places}

    intervals = _intervals_by_event(session, event_ids, filters, since, until)
    counts = _participant_counts(session, ontology, event_ids, filters)

    features: list[EventFeature] = []
    for link in links:
        place = place_by_id.get(link.object_id or "")
        event = entities.get(link.subject_id)
        if place is None or event is None:
            continue
        spans = intervals.get(link.subject_id, [])
        if (since is not None or until is not None) and not spans:
            # Filtered out by time. An undated occurrence is excluded from a
            # bounded window and surfaced through the undated affordance
            # instead — never silently placed at `recorded_at` (§11.2).
            continue
        features.append(
            EventFeature(
                entity_id=event.entity_id,
                label=event.label,
                entity_type=event.entity_type,
                place=place,
                place_role=link.predicate,
                time_intervals=spans,
                participant_count=counts.get(link.subject_id, 0),
            )
        )
    return features, truncated


def _intervals_by_event(
    session: Session,
    event_ids: set[str],
    filters: Sequence[ColumnElement[bool]],
    since: datetime | None,
    until: datetime | None,
) -> dict[str, list[dict[str, Any]]]:
    """Every asserted interval, per event, with the claim that asserts it."""
    query = select(Claim).where(Claim.subject_id.in_(event_ids), *filters)
    if since is not None or until is not None:
        query = query.where(intersects_window(since, until))
    result: dict[str, list[dict[str, Any]]] = {}
    for claim in session.scalars(query.order_by(Claim.claim_id)):
        if claim.event_time_earliest is None and claim.event_time_latest is None:
            continue
        spans = result.setdefault(claim.subject_id, [])
        span = {
            "earliest": claim.event_time_earliest.isoformat()
            if claim.event_time_earliest
            else None,
            "latest": claim.event_time_latest.isoformat()
            if claim.event_time_latest
            else None,
            "claim_id": claim.claim_id,
        }
        if span not in spans:
            spans.append(span)
    return result


def _participant_counts(
    session: Session,
    ontology: Ontology,
    event_ids: set[str],
    filters: Sequence[ColumnElement[bool]],
) -> dict[str, int]:
    """Counted over rows the caller can already read (§7.4)."""
    from aegis.ontology.shapes import participation_predicates

    predicates = list(participation_predicates(ontology))
    if not predicates:
        return {}
    rows = session.execute(
        select(Claim.subject_id, func.count(func.distinct(Claim.object_id)))
        .where(
            Claim.subject_id.in_(event_ids),
            Claim.predicate.in_(predicates),
            *filters,
        )
        .group_by(Claim.subject_id)
    )
    return {subject_id: count for subject_id, count in rows}


__all__ = [
    "EventFeature",
    "GeometryState",
    "PlaceFeature",
    "bbox_condition",
    "event_features",
    "place_features",
    "readable_geometry",
]
