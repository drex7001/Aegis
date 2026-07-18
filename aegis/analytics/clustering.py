"""Community detection over a weighted multiplex graph (Leiden).

Vendored into the core by T21 (H-36).  The prototype kept this in
``legacy.pipeline``, which meant a documented core command — ``aegis
projections rebuild`` — depended on quarantined code that the packaged wheel
does not ship.  Community detection is a **generic algorithm**, not domain
scaffolding: nothing here knows what a node represents, so it belongs in
``aegis.analytics`` and the quarantine loses one more reason to exist.

Primary path: true Leiden via python-igraph + leidenalg. Because the graph is
multiplex, when more than one layer is present we build one igraph per layer
over the SAME vertex set and run leidenalg.find_partition_multiplex(), which
optimises the partition across all layers jointly — the correct multiplex
treatment, not just flattening.

Fallback: if igraph/leidenalg are unavailable, NetworkX Louvain on the
flattened weighted graph (with a printed warning).

Edge weights come from the caller.  The graph emitter passes its display
weight, so better-supported links pull nodes together harder — but that is the
*caller's* interpretation of its own numbers, and this module makes no claim
about what a weight means.

Under Article IX a partition is an analytic finding, never a claim: cells are
a question to investigate, not an assertion about anyone in them.
"""

from __future__ import annotations

from collections import defaultdict


def _group_edges_by_layer(edges: list[dict]) -> dict[str, list[dict]]:
    layers: dict[str, list[dict]] = defaultdict(list)
    for edge in edges:
        layers[edge["layer"]].append(edge)
    return dict(layers)


def _leiden_membership(node_ids: list[str], edges: list[dict]) -> list[int]:
    """Leiden via igraph/leidenalg; multiplex variant when >1 layer present."""
    import igraph as ig
    import leidenalg as la

    index = {nid: i for i, nid in enumerate(node_ids)}

    def layer_graph(layer_edges: list[dict]) -> ig.Graph:
        g = ig.Graph(n=len(node_ids))
        g.add_edges([(index[e["source"]], index[e["target"]]) for e in layer_edges])
        g.es["weight"] = [float(e["weight"]) for e in layer_edges]
        return g

    layers = _group_edges_by_layer(edges)
    if len(layers) > 1:
        graphs = [layer_graph(layer_edges) for layer_edges in layers.values()]
        membership, _improvement = la.find_partition_multiplex(
            graphs, la.ModularityVertexPartition, weights="weight", seed=42
        )
        return membership
    g = layer_graph(edges)
    partition = la.find_partition(g, la.ModularityVertexPartition, weights="weight", seed=42)
    return partition.membership


def _louvain_membership(node_ids: list[str], edges: list[dict]) -> list[int]:
    """Fallback: NetworkX Louvain on the flattened weighted graph."""
    import networkx as nx

    print("WARNING: leidenalg/igraph not available - falling back to NetworkX Louvain "
          "on the flattened graph (install python-igraph + leidenalg for true multiplex Leiden).")
    G = nx.Graph()
    G.add_nodes_from(node_ids)
    for e in edges:
        w = float(e["weight"])
        if G.has_edge(e["source"], e["target"]):
            G[e["source"]][e["target"]]["weight"] += w  # flatten multiplex by summing
        else:
            G.add_edge(e["source"], e["target"], weight=w)
    communities = nx.community.louvain_communities(G, weight="weight", seed=42)
    membership = [0] * len(node_ids)
    index = {nid: i for i, nid in enumerate(node_ids)}
    for cid, members in enumerate(communities):
        for nid in members:
            membership[index[nid]] = cid
    return membership


def detect_cells(graph: dict) -> list[dict]:
    """Assign cluster_id to every node in the graph dict (in place) and return
    a summary of the detected cells.

    graph: {"nodes": [...], "edges": [...]} as produced by ExtractionResult.to_graph_json().
    """
    node_ids = [n["node_id"] for n in graph["nodes"]]
    edges = graph["edges"]

    try:
        membership = _leiden_membership(node_ids, edges)
        algorithm = "leiden"
    except ImportError:
        membership = _louvain_membership(node_ids, edges)
        algorithm = "louvain-fallback"

    # Renumber clusters by size (largest first) for stable, readable output.
    counts: dict[int, int] = defaultdict(int)
    for cid in membership:
        counts[cid] += 1
    order = sorted(counts, key=lambda c: (-counts[c], c))
    renumber = {old: new for new, old in enumerate(order)}
    assignment = {nid: renumber[cid] for nid, cid in zip(node_ids, membership)}

    for node in graph["nodes"]:
        node["cluster_id"] = assignment[node["node_id"]]

    return _summarize(graph, assignment, algorithm)


def _summarize(graph: dict, assignment: dict[str, int], algorithm: str) -> list[dict]:
    members: dict[int, list[str]] = defaultdict(list)
    for nid, cid in assignment.items():
        members[cid].append(nid)

    internal: dict[int, list[dict]] = defaultdict(list)
    external: dict[int, int] = defaultdict(int)
    for e in graph["edges"]:
        cs, ct = assignment[e["source"]], assignment[e["target"]]
        if cs == ct:
            internal[cs].append(e)
        else:
            external[cs] += 1
            external[ct] += 1

    names = {n["node_id"]: n["name"] for n in graph["nodes"]}
    cells = []
    for cid in sorted(members):
        cell_edges = internal[cid]
        layer_weight: dict[str, float] = defaultdict(float)
        for e in cell_edges:
            layer_weight[e["layer"]] += float(e["weight"])
        dominant = max(layer_weight, key=layer_weight.get) if layer_weight else None
        cells.append(
            {
                "cluster_id": cid,
                "algorithm": algorithm,
                "size": len(members[cid]),
                "members": sorted(names[nid] for nid in members[cid]),
                "dominant_layer": dominant,
                "internal_edges": len(cell_edges),
                "avg_confidence_weight": (
                    round(sum(float(e["weight"]) for e in cell_edges) / len(cell_edges), 3)
                    if cell_edges
                    else None
                ),
                # No edges leaving the cluster => an isolated cell.
                "isolated": external[cid] == 0,
            }
        )
    return cells
