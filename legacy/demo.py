"""End-to-end demo: dual-pass extraction -> validation -> Leiden cells -> Neo4j export.

    python demo.py --mock          # fully offline (canned LLM response)
    python demo.py                 # live LLM via EXTRACTION_MODEL (.env)
    python demo.py --mock --push   # also push to Neo4j (needs NEO4J_URI/PASSWORD)

Outputs:
    output/graph.json               Neo4j-ready graph with cluster_ids and cell summary
    output/ingest_generated.cypher  literal Cypher, runs in Neo4j Browser as-is
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from aegis.analytics.clustering import detect_cells  # vendored into the core by T21 (H-36)
from legacy.pipeline.models import ConfidenceTag, LayerType, TemporalEdge
from aegis.projections.cypher import generate_cypher, push_to_neo4j  # vendored by T21 (H-36)
from legacy.pipeline.semantic_pass import extract_semantic
from legacy.pipeline.structural_pass import extract_structural

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data/sample"
OUTPUT = ROOT / "output"


def prove_guardrails() -> None:
    """Show that the Pydantic layer actually enforces the Graphify-style rules."""
    # 1. weight is derived from the confidence tag - a hand-set value is overridden
    edge = TemporalEdge(
        source="a", target="b", relation="test", layer=LayerType.FINANCIAL,
        confidence=ConfidenceTag.AMBIGUOUS, weight=0.99,
    )
    assert edge.weight == 0.4, "weight override was not corrected"
    print("  [ok] hand-set weight 0.99 on an AMBIGUOUS edge corrected to 0.4")

    # 2. an incoherent temporal window is rejected outright
    try:
        TemporalEdge(
            source="a", target="b", relation="test", layer=LayerType.FINANCIAL,
            confidence=ConfidenceTag.INFERRED,
            start_date=date(2024, 1, 1), end_date=date(2023, 1, 1),
        )
    except ValidationError:
        print("  [ok] edge with end_date before start_date rejected by validation")
    else:
        raise SystemExit("guardrail FAILED: invalid temporal window was accepted")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true", help="use the canned LLM response (offline)")
    parser.add_argument("--push", action="store_true", help="push the graph to Neo4j after export")
    args = parser.parse_args()

    print("== 0. Model guardrails ==")
    prove_guardrails()

    print("\n== 1. Structural pass (regex, deterministic) ==")
    arrest_file = "data/sample/pcoi_arrest_list.txt"
    structural = extract_structural(
        (SAMPLES / "pcoi_arrest_list.txt").read_text(encoding="utf-8"), arrest_file
    )
    print(f"  {len(structural.nodes)} persons parsed from the arrest list")
    print(f"  {len(structural.edges)} PRISON_CO_LOCATION edges derived from overlapping remand windows:")
    for e in structural.edges:
        end = e.end_date or "ongoing"
        print(f"    {e.source} <-> {e.target} @ {e.location} [{e.start_date} to {end}] (EXTRACTED, w=1.0)")

    print(f"\n== 2. Semantic pass ({'MOCK' if args.mock else 'live LLM'}) ==")
    report_file = "data/sample/b_report_excerpt.txt"
    semantic = extract_semantic(
        (SAMPLES / "b_report_excerpt.txt").read_text(encoding="utf-8"),
        report_file,
        mock=args.mock,
    )
    print(f"  {len(semantic.nodes)} entities, {len(semantic.edges)} edges extracted from the B-Report:")
    for e in semantic.edges:
        end = e.end_date or ("ongoing" if e.start_date else "-")
        print(f"    {e.source} -[{e.relation}]-> {e.target}  "
              f"layer={e.layer.value} {e.confidence.value} w={e.weight} "
              f"[{e.start_date or '-'} to {end}]")

    print("\n== 3. Merge + audit ==")
    merged = structural.merge(semantic)
    print(f"  merged graph: {len(merged.nodes)} nodes (deduped by node_id), {len(merged.edges)} edges")
    dangling = merged.dangling_edges()
    if dangling:
        print(f"  WARNING: {len(dangling)} edges reference unknown nodes - review before ingesting:")
        for e in dangling:
            print(f"    {e.source} -> {e.target}")
    else:
        print("  [ok] every edge endpoint resolves to a known node")

    print("\n== 4. Leiden community detection (multiplex) ==")
    graph = merged.to_graph_json()
    graph["generated_at"] = datetime.now(timezone.utc).isoformat()
    cells = detect_cells(graph)
    graph["cells"] = cells
    for cell in cells:
        tag = "ISOLATED CELL" if cell["isolated"] else "connected"
        print(f"  cell {cell['cluster_id']} ({tag}, {cell['algorithm']}): "
              f"{', '.join(cell['members'])}")
        print(f"      dominant layer={cell['dominant_layer']} "
              f"internal_edges={cell['internal_edges']} "
              f"avg_confidence_weight={cell['avg_confidence_weight']}")

    print("\n== 5. Export ==")
    OUTPUT.mkdir(exist_ok=True)
    graph_path = OUTPUT / "graph.json"
    graph_path.write_text(json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote {graph_path.relative_to(ROOT)}")

    cypher_path = OUTPUT / "ingest_generated.cypher"
    cypher_path.write_text(generate_cypher(graph), encoding="utf-8")
    print(f"  wrote {cypher_path.relative_to(ROOT)}")

    if args.push:
        print("\n== 6. Neo4j push ==")
        push_to_neo4j(graph)

    print("\nDone. Load output/ingest_generated.cypher in Neo4j Browser, or run:")
    print("  python -m pipeline.neo4j_export --push")


if __name__ == "__main__":
    main()
