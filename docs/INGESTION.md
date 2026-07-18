# Governed ingestion

Use this workflow for every new source. It is the only supported path for
governed data: raw bytes are stored in the evidence vault, a provenance-rich
`source_record` is created, and extraction produces review-queue suggestions
instead of canonical claims (Articles IV and VII).

> Do **not** write source text to `data/real/`, edit `legacy/` datasets, or run
> the legacy LLM/graph commands for governed material. Those historical
> instructions are quarantined under [`legacy/`](../legacy/README.md) and are
> explicitly unsafe for governed data.

## 1. Prepare the platform

Bring up the local stack, install the locked environment, and apply migrations:

```bash
make up && make bootstrap
make install
aegis db upgrade
```

Use only lawfully obtained, open-source material. Choose the handling code
before landing it; `open` is the default, while `restricted` and `sensitive`
require the matching authorization and handling controls.

## 2. Land the original file

Keep a working copy anywhere outside the repository corpus and land it with an
identified operator. Landing is content-addressed and idempotent: re-landing
identical bytes returns the existing record, while a same-name/different-bytes
conflict is quarantined for review.

```bash
aegis ingest land path/to/source.txt --operator user:analyst-1 --handling restricted
aegis ingest status
```

Record the returned `rec_...` identifier. The command stores the original in
the configured vault and writes its provenance envelope, source record, and
audit event in one governed workflow.

## 3. Extract into the review queue

Only text source records can be extracted in Phase 1. PDFs, audio, and video
need a governed text derivative before extraction; do not substitute the
legacy conversion commands for that missing capability.

```bash
aegis ingest extract rec_01... --producer structural --actor user:analyst-1
aegis ingest extract rec_01... --producer semantic --actor user:analyst-1 --mock
```

The semantic command uses `--mock` for an offline verification run. For an
approved configured model, omit `--mock` or supply `--model provider:model`.
Both producers create suggestions only: they never write canonical claims.

## 4. Review and promote

Review suggestions through the governed review-queue API or its future UI.
An analyst must accept or reject each suggestion; acceptance records the
canonical claim and its audit trail. Check ingestion state at any time with:

```bash
aegis ingest status
```

Quarantined records must be resolved through the governed release path before
extraction. Keep original source metadata, provenance, and a purpose for any
sensitive review; do not repair source text in place.

## Legacy reference

Historical PDF/media conversion and prototype graph instructions remain in
[`legacy/INGESTION.md`](../legacy/INGESTION.md),
[`legacy/ADDING_DATA.md`](../legacy/ADDING_DATA.md), and
[`legacy/RUNNING.md`](../legacy/RUNNING.md). They are reference material only
and are unsafe for governed data.
