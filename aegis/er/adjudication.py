"""Ledger mechanics for `adjudicate_identity` (T20; spec 05 §4, ADR-028).

The four modes — confirm, reject, split, unresolved — are the *only* writers to
`identity_decision`, `identity_revision` and `identity_membership` after the
migration baseline.  Each is one transaction: decision + revision + membership
changes + audit, with the scoped concurrency check of spec 05 §2.

Transaction and audit belong to :class:`~aegis.actions.ActionService`; this
module owns the ledger arithmetic so the service does not grow a second
personality.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import and_ as sa_and, or_ as sa_or, select
from sqlalchemy.orm import Session

from aegis.ids import new_id
from aegis.er.canonical import rebuild_canonical_map
from aegis.store import (
    Claim,
    Entity,
    EntityCanonicalMap,
    ErCandidate,
    IdentityDecision,
    IdentityMembership,
    IdentityNegativeConstraint,
    IdentityRevision,
    Mention,
)

ADJUDICATION_MODES = frozenset(
    {"confirm_match", "reject_match", "split_entity", "mark_unresolved"}
)
_MODE_KINDS = {
    "confirm_match": "confirm",
    "reject_match": "reject",
    "split_entity": "split",
    "mark_unresolved": "unresolved",
}


class AdjudicationError(RuntimeError):
    """The decision cannot be applied as stated."""


@dataclass(frozen=True, slots=True)
class InterveningDecision:
    """A decision that landed between the parent revision and now."""

    decision_id: str
    kind: str
    decided_by: str
    decision_note: str
    result_revision_id: int


class StaleRevisionError(AdjudicationError):
    """The decision was computed against evidence that has since changed.

    Carries the intervening decisions so the analyst can be **re-presented**
    with what happened rather than silently retried (spec 05 §2).
    """

    def __init__(self, parent_revision_id: int, intervening: list[IdentityDecision]) -> None:
        self.parent_revision_id = parent_revision_id
        # Snapshotted, not held as ORM rows. This exception is raised precisely
        # when the transaction that loaded them is about to roll back, so
        # anything reading them afterwards — an error handler rendering a 409,
        # a log line — would find them detached from their session.
        self.intervening = [
            InterveningDecision(
                decision_id=decision.decision_id,
                kind=decision.kind,
                decided_by=decision.decided_by,
                decision_note=decision.decision_note,
                result_revision_id=decision.result_revision_id,
            )
            for decision in intervening
        ]
        super().__init__(
            f"decision was computed against revision {parent_revision_id}, but "
            f"{len(intervening)} later decision(s) changed an entity in its scope: "
            + ", ".join(f"{d.decision_id} ({d.kind})" for d in intervening)
        )


@dataclass
class AdjudicationResult:
    decision: IdentityDecision
    revision: IdentityRevision
    moved_mentions: list[str] = field(default_factory=list)
    surviving_entity_id: str | None = None
    new_entity_id: str | None = None
    constraint_id: str | None = None
    #: Claims whose attribution the decision could not settle (spec 02 §3.1
    #: rule 4) — surfaced for a human, never reassigned.
    unattributable_claims: list[str] = field(default_factory=list)


# ── scoped optimistic concurrency (spec 05 §2) ───────────────────────────────


def _entities_of(session: Session, mention_ids: list[str]) -> set[str]:
    return {
        entity_id
        for (entity_id,) in session.execute(
            select(IdentityMembership.entity_id).where(
                IdentityMembership.mention_id.in_(mention_ids),
                IdentityMembership.closed_revision_id.is_(None),
            )
        )
    }


def check_scope_is_current(
    session: Session, *, parent_revision_id: int, scope: set[str]
) -> None:
    """Reject only decisions whose *own* evidence went stale.

    A global head check would make every unrelated concurrent adjudication
    conflict, which in a busy review queue means analysts learn to retry
    blindly — the opposite of the care this check exists to enforce.  So the
    check is scoped: it fails when an entity in this decision's input scope has
    had a membership opened or closed later than ``parent_revision_id``.
    """
    if not scope:
        return
    later = session.scalars(
        select(IdentityMembership.opened_revision_id)
        .where(
            IdentityMembership.entity_id.in_(scope),
            IdentityMembership.opened_revision_id > parent_revision_id,
        )
        .limit(1)
    ).all()
    later += session.scalars(
        select(IdentityMembership.closed_revision_id)
        .where(
            IdentityMembership.entity_id.in_(scope),
            IdentityMembership.closed_revision_id > parent_revision_id,
        )
        .limit(1)
    ).all()
    if not later:
        return
    intervening = list(
        session.scalars(
            select(IdentityDecision)
            .where(IdentityDecision.result_revision_id > parent_revision_id)
            .order_by(IdentityDecision.result_revision_id)
        )
    )
    raise StaleRevisionError(parent_revision_id, intervening)


# ── the ledger write ─────────────────────────────────────────────────────────


def _open_decision(
    session: Session,
    *,
    mode: str,
    actor: str,
    note: str,
    parent_revision_id: int,
    candidate_id: str | None,
    input_mentions: list[str],
) -> tuple[IdentityDecision, IdentityRevision]:
    """Exactly one decision, exactly one new revision (spec 05 §2)."""
    revision = IdentityRevision()
    session.add(revision)
    session.flush()
    decision = IdentityDecision(
        decision_id=new_id("dec"),
        kind=_MODE_KINDS[mode],
        decided_by=actor,
        decision_note=note,
        candidate_id=candidate_id,
        input_mentions=input_mentions,
        parent_revision_id=parent_revision_id,
        result_revision_id=revision.revision_id,
    )
    session.add(decision)
    session.flush()
    revision.decision_id = decision.decision_id
    session.flush()
    return decision, revision


def _move_mentions(
    session: Session,
    *,
    mention_ids: list[str],
    target_entity_id: str,
    revision_id: int,
) -> list[str]:
    """Close each mention's active membership and reopen it on the target.

    History is never deleted: the closed row keeps naming the revision that
    closed it, which is what makes the pre-decision state reconstructible.
    """
    moved: list[str] = []
    for membership in session.scalars(
        select(IdentityMembership)
        .where(
            IdentityMembership.mention_id.in_(mention_ids),
            IdentityMembership.closed_revision_id.is_(None),
        )
        .order_by(IdentityMembership.mention_id)
    ):
        if membership.entity_id == target_entity_id:
            continue
        membership.closed_revision_id = revision_id
        session.add(
            IdentityMembership(
                membership_id=new_id("mem"),
                mention_id=membership.mention_id,
                entity_id=target_entity_id,
                opened_revision_id=revision_id,
            )
        )
        moved.append(membership.mention_id)
    session.flush()
    return moved


def _mentions_of_entity(session: Session, entity_id: str) -> list[str]:
    return list(
        session.scalars(
            select(IdentityMembership.mention_id)
            .where(
                IdentityMembership.entity_id == entity_id,
                IdentityMembership.closed_revision_id.is_(None),
            )
            .order_by(IdentityMembership.mention_id)
        )
    )


def _unattributable_claims(
    session: Session, *, entity_id: str, moved_mentions: set[str]
) -> list[str]:
    """Claims on a split entity that no mention can settle (spec 02 §3.1 rule 4).

    An **anchored** claim follows its mention: the mention moved to a specific
    entity, so the attribution is already decided and no human is asked.  An
    **unanchored** claim has nothing to follow, so it is surfaced for
    re-adjudication rather than silently assigned to either side.

    Two things this has to get right, both found by the T21 projection tests:

    *Both argument positions count.*  Checking only the subject would miss
    every claim naming the split entity as its object — and since symmetric
    predicates are order-normalized at write time, that is roughly half of
    them.  A claim nobody can attribute is equally unattributable whichever end
    it hangs from.

    *Absorbed ids count too.*  A claim written before a merge still names the
    entity that was absorbed, not the survivor being split now.  Matching the
    survivor's id alone would find nothing precisely in the merge-then-split
    case this rule exists for, so the search covers every id that currently
    resolves to it.
    """
    affected = {entity_id} | {
        absorbed
        for (absorbed,) in session.execute(
            select(EntityCanonicalMap.entity_id).where(
                EntityCanonicalMap.canonical_entity_id == entity_id
            )
        )
    }
    return list(
        session.scalars(
            select(Claim.claim_id)
            .where(
                sa_or(
                    sa_and(
                        Claim.subject_id.in_(affected),
                        Claim.subject_mention_id.is_(None),
                    ),
                    sa_and(
                        Claim.object_id.in_(affected),
                        Claim.object_mention_id.is_(None),
                    ),
                ),
                Claim.retracted_at.is_(None),
            )
            .order_by(Claim.claim_id)
        )
    )


def confirm_match(
    session: Session,
    *,
    actor: str,
    note: str,
    parent_revision_id: int,
    mention_a: str,
    mention_b: str,
    candidate_id: str | None = None,
) -> AdjudicationResult:
    """Two mentions name the same entity: move one entity's mentions onto the other.

    The survivor is the entity of ``mention_a``.  The absorbed entity is **not**
    deleted — its id is retained forever and its lineage is recoverable from
    the ledger (ADR-028 §5), which is what makes the merge reversible.
    """
    scope = _entities_of(session, [mention_a, mention_b])
    if len(scope) < 2:
        raise AdjudicationError(
            "both mentions already belong to the same entity (or one is "
            "unresolved); there is nothing to confirm"
        )
    check_scope_is_current(
        session, parent_revision_id=parent_revision_id, scope=scope
    )
    survivor = _active_entity(session, mention_a)
    absorbed = _active_entity(session, mention_b)
    decision, revision = _open_decision(
        session,
        mode="confirm_match",
        actor=actor,
        note=note,
        parent_revision_id=parent_revision_id,
        candidate_id=candidate_id,
        input_mentions=[mention_a, mention_b],
    )
    moved = _move_mentions(
        session,
        mention_ids=_mentions_of_entity(session, absorbed),
        target_entity_id=survivor,
        revision_id=revision.revision_id,
    )
    _settle_candidate(session, candidate_id, "confirmed", decision.decision_id)
    rebuild_canonical_map(session)
    return AdjudicationResult(
        decision=decision,
        revision=revision,
        moved_mentions=moved,
        surviving_entity_id=survivor,
    )


def reject_match(
    session: Session,
    *,
    actor: str,
    note: str,
    parent_revision_id: int,
    mention_a: str,
    mention_b: str,
    evidence_basis: str,
    candidate_id: str | None = None,
) -> AdjudicationResult:
    """These two are different people.  Writes a durable, versioned constraint.

    No membership changes — a reject is a statement about the *future*: this
    pair is not re-suggested while the constraint holds (spec 05 §3.3).
    """
    pair = tuple(sorted((mention_a, mention_b)))
    decision, revision = _open_decision(
        session,
        mode="reject_match",
        actor=actor,
        note=note,
        parent_revision_id=parent_revision_id,
        candidate_id=candidate_id,
        input_mentions=list(pair),
    )
    previous = session.scalar(
        select(IdentityNegativeConstraint)
        .where(
            IdentityNegativeConstraint.mention_a == pair[0],
            IdentityNegativeConstraint.mention_b == pair[1],
            IdentityNegativeConstraint.superseded_by.is_(None),
        )
        .order_by(IdentityNegativeConstraint.version.desc())
    )
    constraint = IdentityNegativeConstraint(
        constraint_id=new_id("neg"),
        mention_a=pair[0],
        mention_b=pair[1],
        version=(previous.version + 1) if previous is not None else 1,
        decision_id=decision.decision_id,
        evidence_basis=evidence_basis,
    )
    session.add(constraint)
    session.flush()
    if previous is not None:
        # Superseded, never erased: the history of both readings is kept
        # (Article VIII).
        previous.superseded_by = constraint.constraint_id
        session.flush()
    _settle_candidate(session, candidate_id, "rejected", decision.decision_id)
    return AdjudicationResult(
        decision=decision, revision=revision, constraint_id=constraint.constraint_id
    )


def split_entity(
    session: Session,
    *,
    actor: str,
    note: str,
    parent_revision_id: int,
    entity_id: str,
    mention_ids: list[str],
    target_entity_id: str | None = None,
) -> AdjudicationResult:
    """Move selected mentions off an entity, onto a new or restored one."""
    if not mention_ids:
        raise AdjudicationError("a split must name the mentions that move")
    check_scope_is_current(
        session, parent_revision_id=parent_revision_id, scope={entity_id}
    )
    held = set(_mentions_of_entity(session, entity_id))
    stray = sorted(set(mention_ids) - held)
    if stray:
        raise AdjudicationError(
            f"mentions {stray} do not currently belong to entity {entity_id!r}"
        )
    if set(mention_ids) == held:
        raise AdjudicationError(
            "a split that moves every mention is a rename, not a split; it would "
            "leave the original entity empty and change nothing that is knowable"
        )

    source = session.get(Entity, entity_id)
    if target_entity_id is None:
        first = session.get(Mention, sorted(mention_ids)[0])
        target = Entity(
            entity_id=new_id("ent"),
            entity_type=source.entity_type,
            label=first.raw_text if first is not None else source.label,
        )
        session.add(target)
        session.flush()
        target_entity_id = target.entity_id
        created = target_entity_id
    else:
        if session.get(Entity, target_entity_id) is None:
            raise AdjudicationError(f"entity {target_entity_id!r} does not exist")
        created = None

    decision, revision = _open_decision(
        session,
        mode="split_entity",
        actor=actor,
        note=note,
        parent_revision_id=parent_revision_id,
        candidate_id=None,
        input_mentions=sorted(mention_ids),
    )
    moved = _move_mentions(
        session,
        mention_ids=sorted(mention_ids),
        target_entity_id=target_entity_id,
        revision_id=revision.revision_id,
    )
    unattributable = _unattributable_claims(
        session, entity_id=entity_id, moved_mentions=set(moved)
    )
    rebuild_canonical_map(session)
    return AdjudicationResult(
        decision=decision,
        revision=revision,
        moved_mentions=moved,
        surviving_entity_id=entity_id,
        new_entity_id=created,
        unattributable_claims=unattributable,
    )


def mark_unresolved(
    session: Session,
    *,
    actor: str,
    note: str,
    parent_revision_id: int,
    mention_a: str,
    mention_b: str,
    candidate_id: str | None = None,
) -> AdjudicationResult:
    """"We looked and we cannot tell" — an explicit decision, not an absence.

    Keeps the pair visible in an unresolved list (Article VIII) instead of
    letting it fall out of the queue and look settled.
    """
    decision, revision = _open_decision(
        session,
        mode="mark_unresolved",
        actor=actor,
        note=note,
        parent_revision_id=parent_revision_id,
        candidate_id=candidate_id,
        input_mentions=sorted((mention_a, mention_b)),
    )
    _settle_candidate(session, candidate_id, "unresolved", decision.decision_id)
    return AdjudicationResult(decision=decision, revision=revision)


def _active_entity(session: Session, mention_id: str) -> str:
    entity_id = session.scalar(
        select(IdentityMembership.entity_id).where(
            IdentityMembership.mention_id == mention_id,
            IdentityMembership.closed_revision_id.is_(None),
        )
    )
    if entity_id is None:
        raise AdjudicationError(
            f"mention {mention_id!r} belongs to no entity; resolve it before "
            "adjudicating it against another"
        )
    return entity_id


def _settle_candidate(
    session: Session, candidate_id: str | None, disposition: str, decision_id: str
) -> None:
    if candidate_id is None:
        return
    candidate = session.get(ErCandidate, candidate_id)
    if candidate is None:
        raise AdjudicationError(f"candidate {candidate_id!r} does not exist")
    if candidate.disposition != "open":
        raise AdjudicationError(
            f"candidate {candidate_id!r} is already {candidate.disposition}"
        )
    candidate.disposition = disposition
    candidate.decision_id = decision_id
    session.flush()


__all__ = [
    "ADJUDICATION_MODES",
    "AdjudicationError",
    "AdjudicationResult",
    "StaleRevisionError",
    "check_scope_is_current",
    "confirm_match",
    "mark_unresolved",
    "reject_match",
    "split_entity",
]
