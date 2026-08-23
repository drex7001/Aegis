"""Rebuildable projections: edges, geometry, legacy graph JSON, Cypher, search (T10/T21/T56, Article XIII)."""

from aegis.projections.edges import (
    AGGREGATION_METHOD,
    AGGREGATION_METHOD_VERSION,
    BUILDER_VERSION,
    EdgeProjectionReport,
    is_stale,
    rebuild_edge_projection,
)
from aegis.projections.documents import (
    DocumentProjectionReport,
    rebuild_document_text_projection,
)
from aegis.projections.geometry import (
    GeometryProjectionReport,
    rebuild_location_geometry_projection,
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
    "DocumentProjectionReport",
    "EdgeProjectionReport",
    "GeometryProjectionReport",
    "build_full_graph",
    "build_graph",
    "is_stale",
    "rebuild_document_text_projection",
    "rebuild_edge_projection",
    "rebuild_location_geometry_projection",
    "write_outputs",
]
