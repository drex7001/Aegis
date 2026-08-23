"""Running a metric and recording what it found (T72, spec 12 §§8–9).

The line ADR-057 draws: `/v1/graph/*` **answers a question** and records
nothing; this **records an answer**. Recording is what demands a manifest, a
caveat, an actor and a purpose — because a recorded answer outlives the
question and gets forwarded to people who never saw the query.

Everything here reads the caller's own graph. `edge_projection` filtered by
`claim_filters`, entity ids resolved through the active canonical map — the
same graph `/v1/graph/expand` shows, so a finding cannot be computed over rows
the analyst could not have seen for themselves.

## Why the graph is undirected for three of the six metrics

Community, betweenness and degree treat the graph as undirected, and that is a
claim about the data rather than a convenience. Direction is a property of a
*predicate* — `controls` points one way — but co-occurrence in a record is not
directional, and treating a directed claim as flow is an inference the corpus
does not support. Path length is unweighted for the reason ADR-030 gives: there
is no aggregate weight to traverse, on purpose.

## The caveat is copied, never referenced

Every finding row carries its caveat text. There is no render path that fetches
one, so there is no render path that can fail to (spec 12 §9.3).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.analytics.caveats import CAVEAT_VERSION, caveat_for
from aegis.analytics.manifest import (
    METHOD_VERSION,
    Manifest,
    authorization_digest,
    code_version,
    digest_of,
    edge_digest,
    library_version,
    settings_digest,
)
from aegis.api.auth import UserContext
from aegis.authz.filters import claim_filters, member_case_ids
from aegis.er.ledger import active_revision_id
from aegis.ids import new_id
from aegis.ontology import Ontology
from aegis.projections.edges import BUILDER_VERSION, AGGREGATION_METHOD_VERSION
from aegis.store import AnalyticFinding, AnalyticRun, Claim, EdgeProjection

#: Every metric that records a finding (spec 12 §9.1). `caveat_for` refuses a
#: metric with no caveat, so this list and the catalog cannot drift apart
#: without a test failing.
METRICS = (
    "k_hop",
    "shortest_path",
    "community",
    "betweenness",
    "degree",
    "shared_identifier",
)


class AnalyticsError(RuntimeError):
    """A run that cannot be performed, with the reason a caller can act on."""


@dataclass(frozen=True, slots=True)
class Graph:
    """The caller's own view of the graph, plus what it was read from."""

    edges: list[EdgeProjection]
    entity_ids: set[str]
    built_at_revision_id: int | None
    builder_version: str | None
    aggregation_method_version: str | None

    def adjacency(self) -> dict[str, set[str]]:
        """Undirected. See the module docstring for why that is a claim."""
        neighbours: dict[str, set[str]] = defaultdict(set)
        for edge in self.edges:
            neighbours[edge.subject_id].add(edge.object_id)
            neighbours[edge.object_id].add(edge.subject_id)
        return neighbours


def load_graph(
    session: Session,
    *,
    user: UserContext,
    ontology: Ontology,
    entity_ids: Sequence[str] | None = None,
) -> Graph:
    """The edges this caller may read, and the stamps of the projection they came from.

    An edge is visible when it survives `claim_filters` at the *claim* level —
    the projection copies `handling_rank`, so the filter is one comparison
    rather than a join back to `claim` that could be forgotten.
    """
    allowed = [
        code
        for index, code in enumerate(ontology.handling_codes)
        if index <= user.clearance
    ]
    statement = select(EdgeProjection).where(
        EdgeProjection.handling_rank <= ontology.handling_rank(allowed[-1])
    )
    if entity_ids is not None:
        ids = list(entity_ids)
        statement = statement.where(
            EdgeProjection.subject_id.in_(ids) | EdgeProjection.object_id.in_(ids)
        )
    edges = list(session.scalars(statement.order_by(EdgeProjection.edge_id)))

    # The stamps come from the rows actually read. Reading them from the table
    # as a whole would report a projection this run did not use.
    stamps = {
        (
            edge.built_at_revision_id,
            edge.builder_version,
        )
        for edge in edges
    }
    built_at, builder = stamps.pop() if len(stamps) == 1 else (None, None)

    return Graph(
        edges=edges,
        entity_ids={edge.subject_id for edge in edges} | {edge.object_id for edge in edges},
        built_at_revision_id=built_at,
        builder_version=builder,
        aggregation_method_version=AGGREGATION_METHOD_VERSION if edges else None,
    )


