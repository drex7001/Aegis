"""Why is this edge here? (T21; GOAL.md §18, specs/06 §2.1)

The question the platform exists to answer.  A graph that shows a line between
two people without being able to say *why* is an accusation with no evidence
behind it — so every rendered edge must open onto the claims, the sources, the
gradings, the disagreements, and the identity decisions that produced it.

Three rules shape what these functions return:

**Nothing is summarized into a verdict.**  Reliability, credibility and
verification come back separately (Article III), and corroboration sits beside
contradiction rather than being netted against it (Article VIII).  The caller
renders; this layer reports.

**Authorization is applied in the query, not after it.**  Claims a caller may
not read never enter the result, so the counts and the identity line are
computed over exactly what that caller can see.  A provenance panel that leaked
"there are 3 more claims you cannot see" would leak the claims' existence.

**Identity is part of the provenance.**  An edge can exist because two mentions
were adjudicated to be one person; if so, the decision that did it — who, when,
and on what note — belongs in the answer as much as any source record does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from aegis.er.canonical import canonical_entity
from aegis.store import (
    Claim,
    ClaimRelation,
    Entity,
    EntityCanonicalMap,
    IdentityDecision,
    IdentityMembership,
    Mention,
    Source,
    SourceRecord,
)

#: specs/06 §2.1 caps the route at 200 claims. An edge with more support than
#: that is a rendering problem, not an evidence problem — the cap is disclosed
#: in the response (``truncated``) rather than silently applied.
MAX_CLAIMS = 200


@dataclass
class ClaimProvenance:
    """One claim, with everything needed to judge it — and nothing fused."""

    claim: Claim
    source: Source | None
    record: SourceRecord | None
    corroborated_by: list[str] = field(default_factory=list)
    contradicted_by: list[str] = field(default_factory=list)
    subject_mention: Mention | None = None
    object_mention: Mention | None = None


@dataclass
class IdentityLine:
    """A decision that put a mention where it now is."""

    decision: IdentityDecision
    entity_id: str


@dataclass
class WhyConnected:
    """The full answer for one pair of entities."""

    subject_id: str
    object_id: str
    #: The ids actually queried, after resolving through the canonical map. They
    #: differ from the requested ids when the caller followed a stale link, and
    #: saying so is more useful than silently answering a different question.
    resolved_subject_id: str
    resolved_object_id: str
    claims: list[ClaimProvenance] = field(default_factory=list)
    identity_line: list[IdentityLine] = field(default_factory=list)
    truncated: bool = False

    @property
    def record_count(self) -> int:
        return len({p.record.record_id for p in self.claims if p.record is not None})


def _absorbed_ids(session: Session, entity_id: str) -> set[str]:
    """Every id that currently resolves to this entity, including itself.

    A claim written before a merge still names the id it was written against.
    Asking only about the surviving id would answer "no evidence" for an edge
    the graph is actively drawing.
    """
    return {entity_id} | {
        absorbed
        for (absorbed,) in session.execute(
            select(EntityCanonicalMap.entity_id).where(
                EntityCanonicalMap.canonical_entity_id == entity_id
            )
        )
    }


def _relation_ids(session: Session, claim_ids: Sequence[str]) -> dict[str, dict[str, list[str]]]:
    """Relations touching these claims, indexed from both ends.

    Directionality is a recording artefact: a claim contradicted by another is
    contested whichever way the row was written (Article VIII).
    """
    index: dict[str, dict[str, list[str]]] = {}
    if not claim_ids:
        return index
    rows = session.execute(
        select(
            ClaimRelation.from_claim, ClaimRelation.to_claim, ClaimRelation.relation
        ).where(
            or_(
                ClaimRelation.from_claim.in_(claim_ids),
                ClaimRelation.to_claim.in_(claim_ids),
            )
        )
    )
    for from_claim, to_claim, relation in rows:
        index.setdefault(from_claim, {}).setdefault(relation, []).append(to_claim)
        index.setdefault(to_claim, {}).setdefault(relation, []).append(from_claim)
    return index


def _hydrate(
    session: Session, claims: Sequence[Claim]
) -> list[ClaimProvenance]:
    """Attach source, record, mentions and relations to each claim."""
    if not claims:
        return []
    record_ids = {claim.record_id for claim in claims}
    records = {
        record.record_id: record
        for record in session.scalars(
            select(SourceRecord).where(SourceRecord.record_id.in_(record_ids))
        )
    }
    sources = {
        source.source_id: source
        for source in session.scalars(
            select(Source).where(
                Source.source_id.in_({r.source_id for r in records.values()})
            )
        )
    }
    mention_ids = {
        mention_id
        for claim in claims
        for mention_id in (claim.subject_mention_id, claim.object_mention_id)
        if mention_id is not None
    }
    mentions = {
        mention.mention_id: mention
        for mention in session.scalars(
            select(Mention).where(Mention.mention_id.in_(mention_ids))
        )
    } if mention_ids else {}
    relations = _relation_ids(session, [claim.claim_id for claim in claims])

    hydrated = []
    for claim in claims:
        record = records.get(claim.record_id)
        touching = relations.get(claim.claim_id, {})
        hydrated.append(
            ClaimProvenance(
                claim=claim,
                record=record,
                source=sources.get(record.source_id) if record is not None else None,
                corroborated_by=sorted(touching.get("corroborates", [])),
                contradicted_by=sorted(touching.get("contradicts", [])),
                subject_mention=mentions.get(claim.subject_mention_id),
                object_mention=mentions.get(claim.object_mention_id),
            )
        )
    return hydrated


def _identity_line(session: Session, entity_ids: set[str]) -> list[IdentityLine]:
    """The decisions that shaped these entities' membership, oldest first.

    This is what makes an edge's *identity* auditable: if two nodes are one node
    because a human said so, the panel shows who said it and why.
    """
    revision_ids = {
        revision_id
        for (revision_id,) in session.execute(
            select(IdentityMembership.opened_revision_id).where(
                IdentityMembership.entity_id.in_(entity_ids)
            )
        )
    } | {
        revision_id
        for (revision_id,) in session.execute(
            select(IdentityMembership.closed_revision_id).where(
                IdentityMembership.entity_id.in_(entity_ids),
                IdentityMembership.closed_revision_id.isnot(None),
            )
        )
    }
    if not revision_ids:
        return []
    decisions = session.scalars(
        select(IdentityDecision)
        .where(IdentityDecision.result_revision_id.in_(revision_ids))
        .order_by(IdentityDecision.result_revision_id)
    ).all()
    # Which entity each decision touched, for display beside it.
    owner: dict[int, str] = {}
    for entity_id, opened in session.execute(
        select(IdentityMembership.entity_id, IdentityMembership.opened_revision_id).where(
            IdentityMembership.entity_id.in_(entity_ids)
        )
    ):
        owner.setdefault(opened, entity_id)
    return [
        IdentityLine(decision=d, entity_id=owner.get(d.result_revision_id, ""))
        for d in decisions
    ]


def why_connected(
    session: Session,
    *,
    subject_id: str,
    object_id: str,
    filters: Sequence[ColumnElement[bool]] = (),
    limit: int = MAX_CLAIMS,
) -> WhyConnected | None:
    """Every claim a caller may see that connects two entities, with its evidence.

    ``filters`` are the caller's authorization conditions and are applied inside
    the query — see the module docstring. Returns ``None`` when either entity
    does not exist, so the route can 404 without leaking which one.
    """
    if session.get(Entity, subject_id) is None or session.get(Entity, object_id) is None:
        return None

    resolved_subject = canonical_entity(session, subject_id)
    resolved_object = canonical_entity(session, object_id)
    subject_ids = _absorbed_ids(session, resolved_subject)
    object_ids = _absorbed_ids(session, resolved_object)

    # Undirected: the edge exists whichever way round the claim was recorded,
    # and symmetric predicates are normalized at write time so the stored
    # direction carries no meaning of its own.
    endpoints = or_(
        Claim.subject_id.in_(subject_ids) & Claim.object_id.in_(object_ids),
        Claim.subject_id.in_(object_ids) & Claim.object_id.in_(subject_ids),
    )
    rows = session.scalars(
        select(Claim)
        .where(endpoints, *filters)
        .order_by(Claim.recorded_at, Claim.claim_id)
        .limit(limit + 1)
    ).all()
    truncated = len(rows) > limit
    claims = list(rows[:limit])

    return WhyConnected(
        subject_id=subject_id,
        object_id=object_id,
        resolved_subject_id=resolved_subject,
        resolved_object_id=resolved_object,
        claims=_hydrate(session, claims),
        identity_line=_identity_line(session, subject_ids | object_ids),
        truncated=truncated,
    )


def claim_provenance(
    session: Session, *, claim_id: str, filters: Sequence[ColumnElement[bool]] = ()
) -> ClaimProvenance | None:
    """Provenance for a single claim — the generic form (B-14, specs/06 §2.1).

    Any value a UI renders from a claim (a property, an alias, an edge label)
    can reach its evidence through this, so provenance is not a graph-only
    feature.
    """
    claim = session.scalar(select(Claim).where(Claim.claim_id == claim_id, *filters))
    if claim is None:
        return None
    return _hydrate(session, [claim])[0]


def identity_history(session: Session, *, entity_id: str) -> list[IdentityLine] | None:
    """The decision line for one entity (specs/06 §2.2): who, when, why."""
    if session.get(Entity, entity_id) is None:
        return None
    return _identity_line(session, _absorbed_ids(session, canonical_entity(session, entity_id)))


__all__ = [
    "MAX_CLAIMS",
    "ClaimProvenance",
    "IdentityLine",
    "WhyConnected",
    "claim_provenance",
    "identity_history",
    "why_connected",
]
