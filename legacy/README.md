# Legacy — the pre-Aegis prototype (quarantined)

This directory holds the prototype Aegis grew out of — *"Sri Lanka Illicit
Networks — Temporal Multiplex Graph"*: a regex + LLM extraction pipeline and a
Cytoscape.js explorer over a static graph JSON.

Per **ADR-023 it is replaced, never extended.** Nothing new is built on or
shaped by this code; it runs only as scaffolding until the platform replaces
each piece:

| Item | Role today | Replaced by |
|---|---|---|
| `pipeline/` | Prototype extraction scaffolding still called by the governed wrapper; historical ingestion instructions are unsafe reference only | Phase 2 mention extraction and later extraction v2 |
| `app/static/index.html` | Explorer UI served by `aegis serve` off the rebuildable projection | React + TS workspace (`ui/`, deleted at P2 T22) |
| `app/server.py` | Deprecated offline-demo server (ADR-019) | Already superseded by `aegis serve` |
| `build_real_graph.py`, `demo.py` | Prototype entry points, kept for reference | `aegis` CLI |
| `cypher/` | Hand-written Neo4j seed | Optional Cypher projection (`aegis projections`) |
| `real_dataset.py` (in `pipeline/`) | Curated-corpus source consumed once by the T8 migration (`aegis/migration/`) | Nothing — deleted with the migration adapters |
| `requirements.txt` | Extraction/ingestion extras (langchain, torch/whisper, PDF tools, neo4j driver) | Platform dependencies in `pyproject.toml` |
| `ARCHITECTURE.md`, `RUNNING.md`, `ADDING_DATA.md`, `INGESTION.md`, `explorer-screenshot.png` | Prototype documentation; the runbooks are unsafe for governed data | `GOAL.md`, `speckit/`, and `docs/INGESTION.md` |

Rules:

- **Do not add features here.** New capability is designed from the ontology
  outward (Article XIV); if legacy behavior is needed, rebuild it on platform
  APIs.
- Bug fixes only where a platform code path (ingestion, migration, projection)
  still calls into this package.
- The `/api/*` legacy-shaped projection surface is loopback-contained until it
  is deleted with the Phase 2 T22 workspace change; this directory is deleted
  piecewise as the table above completes.