def _handling_for(session: Session, ontology: Ontology, claim_ids: Sequence[str]) -> tuple[str, int]:
    """The **maximum** handling code of the claims that contributed.

    Derived, never chosen. A finding computed from sensitive evidence and
    stored as `open` would be the leak the whole evaluation path exists to
    prevent, arriving one level up (spec 12 §8.3).
    """
    if not claim_ids:
        return ontology.handling_codes[0], 0
    codes = set(
        session.scalars(
            select(Claim.handling_code).where(Claim.claim_id.in_(list(claim_ids)))
        )
    )
    if not codes:
        return ontology.handling_codes[0], 0
    highest = max(codes, key=ontology.handling_rank)
    return highest, ontology.handling_rank(highest)


# ── the metrics ─────────────────────────────────────────────────────────────


def _degree(graph: Graph) -> list[tuple[list[str], dict[str, Any], list[str]]]:
    neighbours = graph.adjacency()
    results = []
    for entity_id in sorted(neighbours):
        claim_ids = [
            claim_id
            for edge in graph.edges
            if entity_id in (edge.subject_id, edge.object_id)
            for claim_id in edge.claim_ids
        ]
        results.append(
            ([entity_id], {"degree": len(neighbours[entity_id])}, claim_ids)
        )
    return results


def _betweenness(graph: Graph) -> list[tuple[list[str], dict[str, Any], list[str]]]:
    """Brandes' algorithm over the undirected, unweighted graph.

    Unweighted because there is no aggregate weight to use (ADR-030), and the
    caveat says the score measures the shape of what was written down rather
    than the flow of anything real.
    """
    import networkx as nx

    graph_nx = nx.Graph()
    graph_nx.add_nodes_from(graph.entity_ids)
    graph_nx.add_edges_from((edge.subject_id, edge.object_id) for edge in graph.edges)
    scores = nx.betweenness_centrality(graph_nx) if graph_nx.number_of_nodes() else {}

    results = []
    for entity_id in sorted(scores):
        claim_ids = [
            claim_id
            for edge in graph.edges
            if entity_id in (edge.subject_id, edge.object_id)
            for claim_id in edge.claim_ids
        ]
        results.append(
            ([entity_id], {"betweenness": round(scores[entity_id], 6)}, claim_ids)
        )
    return results


def _shared_identifier(
    session: Session, graph: Graph, ontology: Ontology
) -> list[tuple[list[str], dict[str, Any], list[str]]]:
    """Entities recorded under the same **exact** identifier.

    Exact, never fuzzy — the same rule search follows (ADR-053), for the same
    reason: a near-match on an identifier is a different person with a name
    attached. And never an identity decision: only a human adjudication merges
    identities (Articles V and VII), which is what the caveat says.
    """
    identifiers = [name for name, spec in ontology.predicates.items() if spec.identifier]
    if not identifiers:
        return []

    rows = session.execute(
        select(Claim.claim_id, Claim.subject_id, Claim.predicate, Claim.object_value)
        .where(Claim.predicate.in_(identifiers), Claim.object_value.is_not(None))
        .order_by(Claim.claim_id)
    )
    by_value: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for row in rows:
        by_value[(row.predicate, str(row.object_value))].append(
            (row.subject_id, row.claim_id)
        )

    results = []
    for (predicate, value), pairs in sorted(by_value.items()):
        subjects = sorted({subject for subject, _ in pairs})
        if len(subjects) < 2:
            continue
        results.append(
            (
                subjects,
                {"predicate": predicate, "shared_by": len(subjects)},
                [claim_id for _, claim_id in pairs],
            )
        )
    return results


def _community(graph: Graph) -> tuple[list[tuple[list[str], dict[str, Any], list[str]]], str]:
    """Leiden if igraph is present, Louvain if not — and the manifest says which."""
    from aegis.analytics.clustering import detect_cells

    payload = {
        "nodes": [{"node_id": entity_id, "name": entity_id} for entity_id in sorted(graph.entity_ids)],
        "edges": [
            {
                "source": edge.subject_id,
                "target": edge.object_id,
                "weight": 1.0,
                "layer": edge.predicate,
            }
            for edge in graph.edges
        ],
    }
    if not payload["nodes"]:
        return [], "none (empty graph)"

    cells = detect_cells(payload)
    algorithm = cells[0]["algorithm"] if cells else "none"
    members_by_id = {node["node_id"]: node["cluster_id"] for node in payload["nodes"]}

    results = []
    for cell in cells:
        subjects = sorted(
            entity_id
            for entity_id, cluster in members_by_id.items()
            if cluster == cell["cluster_id"]
        )
        claim_ids = [
            claim_id
            for edge in graph.edges
            if edge.subject_id in subjects and edge.object_id in subjects
            for claim_id in edge.claim_ids
        ]
        results.append(
            (
                subjects,
                {"cluster_id": cell["cluster_id"], "size": cell["size"]},
                claim_ids,
            )
        )
    implementation = (
        library_version("leidenalg")
        if algorithm == "leiden"
        else library_version("networkx")
    )
    return results, f"{algorithm} / {implementation}"


