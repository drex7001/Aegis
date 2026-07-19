# Spec 04 — Ingestion

Status: implemented in Phase 1 — **§4 updated 2026-07-18 by P2 T17c for ADR-031
(typed suggestion envelope): producers emit typed kinds, acceptance dispatches
through the declared action, and the review inbox is a UI composition over
`review_queue` + `er_candidate`. Where this text conflicts with ADR-031, the ADR
wins.** · **§1 stage 3 and §3 updated 2026-07-19 by P2 T23a (ADR-034): the
derivative stage is implemented, and the pipeline is reachable over HTTP.** ·
**§4/§6 updated 2026-07-19 by P2 T25: the committed fictional MVP corpus uses
a prompt-pinned cached semantic envelope for reproducible offline extraction.** ·
Constitutional basis: Articles I, IV, VII · GOAL.md §9 · ADR-027, ADR-031, ADR-034

The existing ingestion stack (`pipeline/ingest.py`, `pdf_ingest.py`, `transcribe.py`,
structural/semantic passes) is kept — this spec changes **where its outputs land and
what they are called**, not how extraction works.

## 1. Pipeline (scaled from GOAL.md §9.1)

```
File / paste / curated entry
   ↓  pipeline/ingest.py (existing routing)
1. RAW LANDING          bytes → vault (content-addressed), source_record row,
                        provenance envelope, ingest_key (idempotent)
   ↓
2. VALIDATION           media-type check, parse sanity; failure ⇒ status=quarantined
   ↓
3. DERIVATIVES          pdf→structured text (opendataloader), a/v→transcript (whisper)
                        each recorded as `derivative` (tool, version, params, hash)
   ↓
4. EXTRACTION           structural_pass (regex) / semantic_pass (LLM) over derivative
                        text → SUGGESTED CLAIMS in review_queue (never claims direct)
   ↓
5. ADJUDICATION         human review_suggestion action → recorded claim (or reject)
   ↓
6. PROJECTIONS          aegis projections rebuild (graph JSON, matview, cypher, search)
```

Curated entry (the `real_dataset.py` style) is a *manual collection method*: it goes
through `record_claim` directly (a human **is** the adjudicator), still requiring a
registered source.

## 2. Provenance envelope (raw landing)

Extends the current provenance headers; stored in `source_record.provenance`:

```json
{
  "source_system": "manual-upload",
  "original_filename": "sc-april-attacks-report-en.pdf",
  "connector": "pipeline.ingest",
  "connector_version": "…git sha…",
  "operator": "user:ayodhya",
  "source_url": "https://…",
  "collection_policy": "public-osint-v1",
  "schema_version": "n/a",
  "notes": "…"
}
```

`ingest_key = sha256(source_system | original_filename_or_id | content_hash)` —
re-ingesting the same artifact is a no-op (GOAL.md §9.3).

### Derivative stage (T23a)

`aegis.ingestion.derivatives.ensure_text` is stage 3 for the text path:
`application/pdf` → pdfplumber → a `derivative` row (tool, version, params,
output content hash) plus the text itself in the vault; `text/*` records need
no derivative and get none, because a row for the identity function lengthens
the provenance chain without making it truer. Anything else is refused by name
(`UnsupportedMediaType`), and a PDF with no text layer is refused as needing
OCR rather than reported as an extraction that proposed nothing.

Re-running the stage over the same record with the same tool **reuses** the
existing row (ADR-034 §4); `params` is part of that key, so changing how the
text is produced produces a new derivative rather than silently reusing the
old one. Audio/video → transcript stays unimplemented; `transcribe.py` is
still prototype-only.

## 3. Quarantine (GOAL.md §9.5, scaled)

`source_record.status='quarantined'` + reason when: unparseable/corrupt file,
media-type mismatch, missing provenance fields, oversized anomaly (>
`AEGIS_INGEST_OVERSIZE_BYTES`, default 25 MiB), or duplicate ingest_key with
*different* content hash (version conflict — needs a human). Quarantined records
are listed by an API route; release/reject are audited actions.

Reasons **accumulate** rather than short-circuit: an artifact that is both a
version conflict and oversized reports both, so an operator who fixes one and
re-lands does not then discover the next (ADR-034 §3).

A separate, larger bound (`AEGIS_INGEST_MAX_BYTES`, default 100 MiB) is a
**transport** ceiling, not a governance rule: landing buffers a body to hash
it, so a request above it is refused `413` and nothing is stored. Quarantine
means "kept and withheld"; this means "not accepted at all", and the two are
deliberately different numbers with different meanings (ADR-034 §2).

### HTTP surface (T23a)

