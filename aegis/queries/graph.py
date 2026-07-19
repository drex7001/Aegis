"""Bounded, authorized traversal over the edge projection (T22; specs/06 §2.6).

This replaces the anonymous ``/api/graph`` bulk dump that ADR-026 retired. Three
properties distinguish it from what it replaces, and each was a finding against
the old surface:

**Nothing is unbounded.**  Expansion takes seeds, a hop limit, and an element
budget; every response says whether it hit them (``truncated``).  A graph API
that will hand over the whole corpus in one call is a scraping surface however
its rows are classified.

**Authorization is a property of the query, not of the response.**  An edge is
visible when the caller can read at least one claim supporting it, expressed as
a correlated ``EXISTS`` over :func:`aegis.authz.filters.claim_filters`.  The
support summary is then rebuilt from *those* claims only — so an edge held up by
one open claim and one restricted claim looks, to a low-clearance caller,
exactly like an edge held up by the open claim alone.  Reporting the restricted
one as a count would disclose its existence (specs/03 §4: absent, not counted).

That cuts the other way too, and it is worth naming: a contradiction the caller
may not read is invisible to them, so an edge can look less contested than it
is.  The constitution already chose between these (Article VIII wants the
disagreement visible; specs/03 §4 and specs/07 §5 forbid teasing hidden rows),
and the marked-redaction mode that would show "1 hidden" is deferred to P7
(H-25).  Until then the rule is absence, applied consistently.

**No aggregate weight.**  Edges carry the ADR-030 support summary and the build
stamps.  The one place a display score is still computed is the legacy JSON
emitter, at the point of rendering, from visible claims.

``handling_rank`` on the row is deliberately *not* used as a pre-filter: it is
the maximum over all supporting claims, so filtering on it would hide edges a
caller is entitled to see through their open support.  It stays for coarse
operational queries; authorization runs through the claims.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Sequence

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from aegis.ontology import Ontology
from aegis.projections.edges import (
    ProjectionStamps,
    projection_stamps,
    relation_index,
    support_summary,
)
from aegis.store import Claim, EdgeProjection, Entity, EntityCanonicalMap, Source, SourceRecord

#: specs/06 §2.6 caps. Requests above them are clamped, not rejected: a client
#: asking for more than the platform will give should get the most it will give,
#: with the truncation disclosed (the pagination convention, specs/06 §4).
MAX_HOPS = 3
MAX_PATH_HOPS = 5
MAX_ELEMENTS = 2000
MAX_SEEDS = 100
#: Paths are enumerated, not sampled, so this bounds the enumeration itself.
MAX_PATHS = 25


@dataclass(frozen=True)
class GraphNode:
    """One entity on the canvas."""

    entity_id: str
    label: str
    entity_type: str


@dataclass(frozen=True)
class GraphEdge:
    """One time segment of one predicate between two entities.

    Two entities related over disjoint intervals are two edges, never one
    continuous line (ADR-030) — so ``segment_from``/``segment_to`` are part of
    the identity of the thing, not decoration on it.
    """

    edge_id: str
    subject_id: str
    object_id: str
    predicate: str
    category: str | None
    segment_from: date | None
    segment_to: date | None
    record_count: int
    support: dict[str, Any]


@dataclass
class GraphView:
    """What one bounded traversal returned, and what it left out."""

    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    seed_ids: list[str] = field(default_factory=list)
    #: Seeds after resolution through the canonical map. A caller following a
    #: link written before a merge asked about an absorbed id; answering about
    #: the survivor while saying so beats answering "no such entity".
    resolved_seed_ids: list[str] = field(default_factory=list)
    truncated: bool = False
    stamps: ProjectionStamps | None = None


@dataclass
class GraphPath:
    """One route between two entities: alternating nodes and edges."""

    entity_ids: list[str]
    edge_ids: list[str]

    @property
    def hops(self) -> int:
        return len(self.edge_ids)


@dataclass
class GraphPaths(GraphView):
    """Shortest routes between two entities, plus the elements they touch."""

    paths: list[GraphPath] = field(default_factory=list)


def _visible_edges(filters: Sequence[ColumnElement[bool]]):
    """An edge is visible when at least one claim behind it is readable.

    Correlated rather than pre-computed: the alternative is materializing every
    visible claim id in the process and passing it back down as an ``IN``, which
    is both slower and a different question — "which claims may you read" rather
    than "which edges do they support".
    """
    return (
        select(Claim.claim_id)
        .where(EdgeProjection.claim_ids.any(Claim.claim_id), *filters)
        .exists()
    )


def _time_overlap(valid_from: date | None, valid_to: date | None):
    """Segments overlapping a window, with NULL bounds meaning unbounded.

    An open-ended segment overlaps every later window: "still true as far as we
    know" must not disappear from a query about last year.
    """
    conditions: list[ColumnElement[bool]] = []
    if valid_to is not None:
        conditions.append(
            or_(
                EdgeProjection.segment_from.is_(None),
                EdgeProjection.segment_from <= valid_to,
            )
        )
    if valid_from is not None:
        conditions.append(
            or_(
                EdgeProjection.segment_to.is_(None),
                EdgeProjection.segment_to >= valid_from,
            )
        )
    return conditions


def _category_predicates(ontology: Ontology, categories: Sequence[str]) -> list[str]:
    """Predicates in the requested ontology categories.

    An unknown category yields no predicates rather than an error: categories
    come from a domain module the core does not know, and a filter naming one
    this ontology has not loaded should return nothing, not 500.
    """
    wanted = {c.lower() for c in categories}
    return [
        name
        for name, spec in ontology.predicates.items()
        if spec.category is not None and spec.category.lower() in wanted
    ]


def _base_query(
    ontology: Ontology,
    filters: Sequence[ColumnElement[bool]],
    categories: Sequence[str],
    valid_from: date | None,
    valid_to: date | None,
):
    query = select(EdgeProjection).where(_visible_edges(filters))
    if categories:
        query = query.where(
            EdgeProjection.predicate.in_(_category_predicates(ontology, categories))
        )
    for condition in _time_overlap(valid_from, valid_to):
        query = query.where(condition)
    # Deterministic and *grouped*: a truncated result keeps an entity's edges
    # together instead of scattering them across the cut.
    return query.order_by(
        EdgeProjection.subject_id,
        EdgeProjection.object_id,
        EdgeProjection.predicate,
        EdgeProjection.segment_from,
        EdgeProjection.edge_id,
    )


def _resolve_seeds(session: Session, seed_ids: Sequence[str]) -> list[str]:
    if not seed_ids:
        return []
    mapped = dict(
        session.execute(
            select(
                EntityCanonicalMap.entity_id, EntityCanonicalMap.canonical_entity_id
            ).where(EntityCanonicalMap.entity_id.in_(seed_ids))
        ).all()
    )
    seen: list[str] = []
    for seed in seed_ids:
        resolved = mapped.get(seed, seed)
        if resolved not in seen:
            seen.append(resolved)
    return seen


def _visible_claim_ids(
    session: Session,
    edges: Iterable[EdgeProjection],
    filters: Sequence[ColumnElement[bool]],
) -> set[str]:
    candidates = {claim_id for edge in edges for claim_id in edge.claim_ids}
    if not candidates:
        return set()
    return set(
        session.scalars(
            select(Claim.claim_id).where(Claim.claim_id.in_(candidates), *filters)
        )
    )


def _hydrate(
    session: Session,
    ontology: Ontology,
    rows: list[EdgeProjection],
    filters: Sequence[ColumnElement[bool]],
    *,
    always_include: Sequence[str] = (),
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Rows → renderable elements, with every summary recomputed per caller.

    ``always_include`` keeps the entities the caller *asked about* on the canvas
    even when nothing connects them: "this person has no links you can see" and
    "this person does not exist" are different answers, and collapsing them into
    an empty response gives the reader the wrong one.
    """
    visible = _visible_claim_ids(session, rows, filters)
    claims = {
        claim.claim_id: claim
        for claim in session.scalars(
            select(Claim).where(Claim.claim_id.in_(visible))
        )
    }
    reliability = dict(
        session.execute(
            select(SourceRecord.record_id, Source.reliability_normalized).join(
                Source, Source.source_id == SourceRecord.source_id
            )
        ).all()
    )
    relations = relation_index(session, visible_to=visible)

    edges: list[GraphEdge] = []
    for row in rows:
        supporting = [claims[cid] for cid in row.claim_ids if cid in claims]
        if not supporting:  # pragma: no cover - _visible_edges guarantees ≥ 1
            continue
        spec = ontology.predicates.get(row.predicate)
        edges.append(
            GraphEdge(
                edge_id=row.edge_id,
                subject_id=row.subject_id,
                object_id=row.object_id,
                predicate=row.predicate,
                category=spec.category if spec is not None else None,
                segment_from=row.segment_from,
                segment_to=row.segment_to,
                # Recomputed, never read off the row: the stored count is over
                # all support, and this caller's view may be a subset of it.
                record_count=len({c.record_id for c in supporting}),
                support=support_summary(supporting, reliability, relations),
            )
        )

    entity_ids = (
        {e.subject_id for e in edges}
        | {e.object_id for e in edges}
        | set(always_include)
    )
    nodes = [
        GraphNode(entity_id=e.entity_id, label=e.label, entity_type=e.entity_type)
        for e in session.scalars(
            select(Entity)
            .where(Entity.entity_id.in_(entity_ids))
            .order_by(Entity.entity_id)
        )
    ]
    return nodes, edges


