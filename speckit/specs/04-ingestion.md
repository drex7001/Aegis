# Spec 04 — Ingestion

Status: implemented in Phase 1 — **§4 updated 2026-07-18 by P2 T17c for ADR-031
(typed suggestion envelope): producers emit typed kinds, acceptance dispatches
through the declared action, and the review inbox is a UI composition over
`review_queue` + `er_candidate`. Where this text conflicts with ADR-031, the ADR
wins.** · Constitutional basis: Articles I, IV, VII · GOAL.md §9 · ADR-027, ADR-031

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

## 3. Quarantine (GOAL.md §9.5, scaled)

`source_record.status='quarantined'` + reason when: unparseable/corrupt file,
media-type mismatch, missing provenance fields, oversized anomaly (> configured
bound), or duplicate ingest_key with *different* content hash (version conflict —
needs a human). Quarantined records are listed by an API route; release/reject are
audited actions.

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
  a separate entity draft: it rides in the claim's `subject_ref`/`object_ref` as an
  unresolved mention, and `record_claim` creates the mention and entity on
  acceptance (specs/02 §3.2 — there is no `entity_draft` kind).
- The reviewer can edit any field before accepting; the edited payload is stored and
  acceptance dispatches through the declared `target_action`, which validates against
  the ontology, writes, and audits (ADR-031 §2). The queue never writes tables itself.
- Acceptance-rate metrics per (model, prompt hash) are computable from `review_queue`
  — this becomes the extraction-quality dashboard.

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
- Later (Dagster trigger, plan §2): scheduled polls of RSS/press sources, webhooks —
  each a `source` with its own reliability grading.