`POST /v1/ingest/file` (multipart) and `POST /v1/ingest/text` (pasted) land
through the same `land_bytes`, so the CLI and the workspace share one set of
rules. The reply separates **what the request did** (`outcome`:
`landed` / `already_landed` / `quarantined`) from **what the record is**
(`record.status`) — they come apart when re-sending something that landed
quarantined. `POST /v1/source-records/{id}/extract` runs the derivative stage
and one producer synchronously; `GET /v1/source-records` and
`…/{id}/derivatives` report state. Landing above the caller's own clearance is
refused: it would create evidence the operator can never afterwards read.

## 4. Extraction passes → suggested claims

### structural_pass (deterministic)
- Output rows: predicate `co_located_with`, computed remand-window overlap, excerpt =
  matched lines, `producer_meta = {rule: "remand-overlap", pattern_version}`.
- Deterministic passes emit **suggestions like every other producer** — no
  auto-accept mode exists (ADR-027; Article VII). Their determinism earns them
  a *pre-verified* rank in the queue and batch-confirm ergonomics (§4 below),
  never a machine write.

### semantic_pass (LLM — Article VII strictly)
- `producer_meta = {model, model_version, prompt_sha256, chunk_index, raw_response_ref}`;
  the raw LLM response is itself stored in the vault (debuggability + GOAL.md §38
  model governance later).
- The pass proposes claims with predicate, grading *suggestion* (mapped from the
  legacy tag rubric), time window, and excerpt. A previously unseen name is **not**
  a separate entity draft: the pass persists a `mention` for it and the claim draft
  carries that mention as its anchor, so `record_claim` creates the **entity** on
  acceptance (specs/02 §3.2 — there is no `entity_draft` kind). The draft also
  carries the node type the pass labelled, as the *proposed* entity type; where
  the predicate allows more than one type and no proposal arrives, acceptance
  fails rather than guessing whether a name is a person or an organization.
- Names the pass reported but could not locate in the text it read are listed in
  `producer_meta.unverified_names`. They still become mentions — dropping them
  would lose the extractor's output (Article VIII) — but with NULL offsets, so a
  fabricated name is visibly unanchored to any position in the source.
- The reviewer can edit any field before accepting; the edited payload is stored and
  acceptance dispatches through the declared `target_action`, which validates against
  the ontology, writes, and audits (ADR-031 §2). The queue never writes tables itself.
- Acceptance-rate metrics per (model, prompt hash) are computable from `review_queue`
  — this becomes the extraction-quality dashboard.

For the T25 fictional demo only, the same adapter accepts an
`aegis.cached-semantic/v1` JSON envelope. It contains a non-empty model label,
the SHA-256 of `SYSTEM_PROMPT`, and an `ExtractionResult`. The prompt digest
must match the running extractor; a stale cache is refused by name. The exact
envelope bytes are vaulted as the raw response, the producer is visibly
prefixed `cached:`, and its digest participates in the suggestion producer
version. This is deterministic replay of a fictional fixture, not a claim that
a hosted model ran. It changes no Article VII rule: output remains a suggestion
until a human accepts it.

### Batch review ergonomics (learned from current `--semantic` noise)
- The review **inbox** is a UI composition over `review_queue` and `er_candidate`
  (ADR-031 §3), grouped by document and by predicate; bulk-reject for hallucinated
  place-name entities; "accept all from this document with edits" flow.
- Dangling-edge pruning (current behavior) becomes: a suggestion whose argument has
  no resolved entity carries its unresolved mention ref and is surfaced as such,
  rather than silently dropped (Article VIII — nothing silently disappears).
- Re-extraction **supersedes** rather than duplicates: a replay writes a new row
  linked by `supersedes`, and the idempotency key stops a re-run from re-suggesting
  anything already decided (specs/02 §3.2).

## 5. Idempotency & replay

- Every stage is re-runnable: landing is content-addressed; derivatives are keyed by
  (parent hash, tool, version, params); extraction suggestions are keyed by
  (derivative hash, producer, producer version) — replays update nothing already
  decided.
- `aegis ingest replay <record_id>` re-runs stages 2–4 (e.g. after a Whisper upgrade),
  producing *new* derivatives/suggestions linked to the same source_record.

## 6. Watch folder & CLI

- Phase 1: `aegis ingest <path|dir>` (wraps existing `pipeline.ingest`) + `aegis
  ingest status`.
- Phase 2 (T23a): `aegis ingest extract` runs the derivative stage first, so a
  PDF is extractable from the CLI and the workspace alike; the same operations
  are reachable over HTTP (§3).
- Phase 2 (T25): `aegis ingest mvp` lands and extracts the committed fictional
  corpus in one offline command. `--reset --yes` restores a fixture-only local
  database to revision 0 and rebuilds empty projections; it refuses mixed or
  non-loopback state.
- Later (Dagster trigger, plan §2): scheduled polls of RSS/press sources, webhooks —
  each a `source` with its own reliability grading. This is also where a job
  model earns its complexity: a scheduled poll has no request to hold open,
  which is why ADR-034 keeps P2 synchronous and revisits it here.