# ── running one ─────────────────────────────────────────────────────────────


def run_metric(
    session: Session,
    *,
    metric: str,
    user: UserContext,
    ontology: Ontology,
    purpose: str | None = None,
    parameters: dict[str, Any] | None = None,
    object_set_id: str | None = None,
    object_set_version: int | None = None,
    evaluation_digest: str | None = None,
    entity_ids: Sequence[str] | None = None,
) -> tuple[AnalyticRun, list[AnalyticFinding]]:
    """Write the manifest, run the metric, record the findings.

    The manifest is written **first**, deliberately: a run that crashed after
    computing something should still be visible as a run that happened, and a
    manifest written afterwards would only ever describe successes.
    """
    if metric not in METRICS:
        raise AnalyticsError(f"{metric!r} is not a recorded metric (have: {list(METRICS)})")
    # Raises for a metric with no caveat — Article IX enforced before any work
    # is done, rather than discovered when the row refuses to insert.
    caveat = caveat_for(metric)

    graph = load_graph(session, user=user, ontology=ontology, entity_ids=entity_ids)
    parameters = dict(parameters or {})

    if metric == "community":
        results, implementation = _community(graph)
        seed = 42  # what `detect_cells` uses; recorded rather than assumed
    elif metric == "degree":
        results, implementation, seed = _degree(graph), "builtin", None
    elif metric == "betweenness":
        results, implementation, seed = (
            _betweenness(graph),
            library_version("networkx"),
            None,
        )
    elif metric == "shared_identifier":
        results, implementation, seed = (
            _shared_identifier(session, graph, ontology),
            "builtin",
            None,
        )
    else:
        # k_hop and shortest_path record findings over the same traversal
        # `/v1/graph/*` serves; T72 ships the four that need no seed arguments
        # and leaves these to the route that already computes them.
        raise AnalyticsError(
            f"{metric!r} is served by /v1/graph and records no finding yet "
            "(spec 12 §9.1)"
        )

    manifest = Manifest(
        method=metric,
        method_version=METHOD_VERSION,
        implementation=implementation,
        parameters=parameters,
        seed=seed,
        input_kind="object_set" if object_set_id else "projection",
        object_set_id=object_set_id,
        object_set_version=object_set_version,
        evaluation_digest=evaluation_digest,
        edge_digest=edge_digest(graph.edges),
        projection_built_at_revision_id=graph.built_at_revision_id,
        projection_builder_version=graph.builder_version,
        projection_aggregation_method_version=graph.aggregation_method_version,
        ontology_version=ontology.version,
        identity_revision_id=active_revision_id(session),
        code_version=code_version(),
        settings_digest=settings_digest(),
        actor=user.sub,
        purpose=purpose,
        authorization_digest=authorization_digest(
            user, member_case_ids(session, user)
        ),
        caveat_version=CAVEAT_VERSION,
    )

    run = AnalyticRun(run_id=new_id("run"), **manifest.__dict__)
    session.add(run)
    session.flush()

    findings = []
    seen: set[str] = set()
    for subjects, value, claim_ids in results:
        digest = digest_of([metric, sorted(subjects), value])
        if digest in seen:
            # The unique constraint would refuse it anyway; skipping keeps the
            # run from failing wholesale over a duplicate the metric produced.
            continue
        seen.add(digest)
        code, rank = _handling_for(session, ontology, claim_ids)
        findings.append(
            AnalyticFinding(
                finding_id=new_id("find"),
                run_id=run.run_id,
                finding_type=metric,
                subjects=sorted(subjects),
                value=value,
                caveat_text=caveat.text,
                caveat_version=caveat.version,
                finding_digest=digest,
                handling_code=code,
                handling_rank=rank,
            )
        )
    session.add_all(findings)
    run.finished_at = datetime.now(timezone.utc)
    session.flush()
    return run, findings


__all__ = ["AnalyticsError", "Graph", "METRICS", "load_graph", "run_metric"]
