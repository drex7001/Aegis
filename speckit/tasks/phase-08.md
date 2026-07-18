# Phase 8 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them; narrower dependencies are noted in the task text. Reference specs in
parentheses. Numbering continues from Phase 7 (T89).

> **Status: PRE-AUTHORED, NOT ACTIVE.** Phases 2–7 must close first (strict
> sequence, ADR-025 — the egress policy builds on P7's legal-authority and
> purpose enforcement). Authored 2026-07-18 ahead of phase start; **the
> charter was amended 2026-07-18 (ADR-033): the AI data-egress policy and
> least-privilege producer runtime are the blocking first deliverable (B-18);
> citations must resolve within the authorized retrieval set with sampled
> faithfulness checks (H-29); evaluation uses held-out multilingual sets with
> absolute minimums (H-30); reproducibility = immutable inputs/config + cached
> outputs, never regeneration; the Python SDK lands here as its first
> consumer**. T90 re-validates this plan against the amended charter and
> dispositions the findings tagged P8 before any other task starts. Charter:
> `../phases/phase-08-controlled-ai.md` · specs: `../specs/14-controlled-ai.md`
> (authored by T90), `../specs/04-ingestion.md` (extraction-v2 producer
> registration).

## Milestone A — Producer contract

**T90. ⛓ Spec 14 + the AI-producer contract** (charter §Specs) — re-validate this
plan against the P3/P4/P6-as-built system (SDK shape, workspace assistant slots,
findings plumbing); author `specs/14-controlled-ai.md`: the uniform **AI-producer
interface** (input, output, provenance fields — producer, model, version, prompt
hash), the **eval-set format**, the research → shadow → production **promotion
workflow**, and the **assistant citation contract** (every rendered assertion
carries claim/source IDs); register extraction v2 as a producer in specs/04. Every
producer routes to the review queue or lands on the evidence plane as a
derivative — never a canonical write (Article VII).
AC: spec 14 exists and defines the producer contract, eval format, promotion
workflow, and citation contract; specs/04 names the extraction-v2 producer; every
AI output type in the charter maps to a landing surface (queue or derivative) in
the spec; divergences from this plan are ADR'd.

**T91. ⛓ AI-producer interface + zero-direct-write test** (specs/14; needs T90) —
implement the uniform producer interface: every AI producer stamps provenance
(producer name, model, version, prompt hash, input refs) and emits only to
`review_queue` or to the evidence plane as a derivative; the single door to
canonical tables stays the human-executed action (Article VII). The headline
guarantee ships as a **CI-blocking** test.
AC: a test proves **zero direct writes** to canonical claim/entity tables from any
AI code path (charter exit №1); every producer's output carries the full
provenance stamp; a doctored producer that attempts a canonical write fails the
test and CI.

## Milestone B — Extraction v2

**T92. ⛓ Ontology-grounded extraction schemas** (specs/14; needs T91, P3 SDK) —
extraction prompts and output schemas **generated from the ontology/SDK**, so the
model can only propose declared types/predicates, each with spans and source
offsets; a schema regeneration follows an ontology bump with no hand-written
prompt surgery.
AC: the model's output schema is generated, not hand-written (drift gate covers
it); a proposed claim referencing an undeclared predicate is impossible to express
in the schema; every proposed claim carries a span and source offset; adding a
predicate via the P3 proposal workflow reaches the extraction schema through regen
alone.

**T93. Batch runner + labeled eval gate** (specs/14; needs T92) — batch extraction
over the corpus with per-content-hash caching and batch caps; a labeled-sample
eval computes precision on typed predicates and is recorded per run; the queue
entry shows model confidence + span context; **reviewer rejection rate is tracked
as a metric** (the reviewer-flood mitigation).
AC: extraction v2 beats the Phase-1 Gemini pass on the labeled sample, measured
and recorded (charter exit №3); a batch run respects its cap and caches by content
hash; the queue entry shows confidence and span context; rejection rate is
queryable as a metric.

## Milestone C — Translation & transcripts

