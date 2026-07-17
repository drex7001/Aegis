# Sri Lanka Illicit Networks — Temporal Multiplex Graph

Extraction + ingestion pipeline **and interactive web UI** that turns unstructured Sri
Lankan legal/intelligence documents (PCoI reports, B-Reports, judgments, news) into a
**Neo4j-ready dynamic temporal multiplex graph** for lawful criminal-network analysis.
The architecture mirrors the open-source **Graphify** pattern: a cheap deterministic pass
plus an LLM pass, with an honest per-edge audit trail.

It ships with a **real, fully-cited OSINT dataset** of ~41 documented figures across three
Sri Lankan networks (historical Colombo underworld · modern transnational narcotics · the
2019 Easter Sunday / NTJ extremist network) and a browser explorer to navigate it.

> **Two data tracks.** `sample_data/` is **fictional** (exercises the regex pass).
> `real_data/` + `pipeline/real_dataset.py` is a **real** open-source model compiled only
> from public reporting — every node/edge carries a citation and an honest confidence tag
> (AMBIGUOUS = alleged/contested). It is **not a determination of guilt**; see
> [`real_data/README.md`](real_data/README.md).

> **Where this is going.** This prototype is being **replaced** by **Aegis**, an
> ontology-driven, governed intelligence platform ([`GOAL.md`](GOAL.md)) in which
> criminal-network analysis is the first application domain — not the platform's
> identity (ADR-023). The build path — constitution, roadmap, ADRs, detailed specs,
> and the declarative ontology — lives in [`speckit/`](speckit/README.md) and
> [`ontology/aegis.yaml`](ontology/aegis.yaml). The prototype documented below is
> legacy scaffolding: kept running until Aegis replaces it, never extended.

## Quickstart — real graph + web UI

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