class _Budget:
    """Admits edges while nodes *and* edges stay inside the element cap.

    Shared by both expansion modes on purpose. When the overview counted only
    rows while the walk counted elements, ``max_elements=2`` returned two edges
    and four nodes — six elements — from the one mode that exists to be bounded.
    One accounting rule, one place to get it wrong.
    """

    def __init__(self, max_elements: int, reached: Iterable[str] = ()) -> None:
        self._max = max_elements
        self._reached: set[str] = set(reached)
        self._edges = 0
        self.full = False

    def admit(self, row: EdgeProjection) -> set[str] | None:
        """Take the row and return its new endpoints, or ``None`` when full."""
        fresh = {row.subject_id, row.object_id} - self._reached
        if self._edges + len(self._reached) + len(fresh) + 1 > self._max:
            self.full = True
            return None
        self._edges += 1
        self._reached |= fresh
        return fresh


def expand(
    session: Session,
    ontology: Ontology,
    *,
    filters: Sequence[ColumnElement[bool]],
    seed_ids: Sequence[str] = (),
    max_hops: int = 1,
    categories: Sequence[str] = (),
    valid_from: date | None = None,
    valid_to: date | None = None,
    max_elements: int = MAX_ELEMENTS,
) -> GraphView:
    """Breadth-first expansion from seeds, or a bounded overview without them.

    Empty seeds are not an error but a distinct, deliberate mode: the *bounded
    overview*, an authorized, capped, deterministically ordered slice used to
    open the canvas before entity search exists (T23c).  It is bounded by the
    same element budget as any expansion, which is what separates it from the
    bulk dump ADR-026 retired.
    """
    max_hops = max(0, min(max_hops, MAX_HOPS))
    max_elements = max(1, min(max_elements, MAX_ELEMENTS))
    base = _base_query(ontology, filters, categories, valid_from, valid_to)

    resolved = _resolve_seeds(session, list(seed_ids)[:MAX_SEEDS])
    view = GraphView(seed_ids=list(seed_ids), resolved_seed_ids=resolved)

    if not resolved:
        # One row costs at least one element, so no more than ``max_elements``
        # can ever fit; fetching one extra is how "there is more" is detected.
        fetched = list(session.scalars(base.limit(max_elements + 1)))
        budget = _Budget(max_elements)
        rows = [row for row in fetched if budget.admit(row) is not None]
        view.truncated = budget.full or len(fetched) > max_elements
    else:
        rows, view.truncated = _breadth_first(
            session, base, resolved, max_hops, max_elements
        )

    view.nodes, view.edges = _hydrate(
        session, ontology, rows, filters, always_include=resolved
    )
    view.stamps = projection_stamps(session)
    return view


