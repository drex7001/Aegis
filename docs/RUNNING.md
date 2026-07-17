# Running the legacy pipeline — exact steps

> **⚠️ Legacy runbook.** These are the commands for the **pre-Aegis prototype**
> (replace, never extend — ADR-023). The platform's own commands (compose
> stack, migrations, `aegis serve`, tests) are in the root
> [`README.md`](../README.md) and [`AGENTS.md`](../AGENTS.md).

Every command you need, in order, with what to expect. Commands are PowerShell (Windows);
on macOS/Linux replace `.venv\Scripts\` with `.venv/bin/`.

> Big picture and concepts: [`../ARCHITECTURE.md`](../ARCHITECTURE.md).
> Adding your own data: [`ADDING_DATA.md`](ADDING_DATA.md).
> Ingesting raw files (PDF/video/audio → text): [`INGESTION.md`](INGESTION.md).

---

## 0. One-time setup

```powershell
cd <repo root>
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

This installs: Pydantic, LangChain (+ `langchain-google-genai` for Gemini), NetworkX,
python-igraph + leidenalg (true Leiden), pdfplumber, the Neo4j driver, and FastAPI + uvicorn.

**Ingestion stack (optional — for raw PDFs and Sinhala video/audio).** On Linux/macOS
run `./scripts/setup_ingestion.sh` once: it creates the venv if needed, installs CPU
torch + the packages above, and puts a project-local Java runtime in `.tools/jre` for
the opendataloader-pdf parser (no root). Then ingest with
`.venv/bin/python -m pipeline.ingest` — see [`INGESTION.md`](INGESTION.md).

**Configure the LLM key (optional, only for the live semantic pass).** `.env` already holds:

```ini
GEMINI_API_KEY=...                                   # your key
EXTRACTION_MODEL=google_genai:gemini-2.5-flash-lite  # provider:model
```

Swap `EXTRACTION_MODEL` for `anthropic:claude-sonnet-5`, `openai:gpt-5`, or `ollama:llama3`
to use a different provider (install the matching `langchain-<provider>` package).

---

## 1. Build the real graph (recommended default — offline, deterministic)

```powershell
.venv\Scripts\python build_real_graph.py
```

Expected tail:

```
== 5. Export ==
  wrote output\real_graph.json  (41 nodes, 57 edges, 7 cells)
  wrote output\real_ingest.cypher
```

This uses only the hand-verified, cited curated dataset — no API key required. It is the
graph the UI serves by default.

---

## 2. Launch the web UI

```powershell
.venv\Scripts\python -m app.server
```

Then open **http://127.0.0.1:8000**. You should see the interactive network with the left
control panel (layers, confidence, temporal slider, analyst queries) and the right
panel (detected cells, breakdown, sources). Ctrl+C stops the server.

> The server re-reads `output/real_graph.json` on every request, so after re-running
> `build_real_graph.py` you only need to **refresh the browser** — no restart.

Quick API checks (in another terminal):

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/stats
Invoke-RestMethod http://127.0.0.1:8000/api/query/brokers
```

---

## 3. Build with the live LLM (Gemini) semantic pass

```powershell
.venv\Scripts\python build_real_graph.py --semantic
```

This runs Gemini over each narrative in `real_data/`, validates and merges the results,
prunes any dangling edges, re-clusters, and rewrites the outputs. Expected: the node/edge
counts grow (e.g. ~46 nodes / ~90 edges) and you'll see per-document lines like:

```
  [ok] narcotics_network.txt: +16 nodes, +26 edges from the LLM
  pruned 20 dangling edge(s) before clustering
```

If a call fails it is skipped (`[skip] ...`) and the curated graph is still written.

> To go back to the clean curated graph for the UI, just run `build_real_graph.py` again
> without `--semantic`.

---

## 4. Load into Neo4j (optional)

Start a database:

```powershell
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/yourpassword neo4j:5
```

Then either **paste** `output/real_ingest.cypher` into Neo4j Browser (http://localhost:7474,
no plugins needed), **or push via the driver** (set `NEO4J_URI/USER/PASSWORD` in `.env`):

```powershell
.venv\Scripts\python build_real_graph.py --semantic --push   # build + push in one go
# or, push an already-built graph:
.venv\Scripts\python -m pipeline.neo4j_export --graph output/real_graph.json --push
```

Analyst queries to try in Neo4j Browser are in [`../cypher/ingest.cypher`](../cypher/ingest.cypher).

---

## 5. The fictional mechanism demo (no API key)

`demo.py` exercises the **regex structural pass** and validation guardrails on invented data:

```powershell
.venv\Scripts\python demo.py --mock
```

Expected: it proves the guardrails (a hand-set weight is corrected; a bad date is rejected),
parses the fictional arrest list, runs the mock semantic result, clusters, and writes
`output/graph.json` + `output/ingest_generated.cypher`. This is for understanding the
machinery — it is **not** the real dataset.

---

## 6. Handy one-liners

```powershell
# Validate the curated dataset and check for dangling edges
.venv\Scripts\python -m pipeline.real_dataset

# List Gemini models your key can use
.venv\Scripts\python -c "import os,urllib.request,json;from dotenv import load_dotenv;load_dotenv();k=os.getenv('GEMINI_API_KEY');d=json.load(urllib.request.urlopen('https://generativelanguage.googleapis.com/v1beta/models?key='+k));print('\n'.join(m['name'] for m in d['models']))"

# Regenerate only the Cypher from an existing graph
.venv\Scripts\python -m pipeline.neo4j_export --graph output/real_graph.json --out output/real_ingest.cypher
```

---

## Command summary

| Goal | Command |
|---|---|
| Install | `.venv\Scripts\pip install -r requirements.txt` |
| Ingestion setup (Linux/macOS, no root) | `./scripts/setup_ingestion.sh` |
| Ingest raw files (PDF/video/audio) | `.venv\Scripts\python -m pipeline.ingest` |
| Build real graph (offline) | `.venv\Scripts\python build_real_graph.py` |
| Build + live Gemini | `.venv\Scripts\python build_real_graph.py --semantic` |
| Build + push to Neo4j | `.venv\Scripts\python build_real_graph.py --semantic --push` |
| Serve the UI | `.venv\Scripts\python -m app.server` |
| Fictional demo | `.venv\Scripts\python demo.py --mock` |
| Validate curated data | `.venv\Scripts\python -m pipeline.real_dataset` |
