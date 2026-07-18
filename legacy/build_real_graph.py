"""Build the REAL Sri Lankan illicit-network graph and write it for Neo4j + the UI.

    python build_real_graph.py                # curated OSINT graph only (offline, deterministic)
    python build_real_graph.py --semantic     # also run the live LLM pass (Gemini via .env) on the
                                              # narrative source docs and merge the result
    python build_real_graph.py --semantic --push   # also push into Neo4j (needs NEO4J_* in .env)

Outputs:
    output/real_graph.json           nodes + edges + cluster_ids + cells + provenance metadata
    output/real_ingest.cypher        literal Cypher, runs in Neo4j Browser as-is

Data provenance & ethics: every node/edge comes from public reporting and carries a citation and an
honest confidence tag (EXTRACTED / INFERRED / AMBIGUOUS). See legacy/pipeline/real_dataset.py for the full
disclaimer. The three networks are kept separate because the public record does not link them.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from aegis.analytics.clustering import detect_cells  # vendored into the core by T21 (H-36)
from legacy.pipeline.models import ExtractionResult
from aegis.projections.cypher import generate_cypher, push_to_neo4j  # vendored by T21 (H-36)
from legacy.pipeline.pdf_loader import split_paragraphs
from legacy.pipeline.real_dataset import build_curated_network, sources_for_meta
from legacy.pipeline.semantic_pass import extract_semantic, resolve_model_name

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "data/real"
OUTPUT = ROOT / "output"

NARRATIVE_DOCS = [
    "narcotics_network.txt",
    "easter_attacks_network.txt",
]

DISCLAIMER = (
    "Analytical model compiled ONLY from public reporting (Wikipedia, PCoI reporting, named Sri Lankan "
    "news outlets). Not a determination of guilt. Confidence tags encode source strength: EXTRACTED = "
    "stated plainly in an official record or by named reporting; INFERRED = probable but not adjudicated; "
    "AMBIGUOUS = alleged / contested. The three networks are not linked in the public record."
)


# Documents longer than this are split into ~chunk-sized paragraph groups, one LLM
# call each, and the results merged — one-shot extraction over a 200-page ingested
# report would blow past output limits and miss most edges.
SEMANTIC_CHUNK_CHARS = 12_000


def extract_semantic_chunked(text: str, source: str) -> ExtractionResult:
    """LLM pass over a document of any length: short docs in one call, long docs
    per ~SEMANTIC_CHUNK_CHARS paragraph group (failed chunks are skipped)."""
    if len(text) <= SEMANTIC_CHUNK_CHARS:
        return extract_semantic(text, source)
    chunks = split_paragraphs(text, min_chars=SEMANTIC_CHUNK_CHARS)
    print(f"    {len(text):,} chars → {len(chunks)} chunks")
    merged = ExtractionResult()
    for i, chunk in enumerate(chunks, 1):
        try:
            merged = merged.merge(extract_semantic(chunk, source))
            print(f"    chunk {i}/{len(chunks)}: total {len(merged.nodes)} nodes, {len(merged.edges)} edges")
        except Exception as exc:  # noqa: BLE001 - a bad chunk shouldn't sink the document
            print(f"    chunk {i}/{len(chunks)}: skipped ({type(exc).__name__}: {exc})")
    return merged


def run_semantic_passes(base: ExtractionResult) -> ExtractionResult:
    """Merge in the live LLM pass over each real narrative document. Failures are
    non-fatal: the curated graph is already complete without them."""
    model = resolve_model_name()
    print(f"  semantic model: {model}")
    merged = base
    for name in NARRATIVE_DOCS:
        path = REAL / name
        try:
            result = extract_semantic_chunked(path.read_text(encoding="utf-8"), f"data/real/{name}")
            print(f"  [ok] {name}: +{len(result.nodes)} nodes, +{len(result.edges)} edges from the LLM")
            merged = merged.merge(result)
        except Exception as exc:  # noqa: BLE001 - report and continue with the curated graph
            print(f"  [skip] {name}: semantic pass failed ({type(exc).__name__}: {exc})")
    return merged


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--semantic", action="store_true", help="also run the live LLM pass (Gemini) and merge")
    parser.add_argument("--push", action="store_true", help="push the graph to Neo4j after export")
    args = parser.parse_args()

    print("== 1. Curated OSINT layer (deterministic, cited) ==")
    graph_result = build_curated_network()
    print(f"  {len(graph_result.nodes)} nodes, {len(graph_result.edges)} edges from public reporting")

    if args.semantic:
        print("\n== 2. Semantic layer (live LLM over real narrative documents) ==")
        graph_result = run_semantic_passes(graph_result)
        print(f"  merged total: {len(graph_result.nodes)} nodes, {len(graph_result.edges)} edges")

    print("\n== 3. Audit ==")
    dangling = graph_result.dangling_edges()
    if dangling:
        print(f"  WARNING: {len(dangling)} edges reference unknown nodes:")
        for e in dangling:
            print(f"    {e.source} -> {e.target} ({e.relation})")
    else:
        print("  [ok] every edge endpoint resolves to a known node")

    print("\n== 4. Leiden community detection (multiplex) ==")
    graph = graph_result.to_graph_json()
    # LLM passes can emit edges to entities they never declared as nodes (e.g. place
    # names). Prune them so clustering/ingest see a consistent node set.
    known = {n["node_id"] for n in graph["nodes"]}
    before = len(graph["edges"])
    graph["edges"] = [e for e in graph["edges"] if e["source"] in known and e["target"] in known]
    if before - len(graph["edges"]):
        print(f"  pruned {before - len(graph['edges'])} dangling edge(s) before clustering")
    cells = detect_cells(graph)
    for cell in cells:
        tag = "ISOLATED CELL" if cell["isolated"] else "connected"
        print(f"  cell {cell['cluster_id']} ({tag}, {cell['algorithm']}, {cell['size']} members, "
              f"dominant={cell['dominant_layer']}): {', '.join(cell['members'][:6])}"
              f"{' …' if cell['size'] > 6 else ''}")

    print("\n== 5. Export ==")
    graph["generated_at"] = datetime.now(timezone.utc).isoformat()
    graph["cells"] = cells
    graph["meta"] = {
        "title": "Sri Lanka Illicit Networks — Temporal Multiplex Graph",
        "disclaimer": DISCLAIMER,
        "sources": sources_for_meta(),
        "layers": {
            "IDEOLOGICAL": "Shared/adopted extremist ideology, membership, allegiance",
            "FINANCIAL": "Money flows and shared illicit enterprise (drug operations, funding, enterprise violence)",
            "PRISON_CO_LOCATION": "Co-located in a prison / remand facility",
            "TRANSNATIONAL": "Cross-border links: foreign networks, smuggling routes, overseas handlers",
        },
        "confidence": {
            "EXTRACTED": "1.0 — stated plainly in an official record or by named reporting",
            "INFERRED": "0.7 — probable link reporting supports but has not adjudicated",
            "AMBIGUOUS": "0.4 — alleged / contested / uncorroborated",
        },
    }

    OUTPUT.mkdir(exist_ok=True)
    graph_path = OUTPUT / "real_graph.json"
    graph_path.write_text(json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote {graph_path.relative_to(ROOT)}  ({len(graph['nodes'])} nodes, {len(graph['edges'])} edges, {len(cells)} cells)")

    cypher_path = OUTPUT / "real_ingest.cypher"
    cypher_path.write_text(generate_cypher(graph), encoding="utf-8")
    print(f"  wrote {cypher_path.relative_to(ROOT)}")

    if args.push:
        print("\n== 6. Neo4j push ==")
        push_to_neo4j(graph)

    print("\nDone. Launch the UI with:  python -m app.server   (then open http://127.0.0.1:8000)")


if __name__ == "__main__":
    main()
