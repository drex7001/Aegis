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
| ~~`pipeline/clustering.py`~~ | **Moved into the core at P2 T21** (H-36) — Leiden is a generic algorithm, not domain scaffolding | `aegis/analytics/clustering.py` |
| ~~`pipeline/neo4j_export.py`~~ | **Moved into the core at P2 T21** (H-36) | `aegis/projections/cypher.py` |
| ~~`app/`~~ | **Deleted at P2 T22** with the anonymous `/api/*` routes it consumed (ADR-026) | React + TS workspace (`ui/`), served by `aegis serve` |
| `build_real_graph.py`, `demo.py` | Prototype entry points, kept for reference | `aegis` CLI |
| `cypher/` | Hand-written Neo4j seed | Optional Cypher projection (`aegis projections`) |
| `real_dataset.py` (in `pipeline/`) | Curated-corpus source consumed once by the T8 migration (`aegis/migration/`) | Nothing — deleted with the migration adapters |
| `requirements.txt` | Extraction/ingestion extras (langchain, torch/whisper, PDF tools, neo4j driver) | Platform dependencies in `pyproject.toml` |
| `ARCHITECTURE.md`, `RUNNING.md`, `ADDING_DATA.md`, `INGESTION.md`, `explorer-screenshot.png` | Prototype documentation; the runbooks are unsafe for governed data | `GOAL.md`, `speckit/`, and `docs/INGESTION.md` |

Rules:

- **Do not add features here.** New capability is designed from the ontology
  outward (Article XIV); if legacy behavior is needed, rebuild it on platform
  APIs.
- Bug fixes only where a platform code path (ingestion, migration) still calls
  into this package. Since T21 the projection path no longer does.
- **The core does not import this directory**, except at the two ADR-023
  exemptions (the one-time migration adapter and the governed extraction
  wrapper). That rule is executable, not advisory:
  `tests/component/test_core_independence.py` enumerates the exemptions and
  fails on any other `legacy.*` import under `aegis/`. The arrow points this
  way only — the entry points here import `aegis`, never the reverse.
- The `/api/*` legacy-shaped projection surface is **gone** (T22): the
  explorer that consumed it and the `public_route` marker that exempted it were
  deleted in the same change, and `POST /v1/graph/expand` replaced it with a
  bounded, authorized traversal. This directory is deleted piecewise as the
  table above completes; `pipeline/` is the last substantial item, and it goes
  with extraction v2.
