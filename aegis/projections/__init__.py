"""Rebuildable projections: edge projection, legacy graph JSON, Cypher, search (T10/T21, Article XIII)."""

from aegis.projections.edges import (
    AGGREGATION_METHOD,
    AGGREGATION_METHOD_VERSION,
    BUILDER_VERSION,
    EdgeProjectionReport,
    is_stale,
    rebuild_edge_projection,
)
from aegis.projections.graph import (
    CONFIDENCE_TAGS,
    EXTRACTION_METHODS,
    NODE_PROPERTY_PREDICATES,
    WEIGHTS,
    build_full_graph,
    build_graph,
    write_outputs,
)

__all__ = [
    "AGGREGATION_METHOD",
    "AGGREGATION_METHOD_VERSION",
    "BUILDER_VERSION",
    "CONFIDENCE_TAGS",
    "EXTRACTION_METHODS",
    "NODE_PROPERTY_PREDICATES",
    "WEIGHTS",
    "EdgeProjectionReport",
    "build_full_graph",
    "build_graph",
    "is_stale",
    "rebuild_edge_projection",
    "write_outputs",
]
