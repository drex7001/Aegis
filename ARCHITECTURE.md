# Architecture — legacy prototype ("Sri Lanka Illicit Networks Temporal Multiplex Graph")

> **⚠️ Legacy document.** This describes the **pre-Aegis prototype** — the static
> extraction pipeline and Cytoscape explorer. Per ADR-023 the prototype is
> **replaced, never extended**: it survives only as scaffolding (the explorer is
> served by `aegis serve` off a rebuildable projection) until the Phase 4
> workspace deletes it. The platform's architecture lives in
> [`GOAL.md`](GOAL.md) and [`speckit/`](speckit/README.md); this file is kept as
> a reference for the legacy code still in the tree.

A guided tour of the prototype: what it is, how the pieces fit, how data flows through
it, how to run it, how to add data, and the exact steps used to build it. Written to be
readable by a non-specialist first, with the technical detail underneath.

> Companion how-tos: [`docs/RUNNING.md`](docs/RUNNING.md) (exact commands) ·
> [`docs/ADDING_DATA.md`](docs/ADDING_DATA.md) (add your own data) ·
> [`real_data/README.md`](real_data/README.md) (sources & ethics).

---

## Table of contents

1. [What this is (in plain words)](#1-what-this-is-in-plain-words)
2. [The mental model: nodes, links, layers, confidence, time](#2-the-mental-model)
3. [System architecture (the big diagram)](#3-system-architecture)
4. [The data contract (what a node and a link look like)](#4-the-data-contract)
5. [How data flows end-to-end](#5-how-data-flows-end-to-end)
6. [Component reference (every file, what it does)](#6-component-reference)
7. [Running the pipeline](#7-running-the-pipeline)
8. [Adding data (three ways)](#8-adding-data-three-ways)
9. [The web UI](#9-the-web-ui)
10. [Neo4j ingestion](#10-neo4j-ingestion)
11. [Confidence & ethics rubric](#11-confidence--ethics-rubric)
12. [The exact steps used to build this](#12-the-exact-steps-used-to-build-this)
13. [Troubleshooting / FAQ](#13-troubleshooting--faq)
14. [Glossary](#14-glossary)

---

## 1. What this is (in plain words)

This project takes messy, unstructured writing about criminal networks — news stories,
court/commission reports, intelligence-style summaries — and turns it into a **graph**:
a set of **people/organisations** (dots) joined by **relationships** (lines). It then
lets you **explore that graph in a web browser** and load it into a **graph database
(Neo4j)** for deeper analysis.

Three things make it more than a plain diagram:

- **Multiplex** — a relationship belongs to one of four *layers* (ideological, financial,
  prison co-location, transnational). You can look at one layer at a time or all together.
- **Temporal** — every relationship has a start and (optionally) end date, so you can ask
  "what did the network look like *as of* a given date?"
- **Honest** — every relationship carries a **confidence tag** and a **source citation**.
  Nothing is stated more firmly than the evidence supports. A suspected-but-unproven link
  is kept and labelled *ambiguous* rather than silently dropped or silently asserted.

It ships with a **real dataset** compiled only from public reporting about documented Sri
Lankan cases (drug networks, the historical Colombo underworld, the 2019 Easter/NTJ
attacks), and a **fictional dataset** used only to test the machinery.

---

## 2. The mental model

Five ideas are all you need:

| Idea | Plain meaning | In the code |
|---|---|---|
| **Node** | A person or organisation | `CriminalNode` |
| **Edge** | A directed relationship between two nodes | `TemporalEdge` |
| **Layer** | *What kind* of relationship it is | `LayerType` (4 values) |
| **Confidence** | *How sure* we are it's real | `ConfidenceTag` (3 values) → a numeric `weight` |
| **Time** | *When* the relationship held | `start_date`, `end_date` (null end = ongoing) |

**The four layers**

- `IDEOLOGICAL` — shared/adopted extremist ideology, membership, allegiance.
- `FINANCIAL` — money flows and shared illicit enterprise (drug operations, funding, enterprise violence).
- `PRISON_CO_LOCATION` — held together in a prison / remand facility.
- `TRANSNATIONAL` — cross-border links: foreign networks, smuggling routes, overseas handlers.

**The three confidence tags** (and the weight each forces)

- `EXTRACTED` = **1.0** — stated plainly in an official record or by named reporting.
- `INFERRED` = **0.7** — probable link reporting supports but has not adjudicated.
- `AMBIGUOUS` = **0.4** — alleged / contested / uncorroborated.

The weight is **derived** from the tag — you cannot set it by hand (see §4). Community
detection uses these weights, so hard facts pull nodes together harder than suspicions.

---

## 3. System architecture

```
                          ┌──────────────────────────────────────────────────┐
   INPUTS                 │                    EXTRACTION                      │
                          │                                                    │
 real_data/*.txt ─────────┼──▶ semantic_pass.py   (LLM: Gemini / Claude / …) ──┼──┐
 (narrative reports)      │      "read prose → nodes + edges"                  │  │
                          │                                                    │  │
 numbered arrest/         │                                                    │  │
 remand annexes ──────────┼──▶ structural_pass.py (regex, deterministic) ──────┼──┤
                          │      "parse list → PRISON_CO_LOCATION edges"       │  │
                          │                                                    │  │
 pipeline/real_dataset.py │                                                    │  │
 (hand-verified, cited) ──┼──▶ build_curated_network()  ──────────────────────┼──┤
                          └────────────────────────────────────────────────────┘  │
                                                                                   ▼
                                                ┌───────────────────────────────────────┐
                                                │  models.py — the Pydantic contract      │
                                                │  • validate every node/edge            │
                                                │  • DERIVE weight from confidence tag    │
                                                │  • slug node IDs (dedupe key)           │
                                                │  • merge() unions passes, dedupes       │
                                                └───────────────────────────────────────┘
                                                                                   │
                                                       ExtractionResult {nodes, edges}
                                                                                   ▼
                                                ┌───────────────────────────────────────┐
                                                │  clustering.py — Leiden (multiplex)     │
                                                │  → writes cluster_id per node           │
                                                │  → returns cell summaries (isolated?)   │
                                                └───────────────────────────────────────┘
                                                                                   │
                                          build_real_graph.py orchestrates all of the above
                                                                                   │
                                        ┌──────────────────────────────────────────┴────────┐
                                        ▼                                                     ▼
                             output/real_graph.json                          output/real_ingest.cypher
                             (nodes+edges+cells+meta)                         (literal MERGE statements)
                                        │                                                     │
                          ┌─────────────┴───────────────┐                                     ▼
                          ▼                             ▼                               Neo4j database
                 app/server.py (FastAPI)      GraphRAG / offline analysis        (paste in Browser, or --push)
                 GET /api/graph,/stats,/query
                          │
                          ▼
                 app/static/index.html  ──  Cytoscape.js explorer (runs in the browser)
```

**Reading the diagram:** three *sources of facts* on the left feed three *extraction
passes*. Everything they produce is forced through one **validation contract**
(`models.py`), merged into a single `ExtractionResult`, **clustered**, and written to two
**outputs**: a JSON graph (which the **web UI** and any downstream analysis read) and a
**Cypher** file (which loads the same graph into **Neo4j**).

**Upstream of this diagram** sits the ingestion layer ([`docs/INGESTION.md`](docs/INGESTION.md)):
raw source files dropped in `Files/` — PDF reports, Sinhala video/audio, pasted text —
are converted by `pipeline/ingest.py` into the `real_data/*.txt` narrative inputs shown
on the left (opendataloader-pdf structured parsing for PDFs, whisper-small-sinhala
speech-to-text for media, provenance headers on everything).

---

## 4. The data contract

Everything — regex output, LLM output, hand-curated facts — is validated by the same two
Pydantic models in `pipeline/models.py`. This is the single most important design idea:
**no matter where a node or edge comes from, it must satisfy the same rules.**

```
CriminalNode                              TemporalEdge
────────────                              ────────────
node_id        slug, auto-derived         source ──▶ target   (node_id slugs, directed)
name                                       relation           (verb slug: partnered_with, …)
aliases[]                                  layer      ∈ {IDEOLOGICAL, FINANCIAL,
nic            (omitted for real people)                     PRISON_CO_LOCATION, TRANSNATIONAL}
affiliations[]                             confidence ∈ {EXTRACTED, INFERRED, AMBIGUOUS}
node_type      ∈ {PERSON, ORGANIZATION}    weight     = DERIVED (1.0 / 0.7 / 0.4)  ← not user-settable
source_file    (citation)                  start_date / end_date   (null end = ongoing)
source_excerpt (supporting quote)          location
                                           source_file / source_excerpt
                                           extraction_method ∈ {STRUCTURAL, SEMANTIC, CURATED}
```

Four rules the contract enforces automatically (you cannot bypass them):

1. **Weight is derived, never set.** `weight = CONFIDENCE_WEIGHTS[confidence]`. If an LLM
   returns `confidence: AMBIGUOUS, weight: 0.95`, the 0.95 is overwritten with 0.4. The
   audit trail cannot be gamed.
2. **Deterministic IDs.** `node_id = slugify(name)` (`"Makandure Madush"` → `makandure_madush`).
   The same person from two documents gets the same ID and **merges** into one node.
3. **Temporal sanity.** An `end_date` before its `start_date` is rejected outright.
4. **No self-loops.** An edge from a node to itself is rejected.

`ExtractionResult` is the container (`{nodes, edges}`). Its `merge()` unions two passes,
deduping nodes by `node_id` (combining their evidence) and edges by a key tuple. Its
`to_graph_json()` produces the plain dict that everything downstream consumes.

---

## 5. How data flows end-to-end

The real graph is produced by `build_real_graph.py` in these ordered steps:

1. **Curated layer** — `build_curated_network()` returns an `ExtractionResult` of the
   hand-verified, cited nodes/edges (the reliable backbone).
2. **Semantic layer (optional, `--semantic`)** — for each narrative in `real_data/`, the
   LLM extracts nodes/edges; each result is validated and `merge()`d in. Failures are
   caught and skipped (the curated graph stands alone).
3. **Audit** — `dangling_edges()` reports any edge whose endpoints aren't in the node set.
4. **Prune + cluster** — dangling edges (common from LLM passes that invent place-nodes)
   are dropped, then `detect_cells()` runs Leiden and writes `cluster_id` onto each node.
5. **Export** — the graph dict (plus `generated_at`, `cells`, and a `meta` block of
   sources/legends) is written to `output/real_graph.json`, and `generate_cypher()` writes
   `output/real_ingest.cypher`.

Then, independently:

6. **Serve** — `app/server.py` reads `output/real_graph.json` and serves it + the UI.
7. **(Optional) Ingest** — paste the Cypher into Neo4j Browser, or `--push` via the driver.

---

## 6. Component reference

| File | Responsibility | Key symbols |
|---|---|---|
| `pipeline/models.py` | The validation contract shared by every pass | `ConfidenceTag`, `LayerType`, `CriminalNode`, `TemporalEdge`, `ExtractionResult`, `slugify` |
| `pipeline/real_dataset.py` | The **real** curated OSINT graph (cited nodes/edges) | `SOURCES`, `build_curated_network()`, `_n()`, `_e()`, name constants |
| `pipeline/structural_pass.py` | Deterministic regex parse of numbered arrest/remand lists → `PRISON_CO_LOCATION` edges from overlapping remand windows | `ARREST_LINE_RE`, `parse_arrest_list()`, `co_location_edges()`, `extract_structural()` |
| `pipeline/semantic_pass.py` | Provider-agnostic LLM extraction from prose (Gemini/Claude/OpenAI/Ollama) + offline mock | `SYSTEM_PROMPT`, `resolve_model_name()`, `extract_semantic()`, `mock_extraction_result()` |
| `pipeline/clustering.py` | Community detection: Leiden multiplex (igraph+leidenalg), NetworkX Louvain fallback | `detect_cells()` |
| `pipeline/neo4j_export.py` | Graph → literal Cypher file, or parameterized driver push | `generate_cypher()`, `push_to_neo4j()` |
| `pipeline/pdf_loader.py` | Extract text from PDFs, split into paragraphs (fallback loader) | `load_pdf_text()`, `split_paragraphs()` |
| `pipeline/ingest.py` | One-command ingestion router: raw PDF/media/text → provenance-headed `real_data/*.txt` | `ingest_file()`, `target_for()`, `main()` |
| `pipeline/pdf_ingest.py` | Structure-aware PDF extraction via opendataloader-pdf (Java CLI, project-local JRE), audit copies in `output/ingest/` | `convert_pdf()`, `find_java()` |
| `pipeline/transcribe.py` | Sinhala speech-to-text (whisper-small-sinhala + bundled ffmpeg), 10-min blocks with incremental writes | `transcribe_media()`, `transcribe_to_file()`, `load_audio()` |
| `scripts/setup_ingestion.sh` | One-time, no-root setup of the ingestion stack (venv, CPU torch, local JRE 21) | — |
| `build_real_graph.py` | **Orchestrator** for the real graph (curated + optional semantic → cluster → export); long docs chunked | `main()`, `run_semantic_passes()`, `extract_semantic_chunked()` |
| `app/server.py` | FastAPI backend: serves the UI and JSON API | `/api/graph`, `/api/stats`, `/api/cells`, `/api/query/{name}` |
| `app/static/index.html` | The Cytoscape.js single-page explorer | (all client-side) |
| `demo.py` | End-to-end run on the **fictional** sample (mechanism proof) | `prove_guardrails()`, `main()` |
| `cypher/ingest.cypher` | Standalone parameterized ingest + 8 analyst queries | — |

---

## 7. Running the pipeline

Prerequisites: Python 3.12, and a one-time install.

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

**Build the real graph (offline, deterministic — recommended default):**

```powershell
.venv\Scripts\python build_real_graph.py
# → output/real_graph.json  (41 nodes, 57 edges, 7 cells)
# → output/real_ingest.cypher
```

**Launch the web UI:**

```powershell
.venv\Scripts\python -m app.server        # http://127.0.0.1:8000
```

**Build with the live LLM (Gemini) semantic pass merged in:**

```powershell
.venv\Scripts\python build_real_graph.py --semantic
```

**Run the fictional mechanism demo (no API key, exercises the regex pass):**

```powershell
.venv\Scripts\python demo.py --mock
```

See [`docs/RUNNING.md`](docs/RUNNING.md) for every command, flag, and expected output.

---

## 8. Adding data (three ways)

You choose the pass that matches what you have. All three go through the same contract, so
they combine cleanly (same person → same `node_id` → merged). Full copy-paste recipes are
in [`docs/ADDING_DATA.md`](docs/ADDING_DATA.md); the summary:

**A. Curated fact (best for verified, cited facts) — edit `pipeline/real_dataset.py`.**
Add a source to `SOURCES`, a node with `_n(...)`, and edges with `_e(...)` (choosing layer,
confidence, dates, and the source key). Rebuild with `python build_real_graph.py`.

```python
# in SOURCES:
"my_source": ("Daily Mirror — 'Headline'", "https://www.dailymirror.lk/..."),
# a node (add to the right network block):
_n("New Person", aliases=["Real Name"], affiliations=["Some network"],
   src="my_source", note="One-line sourced bio."),
# an edge:
_e("New Person", "Makandure Madush", "supplied_narcotics_to", FIN, INFERRED,
   src="my_source", excerpt="Quote or paraphrase that supports the link.",
   start="2018-01-01", location="Colombo"),
```

**B. Structured list (arrest/remand annexes) — deterministic, zero-LLM.**
Format each line exactly as `ARREST_LINE_RE` expects and run `extract_structural()`. It
derives `PRISON_CO_LOCATION` edges from overlapping remand windows at the same facility:

```
1. Kasun WIJERATNE alias "Podda" — arrested 2023-02-14 — remanded, Welikada Prison (2023-02-15 to ongoing)
```

**C. Narrative document (prose) — the LLM semantic pass.**
Drop a `.txt` report in `real_data/`, add its filename to `NARRATIVE_DOCS` in
`build_real_graph.py`, and run `--semantic`. The model follows the honesty rules in
`SYSTEM_PROMPT` (never invent an edge; tag weak links AMBIGUOUS; quote the source sentence;
put place names in `location`, not as nodes). Long documents are chunked automatically
(~12k chars per call) and the results merged.

**D. Raw files (PDF / video / audio) — ingest first.**
`python -m pipeline.ingest <file-or-Files/>` converts raw source material into
extraction-ready `real_data/*.txt` (structured PDF parsing, Sinhala speech-to-text,
provenance headers), then feed the result to pass B or C. Guide: [`docs/INGESTION.md`](docs/INGESTION.md).

**Deduping tip:** use each entity's *common* name as the primary `name` and put formal
names in `aliases`, so the same person from different passes resolves to the same
`node_id`.

---

## 9. The web UI

`app/server.py` (FastAPI) serves `app/static/index.html` (Cytoscape.js). The page fetches
`/api/graph` once and does all filtering client-side:

- **Layer toggles** — show/hide each of the four layers; edges are coloured per layer.
- **Confidence filter** — Extracted/Inferred/Ambiguous, drawn as solid/dashed/dotted lines.
- **Temporal slider** — rightmost = full all-time network; drag left for an *as-of-date*
  snapshot (an edge is active if it started by that date and hasn't ended); **Play**
  animates the timeline.
- **Colour by** — detected cell (Leiden) or dominant layer; node size = degree.
- **Detail panel** — click any node/edge to see its fields, its **source citation (a link)**
  and the **supporting excerpt**.
- **Detected cells / Breakdown / Sources** panels on the right.
- **Analyst queries** — *cross-layer brokers*, *ambiguous review*, *hard facts only*,
  *ongoing now* — highlight matching elements; they mirror `/api/query/{name}` and the
  Cypher analyst queries.

JSON API (also usable headless): `GET /api/graph`, `/api/stats`, `/api/cells`,
`/api/query/{brokers|ambiguous|hard_facts|ongoing}`.

---

## 10. Neo4j ingestion

Two paths, both produced from the same graph:

- **Literal file** — `output/real_ingest.cypher` contains idempotent `MERGE` statements
  with the relationship *type* = the layer (e.g. `-[:FINANCIAL]->`). Paste it into Neo4j
  Browser; no plugins needed. (Safe because the layer is whitelisted against `LayerType`
  before it's interpolated.)
- **Driver push** — `python build_real_graph.py --push` (or `python -m pipeline.neo4j_export
  --push`) batches a parameterized `UNWIND` ingest per layer, reading `NEO4J_URI/USER/PASSWORD`
  from `.env`.

`cypher/ingest.cypher` additionally documents the parameterized/APOC ingest variants and 8
analyst queries (temporal as-of snapshots, per-layer projections, hard-facts-only,
ambiguous-review, confidence-weighted paths, detected cells, cross-layer brokers, ongoing).

---

## 11. Confidence & ethics rubric

This system models **real people from public reporting**, so honesty is built into the
data, not bolted on:

- **Open-source only.** Nothing asserts anything beyond what the cited sources say.
- **Not a determination of guilt.** It is an analytical aid for lawful network analysis.
- **Confidence encodes source strength** (EXTRACTED/INFERRED/AMBIGUOUS). Contested claims
  (e.g. Islamic State *directing* the Easter attacks, which the CID did not establish) are
  tagged `AMBIGUOUS` — kept visible for review, not asserted.
- **National ID numbers are omitted** for real individuals.
- **The three networks are kept separate** because the public record does not link them;
  clustering recovering them as distinct cells is the *finding*, not an assertion of a
  super-network.

Full provenance and the source list: [`real_data/README.md`](real_data/README.md).

---

## 12. The exact steps used to build this

The methodology, in order, so anyone can reproduce or extend it:

1. **Study the pattern.** Adopted the Graphify approach: a cheap deterministic pass + an
   LLM pass, with an honest per-edge audit trail (EXTRACTED/INFERRED/AMBIGUOUS; "never
   invent an edge — if unsure, tag AMBIGUOUS").
2. **Design the contract first** (`models.py`). Made `weight` a *derivation* of the
   confidence tag, node IDs deterministic slugs, temporal windows validated, and the same
   schema serve as the LLM's structured-output target — so every pass is validated identically.
3. **Build the deterministic pass** (`structural_pass.py`): regex over numbered arrest
   lists; derive `PRISON_CO_LOCATION` edges from overlapping remand windows (computed, never guessed).
4. **Build the LLM pass** (`semantic_pass.py`): provider-agnostic `init_chat_model`, the
   schema as `with_structured_output`, and a system prompt encoding the honesty rules,
   layer definitions, and temporal rules.
5. **Research the real data** via web search — Wikipedia (Sri Lankan mobsters; 2019 Easter
   bombings), the Jamestown brief on Zahran/NTJ, PCoI hearing reports, and named outlets
   (Ada Derana, Daily Mirror, News First, dbsjeyaraj, Times of Addu, Lanka News Web).
6. **Curate the dataset** (`real_dataset.py`): encode ~41 figures across three networks as
   validated nodes/edges, each with a citation and an honest confidence tag; keep the
   networks separate (no fabricated bridges).
7. **Wire the live LLM** (Gemini): `google_genai:gemini-2.5-flash-lite`, mapping the
   `GEMINI_API_KEY` for LangChain; narrative summaries in `real_data/` as its input.
8. **Cluster** (`clustering.py`): true multiplex Leiden across per-layer graphs
   (`find_partition_multiplex`), Louvain fallback if igraph/leidenalg are missing.
9. **Export to Neo4j** (`neo4j_export.py`): literal per-layer `MERGE` file + parameterized driver push.
10. **Build the UI** (`app/`): FastAPI serving a Cytoscape.js explorer with layer/confidence
    filters, a temporal slider, cell colouring, source-cited detail cards, and analyst queries.
11. **Verify end-to-end**: built the graph, confirmed Leiden recovered the true network
    structure (7 cells), ran the live Gemini pass, and drove the UI in a browser (rendering,
    filters, detail panel, and the cross-layer-broker query all confirmed).

---

## 13. Troubleshooting / FAQ

- **UI says "Failed to load graph."** Run `python build_real_graph.py` first (the server
  needs `output/real_graph.json`), then refresh.
- **`503` from `/api/graph`.** Same cause — the graph file doesn't exist yet.
- **Gemini `404 ... model no longer available`.** Model names change; list what your key
  supports and pin a current one in `.env` (`EXTRACTION_MODEL=google_genai:gemini-2.5-flash-lite`).
- **`--semantic` adds odd nodes (place names, duplicates).** Expected from raw LLM output.
  Dangling edges are pruned automatically; the *curated* graph (no `--semantic`) is the
  clean default the UI uses.
- **Leiden not used / "louvain-fallback" warning.** `python-igraph` + `leidenalg` aren't
  installed; the Louvain fallback still works. Reinstall requirements for true multiplex Leiden.
- **A new person shows up twice.** Two passes used different primary names → different slugs.
  Give them the same `name` and move the variant into `aliases`.
- **Port 8000 in use.** Edit the port in `app/server.py` `main()`.

---

## 14. Glossary

- **Node / vertex** — a person or organisation.
- **Edge / link** — a directed relationship between two nodes.
- **Multiplex graph** — a graph whose edges are split across several *layers* (here, four).
- **Temporal graph** — a graph whose edges carry time (start/end), so you can view snapshots.
- **Slug** — a normalised ID derived from a name (`makandure_madush`), used to dedupe.
- **Structural pass** — deterministic regex extraction (no LLM).
- **Semantic pass** — LLM extraction from prose.
- **Curated layer** — hand-verified, cited facts encoded directly in code.
- **Leiden / Louvain** — community-detection algorithms that find clusters ("cells").
- **Isolated cell** — a cluster with no edges leaving it (a self-contained group).
- **Cross-layer broker** — a node active on ≥2 layers (a bridge in the multiplex).
- **Cypher** — Neo4j's query language.
