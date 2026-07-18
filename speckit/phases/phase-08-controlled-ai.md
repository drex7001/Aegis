# Phase 8 Charter — Controlled AI & assisted reasoning

Status: charter (amended 2026-07-18, ADR-033) · tasks pre-authored:
`../tasks/phase-08.md` (T90–T101; re-validated by T90 at phase start, which
also dispositions the 2026-07 review findings tagged P8: B-18, H-29, H-30) ·
Constitutional basis: Articles III, IV, VII, X · GOAL.md §26, §38 · promoted
from the old P7 trigger table (ADR-022)

## Objective

AI accelerates analysts without ever becoming a source of fact. Phase 1 built
the containment (review queue, Article VII); this phase builds the capability
inside it: extraction that understands the ontology, translation that preserves
evidence discipline, summarization that cites, and hypothesis assistance that
argues both sides. This is the third step of the reasoning ladder (mechanism →
deterministic analytics → **assisted reasoning**).

## Architecture layers touched

- **Analytics plane / kinetic:** AI producers as governed suggestion sources;
  model governance (research → shadow → production, GOAL.md §38, scaled).
- **Evidence plane:** translations and transcripts as derivatives with parent,
  tool, version, parameters, hash (Article IV — already the rule for Whisper
  output; now uniform).
- **Consumption:** assistant surfaces in the workspace, citation-first.

## Deliverables

0. **AI data-egress policy & runtime boundary first (B-18 — blocking):**
   approved providers/models with deployment location and retention/training
   terms; prohibited data classes; model endpoint allowlist enforced at
   runtime; case-scoped retrieval + minimization/redaction before any hosted
   call; producers run under **least-privilege credentials that can write only
   typed suggestions and derivatives** — a runtime permission boundary, not a
   code scan; prompt-injection/adversarial tests; quotas and incident/rollback
   path. The review queue governs what enters canon; this deliverable governs
   what *leaves* the system.
1. **Extraction v2**: ontology-grounded structured extraction — prompts and
   output schemas *generated from the ontology/SDK* (P3), so the model proposes
   only valid types/predicates with spans and source offsets; batch runs over
   the corpus; per-run eval against a labeled sample; all output to the review
   queue with producer, model, version, and prompt hash (schema already holds
   these).
2. **Translation as derivatives**: Sinhala/Tamil → English (and reverse)
   stored as derivatives of the source record, never replacing it; graded as
   `algorithmic` source when text is claimed from a translation.
3. **Source-grounded summarization**: case and document summaries where every
   sentence carries claim **or immutable source-span** citations (H-29 —
   citation presence alone is insufficient: cited resources are validated to
   be within the authorized retrieval set, grading/contradiction context is
   rendered, and a sampled entailment/faithfulness check runs per release);
   uncited sentences are a rendering error, not a style choice; summaries are
   clearly labeled generated suggestions with a defined storage type.
4. **Hypothesis assistance**: given a hypothesis (P4), the assistant surfaces
   candidate supporting *and* contradicting claims and missing-information
   suggestions (Article VIII in prompt and product shape).
5. **Contradiction-detection suggestions**: candidate `claim_relation`
   (contradicts/corroborates) pairs enter the review queue like any other
   suggestion.
6. **Model governance (scaled)**: model + prompt configs versioned in git;
   research/shadow/production promotion recorded as ADR-style notes; an eval
   set per capability gates promotion (GOAL.md §38 without MLflow until the
   trigger fires).

## Dependencies

- P3: client/ontology grounding for prompts/schemas; Python SDK lands **here**
  (its first consumer — ADR-033).
- P4: workspace (assistant and citation UX); P2 review queue UI (reused).
- P7 gate closed (strict sequence, ADR-025) — the egress policy builds on P7's
  legal-authority and purpose enforcement; P6's findings/caveat plumbing is
  reused for AI-origin suggestions.

## Exit criteria

- [ ] Every AI output type (extraction, translation-claim, summary, hypothesis
      suggestion, contradiction candidate) lands as a **typed** suggestion
      (ADR-031 kinds) or derivative with source references — a **runtime
      permission test** (least-privilege producer credentials) proves zero
      direct writes to canonical tables, in addition to the code-path test.
- [ ] Assistant citations resolve, and every cited resource was inside the
      producer's authorized retrieval set (H-29); an answer with an uncited
      assertion fails its test.
- [ ] Extraction v2 evaluation (H-30): frozen baseline outputs/config;
      held-out multilingual test set; precision/recall/F1 by predicate and
      language with confidence intervals, reviewer minutes per accepted
      claim, cost, latency, abstention, and adversarial prompt-injection
      results; **absolute minimums met, not only improvement over the
      Phase-1 pass**.
- [ ] A translation derivative carries parent hash, tool, version, parameters,
      and the cached original output; reproducibility is proven as immutable
      inputs/config/model-ID + cached output equality — **not** regeneration
      of stochastic output (H-14/B-18).
- [ ] No hosted-model call can carry data classes prohibited by the egress
      policy (test with seeded prohibited fields); promotion of any
      model/prompt config to production has a recorded eval result.

## Risks

| Risk | Mitigation |
|---|---|
| LLM output creeps into canon | Standing risk since P0; the zero-direct-write test is CI-blocking; review queue is the only door (Article VII) |
| Plausible-but-wrong extraction floods reviewers | Batch caps + per-run eval; queue shows model confidence and span context; reviewer rejection rate tracked as a metric |
| Summaries launder uncertainty into prose | Citation-per-sentence requirement; grading shown inline (Article III) |
| Cost/quota of hosted models | Batch scheduling, caching by content hash, local models remain an option (Whisper precedent) |

## Specs to author or update

- `specs/14-controlled-ai.md` — author at phase start (producer contract,
  eval-set format, promotion workflow, assistant citation contract).
- `specs/04-ingestion.md` — extraction v2 producer registration.

## Explicit non-goals

Autonomous agents or auto-adjudication, risk scoring of persons (GOAL.md §25
prohibitions stand), link *prediction* as suggestions (needs the §13.4
explainability bar first), AI-generated entities without source spans,
fine-tuning pipelines.

## Task sketch (milestone level — T-file at phase start)

- **A — Producer contract:** uniform AI-producer interface + provenance
  stamping + zero-direct-write test.
- **B — Extraction v2:** ontology-grounded schemas, batch runner, eval set.
- **C — Translation & transcripts:** derivative pipeline unification.
- **D — Summarization & hypothesis assist:** citation-first services + UX.
- **E — Governance:** config versioning, promotion notes, metrics.
