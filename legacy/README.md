# Legacy — the pre-Aegis prototype (quarantined)

This directory holds the prototype Aegis grew out of — *"Sri Lanka Illicit
Networks — Temporal Multiplex Graph"*: a regex + LLM extraction pipeline and a
Cytoscape.js explorer over a static graph JSON.

Per **ADR-023 it is replaced, never extended.** Nothing new is built on or
shaped by this code; it runs only as scaffolding until the platform replaces
each piece:

| Item | Role today | Replaced by |
|---|---|---|
| `pipeline/` | Extraction passes feeding the review queue as *suggested claims* (T9); ingestion front end (`docs/INGESTION.md`) | Extraction v2 (`aegis/assist/`, Phase 8); mention extraction (Phase 2) |
| `app/static/index.html` | Explorer UI served by `aegis serve` off the rebuildable projection (ADR-019) | React + TS workspace (`ui/`, Phase 4 — deleted at that gate) |
| `app/server.py` | Deprecated offline-demo server (ADR-019) | Already superseded by `aegis serve` |
| `build_real_graph.py`, `demo.py` | Prototype entry points, kept for reference | `aegis` CLI |
| `cypher/` | Hand-written Neo4j seed | Optional Cypher projection (`aegis projections`) |
| `real_dataset.py` (in `pipeline/`) | Curated-corpus source consumed once by the T8 migration (`aegis/migration/`) | Nothing — deleted with the migration adapters |
| `requirements.txt` | Extraction/ingestion extras (langchain, torch/whisper, PDF tools, neo4j driver) | Platform dependencies in `pyproject.toml` |
| `ARCHITECTURE.md`, `explorer-screenshot.png` | Prototype documentation | `GOAL.md` + `speckit/` |

Rules:

- **Do not add features here.** New capability is designed from the ontology
  outward (Article XIV); if legacy behavior is needed, rebuild it on platform
  APIs.
- Bug fixes only where a platform code path (ingestion, migration, projection)
  still calls into this package.
- The `/api/*` legacy-shaped projection surface (ADR-019) is reviewed for
  retirement at the Phase 4 gate; this directory is deleted piecewise as the
  table above completes.
