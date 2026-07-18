"""FastAPI backend for the Sri Lanka temporal multiplex network explorer.

DEPRECATED (speckit T14): the governed API now serves this UI and the same
``/api/*`` projection surface — run ``aegis serve`` (aegis.api.create_app),
which mounts app/static and reads the projection from the claim store. This
standalone server is kept until Phase 3 for offline demos of the legacy
file-based pipeline (build_real_graph.py → output/real_graph.json); it performs
no authorization and must not be exposed beyond localhost.

Serves the interactive UI and a small JSON API over output/real_graph.json:

    GET /                     the single-page Cytoscape.js explorer
    GET /api/graph            full graph (nodes, edges, cells, meta)
    GET /api/stats            node/edge counts, per-layer and per-confidence breakdowns
    GET /api/cells            detected Leiden cells
    GET /api/query/{name}     analyst queries mirroring cypher/ingest.cypher:
                              brokers | ambiguous | hard_facts | ongoing

Run:  python -m app.server        (http://127.0.0.1:8000)
The graph file is read fresh on each request, so re-running build_real_graph.py
is reflected on the next browser refresh — no server restart needed.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[2]
GRAPH_PATH = ROOT / "output" / "real_graph.json"
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Sri Lanka Illicit Networks — Temporal Multiplex Graph")


def load_graph() -> dict:
    if not GRAPH_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail="output/real_graph.json not found — run `python build_real_graph.py` first.",
        )
    return json.loads(GRAPH_PATH.read_text(encoding="utf-8"))


@app.get("/api/graph")
def api_graph() -> JSONResponse:
    return JSONResponse(load_graph())


@app.get("/api/stats")
def api_stats() -> dict:
    g = load_graph()
    by_layer: dict[str, int] = defaultdict(int)
    by_conf: dict[str, int] = defaultdict(int)
    for e in g["edges"]:
        by_layer[e["layer"]] += 1
        by_conf[e["confidence"]] += 1
    by_type: dict[str, int] = defaultdict(int)
    for n in g["nodes"]:
        by_type[n.get("node_type", "PERSON")] += 1
    return {
        "nodes": len(g["nodes"]),
        "edges": len(g["edges"]),
        "cells": len(g.get("cells", [])),
        "by_layer": dict(by_layer),
        "by_confidence": dict(by_conf),
        "by_node_type": dict(by_type),
        "generated_at": g.get("generated_at"),
    }


@app.get("/api/cells")
def api_cells() -> list[dict]:
    return load_graph().get("cells", [])


@app.get("/api/query/{name}")
def api_query(name: str) -> dict:
    """Analyst queries mirroring the Cypher analyst queries in cypher/ingest.cypher."""
    g = load_graph()
    names = {n["node_id"]: n["name"] for n in g["nodes"]}
    edges = g["edges"]

    if name == "brokers":  # people active on >=2 distinct layers (multiplex bridges)
        layers_of: dict[str, set[str]] = defaultdict(set)
        for e in edges:
            layers_of[e["source"]].add(e["layer"])
            layers_of[e["target"]].add(e["layer"])
        rows = [
            {"node_id": nid, "name": names.get(nid, nid), "layers": sorted(ls), "layer_count": len(ls)}
            for nid, ls in layers_of.items()
            if len(ls) >= 2
        ]
        rows.sort(key=lambda r: (-r["layer_count"], r["name"]))
        return {"query": name, "rows": rows}

    if name in ("ambiguous", "hard_facts", "ongoing"):
        if name == "ambiguous":
            sel = [e for e in edges if e["confidence"] == "AMBIGUOUS"]
        elif name == "hard_facts":
            sel = [e for e in edges if e["confidence"] == "EXTRACTED"]
        else:  # ongoing: has a start and no end
            sel = [e for e in edges if e.get("start_date") and not e.get("end_date")]
        rows = [
            {
                "source": names.get(e["source"], e["source"]),
                "target": names.get(e["target"], e["target"]),
                "relation": e["relation"],
                "layer": e["layer"],
                "confidence": e["confidence"],
                "start_date": e.get("start_date"),
                "end_date": e.get("end_date"),
                "source_file": e.get("source_file"),
                "source_excerpt": e.get("source_excerpt"),
            }
            for e in sel
        ]
        return {"query": name, "count": len(rows), "rows": rows}

    raise HTTPException(status_code=404, detail=f"unknown query {name!r}")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def main() -> None:
    import uvicorn

    print("Serving Sri Lanka network explorer at http://127.0.0.1:8000  (Ctrl+C to stop)")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