.venv\Scripts\python build_real_graph.py     # build output/real_graph.json (curated, offline)
.venv\Scripts\python -m app.server           # serve the explorer at http://127.0.0.1:8000
```

Open **http://127.0.0.1:8000**. The explorer (Cytoscape.js + FastAPI) gives you:

- **Multiplex layer toggles** (Ideological / Financial / Prison co-location / Transnational) — edges coloured per layer.
- **Confidence filter** — Extracted / Inferred / Ambiguous, rendered as solid / dashed / dotted links.
- **Temporal slider** — drag left for an _as-of-date_ snapshot (relationships active on that date), rightmost = full all-time network; **Play** animates the timeline.
- **Detected cells** — Leiden communities, colour-coded, with isolated cells flagged; every node/edge detail card shows its **source citation and the supporting excerpt**.
- **Analyst queries** — cross-layer brokers, ambiguous-review queue, hard-facts-only, ongoing-now — mirroring the Cypher analyst queries and the `/api/query/*` endpoints.

### Live LLM (Gemini) semantic pass

The semantic pass is provider-agnostic (`init_chat_model`). A `GEMINI_API_KEY` in `.env`
defaults it to `google_genai:gemini-2.5-flash-lite`:

```powershell
.venv\Scripts\python build_real_graph.py --semantic   # merge a live LLM pass over the real narratives
```

`build_real_graph.py --semantic` runs Gemini over the `real_data/*.txt` narratives, validates
its JSON against the same Pydantic schema, prunes any dangling edges, and merges the result
into the curated graph. Failures are non-fatal — the curated graph stands on its own.

## Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — full guided tour: the mental model, the system
  diagram, a component-by-component reference, how data flows end-to-end, the confidence &
  ethics rubric, and the exact steps used to build this. Start here to understand the system.
- **[docs/INGESTION.md](docs/INGESTION.md)** — turn raw source material (PDF reports,
  video/audio in Sinhala, pasted text) into extraction-ready documents: opendataloader-pdf
  structured parsing + whisper-small-sinhala speech-to-text, one command.
- **[docs/RUNNING.md](docs/RUNNING.md)** — every command, flag, and expected output.
- **[docs/ADDING_DATA.md](docs/ADDING_DATA.md)** — copy-paste recipes to add your own data
  the three ways (curated fact · structured list · narrative document).
- **[real_data/README.md](real_data/README.md)** — data provenance, source list, and ethics.

## Architecture

```
Files/ (raw drop zone: PDF / MP4 / MP3 / WAV / TXT)
             │
             └─> pipeline/ingest.py   one-command ingestion (docs/INGESTION.md)
                   ├─ .pdf   → pdf_ingest.py   opendataloader-pdf structured markdown
                   │                           (Java CLI; pdfplumber fallback)
                   ├─ media  → transcribe.py   whisper-small-sinhala speech-to-text
                   └─ .txt   → provenance-headed copy
                              │
                    real_data/<slug>.txt   (review → register in NARRATIVE_DOCS)
                              │
PDFs / text ─┬─> structural_pass.py   regex on structured lists (arrest annexes)
             │      └─ EXTRACTED nodes + deterministic PRISON_CO_LOCATION edges
             │
             └─> semantic_pass.py     LangChain init_chat_model() on narrative text
                    └─ LLM output validated against the same Pydantic schema
                       (long docs auto-chunked ~12k chars/call, results merged)
                              │
                    models.py  ExtractionResult.merge()  (dedup by node_id)
                              │
                    clustering.py  Leiden (leidenalg.find_partition_multiplex
                              │            across layers; Louvain fallback)
                              │
             ┌────────────────┴────────────────┐
     output/graph.json              output/ingest_generated.cypher
     (GraphRAG/driver-ready)        (runs in Neo4j Browser as-is)
```

## Edge contract (Graphify-style)

Every edge carries all of the following — the Pydantic layer enforces it:

| Field                            | Rule                                                                                                                            |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `confidence`                     | `EXTRACTED` (hard fact: judgments, official lists) / `INFERRED` (probable, from context) / `AMBIGUOUS` (suspected, unconfirmed) |
| `weight`                         | **Derived** from the tag: 1.0 / 0.7 / 0.4. A hand-set value is overwritten.                                                     |
| `layer`                          | `IDEOLOGICAL` \| `FINANCIAL` \| `PRISON_CO_LOCATION` \| `TRANSNATIONAL` — also the Neo4j relationship type                      |
| `start_date` / `end_date`        | ISO dates; `end_date = null` means ongoing. `end < start` is rejected.                                                          |
| `source_file` / `source_excerpt` | Provenance: the document and the verbatim supporting sentence                                                                   |
| `extraction_method`              | `STRUCTURAL` (regex) or `SEMANTIC` (LLM)                                                                                        |

Honesty rule inherited from Graphify: **never invent an edge — if unsure, tag it
AMBIGUOUS rather than omit it**, so weak links enter the analyst review queue
(`cypher/ingest.cypher` Q4) instead of silently disappearing.

## Quickstart

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# fully offline end-to-end run (canned LLM response):
.venv\Scripts\python demo.py --mock

# live LLM run: copy .env.example to .env, set EXTRACTION_MODEL + API key
.venv\Scripts\python demo.py
```

`demo.py` runs both passes on the samples, proves the validation guardrails, merges,
detects cells with Leiden, and writes `output/graph.json` + `output/ingest_generated.cypher`.

## Neo4j

```powershell
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/yourpassword neo4j:5
```

Then either paste `output/ingest_generated.cypher` into Neo4j Browser (no plugins
needed — relationship types are inlined per layer), or push via the driver:

```powershell
.venv\Scripts\python -m pipeline.neo4j_export --push   # reads NEO4J_* from .env
```

`cypher/ingest.cypher` additionally documents the parameterized `UNWIND` ingest
(APOC and no-APOC variants) and eight analyst queries: temporal as-of snapshots,
per-layer projections, hard-facts-only and AMBIGUOUS-review filters,
confidence-weighted paths, detected cells, and cross-layer brokers.

## Processing real documents

Raw source material — PDF reports, Sinhala video/audio, pasted text — is ingested with
one command (full guide: [docs/INGESTION.md](docs/INGESTION.md)):

```bash
./scripts/setup_ingestion.sh              # one-time: venv + packages + local JRE (no root)
.venv/bin/python -m pipeline.ingest       # ingest everything new in Files/
```

PDFs go through **opendataloader-pdf** (structure-aware markdown + JSON layout audit
copies in `output/ingest/`), media through **whisper-small-sinhala** (timestamped Sinhala
transcript; slow on CPU — use `--max-minutes 2` to test first). Everything lands in
`real_data/` with a provenance header, ready to register in `NARRATIVE_DOCS`
(`build_real_graph.py`) for the semantic pass — long documents are chunked automatically.

The lower-level API remains available:

```python
from pipeline.pdf_ingest import convert_pdf
from pipeline.pdf_loader import split_paragraphs
from pipeline.structural_pass import extract_structural
from pipeline.semantic_pass import extract_semantic

text = convert_pdf("pcoi_report.pdf")     # structured markdown (pdfplumber fallback)
result = extract_structural(text, "pcoi_report.pdf")
for para in split_paragraphs(text):
    result = result.merge(extract_semantic(para, "pcoi_report.pdf"))
```

Adjust `ARREST_LINE_RE` in `pipeline/structural_pass.py` to the exact annex format
of the documents you hold; everything downstream is format-agnostic.

## Layout

```
pipeline/
  models.py           Pydantic schema: CriminalNode, TemporalEdge, ExtractionResult
  real_dataset.py     REAL curated OSINT graph (cited nodes/edges) — the deterministic layer
  structural_pass.py  regex pass (EXTRACTED only, deterministic co-location)
  semantic_pass.py    LangChain LLM pass (Gemini/Anthropic/OpenAI/Ollama) + offline mock
  clustering.py       Leiden multiplex community detection (Louvain fallback)
  neo4j_export.py     Cypher generation + parameterized driver push
  ingest.py           one-command raw-file ingestion: PDF/media/text → real_data/*.txt
  pdf_ingest.py       opendataloader-pdf structured extraction (Java; audit JSON+MD)
  transcribe.py       Sinhala speech-to-text (whisper-small-sinhala, bundled ffmpeg)
  pdf_loader.py       pdfplumber text extraction (fallback loader)
scripts/
  setup_ingestion.sh  one-time no-root setup: venv, packages, project-local JRE 21
app/
  server.py           FastAPI backend: serves the UI + /api/graph, /api/stats, /api/query/*
  static/index.html   Cytoscape.js explorer (layers, confidence, temporal slider, cells, sources)
real_data/            REAL narrative docs (semantic-pass input) + provenance/ethics README
cypher/ingest.cypher  parameterized ingest + analyst queries
sample_data/          FICTIONAL PCoI arrest list + B-Report excerpt (regex-pass demo only)
build_real_graph.py   real-graph orchestrator  ->  output/real_graph.json + output/real_ingest.cypher
demo.py               fictional end-to-end orchestrator (mechanism proof)
output/               generated graph JSON + Cypher (real_graph.json powers the UI)
```

## UI

![alt text](image.png)
