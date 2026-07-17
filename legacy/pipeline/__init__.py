"""Temporal multiplex graph extraction pipeline for legal/intelligence documents.

Dual-pass architecture (mirrors Graphify):
  - structural_pass: deterministic regex parsing of structured lists (free, EXTRACTED only)
  - semantic_pass:   LLM extraction of narrative text (provider-agnostic via LangChain)

Every edge carries a Graphify-style confidence tag (EXTRACTED / INFERRED / AMBIGUOUS),
a derived weight (1.0 / 0.7 / 0.4), a multiplex layer, and a temporal window.
"""

from legacy.pipeline.models import (
    CONFIDENCE_WEIGHTS,
    ConfidenceTag,
    CriminalNode,
    ExtractionMethod,
    ExtractionResult,
    LayerType,
    NodeType,
    TemporalEdge,
    slugify,
)

__all__ = [
    "CONFIDENCE_WEIGHTS",
    "ConfidenceTag",
    "CriminalNode",
    "ExtractionMethod",
    "ExtractionResult",
    "LayerType",
    "NodeType",
    "TemporalEdge",
    "slugify",
]
