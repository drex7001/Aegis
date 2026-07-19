"""The v2 edge projection builder (T21; spec 02 §7, ADR-029, ADR-030).

Three rules govern everything here, and each exists because the Phase-1 view
broke it:

**Resolve, never rewrite.**  Entity arguments are resolved at build time, so
merging B into A collapses their nodes and edges and splitting B back out
restores them — while every claim row still says exactly what it always said
(ADR-029 §3).  Identity is a property of the projection, not of the claim.

Resolution has two paths, and the order matters.  A claim with a **mention
anchor** resolves through that mention's active membership: the anchor is the
textual evidence the argument came from, so wherever adjudication moves the
mention, the claim follows — which is what makes a split *restore* the
pre-merge edges rather than merely add new ones.  A claim without an anchor can
only be resolved through ``entity_canonical_map``, which follows merges but
cannot follow splits: nothing records which side of the split it belonged to.
That is not a gap in this module — it is why a split queues its unanchored
claims for re-adjudication instead of guessing (spec 02 §3.1 rule 4), and why
anchors are required for observed and reported claims in the first place.

**Segment, never collapse.**  One row is one *maximal interval over which the
same supporting claim set holds*.  Claims covering 2019 and 2023 produce two
segments with a gap between them, because nobody claimed anything about 2021
and a projection that says otherwise is fabricating evidence.

**Summarize, never average.**  There is no aggregate weight.  The support
summary carries each supporting claim's three grading dimensions separately
(Article III), the corroboration and contradiction counts around it, and the
method that produced the summary.  A reader can always get back to the claims;
an averaged scalar is a one-way door.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
import hashlib
from typing import Any, Iterable, NamedTuple

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from aegis.er.ledger import active_revision_id
from aegis.ontology import Ontology
from aegis.store import (
    Claim,
    ClaimRelation,
    EdgeProjection,
    EntityCanonicalMap,
    IdentityMembership,
    Source,
    SourceRecord,
)

#: Bumped whenever the segmentation or summary shape changes, so a row built by
#: an older builder is identifiable without guessing from its contents.
BUILDER_VERSION = "edge-projection-v2"

#: Named in every support summary. The name is a promise about *what the
#: numbers mean*: claims are grouped by segment and reported individually — no
#: score is combined across them.
AGGREGATION_METHOD = "segmented-support"
AGGREGATION_METHOD_VERSION = 1

#: Sentinels for unbounded interval ends. ``date.min``/``date.max`` are real
#: dates, so ordinary comparison works; they never reach the database, because
#: :func:`_to_bound` converts them back to NULL.
_NEG_INF = date.min
_POS_INF = date.max
_DAY = timedelta(days=1)


class _Interval(NamedTuple):
    """A claim's validity as a half-open ``[start, end)`` range."""

    start: date
    end: date
    claim_id: str


@dataclass
class EdgeProjectionReport:
    """What one rebuild produced — and what it deliberately excluded."""

    edges: int = 0
    segments: int = 0
    claims_considered: int = 0
    collapsed_endpoints: int = 0
    #: Endpoints resolved through a mention anchor vs. through the canonical
    #: map.  Reported because the second kind cannot survive a split, so the
    #: ratio is a live measure of how reversible the graph actually is.
    anchor_resolved: int = 0
    map_resolved: int = 0
    built_at_revision_id: int = 0
    ontology_version: str = ""
    builder_version: str = BUILDER_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "edges": self.edges,
            "segments": self.segments,
            "claims_considered": self.claims_considered,
            "collapsed_endpoints": self.collapsed_endpoints,
            "anchor_resolved": self.anchor_resolved,
            "map_resolved": self.map_resolved,
            "built_at_revision_id": self.built_at_revision_id,
            "ontology_version": self.ontology_version,
            "builder_version": self.builder_version,
        }


@dataclass
class _Group:
    """Claims resolving to one canonical (subject, object, predicate)."""

    claims: list[Claim] = field(default_factory=list)