**T94. ⛓ Derivative pipeline unification** (specs/14; Article IV; needs T91) —
Sinhala/Tamil ↔ English translation and Whisper transcripts stored uniformly as
**derivatives** of the source record (parent hash, tool, version, parameters,
output hash), never replacing the source; the Whisper precedent becomes the
general rule.
AC: a translation derivative carries parent hash, tool, version, and parameters;
deleting derivatives and re-running reproduces them (charter exit №4); the source
record is untouched; transcripts and translations share one derivative pipeline.

**T95. Translation-claim grading** (specs/14; needs T94) — when text is claimed
from a translation, the resulting suggested claim is graded `algorithmic` source
and links the derivative as its basis; the reverse translation direction is
supported; all such claims land in the review queue.
AC: a claim whose text comes from a translation is graded `algorithmic` and links
its derivative; the claim reaches canon only via human acceptance; grading is
visible inline in the queue (Article III).

## Milestone D — Summarization & hypothesis assist

**T96. ⛓ Source-grounded summarization** (specs/14; needs T91, P4 workspace) —
case and document summaries where **every sentence carries claim/source
citations**; an uncited sentence is a rendering error, not a style choice; the
citation contract comes from spec 14.
AC: an assistant answer renders with claim-ID citations; an answer containing an
uncited assertion fails its test (charter exit №2); no summarization rendering
path can emit an uncited sentence.

**T97. Hypothesis assistance — both sides** (specs/14; needs T96, P4 hypotheses) —
given a P4 hypothesis, the assistant surfaces candidate **supporting and
contradicting** claims plus missing-information suggestions; Article VIII is shaped
into both the prompt and the product (never one-sided).
AC: for a seeded hypothesis the assistant returns both supporting and
contradicting candidates; a one-sided rendering path does not exist; each
suggestion cites the claim IDs it rests on; suggestions land in the review queue,
never as direct hypothesis edges.

**T98. Contradiction-detection suggestions** (specs/14; needs T91) — candidate
`claim_relation` (contradicts / corroborates) pairs enter the review queue like
any other suggestion; no relation is written directly.
AC: a seeded contradicting pair yields a `claim_relation` suggestion in the queue
carrying both claim IDs; acceptance is the only path to a recorded relation;
rejection leaves no canonical trace.

## Milestone E — Governance & close-out

**T99. ⛓ Model governance — config versioning + promotion gate** (specs/14;
charter §Governance) — model + prompt configs versioned in git; research → shadow
→ production promotion recorded as ADR-style notes; an eval set per capability
gates promotion (GOAL.md §38, scaled — no MLflow until its trigger fires).
AC: promoting any model/prompt config to production has a recorded eval result
(charter exit №5); configs are versioned in git and a promotion note references
its eval; a promotion without a recorded eval is rejected in review.

**T100. Controlled-AI full proof** (charter exits №1–2; needs T91, T96, T99) — the
owning task for the phase's headline guarantees, as an automated matrix: for every
producer type (extraction, translation-claim, summary, hypothesis suggestion,
contradiction candidate) the zero-direct-write test holds **and** every rendered
assertion carries a citation; the assistant loop is scripted for the demo runbook.
AC: the matrix passes for every producer type — no canonical write, full
provenance, cited output; a newly added AI producer fails CI until it registers in
the contract and the matrix; the script joins the demo runbook.

**T101. Phase exit review** — walk the charter's exit criteria; update speckit
docs where reality diverged; append ADRs; write
`../reviews/phase-08-exit-review.md`; tag `phase-8-controlled-ai` per the git
workflow.
AC: every gate criterion checked (non-deferrable, ADR-025); non-blocking
deliverables carried over with owner + target phase recorded.

## Explicit non-goals for Phase 8

Autonomous agents or auto-adjudication, risk scoring of persons (GOAL.md §25
prohibitions stand), link *prediction* as suggestions (needs the §13.4
explainability bar first — not this phase), AI-generated entities without source
spans, fine-tuning pipelines, MLflow / model-registry infra (trigger-gated),
model-hosting choices beyond the Whisper local/hosted precedent.