def _breadth_first(
    session: Session,
    base,
    seeds: Sequence[str],
    max_hops: int,
    max_elements: int,
) -> tuple[list[EdgeProjection], bool]:
    """Hop-by-hop expansion, stopping at the hop limit or the element budget.

    The budget counts nodes *and* edges, because that is what the canvas has to
    draw and what specs/06 §2.6 bounds.  Hitting it stops the walk mid-hop
    rather than dropping a completed hop: a partial frontier is disclosed as
    truncation, while a silently missing hop looks like an absence of evidence.
    """
    frontier = list(seeds)
    budget = _Budget(max_elements, reached=seeds)
    collected: dict[str, EdgeProjection] = {}

    for _ in range(max_hops):
        if not frontier or budget.full:
            break
        rows = session.scalars(
            base.where(
                or_(
                    EdgeProjection.subject_id.in_(frontier),
                    EdgeProjection.object_id.in_(frontier),
                )
            )
        ).all()
        next_frontier: list[str] = []
        for row in rows:
            if row.edge_id in collected:
                continue
            fresh = budget.admit(row)
            if fresh is None:
                break
            collected[row.edge_id] = row
            next_frontier.extend(fresh)
        frontier = next_frontier

    ordered = sorted(
        collected.values(),
        key=lambda r: (r.subject_id, r.object_id, r.predicate, r.edge_id),
    )
    return ordered, budget.full