def _edge_id(
    subject_id: str,
    object_id: str,
    predicate: str,
    segment_from: date | None,
    segment_to: date | None,
) -> str:
    """Content-derived, so the same segment keeps its id across rebuilds.

    A random id per build would make every rebuild look like a total change and
    would make two builds impossible to diff.  The stamps, not the id, are what
    distinguish a fresh row from a stale one.
    """
    material = "|".join(
        [
            subject_id,
            object_id,
            predicate,
            segment_from.isoformat() if segment_from else "",
            segment_to.isoformat() if segment_to else "",
        ]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"edg_{digest[:32]}"


def _intervals(claims: Iterable[Claim]) -> list[_Interval]:
    """Claim validity as half-open ranges, with NULL bounds meaning unbounded.

    Half-open is what makes adjacency work: a claim ending 2019-12-31 and one
    starting 2020-01-01 must not leave a phantom one-day gap between segments.
    """
    return [
        _Interval(
            start=claim.valid_from or _NEG_INF,
            end=(claim.valid_to + _DAY) if claim.valid_to else _POS_INF,
            claim_id=claim.claim_id,
        )
        for claim in claims
    ]


def _segment(intervals: list[_Interval]) -> list[tuple[date, date, tuple[str, ...]]]:
    """Split into maximal ranges over which the covering claim set is constant.

    Every interval boundary becomes a cut point; each elementary range between
    consecutive cuts gets the set of claims covering it; ranges with no claims
    are dropped (that is the gap); and neighbours with an identical claim set
    are merged back together so the result is *maximal* rather than merely
    correct.
    """
    cuts = sorted({bound for interval in intervals for bound in (interval.start, interval.end)})

    elementary: list[tuple[date, date, tuple[str, ...]]] = []
    for low, high in zip(cuts, cuts[1:]):
        covering = tuple(
            sorted(i.claim_id for i in intervals if i.start <= low < i.end)
        )
        if covering:
            elementary.append((low, high, covering))

    merged: list[tuple[date, date, tuple[str, ...]]] = []
    for low, high, covering in elementary:
        if merged and merged[-1][2] == covering and merged[-1][1] == low:
            merged[-1] = (merged[-1][0], high, covering)
        else:
            merged.append((low, high, covering))
    return merged


def _to_bound(value: date, *, upper: bool) -> date | None:
    """Sentinel → NULL, and half-open upper bound → inclusive date."""
    if upper:
        return None if value == _POS_INF else value - _DAY
    return None if value == _NEG_INF else value


def relation_index(
    session: Session, *, visible_to: set[str] | None = None
) -> dict[str, list[tuple[str, str]]]:
    """claim → the relations touching it, as ``(other_claim, relation)``.

    ``claim_relation`` is stored directionally, but "this claim is contradicted"
    is true of both ends: a claim nobody pointed *at* is not thereby
    uncontested (Article VIII).  So each relation is indexed under both.

    ``visible_to`` restricts both ends to a set of claim ids.  The build path
    passes nothing (it summarizes for no particular reader); a read path passes
    the caller's visible claims, because a relation to a claim they may not see
    would otherwise report that claim's existence as a count (specs/03 §4 —
    absent, not counted).
    """
    query = select(
        ClaimRelation.from_claim, ClaimRelation.to_claim, ClaimRelation.relation
    )
    if visible_to is not None:
        if not visible_to:
            return {}
        query = query.where(
            ClaimRelation.from_claim.in_(visible_to),
            ClaimRelation.to_claim.in_(visible_to),
        )
    index: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for from_claim, to_claim, relation in session.execute(query):
        index[from_claim].append((to_claim, relation))
        index[to_claim].append((from_claim, relation))
    return index


def support_summary(
    claims: list[Claim],
    reliability: dict[str, str | None],
    relations: dict[str, list[tuple[str, str]]],
) -> dict[str, Any]:
    """The inspectable summary that replaces the aggregate weight.

    Public because the read path calls it too (T22): a caller who may not see
    every supporting claim must get a summary over the claims they *can* see,
    and computing that with a second, similar-looking function is how the graph
    view and the provenance panel would quietly start disagreeing.

    Reliability is read from the *source*, not the claim, because that is where
    the ontology grades it — a claim does not get more reliable by being
    repeated.

    The segment-level counts are of **distinct relations**, not a sum of
    per-claim counts.  Two claims on one edge that contradict each other are
    one disagreement; reporting two would inflate the very number a reader
    consults to judge how contested the edge is.  Per-claim counts stay on the
    claim entries, where double-counting is impossible by construction.
    """
    entries = []
    distinct: set[tuple[str, str, str]] = set()
    for claim in sorted(claims, key=lambda c: c.claim_id):
        touching = relations.get(claim.claim_id, [])
        counts = {"corroborates": 0, "contradicts": 0}
        for other, relation in touching:
            counts[relation] = counts.get(relation, 0) + 1
            # Normalized pair key: the same relation reached from either end is
            # one relation.  A relation pointing outside the segment still
            # counts — it contests this edge just as much.
            low, high = sorted((claim.claim_id, other))
            distinct.add((low, high, relation))
        entries.append(
            {
                "claim_id": claim.claim_id,
                "record_id": claim.record_id,
                # Three dimensions, never fused into one number (Article III).
                "reliability": reliability.get(claim.record_id),
                "credibility": claim.credibility_normalized,
                "verification": claim.verification_status,
                "analytic_confidence": claim.analytic_confidence,
                "assertion_type": claim.assertion_type,
                "handling_code": claim.handling_code,
                "corroborated_by": counts["corroborates"],
                "contradicted_by": counts["contradicts"],
            }
        )
    corroboration = sum(1 for _, _, rel in distinct if rel == "corroborates")
    contradiction = sum(1 for _, _, rel in distinct if rel == "contradicts")
    return {
        "method": AGGREGATION_METHOD,
        "method_version": AGGREGATION_METHOD_VERSION,
        "claims": entries,
        "corroboration_count": corroboration,
        "contradiction_count": contradiction,
        # DISTINCT records. Deliberately not called "independent": independence
        # is a claim about source derivation Aegis cannot yet make (ADR-030 §3).
        "record_count": len({claim.record_id for claim in claims}),
    }


def _handling_rank(code: str | None) -> int:
    """Python twin of the SQL ``handling_code_rank`` (migration 0006).

    Unknown handling ranks maximally restricted, so a vocabulary the code has
    not seen fails closed rather than leaking.
    """
    return {"open": 0, "restricted": 1, "sensitive": 2}.get(code or "", 999)


def rebuild_edge_projection(
    session: Session, *, ontology: Ontology
) -> EdgeProjectionReport:
    """Rebuild the whole projection from claims. Idempotent by construction.

    Full rebuild rather than incremental update: the table is a cache, an
    identity decision can change any row in it, and a rebuild that is cheap to
    reason about is worth more than one that is cheap to run (Article XIII).
    """
    revision_id = active_revision_id(session)
    report = EdgeProjectionReport(
        built_at_revision_id=revision_id, ontology_version=ontology.version
    )

    canonical = {
        entity_id: canonical_id
        for entity_id, canonical_id in session.execute(
            select(
                EntityCanonicalMap.entity_id, EntityCanonicalMap.canonical_entity_id
            )
        )
    }
    # mention → the entity it currently belongs to. The authoritative path:
    # adjudication moves memberships, so this follows both merges and splits.
    anchors = {
        mention_id: entity_id
        for mention_id, entity_id in session.execute(
            select(
                IdentityMembership.mention_id, IdentityMembership.entity_id
            ).where(IdentityMembership.closed_revision_id.is_(None))
        )
    }

    def resolve(entity_id: str, mention_id: str | None) -> str:
        if mention_id is not None and mention_id in anchors:
            report.anchor_resolved += 1
            return anchors[mention_id]
        report.map_resolved += 1
        return canonical.get(entity_id, entity_id)

    reliability = dict(
        session.execute(
            select(SourceRecord.record_id, Source.reliability_normalized).join(
                Source, Source.source_id == SourceRecord.source_id
            )
        ).all()
    )
    relations = relation_index(session)

    groups: dict[tuple[str, str, str], _Group] = defaultdict(_Group)
    claims = session.scalars(
        select(Claim)
        .where(Claim.object_id.isnot(None), Claim.retracted_at.is_(None))
        .order_by(Claim.claim_id)
    ).all()
    for claim in claims:
        report.claims_considered += 1
        subject = resolve(claim.subject_id, claim.subject_mention_id)
        obj = resolve(claim.object_id, claim.object_mention_id)
        spec = ontology.predicates.get(claim.predicate)
        if spec is not None and spec.symmetric and obj < subject:
            # Symmetric arguments are normalized at *write* time, but identity
            # resolution happens later and can reverse the pair: after a merge,
            # "A allied_with C" and "C allied_with B(→A)" point opposite ways
            # while describing one undirected edge.  Re-normalizing here is
            # what makes them collapse into a single edge instead of two
            # mirror images — the failure the Phase-1 view shipped with.
            subject, obj = obj, subject
        if subject == obj:
            # A merge just made both ends of this edge the same entity. The
            # claim is untouched and the split will bring the edge back; a
            # self-loop in the projection would be an artefact, not a fact.
            report.collapsed_endpoints += 1
            continue
        groups[(subject, obj, claim.predicate)].claims.append(claim)

    by_claim = {claim.claim_id: claim for claim in claims}
    rows: list[dict[str, Any]] = []
    for (subject, obj, predicate), group in sorted(groups.items()):
        report.edges += 1
        for low, high, claim_ids in _segment(_intervals(group.claims)):
            segment_from = _to_bound(low, upper=False)
            segment_to = _to_bound(high, upper=True)
            segment_claims = [by_claim[claim_id] for claim_id in claim_ids]
            rows.append(
                {
                    "edge_id": _edge_id(
                        subject, obj, predicate, segment_from, segment_to
                    ),
                    "subject_id": subject,
                    "object_id": obj,
                    "predicate": predicate,
                    "segment_from": segment_from,
                    "segment_to": segment_to,
                    "claim_ids": list(claim_ids),
                    "record_count": len({c.record_id for c in segment_claims}),
                    "support": support_summary(
                        segment_claims, reliability, relations
                    ),
                    "handling_rank": max(
                        _handling_rank(c.handling_code) for c in segment_claims
                    ),
                    "built_at_revision_id": revision_id,
                    "ontology_version": ontology.version,
                    "builder_version": BUILDER_VERSION,
                }
            )
            report.segments += 1

    # Core delete + bulk insert rather than ORM objects.  Edge ids are
    # content-derived, so a rebuild in a session that already loaded the
    # previous build would otherwise collide in the identity map: same primary
    # key, different instance.  Expunging the stale instances keeps a caller
    # that holds one from reading a row that no longer exists.
    for stale in list(session.identity_map.values()):
        if isinstance(stale, EdgeProjection):
            session.expunge(stale)
    session.execute(delete(EdgeProjection))
    if rows:
        session.execute(insert(EdgeProjection), rows)

    session.flush()
    return report


@dataclass(frozen=True)
class ProjectionStamps:
    """What built the rows a response is made of (spec 02 §7, specs/06 §3).

    Carried on every projection-backed response so a stale read is *detectable*
    rather than silently wrong.  An empty projection reports ``None`` versions
    rather than the current ones: claiming a build that never happened is the
    precise failure the stamps exist to prevent.
    """

    built_at_revision_id: int | None
    active_revision_id: int
    ontology_version: str | None
    builder_version: str | None
    stale: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "built_at_revision_id": self.built_at_revision_id,
            "active_revision_id": self.active_revision_id,
            "ontology_version": self.ontology_version,
            "builder_version": self.builder_version,
            "stale": self.stale,
        }


