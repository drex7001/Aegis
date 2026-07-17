# Ingesting raw data — PDFs, video, audio, text

> **Note.** This toolchain (opendataloader-pdf, whisper-small-sinhala) predates
> Aegis but is **not** legacy-only: it remains the front end of the governed
> landing zone (speckit specs/04) — ingested text becomes *sources* whose
> extraction output lands in the review queue.

How to take **raw source material** (a scanned commission report, a news video, an
interview recording, a pasted article) and get it into the extraction pipeline. This is
the step *before* [`ADDING_DATA.md`](ADDING_DATA.md): ingestion produces the
extraction-ready `.txt` files in `real_data/` that the structural/semantic passes and
`build_real_graph.py --semantic` consume.

Commands are Linux/macOS (`.venv/bin/...`); on Windows use `.venv\Scripts\...`.

```
Files/  (drop zone: .pdf .mp4 .mp3 .wav .txt …)
   │
   │   python -m pipeline.ingest
   ▼
┌───────────────────────────────────────────────────────────────────────┐
│  .pdf   → pipeline/pdf_ingest.py   opendataloader-pdf (Java CLI):     │
│           structure-aware markdown; audit copies in output/ingest/;   │
│           pdfplumber plain-text fallback if Java is unavailable       │
│  media  → pipeline/transcribe.py   whisper-small-sinhala (local,      │
│           CPU-friendly but slow): timestamped Sinhala transcript      │
│  .txt   → verbatim copy with a provenance header                      │
└───────────────────────────────────────────────────────────────────────┘
   │
   ▼
real_data/<slug>.txt          ← review it, then register in NARRATIVE_DOCS
   │                             (build_real_graph.py) and run:
   ▼
python build_real_graph.py --semantic
```

Every produced file starts with a **provenance header** (source file, method, timestamp)
— the LLM pass reads it as context, and analysts can always trace a graph edge back to
the raw source.

---

## 0. One-time setup

```bash
./scripts/setup_ingestion.sh                # venv + packages + project-local Java
./scripts/setup_ingestion.sh --with-model   # …also pre-download the STT model (~1 GB)
```

The script is idempotent and needs **no root**. It sets up:

| Piece | What / why | Where |
|---|---|---|
| Python 3.12 venv | project interpreter (uses [`uv`](https://docs.astral.sh/uv/) if installed, else `python3 -m venv`) | `.venv/` |
| `opendataloader-pdf` | structure-aware PDF → markdown/JSON parser (bundled Java JAR) | `.venv` |
| Temurin JRE 21 | Java runtime the PDF parser needs — installed **project-locally** only when no `java`/`JAVA_HOME` exists | `.tools/jre/` |
| `torch` (CPU) + `transformers` | run the speech-to-text model; CPU wheels avoid the multi-GB CUDA download | `.venv` |
| `imageio-ffmpeg` | static ffmpeg binary for audio decoding — no system ffmpeg needed | `.venv` |
| `Lingalingeswaran/whisper-small-sinhala` | Whisper-small fine-tuned for Sinhala (Apache-2.0); downloads on first use | `~/.cache/huggingface` |

On Windows, run the pip commands from `requirements.txt` manually and install a JRE from
[adoptium.net](https://adoptium.net) — everything else is identical.

---

## 1. Add new data (the whole workflow)

### Step 1 — drop the raw file(s) in `Files/`

`Files/` is the git-ignored drop zone. Any mix of: `.pdf`, `.mp4 .mkv .mov .webm`,
`.mp3 .wav .m4a .aac .flac .ogg .opus`, `.txt`, `.md`. (You can also point the command
at any other file or folder.)

### Step 2 — run the ingester

```bash
.venv/bin/python -m pipeline.ingest                     # everything new in Files/
.venv/bin/python -m pipeline.ingest docs/report.pdf     # or specific files/folders
```

What you'll see, per file type:

```
[pdf ] sc-april-attacks-report-en.pdf → real_data/sc_april_attacks_report_en.txt
[stt ] videoplayback.mp4 → real_data/videoplayback_transcript.txt
transcribing videoplayback.mp4: 00:33:32 of audio with Lingalingeswaran/whisper-small-sinhala
  (CPU is ~6x real-time — expect roughly 03:21:12; watch with: tail -f real_data/videoplayback_transcript.txt)
  [00:10:00 / 00:33:32] 42 segments
```

Files whose output already exists are skipped — `--force` re-ingests. A media file can
be **test-sliced** first (highly recommended before committing to a multi-hour run):

```bash
.venv/bin/python -m pipeline.ingest Files/interview.mp4 --max-minutes 2
# → real_data/interview_transcript_first2min.txt in a few minutes
```

Long transcriptions are safe to leave running: the output file is rewritten after every
10-minute block with an `[... IN PROGRESS ...]` marker, so you can `tail -f` it, and an
interrupted run keeps everything transcribed so far.

### Step 3 — review the output (do not skip)

Open the new `real_data/*.txt` and check it honestly:

- **Transcripts are machine output.** Whisper misrecognises exactly what matters most —
  proper names, amounts, dates — and can emit repetition artifacts on noisy audio. Fix
  names you can verify; leave the `[MACHINE TRANSCRIPT …]` header in place so the
  provenance stays honest. Timestamps let you jump back into the source media to check.
- **PDF extractions** are structure-aware markdown; skim for broken tables or
  running-header noise. The full layout tree (with bounding boxes) is kept for audit in
  `output/ingest/<stem>.json`, next to the raw markdown.
- Trim boilerplate that would waste LLM context (cover pages, tables of contents,
  signature blocks).

### Step 4 — register the document for the semantic pass

Add the filename to `NARRATIVE_DOCS` in `build_real_graph.py`:

```python
NARRATIVE_DOCS = [
    "narcotics_network.txt",
    "easter_attacks_network.txt",
    "sc_april_attacks_report_en.txt",   # ← your ingested document
]
```

### Step 5 — run the extraction

```bash
.venv/bin/python build_real_graph.py --semantic
```

Long documents are **chunked automatically** (~12k characters per LLM call, results
merged and deduped by the shared Pydantic contract) — a 200-page report becomes ~70
calls, so expect it to take a while and to consume API quota. Everything the LLM emits
is validated, weight-corrected, pruned of dangling edges, clustered, and written to
`output/real_graph.json` + `output/real_ingest.cypher` exactly as described in
[`../ARCHITECTURE.md`](../ARCHITECTURE.md).

Then refresh the UI (`python -m app.server` → http://127.0.0.1:8000).

---

## 2. Which pass should my data feed?

Ingestion gives you *text*; what you do with it depends on what the text is
(full decision guide: [`ADDING_DATA.md`](ADDING_DATA.md)):

| The text is… | Feed it to | How |
|---|---|---|
| Narrative prose (reports, articles, transcripts) | **Semantic pass** (LLM) | register in `NARRATIVE_DOCS`, `--semantic` |
| A numbered arrest/remand annex | **Structural pass** (regex, deterministic) | format per `ARREST_LINE_RE`, see ADDING_DATA §B |
| A fact you verified yourself against sources | **Curated layer** | encode in `pipeline/real_dataset.py` with a citation |

A Sinhala transcript can go straight to the semantic pass — Gemini/Claude read Sinhala —
but for high-stakes facts prefer to verify and encode them in the curated layer, citing
the source media + timestamp as the excerpt.

---

## 3. Direct module usage (without the router)

```bash
# PDF → markdown to stdout / file (audit copies always land in output/ingest/)
.venv/bin/python -m pipeline.pdf_ingest docs/report.pdf
.venv/bin/python -m pipeline.pdf_ingest docs/report.pdf -o extracted.txt

# Speech-to-text with full control
.venv/bin/python -m pipeline.transcribe Files/videoplayback.mp4 --max-minutes 5
.venv/bin/python -m pipeline.transcribe interview.mp3 --out real_data/interview.txt \
    --model Lingalingeswaran/whisper-small-sinhala --language sinhala --batch-size 4
```

As a library:

```python
from pipeline.pdf_ingest import convert_pdf
from pipeline.transcribe import transcribe_media, transcribe_to_file

markdown = convert_pdf("docs/report.pdf")                 # str (structured markdown)
result = transcribe_media("clip.mp4", max_minutes=2)      # {"text", "lines", ...}
path = transcribe_to_file("Files/videoplayback.mp4")      # → real_data/..._transcript.txt
```

Both integrate with the extraction snippet the README shows (`extract_structural`,
`extract_semantic`, `split_paragraphs`) since they just produce text.

---

## 4. Performance & quality expectations

| Operation | Speed | Notes |
|---|---|---|
| PDF (300 pages, opendataloader-pdf) | seconds–a minute | JVM start is ~1 s; parsing is fast |
| Speech-to-text on CPU (6 cores) | **~6× real-time** | 30-min video ≈ 3 h. Plan around it: `--max-minutes` to sample, leave full runs overnight, or run on a CUDA box (torch will use it automatically if the CUDA build is installed) |
| Semantic pass on a big report | ~70 LLM calls / 200 pages | chunked automatically; failed chunks are skipped, not fatal |

Quality notes, honestly stated:

- `whisper-small-sinhala` is a small model trained on Common Voice; it handles clear
  narration well, struggles with overlapping speech/music, and **will** garble some
  proper names. Treat transcripts as leads, not evidence — that is exactly the
  EXTRACTED/INFERRED/AMBIGUOUS discipline the rest of the pipeline enforces.
- opendataloader-pdf keeps its content-safety filters on (hidden text, off-page text),
  which doubles as prompt-injection hygiene for text that later reaches the LLM pass.
  It does **not** OCR scanned image-only PDFs — for those you'd need an OCR step first
  (e.g. print a searchable copy, or add one later; the parser's `--hybrid` mode with a
  docling server is the built-in path when you need it).

---

## 5. Troubleshooting

- **`no Java runtime found` warning during PDF ingestion** — run
  `./scripts/setup_ingestion.sh` (installs `.tools/jre`); the file still ingested via the
  pdfplumber fallback, just without structure.
- **First transcription stalls at start** — it's downloading the ~1 GB model from
  Hugging Face; pre-fetch with `./scripts/setup_ingestion.sh --with-model`. Set `HF_HOME`
  to relocate the cache.
- **Out-of-memory during transcription** — lower `--batch-size` (default 4 → try 1–2).
- **Transcript has repeated syllables / loops** — a known Whisper artifact on noisy
  segments; the timestamps tell you where to listen and correct by hand.
- **Different audio language** — pass `--model <any-HF-whisper-checkpoint>` and
  `--language <lang>`, or set `SINHALA_ASR_MODEL` in `.env`.
- **`videoplayback_transcript.txt` ends with `[... IN PROGRESS ...]`** — the run is
  still going (or was interrupted); re-run `python -m pipeline.ingest --force` to redo
  a partial file.

---

## Command summary

| Goal | Command |
|---|---|
| One-time setup (no root) | `./scripts/setup_ingestion.sh` |
| Ingest everything new in `Files/` | `.venv/bin/python -m pipeline.ingest` |
| Ingest a specific file/folder | `.venv/bin/python -m pipeline.ingest <path…>` |
| Quick 2-min transcription test | `.venv/bin/python -m pipeline.ingest <video> --max-minutes 2` |
| Re-ingest (overwrite) | `.venv/bin/python -m pipeline.ingest <path> --force` |
| PDF only, to stdout | `.venv/bin/python -m pipeline.pdf_ingest <pdf>` |
| Transcribe only, full control | `.venv/bin/python -m pipeline.transcribe <media> [--max-minutes N]` |
| Extract graph from ingested docs | `.venv/bin/python build_real_graph.py --semantic` |
