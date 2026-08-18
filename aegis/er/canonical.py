"""`entity_canonical_map` — a projection, not a source of truth (spec 05 §5).

Rebuildable from the ledger alone: dropping the whole table loses nothing
(Article XIII).  It answers one question — "which entity does this entity
resolve to *now*" — so a merge collapses two nodes into one and a split
restores them without any claim row being rewritten (ADR-029 §3).

The map is derived by **replaying decisions in revision order**, not by reading
current memberships.  Both would agree in the simple cases, but only the replay
is deterministic when a merged entity's mentions are later scattered across a
split: the replay still knows which entity absorbed it, whereas the membership
state alone can only shrug.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from aegis.store import (
    Entity,
    EntityCanonicalMap,
    IdentityDecision,
    IdentityMembership,
)

#: Decision kinds that move mentions from one entity onto another.
_MERGING_KINDS = frozenset({"confirm", "merge"})


class CanonicalMapError(RuntimeError):
    """The ledger cannot be replayed into a consistent map."""


@dataclass
class CanonicalMapReport:
    entities: int = 0
    merged: int = 0  # entities resolving to a different entity
    tombstoned: int = 0
    lineage: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, int]:
        return {
            "entities": self.entities,
            "merged": self.merged,
            "tombstoned": self.tombstoned,
        }


def _lineage_from_ledger(
    session: Session, *, up_to_revision: int | None = None
) -> dict[str, str]:
    """Replay decisions in revision order into `loser → winner` edges.

    ``up_to_revision`` stops the replay at a point in the ledger, which is what
    makes ``?asOfRevision=`` possible (spec 06 §3, B-11): identity as it was
    understood then, rather than as it is understood now. Decisions above the
    pin have not happened yet from the query's point of view, so a merge made
    afterwards does not collapse two entities, and a split made afterwards does
    not restore them.

    The pin is a *decision* bound rather than a membership bound on purpose. A
    membership row only takes effect through the decision that opened or closed
    it, so filtering decisions is sufficient and does not require reasoning
    about rows that were written but not yet acted on.
    """
    opened: dict[int, set[str]] = defaultdict(set)
    closed: dict[int, set[str]] = defaultdict(set)
    for revision_id, entity_id in session.execute(
        select(IdentityMembership.opened_revision_id, IdentityMembership.entity_id)
    ):
        opened[revision_id].add(entity_id)
    for revision_id, entity_id in session.execute(
        select(IdentityMembership.closed_revision_id, IdentityMembership.entity_id).where(
            IdentityMembership.closed_revision_id.isnot(None)
        )
    ):
        closed[revision_id].add(entity_id)

    decisions = select(
        IdentityDecision.kind, IdentityDecision.result_revision_id
    ).order_by(IdentityDecision.result_revision_id)
    if up_to_revision is not None:
        decisions = decisions.where(
            IdentityDecision.result_revision_id <= up_to_revision
        )

    parent: dict[str, str] = {}
    for kind, revision_id in session.execute(decisions):
        gained = opened.get(revision_id, set())
        lost = closed.get(revision_id, set()) - gained
        if kind in _MERGING_KINDS:
            # A merge has exactly one winner; anything else is not a merge and
            # is left alone rather than guessed at.
            if len(gained) == 1:
                winner = next(iter(gained))
                for loser in lost:
                    parent[loser] = winner
        elif kind == "split":
            # Whatever gained mentions here stands on its own again — this is
            # what makes a split *restore* the pre-merge resolution instead of
            # merely adding a new entity beside the old answer.
            for gainer in gained:
                parent.pop(gainer, None)
    return parent


def _resolve(entity_id: str, parent: dict[str, str]) -> str:
    """Follow the lineage chain to its end, refusing to guess on a cycle."""
    seen = [entity_id]
    current = entity_id
    while current in parent:
        current = parent[current]
        if current in seen:
            raise CanonicalMapError(
                "merge lineage contains a cycle, which can only mean a corrupt "
                f"ledger: {' -> '.join(seen + [current])}. The rebuild refuses to "
                "break it by picking a winner (spec 05 §5)."
            )
        seen.append(current)
    return current


def rebuild_canonical_map(session: Session) -> CanonicalMapReport:
    """Rebuild the whole map from the ledger.  Idempotent by construction."""
    parent = _lineage_from_ledger(session)
    active_entities = {
        entity_id
        for (entity_id,) in session.execute(
            select(IdentityMembership.entity_id)
            .where(IdentityMembership.closed_revision_id.is_(None))
            .distinct()
        )
    }
    head_revision = session.scalar(
        select(IdentityMembership.opened_revision_id)
        .order_by(IdentityMembership.opened_revision_id.desc())
        .limit(1)
    )

    report = CanonicalMapReport(lineage=dict(parent))
    session.execute(delete(EntityCanonicalMap))
    for entity in session.scalars(select(Entity).order_by(Entity.entity_id)):
        canonical = _resolve(entity.entity_id, parent)
        report.entities += 1
        if canonical != entity.entity_id:
            report.merged += 1
        # Tombstone: no active memberships and no lineage target.  It resolves
        # to itself, is excluded from projections, and is retained forever —
        # ids are never reused (spec 05 §5).
        orphaned = (
            entity.entity_id not in active_entities and canonical == entity.entity_id
        )
        if orphaned:
            if entity.tombstoned_at is None:
                entity.tombstoned_at = _now(session)
            report.tombstoned += 1
        elif entity.tombstoned_at is not None:
            # A split can bring a tombstoned entity back into use.  Clearing
            # the tombstone is not id reuse: it is the same entity resuming.
            entity.tombstoned_at = None
        session.add(
            EntityCanonicalMap(
                entity_id=entity.entity_id,
                canonical_entity_id=canonical,
                at_revision_id=head_revision if head_revision is not None else 0,
            )
        )
    session.flush()
    return report


def canonical_entity(session: Session, entity_id: str) -> str:
    """Resolve one entity through the map, falling back to itself.

    A missing row is not an error: the map is a cache, and a cold cache must
    degrade to "resolves to itself" rather than to a failure (Article XIII).
    """
    row = session.get(EntityCanonicalMap, entity_id)
    return row.canonical_entity_id if row is not None else entity_id


def canonical_lineage_at(session: Session, revision_id: int) -> dict[str, str]:
    """`loser → winner` as of a revision — the pinned form of the map (T49).

    Computed rather than read: `entity_canonical_map` caches exactly one
    answer, the active one, and caching every historical revision would be a
    table that grows with the ledger to serve a question nobody asks twice.

    The cost is a full ledger replay per pinned read. That is the honest price
    of an as-of query and it is bounded by the number of identity *decisions*,
    which is a number a human produces one at a time.
    """
    return _lineage_from_ledger(session, up_to_revision=revision_id)


def canonical_entity_at(session: Session, entity_id: str, revision_id: int) -> str:
    """Resolve one entity as identity was understood at ``revision_id``."""
    return _resolve(entity_id, canonical_lineage_at(session, revision_id))


def absorbed_ids_at(session: Session, entity_id: str, revision_id: int) -> set[str]:
    """Every id resolving to this one at ``revision_id``, including itself.

    The pinned counterpart of reading `entity_canonical_map` backwards: a claim
    written against an id that had already been merged away by then still
    belongs to the answer, and one merged away *afterwards* does not.
    """
    parent = canonical_lineage_at(session, revision_id)
    return {entity_id} | {
        candidate for candidate in parent if _resolve(candidate, parent) == entity_id
    }


def _now(session: Session):
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


__all__ = [
    "CanonicalMapError",
    "CanonicalMapReport",
    "absorbed_ids_at",
    "canonical_entity",
    "canonical_entity_at",
    "canonical_lineage_at",
    "rebuild_canonical_map",
]
