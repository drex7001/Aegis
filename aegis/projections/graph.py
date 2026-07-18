"""Legacy graph-JSON projection (speckit T10, plan §4.4, ADR-002).

Rebuilds ``output/real_graph.json`` — the exact schema the current UI and the
Cypher exporter consume — from the canonical claim store:

* nodes come from entities, their mention (slug + note + backing source), and
  their node-property claims (``known_as`` → aliases, ``affiliated_with`` →
  affiliations);
* edges come from the ``edge_projection`` **table** (T21), one legacy edge per
  segment, detail fields from the strongest claim supporting that segment;
* cells come from :func:`aegis.analytics.detect_cells` over the result.

This emitter is scheduled for deletion at T22 with the explorer it feeds
(ADR-026).  It is also the one place a **display weight** is still computed:
ADR-030 removed the aggregate weight from the projection itself, and this
module recomputes one from the visible claims for the legacy schema's
``weight`` field.  That is the ADR's intended shape — a display score derived
where it is rendered, from claims the reader can inspect — not a survival of
the thing the ADR condemned.

Everything here is derived state (Article XIII): safe to delete and rebuild.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.er.normalize import norm_key
from aegis.ontology import Ontology
from aegis.store import (
    Claim,
    EdgeProjection,
    Entity,
    IdentityMembership,
    Mention,
    Source,
    SourceRecord,
)

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
# ``merged_into`` is gone: merge lineage is ledger metadata, not a claim
# (ADR-028 §5), and the predicate is retired from the ontology by T17.
NODE_PROPERTY_PREDICATES = frozenset({"known_as", "affiliated_with"})

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
    """Fallback node id for an entity with no mention.

    ``norm_key`` is the platform's replacement for the prototype's ``slugify``
    and is deliberately compatible with it on Latin text, so ids written by the
    Phase-1 migration still match (T17).
    """
    return norm_key(label)


def build_graph(
    session: Session, ontology: Ontology, *, open_only: bool = True
) -> dict[str, Any]:
    """The legacy ``real_graph.json`` dict (without cells/meta — see build_full).

    ``open_only`` (the default) restricts the projection to ``open``-handling,
    case-less claims: this artifact backs the token-less legacy UI and the
    committed output files, so nothing above the public floor may enter it.
    """
    # Tombstoned entities are excluded: an entity absorbed by a merge keeps its
    # id forever (specs/05 §5), but rendering it would put a node on the canvas
    # that no edge can reach and no mention belongs to.  A split clears the
    # tombstone and it returns.
    entities = session.scalars(
        select(Entity)
        .where(Entity.tombstoned_at.is_(None))
        .order_by(Entity.entity_id)
    ).all()

    # entity → mention (slug, note) + backing source publication
    mention_info: dict[str, tuple[str, str | None, str]] = {}
    rows = session.execute(
        select(Entity.entity_id, Mention.norm_key, Mention.context, Source.name)
        .join(IdentityMembership, IdentityMembership.entity_id == Entity.entity_id)
        .join(Mention, Mention.mention_id == IdentityMembership.mention_id)
        .join(SourceRecord, SourceRecord.record_id == Mention.record_id)
        .join(Source, Source.source_id == SourceRecord.source_id)
        .where(IdentityMembership.closed_revision_id.is_(None))
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

    # edges from the v2 table — one legacy edge per *segment*, so an entity
    # pair with disjoint validity intervals renders as separate edges rather
    # than one fabricated span (ADR-030).
    segments = session.scalars(
        select(EdgeProjection).order_by(
            EdgeProjection.subject_id,
            EdgeProjection.object_id,
            EdgeProjection.predicate,
            EdgeProjection.segment_from,
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
    for row in segments:
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
                # The display score ADR-030 allows: computed here, from the
                # claims visible to this caller, so the open-only floor holds
                # and a reader can reach every claim behind the number.
                "weight": max(
                    WEIGHTS.get(c.credibility_normalized, 0.4) for c in claims
                ),
                "start_date": _iso(row.segment_from),
                "end_date": _iso(row.segment_to),
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
    from aegis.analytics import detect_cells

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
    from aegis.projections.cypher import generate_cypher

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
