"""One timeline over claims (T61, spec 10 §11.1).

**Timeline items are claims.** Events do not get items of their own — an event
appears through the claims that assert it, which is what makes "no duplicates"
structural rather than a de-duplication pass: there is only ever one row per
assertion.

`certainty` is derived from the interval rather than asserted, so a source that
said "some time in March" cannot be rendered as 1 March by anything downstream:

===========  ==========================================
`exact`      `earliest == latest` — the source stated an instant
`bounded`    both set and different — a range the source stated
`open`       one set — "after March, end unknown"
`undated`    neither — and said so, never placed at `recorded_at`
===========  ==========================================

The window rule is intersection, and undated is deliberately **outside** every
bounded window (§11.2). A claim we cannot place in time is not evidence that it
falls in the range you happen to be looking at.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Sequence

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from aegis.queries.geo import _intersects_window
from aegis.store import Claim, Entity

Certainty = Literal["exact", "bounded", "open", "undated"]


@dataclass
class TimelineItem:
    """One claim, placed in time as honestly as its source allows."""

    claim_id: str
    subject_id: str
    subject_label: str | None
    subject_type: str | None
    predicate: str
    object_id: str | None
    object_label: str | None
    object_value: Any
    earliest: datetime | None
    latest: datetime | None
    certainty: Certainty
    record_id: str
    handling_code: str
    recorded_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "subject_id": self.subject_id,
            "subject_label": self.subject_label,
            "subject_type": self.subject_type,
            "predicate": self.predicate,
            "object_id": self.object_id,
            "object_label": self.object_label,
            "object_value": self.object_value,
            "earliest": self.earliest,
            "latest": self.latest,
            "certainty": self.certainty,
            "record_id": self.record_id,
            "handling_code": self.handling_code,
            "recorded_at": self.recorded_at,
        }


def certainty_of(earliest: datetime | None, latest: datetime | None) -> Certainty:
    if earliest is None and latest is None:
        return "undated"
    if earliest is None or latest is None:
        return "open"
    return "exact" if earliest == latest else "bounded"


def timeline_items(
    session: Session,
    *,
    filters: Sequence[ColumnElement[bool]],
    entity_id: str | None = None,
    case_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    after: tuple[str, str] | None = None,
    limit: int = 50,
) -> tuple[list[TimelineItem], bool, int]:
    """Claims on a timeline, plus how many are undated.

    The undated count is returned rather than folded into the items, because
    an undated claim is *excluded* from a bounded window and must still be
    surfaced — silently dropping it would let a narrow window look like a
    complete account of everything known (§11.2).
    """
    query = select(Claim).where(*filters)
    if entity_id is not None:
        # Both directions: an arrest's date reaches a participant's timeline
        # only through the claim the *event* is the subject of (spec 10 §13).
        query = query.where(
            (Claim.subject_id == entity_id) | (Claim.object_id == entity_id)
        )
    if case_id is not None:
        query = query.where(Claim.case_id == case_id)

    undated_count = _count_undated(session, query)

    if since is not None or until is not None:
        query = query.where(_intersects_window(since, until))
    # Order by time, then id: two claims stating the same instant need a stable
    # order or a cursor cannot resume without repeating or skipping one.
    ordering = (
        func.coalesce(Claim.event_time_earliest, Claim.event_time_latest),
        Claim.claim_id,
    )
    if after is not None:
        cursor_time, cursor_id = after
        query = query.where(
            func.coalesce(Claim.event_time_earliest, Claim.event_time_latest)
            > cursor_time
            if cursor_time
            else Claim.claim_id > cursor_id
        )
    rows = list(session.scalars(query.order_by(*ordering).limit(limit + 1)).all())
    truncated = len(rows) > limit
    rows = rows[:limit]

    labels = _labels(session, rows)
    items = [
        TimelineItem(
            claim_id=claim.claim_id,
            subject_id=claim.subject_id,
            subject_label=labels.get(claim.subject_id, (None, None))[0],
            subject_type=labels.get(claim.subject_id, (None, None))[1],
            predicate=claim.predicate,
            object_id=claim.object_id,
            object_label=(
                labels.get(claim.object_id, (None, None))[0] if claim.object_id else None
            ),
            object_value=claim.object_value,
            earliest=claim.event_time_earliest,
            latest=claim.event_time_latest,
            certainty=certainty_of(claim.event_time_earliest, claim.event_time_latest),
            record_id=claim.record_id,
            handling_code=claim.handling_code,
            recorded_at=claim.recorded_at,
        )
        for claim in rows
    ]
    return items, truncated, undated_count


def _count_undated(session: Session, query) -> int:
    """Counted over the same filtered set, before the window narrows it."""
    undated = query.where(
        Claim.event_time_earliest.is_(None), Claim.event_time_latest.is_(None)
    )
    return session.scalar(
        select(func.count()).select_from(undated.subquery())
    ) or 0


def _labels(
    session: Session, claims: Sequence[Claim]
) -> dict[str, tuple[str | None, str | None]]:
    ids = {claim.subject_id for claim in claims} | {
        claim.object_id for claim in claims if claim.object_id
    }
    if not ids:
        return {}
    return {
        entity.entity_id: (entity.label, entity.entity_type)
        for entity in session.scalars(select(Entity).where(Entity.entity_id.in_(ids)))
    }


__all__ = ["Certainty", "TimelineItem", "certainty_of", "timeline_items"]
