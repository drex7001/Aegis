"""The one time window, shared by map, timeline and graph (T62, spec 10 §11.2).

One function, in one place, because T62's acceptance criterion is *"nothing
renders on one surface that the filter excludes on another"* — and the only way
to make that a property rather than a promise is for there to be nothing to keep
in step. It lived as a private helper inside the geo queries until three callers
wanted it, which is one more than a private helper should have.

Two rules, and both are decisions rather than conveniences:

**Intersection, not containment.** A claim spanning the whole of April is in a
window covering half of it. Containment would hide long-running assertions from
every window narrower than they are, which is the opposite of what a reader
narrowing a window is asking for.

**Undated is outside every bounded window.** A claim we cannot place in time is
not evidence that it falls in the range you happen to be looking at. It is
surfaced through a separate count instead (`undated_count`), so a narrowed
window can never look like a complete account of everything known — and it is
never placed at `recorded_at`, because when we wrote something down is a fact
about us and the axis is about the world.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ColumnElement, and_, or_

from aegis.store import Claim


def intersects_window(
    since: datetime | None, until: datetime | None
) -> ColumnElement[bool]:
    """Claims whose asserted interval intersects ``[since, until]``.

    An open-ended interval intersects everything after its bound, which is why
    the null cases are written out rather than left to SQL's three-valued logic:
    ``NULL <= :until`` is NULL, not true, and "after March, end unknown" would
    silently vanish from a query about this year.
    """
    conditions: list[ColumnElement[bool]] = []
    if until is not None:
        conditions.append(
            or_(Claim.event_time_earliest.is_(None), Claim.event_time_earliest <= until)
        )
    if since is not None:
        conditions.append(
            or_(Claim.event_time_latest.is_(None), Claim.event_time_latest >= since)
        )
    conditions.append(
        or_(
            Claim.event_time_earliest.is_not(None),
            Claim.event_time_latest.is_not(None),
        )
    )
    return and_(*conditions)


__all__ = ["intersects_window"]
