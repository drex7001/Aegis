"""Legacy-compatible projection surface (spec 06 Projections; plan §4.4, T14).

The existing single-page UI fetches these unversioned ``/api/*`` routes with no
bearer token, so they are deliberately **public** — and safe to be, because
they serve only the open-handling, case-less projection (the public OSINT
floor).  Anything above ``open`` never enters ``output/real_graph.json`` (the
emitter forces ``open_only``), so there is nothing here to leak.

The routes read the committed projection file, exactly as the retired
``app/server.py`` did, so the UI's data source and shapes are unchanged.  Run
``aegis projections rebuild`` to refresh it from the claim store.
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from aegis.api.deps import public_route

router = APIRouter(tags=["projections"])

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GRAPH_PATH = _REPO_ROOT / "output" / "real_graph.json"


def _load_graph() -> dict:
    if not _GRAPH_PATH.exists():
        raise HTTPException(
            503,
            "output/real_graph.json not found — run `aegis projections rebuild`.",
        )
    return json.loads(_GRAPH_PATH.read_text(encoding="utf-8"))


@router.get("/api/graph")
@public_route
def api_graph() -> JSONResponse:
    return JSONResponse(_load_graph())


@router.get("/api/stats")
@public_route
def api_stats() -> dict:
    graph = _load_graph()
    by_layer: dict[str, int] = defaultdict(int)
    by_conf: dict[str, int] = defaultdict(int)
    for edge in graph["edges"]:
        by_layer[edge["layer"]] += 1
        by_conf[edge["confidence"]] += 1
    by_type: dict[str, int] = defaultdict(int)
    for node in graph["nodes"]:
        by_type[node.get("node_type", "PERSON")] += 1
    return {
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
        "cells": len(graph.get("cells", [])),
        "by_layer": dict(by_layer),
        "by_confidence": dict(by_conf),
        "by_node_type": dict(by_type),
        "generated_at": graph.get("generated_at"),
    }


@router.get("/api/cells")
@public_route
def api_cells() -> list[dict]:
    return _load_graph().get("cells", [])


@router.get("/api/query/{name}")
@public_route
def api_query(name: str) -> dict:
    graph = _load_graph()
    names = {n["node_id"]: n["name"] for n in graph["nodes"]}
    edges = graph["edges"]

    if name == "brokers":
        layers_of: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            layers_of[edge["source"]].add(edge["layer"])
            layers_of[edge["target"]].add(edge["layer"])
        rows = [
            {"node_id": nid, "name": names.get(nid, nid), "layers": sorted(ls), "layer_count": len(ls)}
            for nid, ls in layers_of.items()
            if len(ls) >= 2
        ]
        rows.sort(key=lambda r: (-r["layer_count"], r["name"]))
        return {"query": name, "rows": rows}

    if name in ("ambiguous", "hard_facts", "ongoing"):
        if name == "ambiguous":
            selected = [e for e in edges if e["confidence"] == "AMBIGUOUS"]
        elif name == "hard_facts":
            selected = [e for e in edges if e["confidence"] == "EXTRACTED"]
        else:
            selected = [e for e in edges if e.get("start_date") and not e.get("end_date")]
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
            for e in selected
        ]
        return {"query": name, "count": len(rows), "rows": rows}

    raise HTTPException(404, f"unknown query {name!r}")
