# Adding data — exact steps (legacy prototype track)

> **⚠️ Legacy recipes.** These paths feed the **pre-Aegis prototype** (curated
> code, regex pass, LLM pass → static graph JSON). In Aegis the same material
> enters through the governed landing zone as *sources → suggested claims →
> review queue* (speckit specs/04); the prototype track is kept only until the
> platform replaces it (ADR-023).

Three ways to add data, matched to what you have. All three pass through the same
validation contract (`pipeline/models.py`), so they combine automatically — the same
person from different sources resolves to one node (see [Deduping](#deduping--merging)).

> **Starting from a raw file instead of text?** A PDF report, a news video, an audio
> recording — ingest it first: `python -m pipeline.ingest <file-or-Files/>` converts it
> to an extraction-ready `real_data/*.txt` (opendataloader-pdf for PDFs,
> whisper-small-sinhala for Sinhala speech). Full guide: [`INGESTION.md`](INGESTION.md).
> Then continue below — ingested prose is path **C**, an ingested arrest annex is path **B**.

| You have… | Use | Effort | Confidence it produces |
|---|---|---|---|
| A verified, citable fact | **A. Curated** (edit `real_dataset.py`) | low | you choose (typically EXTRACTED/INFERRED) |
| A numbered arrest/remand list | **B. Structural** (regex) | low | EXTRACTED (deterministic) |
| A narrative report (prose) | **C. Semantic** (LLM) | zero-code | LLM chooses per the honesty rules |
| A raw PDF / video / audio file | **Ingest first** ([`INGESTION.md`](INGESTION.md)) | one command | n/a — produces text for B or C |

> Concepts and the field-by-field contract: [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §4.

---

## A. Curated fact — edit `pipeline/real_dataset.py`

Best for individual, verified, citable facts. This is the reliable backbone the UI uses.

### Step 1 — add the source

Add an entry to the `SOURCES` dict (`key → (publication, url)`):

```python
SOURCES = {
    # ... existing ...
    "dm_newcase": ("Daily Mirror — 'Suspect X charged over Y'",
                   "https://www.dailymirror.lk/news/....html"),
}
```

### Step 2 — add the node(s)

Add a `CriminalNode` via the `_n()` helper into the right network block
(`_NARCOTICS_NODES`, `_HISTORICAL_NODES`, or `_EXTREMISM_NODES`). Optionally add a name
constant at the top so edges can reference it without typos.

```python
# person
_n("Suspect X",
   aliases=["Full Legal Name"],          # optional; the common name is the primary `name`
   affiliations=["Madush drug network"], # optional
   src="dm_newcase",
   note="One-line sourced description of who they are."),

# organisation → org=True (renders as a square, node_type ORGANIZATION)
_n("Some Cartel", org=True, src="dm_newcase", note="Sourced one-liner."),
```

### Step 3 — add the edge(s)

Add a `TemporalEdge` via `_e()` into the matching `_..._EDGES` list. Pick a **layer**
(`IDEO`, `FIN`, `PRISON`, `TRANS`), a **confidence** (`EXTRACTED`, `INFERRED`, `AMBIGUOUS`
— all pre-imported as shorthands in this file), and dates where known.

```python
_e("Suspect X", "Makandure Madush",      # source → target (names are auto-slugged to IDs)
   "supplied_narcotics_to",              # relation: a short verb slug
   FIN, INFERRED,                        # layer, confidence  (weight is derived, don't pass it)
   src="dm_newcase",
   excerpt="The exact sentence or a faithful paraphrase that supports this link.",
   start="2018-06-01",                   # ISO date; month-only → first of month; omit if unknown
   end=None,                             # None = ongoing
   location="Colombo"),                  # optional
```

Rules the helper enforces for you: `weight` is derived from the tag; an `end` before
`start` is rejected; a self-loop is rejected; IDs are slugged so references line up.

### Step 4 — validate, then rebuild

```powershell
.venv\Scripts\python -m pipeline.real_dataset      # prints counts + "dangling edges (should be 0)"
.venv\Scripts\python build_real_graph.py           # regenerate output/real_graph.json
```

Refresh the browser (the server re-reads the file). If validation prints a dangling edge,
an edge references a name that isn't a node — fix the spelling or add the missing node.

**Choosing the layer** — ask *why are these two connected?* Ideology/membership → `IDEO`;
money or shared illicit enterprise → `FIN`; held in the same prison → `PRISON`; a
cross-border tie → `TRANS`. **Choosing the confidence** — stated plainly by an official
record/named outlet → `EXTRACTED`; a probable but unadjudicated link → `INFERRED`; alleged
or contested → `AMBIGUOUS`.

---

## B. Structured list (arrest/remand annexes) — deterministic, zero-LLM

Best when you have a numbered list like a PCoI annex. The pass parses each line and derives
`PRISON_CO_LOCATION` edges between people whose remand windows overlap **at the same facility**.

### Step 1 — write the list in the exact format

Each line must match `ARREST_LINE_RE` in `pipeline/structural_pass.py`:

```
<n>. <NAME> [alias "<ALIAS>"] [(NIC <9digits+V | 12digits>)] — arrested <YYYY-MM-DD> — remanded, <FACILITY> (<YYYY-MM-DD> to <YYYY-MM-DD|ongoing>)
```

Example file `real_data/remand_list.txt` (omit NIC for real people):

```
1. Wele Suda alias "Samantha" — arrested 2015-02-14 — remanded, Boossa Prison (2015-03-01 to ongoing)
2. Ganemulla Sanjeewa — arrested 2016-05-10 — remanded, Boossa Prison (2016-05-20 to ongoing)
```

Dashes may be `-`, `–`, or `—`; alias and NIC are optional; remand end may be a date or the
literal `ongoing`.

### Step 2 — run it (standalone)

```powershell
.venv\Scripts\python -c "from pathlib import Path; from pipeline.structural_pass import extract_structural; r=extract_structural(Path('real_data/remand_list.txt').read_text(encoding='utf-8'),'real_data/remand_list.txt'); print(len(r.nodes),'nodes',len(r.edges),'edges'); [print(e.source,'<->',e.target,'@',e.location) for e in r.edges]"
```

### Step 3 — (optional) merge it into the real build

Add three lines to `build_real_graph.py` after the curated network is built:

```python
from pipeline.structural_pass import extract_structural   # top of file

# inside main(), after: graph_result = build_curated_network()
remand = (REAL / "remand_list.txt")
if remand.exists():
    graph_result = graph_result.merge(
        extract_structural(remand.read_text(encoding="utf-8"), "real_data/remand_list.txt")
    )
```

Then `python build_real_graph.py`. Because IDs are slugged, "Wele Suda" here merges with the
"Wele Suda" already in the curated dataset — he gains the co-location edge without duplicating.

### Adapting the regex to a different annex format

Real annexes vary. Edit `ARREST_LINE_RE` (a documented verbose regex) so its named groups
(`name`, `alias`, `nic`, `arrested`, `facility`, `start`, `end`) capture your layout.
Everything downstream is format-agnostic.

---

## C. Narrative document (prose) — the LLM semantic pass

Best for reports/articles written as prose. The LLM reads them and emits nodes/edges under
the honesty rules.

### Step 1 — add the document

Drop a `.txt` file in `real_data/`, e.g. `real_data/prison_gangs.txt`. Keep it factual and,
ideally, note your sources at the top (they become part of the model's context).

### Step 2 — register it

Add the filename to `NARRATIVE_DOCS` in `build_real_graph.py`:

```python
NARRATIVE_DOCS = [
    "narcotics_network.txt",
    "easter_attacks_network.txt",
    "prison_gangs.txt",     # ← your new document
]
```

### Step 3 — run the semantic build

```powershell
.venv\Scripts\python build_real_graph.py --semantic
```

The model (Gemini by default) follows `SYSTEM_PROMPT` in `pipeline/semantic_pass.py`:
never invent an edge; tag weak links `AMBIGUOUS`; quote the supporting sentence; use ISO
dates (null end = ongoing); put place names in `location`, **not** as nodes. Its JSON is
validated against the same schema, dangling edges are pruned, and the result is merged.

> Raw LLM output is noisier than curated data (occasional duplicate names or stray
> entities). For a pristine graph, prefer path **A** for facts you care about; use path
> **C** for breadth/discovery. Re-running without `--semantic` restores the clean curated graph.

### Processing a PDF instead of a `.txt`

Preferred: `python -m pipeline.ingest report.pdf` — structure-aware extraction with an
audit copy, straight into `real_data/` (see [`INGESTION.md`](INGESTION.md)). Registered
documents of any size are safe: `build_real_graph.py --semantic` chunks long texts
(~12k chars per LLM call) and merges the results. The manual API:

```python
from pipeline.pdf_ingest import convert_pdf
from pipeline.semantic_pass import extract_semantic

text = convert_pdf("report.pdf")                       # markdown (pdfplumber fallback)
result = extract_semantic(text, "report.pdf")          # or loop split_paragraphs(text) for long docs
```

---

## Deduping & merging

- **One entity, one `node_id`.** The ID is `slugify(name)`, so `"Makandure Madush"` →
  `makandure_madush` regardless of which pass produced it. Same slug ⇒ the nodes **merge**
  and their evidence (aliases, affiliations, sources) is combined.
- **Keep names consistent.** Use the *common* name as the primary `name` and put formal or
  alternate names in `aliases`. If two passes call the same person different things
  (`"Naufer Moulavi"` vs `"Muhammed Naufer"`), you get two nodes — fix by aligning the `name`.
- **Edges** dedupe on `(source, target, relation, layer, start, end)`.

---

## Validation checklist

Before committing new data:

```powershell
.venv\Scripts\python -m pipeline.real_dataset      # 1. dangling edges should be 0
.venv\Scripts\python build_real_graph.py           # 2. builds without error; check the cell summary
```

- [ ] Every new node has a `src` (citation) and a `note`/`excerpt`.
- [ ] Every new edge has a layer, a confidence tag, a `src`, and an `excerpt`.
- [ ] Confidence honestly reflects the source (contested → `AMBIGUOUS`).
- [ ] No fabricated links between otherwise-unconnected networks.
- [ ] Dangling-edge count is 0; the graph builds and clusters cleanly.