def paths(
    session: Session,
    ontology: Ontology,
    *,
    filters: Sequence[ColumnElement[bool]],
    from_id: str,
    to_id: str,
    max_hops: int = MAX_PATH_HOPS,
    categories: Sequence[str] = (),
    valid_from: date | None = None,
    valid_to: date | None = None,
    max_paths: int = MAX_PATHS,
) -> GraphPaths:
    """All shortest routes between two entities, bounded by hops and count.

    Shortest only: "every route under 5 hops" between two well-connected people
    is a combinatorial answer that no reader can audit, and a path nobody can
    check is exactly the kind of machine-produced insinuation Article IX exists
    to prevent.  A shortest path is short enough to open every edge on it.
    """
    max_hops = max(1, min(max_hops, MAX_PATH_HOPS))
    max_paths = max(1, min(max_paths, MAX_PATHS))
    base = _base_query(ontology, filters, categories, valid_from, valid_to)

    # One element back means both ids resolved to the same entity — a merge
    # happened between the caller reading the graph and asking about it.
    resolved = _resolve_seeds(session, [from_id, to_id])
    source = resolved[0]
    target = resolved[1] if len(resolved) > 1 else resolved[0]

    found = _shortest_paths(session, base, source, target, max_hops, max_paths)
    rows = list(
        session.scalars(
            base.where(
                EdgeProjection.edge_id.in_(
                    {edge_id for path in found for edge_id in path.edge_ids}
                )
            )
        )
    )
    nodes, edges = _hydrate(
        session, ontology, rows, filters, always_include=[source, target]
    )
    return GraphPaths(
        nodes=nodes,
        edges=edges,
        seed_ids=[from_id, to_id],
        resolved_seed_ids=[source, target],
        paths=found,
        truncated=len(found) >= max_paths,
        stamps=projection_stamps(session),
    )


def _shortest_paths(
    session: Session,
    base,
    source: str,
    target: str,
    max_hops: int,
    max_paths: int,
) -> list[GraphPath]:
    """BFS to the first level that reaches the target, then enumerate that level."""
    if source == target:
        return [GraphPath(entity_ids=[source], edge_ids=[])]

    # entity → the (edge_id, neighbour) pairs found at the depth it was reached
    parents: dict[str, list[tuple[str, str]]] = defaultdict(list)
    depth = {source: 0}
    frontier = deque([source])
    reached_at: int | None = None

    for hop in range(1, max_hops + 1):
        if not frontier or reached_at is not None:
            break
        current = list(frontier)
        frontier.clear()
        rows = session.scalars(
            base.where(
                or_(
                    EdgeProjection.subject_id.in_(current),
                    EdgeProjection.object_id.in_(current),
                )
            )
        ).all()
        for row in rows:
            for near, far in ((row.subject_id, row.object_id), (row.object_id, row.subject_id)):
                if depth.get(near) != hop - 1:
                    continue
                if far in depth and depth[far] < hop:
                    continue
                if far not in depth:
                    depth[far] = hop
                    frontier.append(far)
                parents[far].append((row.edge_id, near))
        if target in depth:
            reached_at = depth[target]

    if reached_at is None:
        return []

    # Walk the parent DAG backwards. Only edges recorded at the target's depth
    # participate, so every enumerated route is a *shortest* one.
    found: list[GraphPath] = []
    stack: list[tuple[str, list[str], list[str]]] = [(target, [target], [])]
    while stack and len(found) < max_paths:
        node, entity_ids, edge_ids = stack.pop()
        if node == source:
            found.append(
                GraphPath(entity_ids=list(reversed(entity_ids)), edge_ids=list(reversed(edge_ids)))
            )
            continue
        for edge_id, previous in sorted(parents.get(node, [])):
            if depth.get(previous) != depth[node] - 1:
                continue
            stack.append((previous, entity_ids + [previous], edge_ids + [edge_id]))
    return sorted(found, key=lambda p: (len(p.edge_ids), p.entity_ids))


__all__ = [
    "MAX_ELEMENTS",
    "MAX_HOPS",
    "MAX_PATHS",
    "MAX_PATH_HOPS",
    "MAX_SEEDS",
    "GraphEdge",
    "GraphNode",
    "GraphPath",
    "GraphPaths",
    "GraphView",
    "expand",
    "paths",
]