def projection_stamps(session: Session) -> ProjectionStamps:
    """The stamps of the *oldest* row in the projection, plus staleness.

    Oldest, not newest: a rebuild is all-or-nothing, so the two agree in normal
    operation — and if they ever disagree, the honest thing to report is the
    weakest guarantee in the table, not the strongest.
    """
    oldest, ontology_version, builder_version = session.execute(
        select(
            func.min(EdgeProjection.built_at_revision_id),
            func.min(EdgeProjection.ontology_version),
            func.min(EdgeProjection.builder_version),
        )
    ).one()
    active = active_revision_id(session)
    return ProjectionStamps(
        built_at_revision_id=oldest,
        active_revision_id=active,
        ontology_version=ontology_version,
        builder_version=builder_version,
        stale=oldest is not None and oldest < active,
    )


def is_stale(session: Session) -> bool:
    """Was any row built at an older identity revision than the active one?

    Staleness is a fact about the projection, not an error: a stale projection
    is usable and honest as long as it is *detectable* (spec 02 §7 stamps).
    """
    oldest = session.scalar(select(func.min(EdgeProjection.built_at_revision_id)))
    if oldest is None:
        return False
    return oldest < active_revision_id(session)


__all__ = [
    "AGGREGATION_METHOD",
    "AGGREGATION_METHOD_VERSION",
    "BUILDER_VERSION",
    "EdgeProjectionReport",
    "is_stale",
    "projection_stamps",
    "rebuild_edge_projection",
    "relation_index",
    "support_summary",
]
