"""Identity ledger primitives (T17; ADR-028, spec 05 §2).

The read side of the decision ledger plus the one write that is *not* an
adjudication: opening a membership for a mention nobody has ever ruled on.

Everything that changes an existing identity — merge, split, reject, mark
unresolved — is an ``adjudicate_identity`` action landing in T20, and it writes
a :class:`~aegis.store.IdentityDecision` with a human actor.  Nothing in this
module may be used to move a mention between entities (ADR-027, Article VII).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aegis.ids import new_id
from aegis.store import IdentityMembership, IdentityRevision, Mention

#: The migration baseline.  Phase-1 one-mention clusters are *verified* as this
#: revision rather than given an invented decision (spec 05 §7 step 3), so it
#: is the only revision carrying ``decision_id IS NULL``.
BASELINE_REVISION = 0


class LedgerError(RuntimeError):
    """The ledger is in a state no caller can proceed from."""


def active_revision_id(session: Session) -> int:
    """The head of the revision chain — what identity means *now*.

    Projections and new claims resolve against this (spec 02 §3.1 rules 2-3).
    An as-of query pins an explicit revision instead.
    """
    head = session.scalar(select(func.max(IdentityRevision.revision_id)))
    if head is None:
        raise LedgerError(
            "no identity revision exists: migration 0007 inserts revision 0 as "
            "the baseline, so an empty chain means the database is not migrated"
        )
    return int(head)


def active_entity_for_mention(session: Session, mention_id: str) -> str | None:
    """The entity this mention currently belongs to, or ``None`` if unresolved.

    At most one row can match — the partial unique index guarantees it.
    """
    return session.scalar(
        select(IdentityMembership.entity_id).where(
            IdentityMembership.mention_id == mention_id,
            IdentityMembership.closed_revision_id.is_(None),
        )
    )


def resolve_norm_key(session: Session, norm_key: str) -> str | None:
    """Exact mention-key lookup — the only resolution Phase 1 ever had.

    ``norm_key`` is a *blocking and lookup key*, never identity (Article V):
    two mentions sharing one is a reason to raise a candidate, not to merge.
    Deterministic rules (T18) and Splink (T19) replace this as the candidate
    source; it survives here so a newly extracted mention can attach to an
    entity a human already adjudicated.
    """
    return session.scalar(
        select(IdentityMembership.entity_id)
        .join(Mention, Mention.mention_id == IdentityMembership.mention_id)
        .where(
            Mention.norm_key == norm_key,
            IdentityMembership.closed_revision_id.is_(None),
        )
        .order_by(IdentityMembership.membership_id)
        .limit(1)
    )


def open_membership(
    session: Session,
    *,
    mention_id: str,
    entity_id: str,
    revision_id: int | None = None,
) -> IdentityMembership:
    """Attach a so-far-unresolved mention to an entity at the current revision.

    This is *not* an adjudication and creates no decision: a mention nobody has
    ruled on joining a single-mention entity is resolution, not a merge (spec
    02 §3.2).  Moving a mention that already has an active membership **is** an
    adjudication, so it is refused here — the database would refuse it anyway
    via ``ux_membership_one_active``, and failing in Python names the reason.
    """
    existing = active_entity_for_mention(session, mention_id)
    if existing is not None:
        raise LedgerError(
            f"mention {mention_id!r} already belongs to entity {existing!r}; "
            "moving it is an adjudicate_identity decision, not a membership open "
            "(ADR-027)"
        )
    row = IdentityMembership(
        membership_id=new_id("mem"),
        mention_id=mention_id,
        entity_id=entity_id,
        opened_revision_id=(
            revision_id if revision_id is not None else active_revision_id(session)
        ),
    )
    session.add(row)
    session.flush()
    return row


__all__ = [
    "BASELINE_REVISION",
    "LedgerError",
    "active_entity_for_mention",
    "active_revision_id",
    "open_membership",
    "resolve_norm_key",
]
