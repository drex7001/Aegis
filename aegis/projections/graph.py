"""Legacy graph-JSON projection (speckit T10, plan §4.4, ADR-002).

Rebuilds ``output/real_graph.json`` — the exact schema the current UI and the
Cypher exporter consume — from the canonical claim store:

* nodes come from entities, their mention (slug + note + backing source), and
  their node-property claims (``known_as`` → aliases, ``affiliated_with`` →
  affiliations);
* edges come from the ``edge_projection`` materialized view, detail fields
  from the strongest claim in each group;
* cells come from the unchanged prototype clustering
  (:func:`pipeline.clustering.detect_cells`) running on the projection.

Everything here is derived state (Article XIII): safe to delete and rebuild.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from aegis.ontology import Ontology
from aegis.store import Claim, Entity, IdentityMembership, Mention, Source, SourceRecord

# Display/traversal weight per normalized credibility (spec 02 §6; the SQL twin
# lives in migration 0006 — test_projections asserts they agree).
WEIGHTS: dict[str, float] = {
    "confirmed": 1.0,
    "probably_true": 0.7,
    "possibly_true": 0.55,
    "doubtful": 0.4,
    "improbable": 0.2,
    "cannot_judge": 0.4,
}

# Reverse maps back into the legacy schema vocabulary.
CONFIDENCE_TAGS: dict[str, str] = {
    "confirmed": "EXTRACTED",
    "probably_true": "INFERRED",
    "possibly_true": "AMBIGUOUS",
    "doubtful": "AMBIGUOUS",
    "improbable": "AMBIGUOUS",
    "cannot_judge": "AMBIGUOUS",
}
EXTRACTION_METHODS: dict[str, str] = {
    "curated": "CURATED",
    "manual": "CURATED",
    "structural": "STRUCTURAL",
    "semantic_llm": "SEMANTIC",
}

# Claims that describe the subject rather than connect two graph nodes; they
# render as node properties, not edges.
NODE_PROPERTY_PREDICATES = frozenset({"known_as", "affiliated_with", "merged_into"})

DISCLAIMER = (
    "Analytical model compiled ONLY from public reporting (Wikipedia, PCoI reporting, "
    "named Sri Lankan news outlets). Not a determination of guilt. Confidence tags "
    "encode source strength: EXTRACTED = stated plainly in an official record or by "
    "named reporting; INFERRED = probable but not adjudicated; AMBIGUOUS = alleged / "
    "contested. The three networks are not linked in the public record."
)

LAYER_DESCRIPTIONS = {
    "IDEOLOGICAL": "Shared/adopted extremist ideology, membership, allegiance",
    "FINANCIAL": "Money flows and shared illicit enterprise (drug operations, funding, enterprise violence)",
    "PRISON_CO_LOCATION": "Co-located in a prison / remand facility",
    "TRANSNATIONAL": "Cross-border links: foreign networks, smuggling routes, overseas handlers",
    "KINSHIP": "Family and spousal ties (sibling_of, spouse_of)",
}

CONFIDENCE_DESCRIPTIONS = {
    "EXTRACTED": "1.0 — stated plainly in an official record or by named reporting",
    "INFERRED": "0.7 — probable link reporting supports but has not adjudicated",
    "AMBIGUOUS": "0.4 — alleged / contested / uncorroborated",
}


def _slugify(label: str) -> str:
    from pipeline.models import slugify

    return slugify(label)


def refresh_edge_projection(session: Session, *, concurrently: bool = False) -> None:
    keyword = "CONCURRENTLY " if concurrently else ""
    session.execute(text(f"REFRESH MATERIALIZED VIEW {keyword}edge_projection"))


def build_graph(
    session: Session, ontology: Ontology, *, open_only: bool = True
) -> dict[str, Any]:
    """The legacy ``real_graph.json`` dict (without cells/meta — see build_full).

    ``open_only`` (the default) restricts the projection to ``open``-handling,
    case-less claims: this artifact backs the token-less legacy UI and the
    committed output files, so nothing above the public floor may enter it.
    """
    entities = session.scalars(select(Entity).order_by(Entity.entity_id)).all()

    # entity → mention (slug, note) + backing source publication
    mention_info: dict[str, tuple[str, str | None, str]] = {}
    rows = session.execute(
        select(Entity.entity_id, Mention.norm_key, Mention.context, Source.name)
        .join(IdentityMembership, IdentityMembership.entity_id == Entity.entity_id)
        .join(Mention, Mention.mention_id == IdentityMembership.mention_id)
        .join(SourceRecord, SourceRecord.record_id == Mention.record_id)
        .join(Source, Source.source_id == SourceRecord.source_id)
        .where(IdentityMembership.valid_to.is_(None))
    ).all()
    for entity_id, norm_key, context, source_name in rows:
        mention_info.setdefault(entity_id, (norm_key, context, source_name))

    label_by_id = {e.entity_id: e.label for e in entities}
    slug_by_id = {
        e.entity_id: mention_info.get(e.entity_id, (_slugify(e.label), None, ""))[0]
        for e in entities
    }

    # node-property claims, in recording order (claim ids are time-sortable)
    aliases: dict[str, list[str]] = {}
    affiliations: dict[str, list[str]] = {}
    property_query = select(Claim).where(
        Claim.predicate.in_(["known_as", "affiliated_with"]),
        Claim.retracted_at.is_(None),
    )
    if open_only:
        property_query = property_query.where(
            Claim.handling_code == "open", Claim.case_id.is_(None)
        )
    property_claims = session.scalars(property_query.order_by(Claim.claim_id)).all()
    for claim in property_claims:
        if claim.predicate == "known_as":
            aliases.setdefault(claim.subject_id, []).append(str(claim.object_value))
        else:
            value = (
                label_by_id.get(claim.object_id, claim.object_id)
                if claim.object_id is not None
                else str(claim.object_value)
            )
            affiliations.setdefault(claim.subject_id, []).append(value)

    nodes = [
        {
            "node_id": slug_by_id[e.entity_id],
            "name": e.label,
            "aliases": aliases.get(e.entity_id, []),
            "nic": None,  # deliberately omitted for real people (ethics rubric)
            "affiliations": affiliations.get(e.entity_id, []),
            "node_type": e.entity_type.upper(),
            "source_file": mention_info.get(e.entity_id, ("", None, ""))[2],
            "source_excerpt": mention_info.get(e.entity_id, ("", None, ""))[1],
        }
        for e in entities
    ]

    # edges from the materialized view; detail from the strongest claim
    view_rows = session.execute(
        text(
            "SELECT subject_id, object_id, predicate, valid_from, valid_to, "
            "       claim_count, independent_records, weight, claim_ids, handling_rank "
            "FROM edge_projection ORDER BY subject_id, object_id, predicate"
        )
    ).all()
    source_by_record: dict[str, str] = dict(
        session.execute(
            select(SourceRecord.record_id, Source.name).join(
                Source, Source.source_id == SourceRecord.source_id
            )
        ).all()
    )
    edges: list[dict[str, Any]] = []
    for row in view_rows:
        if row.predicate in NODE_PROPERTY_PREDICATES:
            continue
        claims = session.scalars(
            select(Claim).where(Claim.claim_id.in_(row.claim_ids))
        ).all()
        if open_only:
            claims = [
                c for c in claims if c.handling_code == "open" and c.case_id is None
            ]
            if not claims:
                continue
        best = max(
            claims,
            key=lambda c: (WEIGHTS.get(c.credibility_normalized, 0.4), c.claim_id),
        )
        spec = ontology.predicates.get(row.predicate)
        category = spec.category if spec is not None and spec.category else "uncategorized"
        edges.append(
            {
                "source": slug_by_id.get(row.subject_id, row.subject_id),
                "target": slug_by_id.get(row.object_id, row.object_id),
                "relation": row.predicate,
                "layer": category.upper(),
                "confidence": CONFIDENCE_TAGS.get(best.credibility_normalized, "AMBIGUOUS"),
                # recomputed over the visible claims so the open-only floor holds
                "weight": max(
                    WEIGHTS.get(c.credibility_normalized, 0.4) for c in claims
                ),
                "start_date": _iso(row.valid_from),
                "end_date": _iso(row.valid_to),
                "location": best.location_text,
                "source_file": source_by_record.get(best.record_id, ""),
                "source_excerpt": best.excerpt,
                "extraction_method": EXTRACTION_METHODS.get(
                    best.collection_method or "", "CURATED"
                ),
            }
        )
    return {"nodes": nodes, "edges": edges}


def build_full_graph(session: Session, ontology: Ontology) -> dict[str, Any]:
    """Graph + cells + meta — the complete legacy output/real_graph.json shape."""
    from pipeline.clustering import detect_cells

    graph = build_graph(session, ontology)
    cells = detect_cells(graph)  # also stamps cluster_id onto every node
    graph["generated_at"] = datetime.now(timezone.utc).isoformat()
    graph["cells"] = cells

    sources = session.scalars(select(Source).order_by(Source.created_at, Source.source_id)).all()
    graph["meta"] = {
        "title": "Sri Lanka Illicit Networks — Temporal Multiplex Graph",
        "disclaimer": DISCLAIMER,
        "sources": [
            {
                "key": s.source_id.removeprefix("src_legacy_"),
                "publication": s.name,
                "url": s.url,
            }
            for s in sources
        ],
        "layers": LAYER_DESCRIPTIONS,
        "confidence": CONFIDENCE_DESCRIPTIONS,
    }
    return graph


def write_outputs(graph: dict[str, Any], output_dir: Path) -> list[Path]:
    """real_graph.json + real_ingest.cypher (the preserved Cypher export path)."""
    from pipeline.neo4j_export import generate_cypher

    output_dir.mkdir(parents=True, exist_ok=True)
    graph_path = output_dir / "real_graph.json"
    graph_path.write_text(
        json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    cypher_path = output_dir / "real_ingest.cypher"
    cypher_path.write_text(generate_cypher(graph), encoding="utf-8")
    return [graph_path, cypher_path]


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None
