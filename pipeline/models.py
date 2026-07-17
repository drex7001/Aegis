"""Pydantic models for the Neo4j-ready temporal multiplex graph.

Design rules (Graphify conventions, adapted to this domain):
  - Every edge MUST carry a confidence tag; the numeric weight is DERIVED from the
    tag and cannot be set independently — an LLM emitting weight=0.95 on an
    AMBIGUOUS edge is silently corrected to 0.4.
  - Node IDs are deterministic slugs of the entity name (lowercase, [a-z0-9_]),
    so the same entity always produces the same ID regardless of which pass or
    document produced it.
  - end_date=None means the relationship is ongoing as of the source's reporting date.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class ConfidenceTag(str, Enum):
    """Graphify-style audit tag. Never invent an edge — if unsure, use AMBIGUOUS."""

    EXTRACTED = "EXTRACTED"  # hard fact stated in an official record (judgment, remand list)
    INFERRED = "INFERRED"    # probable link derived from narrative context
    AMBIGUOUS = "AMBIGUOUS"  # suspected but unconfirmed (e.g. single uncorroborated informant)


CONFIDENCE_WEIGHTS: dict[ConfidenceTag, float] = {
    ConfidenceTag.EXTRACTED: 1.0,
    ConfidenceTag.INFERRED: 0.7,
    ConfidenceTag.AMBIGUOUS: 0.4,
}


class LayerType(str, Enum):
    """Multiplex layer. Doubles as the Neo4j relationship type."""

    IDEOLOGICAL = "IDEOLOGICAL"
    FINANCIAL = "FINANCIAL"
    PRISON_CO_LOCATION = "PRISON_CO_LOCATION"
    TRANSNATIONAL = "TRANSNATIONAL"
    # Added by the aegis ontology (T10): kinship predicates (sibling_of,
    # spouse_of) were previously misfiled under FINANCIAL/IDEOLOGICAL.
    KINSHIP = "KINSHIP"


class ExtractionMethod(str, Enum):
    STRUCTURAL = "STRUCTURAL"  # deterministic regex/NLP pass
    SEMANTIC = "SEMANTIC"      # LLM pass
    CURATED = "CURATED"        # human-verified OSINT from cited public reporting


class NodeType(str, Enum):
    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Deterministic node ID: lowercase, only [a-z0-9_], same input -> same ID."""
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = _SLUG_RE.sub("_", normalized.lower()).strip("_")
    return slug or "unknown"


class CriminalNode(BaseModel):
    node_id: str = Field(
        default="",
        description="Deterministic snake_case slug of the entity name. Leave blank to auto-derive.",
    )
    name: str = Field(description="Full name of the person or organisation as written in the source.")
    aliases: list[str] = Field(default_factory=list, description="Known aliases / street names.")
    nic: Optional[str] = Field(
        default=None, description="National Identity Card number if stated in the source."
    )
    affiliations: list[str] = Field(
        default_factory=list, description="Named groups/organisations the entity is linked to."
    )
    node_type: NodeType = NodeType.PERSON
    source_file: str = Field(default="", description="Document the entity was extracted from.")
    source_excerpt: Optional[str] = Field(
        default=None, description="Verbatim text supporting this entity's existence."
    )

    @model_validator(mode="after")
    def _derive_id(self) -> "CriminalNode":
        self.node_id = slugify(self.node_id) if self.node_id else slugify(self.name)
        return self

    def merged_with(self, other: "CriminalNode") -> "CriminalNode":
        """Combine two records of the same entity (same node_id), keeping all evidence."""
        merged = self.model_copy(deep=True)
        for alias in other.aliases:
            if alias not in merged.aliases:
                merged.aliases.append(alias)
        for aff in other.affiliations:
            if aff not in merged.affiliations:
                merged.affiliations.append(aff)
        merged.nic = merged.nic or other.nic
        merged.source_excerpt = merged.source_excerpt or other.source_excerpt
        if other.source_file and other.source_file not in merged.source_file:
            merged.source_file = (
                f"{merged.source_file}; {other.source_file}" if merged.source_file else other.source_file
            )
        return merged


class TemporalEdge(BaseModel):
    source: str = Field(description="node_id of the source entity.")
    target: str = Field(description="node_id of the target entity.")
    relation: str = Field(
        description="Verb phrase slug, e.g. met_in_prison, transferred_funds_to, adheres_to_ideology_of."
    )
    layer: LayerType
    confidence: ConfidenceTag
    weight: float = Field(
        default=0.0,
        description="Derived from confidence (EXTRACTED=1.0, INFERRED=0.7, AMBIGUOUS=0.4). Any provided value is overwritten.",
    )
    start_date: Optional[date] = Field(
        default=None, description="ISO date the relationship began, if known."
    )
    end_date: Optional[date] = Field(
        default=None, description="ISO date the relationship ended. null = ongoing."
    )
    location: Optional[str] = Field(
        default=None, description="Facility or place tied to the relationship, if any."
    )
    source_file: str = Field(default="", description="Document the edge was extracted from.")
    source_excerpt: Optional[str] = Field(
        default=None, description="Verbatim sentence supporting this edge."
    )
    extraction_method: ExtractionMethod = ExtractionMethod.SEMANTIC

    @field_validator("source", "target", "relation")
    @classmethod
    def _slug(cls, v: str) -> str:
        return slugify(v)

    @model_validator(mode="after")
    def _enforce_invariants(self) -> "TemporalEdge":
        # Weight is an audit artefact of the tag, never a free parameter.
        self.weight = CONFIDENCE_WEIGHTS[self.confidence]
        if self.source == self.target:
            raise ValueError(f"self-loop rejected: {self.source} -> {self.target}")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError(
                f"end_date {self.end_date} precedes start_date {self.start_date} "
                f"on {self.source} -[{self.relation}]-> {self.target}"
            )
        return self

    def dedup_key(self) -> tuple:
        return (self.source, self.target, self.relation, self.layer, self.start_date, self.end_date)


class ExtractionResult(BaseModel):
    """Container for one extraction pass. Also the LLM structured-output schema."""

    nodes: list[CriminalNode] = Field(default_factory=list)
    edges: list[TemporalEdge] = Field(default_factory=list)

    def merge(self, other: "ExtractionResult") -> "ExtractionResult":
        """Union of two passes: nodes deduped by node_id (evidence merged), edges deduped by key."""
        by_id: dict[str, CriminalNode] = {}
        for node in [*self.nodes, *other.nodes]:
            by_id[node.node_id] = by_id[node.node_id].merged_with(node) if node.node_id in by_id else node

        seen: set[tuple] = set()
        edges: list[TemporalEdge] = []
        for edge in [*self.edges, *other.edges]:
            key = edge.dedup_key()
            if key not in seen:
                seen.add(key)
                edges.append(edge)
        return ExtractionResult(nodes=list(by_id.values()), edges=edges)

    def dangling_edges(self) -> list[TemporalEdge]:
        """Edges whose endpoints are not in the node list — audit before ingesting."""
        known = {n.node_id for n in self.nodes}
        return [e for e in self.edges if e.source not in known or e.target not in known]

    def to_graph_json(self) -> dict:
        """Neo4j-ready dict (dates as ISO strings, enums as values)."""
        return self.model_dump(mode="json")
