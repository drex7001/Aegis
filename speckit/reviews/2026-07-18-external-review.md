# Aegis documentation review by Codex

> **Speckit note (2026-07-18).** This is the raw external AI review, kept
> verbatim as the authoritative definition of finding IDs (B-01…B-19, H-xx,
> M-xx) cited across charters, task files, and ADRs. It was **not adopted
> wholesale** — the accept/narrow/reject record is
> [`2026-07-18-external-review-disposition.md`](2026-07-18-external-review-disposition.md);
> where this text conflicts with the constitution, ADR-025…033, or the
> current roadmap, those win.

**Review date:** 2026-07-18  
**Review posture:** documentation and plan review only; no code was edited  
**Current gate reviewed:** Phase 2 — identity, provenance, and analyst-console MVP

## Executive assessment

Aegis has a strong ethical center and several sound architectural instincts: claims rather than facts, reversible identity, source/information grading separation, human review of AI output, a PostgreSQL system of record, rebuildable projections, and early authorization boundaries. Those principles are unusually clear.

The plan is **not yet implementation-ready as written**, however. Several documents contradict the constitution on precisely the controls described as non-negotiable. Phase 1 is marked complete despite known authorization gaps; Phase 2's MVP exit requires a UI capability for which no task exists; the identity schema cannot reliably implement the promised exact merge reversal or reroute claims after a split; and the generic review queue cannot represent several suggestion types assigned to it. Later phases also defer basic security, legal authority, retention, evidence immutability, and production hygiene until after the system is already processing real-person data.

The most serious issue is not missing polish. It is that the project currently has three competing rule sets:

1. The constitution says every route is authorized, no algorithm writes identity/claims, and every relationship or attribute has a source.
2. Detailed specs allow public anonymous graph routes, deterministic auto-merges, structural auto-accept, and direct `system_claim` writes.
3. Phase exit tasks permit unmet criteria to be “explicitly deferred,” even though the roadmap says phases are hard gates.

Those cannot all be true. Resolve the conflicts before T17. Otherwise the project will build behavior that its own governance documents classify as defective.

### Recommended decision

Treat the current state as **conditional no-go for Phase 2 implementation** until the blocker list below is dispositioned in an ADR/documentation repair PR. This does not require abandoning the architecture. It requires making the rules executable and making the MVP task list actually cover the MVP.

## Scope and method

The review covered the primary documentation set and supporting operational documents: `README.md`, `GOAL.md`, the constitution, product spec, technical plan, roadmap, ADR-001 through ADR-024, specs 01–08, all P0–P9 charters, all T1–T113 task files, the Phase 1 exit review, ontology documentation and artifact, data-ethics documents, runbooks, SDK/UI scaffolding documents, and the Git workflow. CI, packaging, and the Makefile were read only to verify statements made by the documentation.

Legacy implementation documentation was considered where living documents still direct users to it. Historical ADR text was not treated as a defect merely because paths or phase numbers were later superseded; living documents that still instruct users to use obsolete or unsafe paths were treated as defects.

Severity used below:

- **Blocker:** invalidates a constitutional claim, phase gate, security boundary, or central data invariant.
- **High:** likely to cause redesign, data loss, leakage, misleading analysis, or substantial avoidable work.
- **Medium:** material ambiguity, missing acceptance detail, or maintainability risk.
- **Low:** wording, status, or documentation hygiene issue.

## Blockers

### B-01 — Phase 1 is marked complete while Article VI is knowingly unmet

**Evidence:** Constitution Article VI says every read and write has backend authorization and that every route has an explicit authorization dependency. Article X requires attributable audit for every read. ADR-019 instead permits anonymous `public_route` graph endpoints. The Phase 1 exit review also says field-level sensitivity filtering and the best-effort synchronous FGA revocation delete were deferred. `README.md` nevertheless says every route has an authorization dependency and Milestone I is complete.

**Why this is a problem:** An anonymous real-person relationship graph cannot record an authenticated actor, purpose, case, or authorization decision. “Open-only” is a data classification, not an authorization decision. It also creates a permanent exception pattern to the deny-by-default lint. The deferred field filter is especially serious because the ontology already contains restricted properties such as phone numbers and national identifiers. Even if every returned row is genuinely open, a bulk graph endpoint creates an avoidable scraping, enumeration, and resource-exhaustion surface over a real-person corpus.

**Recommendation:** Choose one of two honest paths:

1. Preferred: remove anonymous graph access now, put the interim UI behind OIDC, and implement field filtering plus revocation safety as Phase 2 prerequisites.
2. If a public demo is truly required, use a separate, fictional, statically generated demo artifact outside the governed API. Amend the constitution explicitly if anonymous production routes are intended; do not hide the exception in a lint marker.

Reopen the Phase 1 verdict or record a formal conditional-completion ADR with a deadline and a blocking Phase 2 prerequisite. The current “complete” label is inaccurate.

If the legacy endpoint must survive briefly during local migration, bind it to loopback by default and impose request-rate, response-size, query-cost, and cache limits. Those are temporary exposure controls, not substitutes for Article VI authorization and attributable audit.

### B-02 — Algorithmic canonical writes contradict Article VII in four places

**Evidence:** Article VII says model output, ER candidates, link prediction, and alerts enter a review queue, and nothing algorithmic writes canonical claims or identity clusters. In conflict with that:

- Spec 04 §4 allows deterministic structural passes to auto-accept.
- Spec 05 §2.1 and T18 auto-decide identity merges.
- Spec 08 §5, the P3 charter, and T32–T33 allow `system_claim` to write recorded claims directly.
- GOAL.md §7.8 also permits explicit system claims, while its mission says accountable humans decide accepted knowledge.

The current ontology's `algorithmic` source comment says it may source suggestions only, reinforcing the contradiction.

**Why this is a problem:** An ADR cannot override a constitutional article without amending the constitution. Auditing an automatic decision does not turn it into human adjudication. Identity is particularly dangerous because one wrong deterministic match contaminates all downstream analysis.

**Recommendation:** Make all extraction and ER outputs suggestions. Deterministic derivations that are mathematically implied by accepted inputs should be rebuildable projections/findings, not canonical claims. If the team wants a narrow class of machine-recorded derived claims, amend Article VII first and define all of: admissible derivation class, proof obligation, provenance, retraction behavior, failure semantics, and approval authority. Merely requiring an ADR reference is not a safety boundary.

### B-03 — “Exact merge reversal” is not supported by the specified identity model

**Evidence:** Spec 02 stores membership rows with `valid_from` and `valid_to`; T20 promises that merge then split restores the exact prior state. No identity decision/revision ID, operation group, predecessor link, optimistic concurrency field, or partial uniqueness/exclusion constraint is specified. Candidate-pair and negative-constraint storage are also absent. `merged_into` is modeled as a claim, even though claims require a source record and an identity decision is not a source observation.

**Why this is a problem:** Timestamps alone cannot reliably invert a merge after intervening edits or concurrent adjudications. Two active memberships for one mention are not forbidden by the illustrated schema. A split cannot know which exact rows formed the pre-merge state. Modeling administrative identity history as a domain claim also invents a source-record requirement and puts an identity operation in the misleading `kinship` category.

**Recommendation:** Before T17, specify an identity ledger:

- `identity_decision`/`cluster_revision` with revision ID, parent revision, action, actor/rule, note, evidence references, and transaction time.
- Membership rows keyed to a revision/decision, with a database invariant that one mention has at most one current membership.
- Persisted candidate pairs, model/version/snapshot, dispositions, and versioned negative constraints.
- Optimistic concurrency on adjudication and a defined policy for intervening changes.
- Identity merge lineage as identity metadata, not a sourced domain claim.

Use PostgreSQL range types and exclusion constraints where helpful; PostgreSQL explicitly supports range/exclusion constraints for preventing overlapping intervals ([PostgreSQL range types](https://www.postgresql.org/docs/current/rangetypes.html)). Test reversal after multiple merges, partial splits, concurrent decisions, and later mention additions—not only immediate merge→split.

### B-04 — Phase 2's UI-driven MVP has no UI ingestion/extraction task

**Evidence:** The P2 exit gate requires a non-builder to run “land a source → extraction suggests → review → accept → projection” from the UI. T22–T25 add provenance, review, contradiction, and search surfaces, but no task adds source upload, provenance capture, quarantine/status display, extraction selection/triggering, or projection refresh/status in the UI. T27 writes a runbook; a runbook cannot create missing product capability.

**Why this is a problem:** The headline MVP acceptance criterion is impossible to satisfy from the listed deliverables. It would either require hidden CLI steps or produce last-minute unplanned UI/API work.

**Recommendation:** Add an explicit blocking task before T23 for an authenticated landing/extraction UI covering multipart upload/paste, required provenance, source status/quarantine, derivative/extraction progress, idempotent re-upload feedback, and safe projection-refresh status. Define whether extraction is synchronous or job-based, how failure/retry is shown, and who is authorized. Add a browser-level full-loop test owned by that task; keep T27 as documentation and usability validation.

### B-05 — The shared review queue cannot represent its planned workloads

**Evidence:** Spec 02's `review_queue` is a claim-draft JSON payload with `result_claim`. P2 puts claim suggestions and identity candidates in the same surface. P8 additionally sends claim relations, hypothesis links, missing-information suggestions, summaries, and contradiction candidates through it. Those outcomes do not all produce a claim ID and have different authorization, validation, edit, accept, and rejection semantics.

**Why this is a problem:** An opaque JSON queue plus one `result_claim` FK will become a polymorphic state machine without declared types or referential integrity. It cannot safely prove that acceptance called the right action, nor can it express an identity decision or accepted claim relation.

**Recommendation:** Define a typed suggestion envelope now: `suggestion_kind`, schema version, target action/aggregate, source/input references, producer identity/version, authorization scope, idempotency key, expiry/supersession, decision, and typed result reference. Use per-kind payload schemas generated from action parameters. Acceptance must dispatch through the declared human action, not a generic JSON writer. Separate high-volume machine candidates into dedicated tables if their lifecycle/query needs differ, while preserving one review inbox as a UI composition.

### B-06 — Hard phase gates are undermined by every exit task

**Evidence:** The roadmap says phases are gated by exit criteria and no later phase starts before an earlier gate. T16, T28, T40, T53, T65, T77, T89, T101, and T113 all accept “all exit boxes checked or explicitly deferred with reason.” P6 calls P5 a soft dependency; P7 calls P6 soft; P8 calls P6 soft; P9 tasks may begin after P4.

**Why this is a problem:** A criterion that may be deferred is not a gate. This allows the MVP or a governance phase to close while its defining safety property remains absent, then makes all dependency claims unreliable.

**Recommendation:** Define two distinct concepts:

- **Gate criterion:** cannot be deferred; phase remains open or a superseding ADR must change the charter before review.
- **Non-blocking deliverable:** may be deferred with an owner, target phase, and dependency impact.

Either keep a strict sequential roadmap and remove all “soft dependency/start early” language, or introduce explicit parallel workstreams with dependency DAGs. Do not mix both models.

### B-07 — The platform-first/module claim has no module architecture or validation milestone

**Evidence:** The mission, Article XIV, GOAL.md, README, and ontology README say domains are ontology modules. Spec 01 defines one `ontology/aegis.yaml`; Spec 08 adds interfaces/functions/actions but no imports, namespaces, module manifests, dependency resolution, conflict rules, enablement profiles, migrations per module, or cross-module version compatibility. No phase proves the core with a second domain. The existing ontology mixes platform actions and criminal-network vocabulary in one artifact.

**Why this is a problem:** “One file with more types” is not a module system. Without composition rules, the first domain will keep shaping the supposedly neutral core, and later domains will cause name collisions, migration coupling, permission ambiguity, and all-or-nothing deployments.

**Recommendation:** Add a module-composition deliverable, preferably in a narrowed P3:

- A small platform/governance ontology plus separate domain module manifests.
- Stable namespaces, imports/dependencies, version constraints, type ownership, extension rules, and conflict resolution.
- Module-scoped migrations and enable/disable semantics.
- A CI fixture for a tiny second fictional domain (for example border cargo or financial compliance) proving no core code change.

Until that proof exists, soften public claims from “powers every domain” to “designed to support future domains.”

### B-08 — Legal authority, purpose enforcement, retention, and minimization are promised but largely absent

**Evidence:** GOAL.md Rules 4 and 6 and §24 make legal authority, purpose, retention, jurisdiction, and policy packs structural. The claim schema has no legal-authority reference or retention fields. Security currently requires a purpose string for some reads but does not use purpose in an authorization policy. Legal-authority objects wait until P7; no phase owns retention schedules, legal holds, correction/challenge, data-subject handling, or policy packs. Source contracts, authority expiry, malware scanning, and minimization from GOAL.md §9 are also not assigned.

**Why this is a problem:** Recording a purpose in audit after access is not purpose-based authorization. Real OSINT can still be personal data and can still require retention, correction, and dissemination policy. These are data-model concerns; adding them in P7 will force migrations and reclassification of existing records.

**Recommendation:** Add a minimal governance baseline before the MVP:

- Collection-policy/legal-authority reference on source records and sensitive actions.
- Purpose vocabulary and policy evaluation, not an arbitrary string only.
- Authority validity interval and fail-closed expiry checks.
- Retention class, review/expiry date, hold override, and governed disposition workflow.
- A deployment policy profile explicitly stating which controls are disabled for the solo OSINT profile and why.

Keep advanced judicial and cross-agency policy in P7, but do not postpone the fields and enforcement seams.

### B-09 — Evidence and audit are tamper-evident only against a narrow threat, not immutable

**Evidence:** ADR-007 treats MinIO versioning as immutable and defers Object Lock/WORM. The backup runbook uses `mc mirror`, which is not documented as preserving every object version, lock, legal hold, and retention property. The audit chain is in the same PostgreSQL database and has no externally protected head/checkpoint. A privileged attacker can truncate a valid suffix or restore an older database and vault snapshot. ADR-015 claims hundreds of audited actions per second, while the Phase 1 review reports approximately one second per migrated claim.

**Why this is a problem:** Hash chaining detects modification only relative to a trusted head and complete history. Versioning permits privileged deletion; it is not WORM. The project currently overstates evidence integrity and audit independence.

**Recommendation:** Enable MinIO Object Lock/legal hold for evidence buckets now, with a documented development-mode exception. MinIO documents WORM locking as the immutability mechanism, distinct from ordinary versioning ([MinIO object locking](https://docs.min.io/aistor/administration/object-locking-and-immutability/)). Periodically sign and export audit checkpoints to an independently protected location; record backup sequence/head hashes. Add database-level audit coverage such as [pgAudit](https://github.com/pgaudit/pgaudit) as defense in depth, not as a replacement for semantic action audit. Rewrite ADR-015's capacity claim using measured results and define a benchmark.

### B-10 — Production and security baselines arrive after real-person use

**Evidence:** P7 says it finally applies field sensitivity and becomes safe for a second untrusted user. P9 first adds TLS everywhere, secrets handling, dependency/container scanning, rate limiting, observability, automated encrypted/off-host backup, and penetration testing. Yet P1 already processes a real OSINT corpus, P2 asks a second non-builder to drive the UI, and the product is called a usable MVP at P2.

**Why this is a problem:** Security controls are not only scale features. The longer they are deferred, the more routes, projections, search indexes, tiles, and exports must later be audited and repaired. This directly conflicts with the constitution's “do not retrofit” stance.

**Recommendation:** Split P9 into:

- **Minimum operating baseline before P2 demo:** authenticated UI, TLS outside localhost, secret-file hygiene, dependency lock, basic scanning, request/body limits, encrypted verified backups, health/structured logs, and security headers.
- **Production certification at P9:** SLOs, complete dashboards, automated DR, performance/fault testing, supply-chain attestations, and trigger review.

P7 should remain advanced trust-boundary work, not the first correct implementation of field authorization.

### B-11 — The time model does not support the advertised as-of guarantee

**Evidence:** ADR-008 collapses knowledge and system time, omits authorization time, and uses `DATE` for claim validity. P4 promises a defensible “what was recorded before X?” view. Entity labels, identity memberships, source evaluations, case membership, ontology interpretation, projection versions, and authorization policy changes are not all modeled as-of. GOAL.md asks the stronger question “what was known and legally available at the time?”

**Why this is a problem:** Filtering claim `recorded_at`/`retracted_at` alone can return a historically impossible view—for example a current entity merge applied to old claims, a current label, or data visible under today's permission but not the historical authority. Date precision also cannot represent many event timestamps.

**Recommendation:** Narrow the P4 promise to a precisely defined claim-recording snapshot, or extend the model. At minimum version identity membership, source evaluations, and projection inputs; return snapshot/ontology/identity revision IDs; distinguish transaction time from knowledge time; and use timestamp/range types where event precision requires it. Add tests for late-arriving information, backdated claims, later retraction, identity merge/split, and authority expiry.

### B-12 — Claim projection aggregation can fabricate time and confidence

**Evidence:** Spec 02's `edge_projection` takes `min(valid_from)`, `max(valid_to)` (or open-ended if any claim is open), the maximum credibility weight, and `count(DISTINCT record_id)` labeled as independent records.

**Why this is a problem:** Two disjoint claim intervals become one continuous relationship. One open-ended weak report can make the entire edge open-ended. Taking maximum credibility ignores contradictions and source reliability/verification. Different records from the same copied report are not independent sources. These projections can visually overstate duration and support—the exact “authoritative rumor engine” the project aims to avoid.

**Recommendation:** Preserve interval sets or emit time-segmented projected edges. Never collapse contradictions into one unqualified weight. Expose an inspectable support summary containing source lineage, grading dimensions, conflict count, and aggregation method/version. Model source derivation/copy relationships before claiming independence. Make any scalar display score explicitly optional and non-authoritative.

### B-13 — Event and geospatial plans reintroduce facts outside the claim store

**Evidence:** Article I says attributes and relationships are claims. P5 proposes a PostGIS `geometry` column and `precision` on location entities plus role-typed participation rows, while simultaneously saying everything comes from one claim set. T56 only requires each participation row to trace to a source, not that it is itself a claim. `location.precision` is already an optional ontology property, but T55 proposes making it required in a minor version bump.

**Why this is a problem:** Direct geometry/precision columns create mutable asserted properties. Parallel participation storage duplicates the predicate/claim model. Tightening an existing property from optional to required is breaking under Spec 01's own semver rules, not a minor additive change.

**Recommendation:** Store asserted geometry, precision, participant roles, time, and location links as typed claims; build PostGIS event/location projection tables for spatial queries. If performance requires canonical event tables, explicitly amend Article I and define which columns are identity/structure versus assertions. Split geographic representation into geometry type, administrative level, accuracy/uncertainty, and derivation method; do not default precision. Treat the required-property change as major or migrate existing rows before enforcing it.

### B-14 — The API authorization contract is incomplete and internally stale

**Evidence:** Spec 06 lists `POST /claims/{id}/relations`, review accept/reject, sources, projections rebuild, and some identity writes without complete FGA/case/handling gates. `/api/*` is shown with `H` despite ADR-019's anonymous static projection. The why-connected route is entity-to-entity, but P4 claims it can provide provenance for literal property values. Search purpose is required only for a sensitive scope/opened hit, whereas GOAL.md requires purpose before sensitive searches.

**Why this is a problem:** A role-only relation or review action can join or promote records outside the actor's case. A global projection rebuild by any analyst is a denial-of-service/staleness risk. The documented API cannot satisfy “every value opens its provenance.” Stale auth annotations undermine generated SDK and security tests.

**Recommendation:** Make a route-by-route authorization matrix authoritative before generating SDKs. Include resource lookup order, no-existence-leak behavior, case/compartment/handling/purpose/legal-authority gates, audit behavior, and rate/body limits. Add a generic claim provenance endpoint for property values. Restrict rebuild to a controlled job/action. Use PostgreSQL Row-Level Security as defense in depth against a missed query-layer filter; PostgreSQL supports default-deny RLS policies ([PostgreSQL RLS](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)). OpenFGA remains responsible for relationships; RLS reduces the blast radius of application omissions.

### B-15 — Existing ingestion runbooks bypass the governed pipeline

**Evidence:** `docs/INGESTION.md` calls the legacy toolchain “not legacy-only” but writes mutable text files into `data/real`, instructs the user to edit/trim transcripts, register filenames in `legacy/build_real_graph.py`, and run the legacy semantic build. `docs/RUNNING.md` likewise documents an LLM pass that validates/merges output into graph JSON. This conflicts with Spec 04's vault→derivative→review-queue path and Article IV's immutable derivatives. `--force` overwrites outputs and filename skipping is not content-addressed idempotency.

**Why this is a problem:** These are executable instructions, so users are likely to bypass the platform even if the design docs are correct. Editing machine output in place destroys provenance. The docs also normalize putting live API keys in `.env` by saying one “already holds” a key.

**Recommendation:** Move legacy-only runbooks under `legacy/` with a prominent “unsafe for governed data” banner. Rewrite the active ingestion runbook around `aegis ingest`/`POST /v1/ingest`, vault registration, immutable derivative versions, correction annotations/new derivatives, and review. Disable or clearly isolate the legacy semantic-to-graph path for real data. Never state that a secret already exists; show placeholder setup and safe validation without printing it.

### B-16 — Backup/restore does not recover the complete security and evidence state

**Evidence:** `docs/BACKUP_RESTORE.md` backs up one PostgreSQL database and current MinIO objects. It treats Keycloak as reproducible realm configuration and OpenFGA as reconstructible. Dynamic Keycloak users, credentials, sessions/config changes, client secrets, bucket version history/locks, encryption keys, and possibly FGA store identifiers are not covered. Encryption is an instruction to perform manually after backup, not a property of the backup command. FGA rebuild is manual after restore.

**Why this is a problem:** A successful claim-store restore may still leave users unable to authenticate, evidence versions missing, policy state incomplete, or plaintext backups exposed. A valid hash chain on an old snapshot does not prove freshness.

**Recommendation:** Define the recovery boundary and back up every non-reconstructible component. Automate encryption and manifest verification; fail if encryption or off-host copy fails. Preserve object versions, locks, legal holds, and metadata. Export/version Keycloak configuration and back up its database if local users are production state. Make FGA rebuild mandatory in restore. Record RPO/RTO, backup sequence, audit head, ontology/app version, restore order, and key-recovery procedure. Test loss of each service, not only PostgreSQL + current vault files.

### B-17 — Search and object sets can leak or silently widen scope

**Evidence:** ADR-012 and P6 search all records, then re-check authorization before hydration. Object sets store dynamic interface queries and are expected to pick up new interface members automatically after ontology changes. No filter grammar complexity limits, cycle detection, cost model, timeout, safe SQL compilation, definition-level redaction, or ontology-version pinning is specified.

**Why this is a problem:** Post-filtering can leak restricted rows through ranking, counts, pagination gaps, timing, snippets, or resource consumption. A shared set definition can reveal hidden identifiers even if results are filtered. Automatically adding future interface members changes the meaning of a saved analytic/watchlist without review. Recursive composition can cause denial of service.

**Recommendation:** Apply authorization constraints in candidate generation, not only hydration. Define count/pagination semantics that do not leak. Store a validated AST, never raw SQL; cap depth, nodes, runtime, cardinality, and composition cycles. Version set definitions and pin the ontology/interface expansion by default, with an explicit “track future members” option and change notification. Treat definition contents as protected data. Add property-based and adversarial tests.

### B-18 — Advanced AI is missing the data-boundary controls required by GOAL.md

**Evidence:** GOAL.md §26 requires purpose/authorization, case-scoped retrieval, redaction and minimization, then an approved model. P8 specifies producer metadata and review-queue output but not provider approval, data residency, retention/training terms, prompt injection, secret scanning, model endpoint allowlists, authorized ontology subsets, or a separate producer database role. It also demands byte-identical reproduction of translations/derivatives from potentially nondeterministic hosted models.

**Why this is a problem:** The review queue prevents false facts from entering canon but does not prevent unauthorized data from leaving the system. A unit test that scans “AI code paths” is weaker than a runtime permission boundary. Hosted model aliases and stochastic output cannot guarantee byte-for-byte reruns.

**Recommendation:** Add an AI data-egress policy and architecture before P8: approved providers/models, deployment location, prohibited data classes, minimization/redaction, retention/training guarantees, endpoint allowlisting, per-case authorization, prompt-injection/adversarial tests, quotas, and incident/rollback. Run producers with credentials that can write only typed suggestions/derivatives, never canonical tables. Define reproducibility as immutable input/config/model identifiers plus cached original output and evaluation—not identical regeneration. Use held-out multilingual evaluation with precision, recall, reviewer effort, cost, and latency, not “beats Gemini” alone.

### B-19 — Claims are disconnected from the reversible identity evidence needed for splits

**Evidence:** Spec 02 stores entity-valued claim arguments directly as `claim.subject_id` and `claim.object_id`. Spec 05 separately resolves `mention` rows through active `identity_membership` rows, while T20 moves memberships during merge/split decisions. The specified `edge_projection` groups the claim table's raw subject/object IDs and has no join to the active identity revision. Spec 05 nevertheless says projections re-aggregate automatically after an identity decision.

**Why this is a problem:** After Entity B is merged into Entity A, old claims still produce edges for B unless the projection resolves a canonical representative. A canonical merge map can collapse those nodes, but it cannot correctly undo a mistaken merge: when mentions are split out again, the system has no record of which entity-valued claims arose from those mentions. Rewriting every old claim during adjudication would make reversibility expensive, race-prone, and contrary to the immutable-history intent. The graph can therefore disagree with the active identity decision or silently attach historical claims to the wrong person.

**Recommendation:** Define claim-argument attribution and identity-aware projection semantics before T17/T20:

1. For extracted/reported entity arguments, preserve the source `mention_id` (for example, `subject_mention_id`/`object_mention_id` or a normalized `claim_argument` table) alongside the semantic entity target and source span.
2. Stamp the identity revision used when the claim was recorded. Resolve current graph/search projections through the active membership for anchored arguments; support an explicit revision for reproducible/as-of analysis.
3. Permit manual or assessment claims without textual mentions only under an explicit unanchored-argument rule. On a later split, route ambiguous unanchored claims to re-adjudication rather than silently choosing a new entity.
4. If a canonical entity map is retained for fast merge resolution, make it a rebuildable projection derived from the identity ledger—not a recursive interpretation of ordinary `merged_into` claims—and specify cycle, tombstone, concurrency, and revision behavior.
5. Add blocking tests proving that a merge collapses nodes/edges, a split restores mention-attributable edges, unchanged claims are not rewritten, and ambiguous claims enter review.

Replacing all entity references with mention-only references is not sufficient by itself because analyst-authored and assessment claims may not originate in one textual mention. The durable design is a claim argument with optional mention evidence plus explicit identity-revision semantics.

## High-priority cross-document findings

### H-01 — Source grading is conceptually right but technically incomplete

ADR-011 says 5×5×5, 3×5×2, and Admiralty inputs can be ingested faithfully. The current ontology maps only a subset of Admiralty source-reliability grades and contains no complete external information-credibility mappings. Reliability is stored as a mutable property of `source`, although a source's reliability can change over time or differ by context/case.

**Improve by:** defining complete, versioned external schemes; preserving every original component; adding a versioned source-evaluation record with actor, time, basis, scope, and supersession; and preventing inferred legacy confidence from masquerading as an original official grade. Add fixture-based round-trip tests for every supported scheme value.

### H-02 — Handling-code inheritance can silently downgrade data

Claims and source records default to `open`; no rule requires a claim to be at least as restrictive as its source record, property sensitivity, case, derivative, compartment, or legal restriction.

**Improve by:** specifying an effective-classification function (`max` of applicable controls plus non-ordinal caveats), rejecting unauthorized downgrades, requiring approval for deliberate declassification, and testing all ingestion/promotion/export paths. Compartments and originator controls are not ordinal handling codes and must remain separate mandatory controls.

### H-03 — Provenance supports only one source record per claim and too few basis relations

A claim has one `record_id`; assessment claims can weigh multiple claims/sources, and findings promoted to assessments need an analytic basis. `claim_relation` supports only `corroborates`/`contradicts`; there is no `based_on`, `quotes`, `derived_from`, `corrects`, or assessment-basis structure. P6's finding promotion has no schema link, and T74 says assertion type `assessment` while Spec 02 defines `assessed`.

**Improve by:** keeping one source-backed reported claim per source, and introducing explicit provenance/basis links for assessments and derived outputs. Resolve `assessed` versus `assessment` everywhere. Consider mapping the internal lineage model to [W3C PROV-O](https://www.w3.org/TR/prov-o/) instead of inventing unrelated provenance terms.

### H-04 — Idempotency definitions disagree

Spec 02 describes one ingestion-key formula, Spec 04 uses source system + filename/id + content hash, GOAL.md uses source system + source record ID + version, and the active legacy runbook skips by output filename. Replay semantics say already-decided suggestions are unchanged but do not say how a corrected producer version, changed ontology, or partial failure is represented.

**Improve by:** define separate immutable keys for received record identity, payload content, derivative computation, producer run, and suggestion. Specify version conflicts, replay lineage, partial completion, and whether identical bytes from two sources are one object but two source records.

### H-05 — The derivative schema and workflow lack key integrity constraints

The illustrative `derivative` check allows both parent columns to be set, not exactly one. No uniqueness key enforces `(parent hash, tool, version, canonical parameters)`, no working/final state is defined, and active runbooks overwrite in-progress outputs.

**Improve by:** enforce exact-one parent, canonicalize parameters, version algorithms/models, distinguish ephemeral work files from registered immutable derivatives, and store correction/annotation as new derivatives. Preserve original machine transcript and reviewed transcript separately.

### H-06 — Entity mentions are underspecified for multilingual extraction

`mention` lacks character/page/time offsets, language/script, mention type, normalized-form version, tokenization/transliteration version, and extraction provenance. P8 later requires source spans/offsets, so P2's model will need migration.

**Improve by:** add stable anchors into the immutable derivative, language/script, normalization pipeline/version, producer, and context window/hash now. Define behavior when a derivative is superseded.

### H-07 — Deterministic ER rules are unsafe even apart from Article VII

Same normalized name within one document is not proof of identity; two people with a common name may appear in one report. Passport/NIC/registration records can contain errors, fraud, duplicates, reassignment, or jurisdiction ambiguity. Graph-context features risk feedback loops: existing mistaken links increase match scores, and merges then strengthen those links.

**Improve by:** make exact identifiers high-priority candidates, not auto-merges; require issuer/type/validity and conflict checks; remove same-name auto-merge; version the graph snapshot used for contextual features; evaluate models with and without context; and prevent candidate-generated relationships from feeding their own score.

### H-08 — Splink acceptance and evaluation criteria are contradictory or weak

The P2 risk table says poor Splink transliteration quality is not a blocker because deterministic rules carry the demo, but the exit criterion explicitly requires Splink to find the seeded transliteration pair. T26 publishes precision/recall but sets no numeric threshold, sample size, uncertainty interval, or review-load target.

**Improve by:** make the exit requirement unambiguous; use a fictional/licensed labeled set with hard positives, hard negatives, common names, script variants, and missing fields; set minimum pairwise precision/recall and maximum review candidates per 1,000 mentions; and keep a separate held-out set. Do not use real-person identifiers in CI.

### H-09 — The MVP demo uses real OSINT where fictional data should own the gate

P2 requires a real-corpus run and a non-builder tester. This makes the repeatable gate depend on hosted model access, quota, potentially sensitive content, mutable provider behavior, and permission to expose real-person material to the tester or screenshots.

**Improve by:** make a fictional, fully local, deterministic fixture the blocking automated demo. Run the real OSINT walkthrough as an authorized manual smoke test with no captured sensitive output, explicit provider/data-egress approval, and a documented cleanup path.

### H-10 — P2 deliberately duplicates disposable UI work

ADR-023 says legacy is replaced, never extended, yet P2 adds multiple panels/pages to it and P4 reimplements them in React. The charter acknowledges this is throwaway work. Spec 07 says the Phase 4 explorer retires “at parity,” while ADR-023 rejects parity. Living P4 tasks also refer to deleting `app/static`/`app/server.py`, not the post-ADR `legacy/app/...` paths.

**Improve by:** either build a minimal durable authenticated React shell in P2 and grow it in P4, or use server-rendered components with durable API/view-model contracts that can be embedded later. Jinja2 + HTMX is a reasonable implementation of the second option and is already permitted by Spec 07; it is not a newly missing architecture decision. Keep the temporary surface small, accessibility-testable, and separated from the legacy Cytoscape file. Update living paths and remove “parity” language. Avoid making intentional waste a milestone strategy.

### H-11 — P3 bundles too many risky abstractions before a durable UI consumes them

P3 combines module-like interfaces, shared properties, functions, actions v2, a generic side-effect system, ontology governance, Python SDK, TypeScript SDK, FGA codegen, and UI metadata. This is likely larger than its `M` estimate and delays the real workspace. Several features have no immediate consumer or conflate concerns: FGA authorization object types are not automatically the same as ontology interfaces, and an API client cannot be generated from the ontology alone because search, pagination, cases, audit, and files are API concepts.

**Improve by:** split P3:

- **P3a:** module composition, shared schemas/interfaces, stable OpenAPI operation IDs, JSON Schema/UI metadata, and only the TypeScript client required by P4.
- **P3b/later:** functions and generalized action side effects when a concrete consumer requires them; Python client only when pipelines/notebooks need it.

Keep the ontology authoritative for domain vocabulary and action semantics; keep OpenAPI authoritative for HTTP transport. Generate clients from FastAPI's OpenAPI document rather than maintaining a custom full client generator. OpenAPI Generator has stable Python and `typescript-fetch` client targets ([Python generator](https://openapi-generator.tech/docs/generators/python/), [TypeScript Fetch generator](https://openapi-generator.tech/docs/generators/typescript-fetch/)).

### H-12 — Ontology actions duplicate authorization policy and mix platform/domain concerns

Roles live in Keycloak/security specs, FGA models, route dependencies, action code, and ontology action declarations. Platform actions such as case membership, quarantine release, evidence custody, and sealing are inside the same criminal-domain artifact. It is unclear which layer wins when they disagree.

**Improve by:** define authoritative ownership: ontology declares domain action parameters/invariants; a policy model declares authorization; OpenAPI declares transport. Add drift checks rather than duplicating role lists. Put platform actions in a platform module if module composition is adopted.

### H-13 — Arbitrary function implementation paths in YAML are a code-execution boundary

Spec 08 permits `implementation: aegis.functions...` and validates importability. An ontology deployer can therefore select importable code. The security model says admins manage ontology but cannot read content; a malicious or mistaken implementation could access content during a rebuild.

**Improve by:** allow only functions registered in a code-side allowlist with declared capabilities, input/output schemas, deterministic/resource limits, and security review. Ontology selects a registered identifier and version, not an arbitrary import path. Run expensive functions as bounded jobs over authorized snapshots.

### H-14 — Function-output deletion and byte-for-byte reproduction conflict with immutable knowledge

T33 says delete function outputs and reproduce them byte-for-byte. Canonical claims have generated IDs/timestamps/audit and should not be deleted. Nondeterministic ordering also makes byte equality meaningless.

**Improve by:** keep derivations in rebuildable projection/finding tables keyed by deterministic content identity. Test semantic equality or a canonical digest over inputs/config/output, not database-byte identity. If reviewed outputs become claims, retract/supersede them rather than deleting them.

### H-15 — The side-effect outbox is not designed

Spec 08 borrows the “ADR-014 precedent,” but the existing `authz_outbox` schema only holds FGA tuples. Refreshing a materialized view after every accepted suggestion can be expensive and blocks freshness guarantees; notification semantics, deduplication, ordering, poison messages, and operator recovery are unspecified.

**Improve by:** define a generic transactional outbox/event envelope separately from FGA projection work. Include aggregate/version, event type, idempotency key, attempts, visibility time, terminal failure, and dead-letter/replay operations. Debounce/coalesce projection refreshes and expose staleness; do not refresh synchronously per claim.

### H-16 — Ontology change-management CI relies on brittle commit history

Spec 08/T36 requires the bump commit to reference a proposal, but the Git workflow squash-merges a PR into one generated commit and CI may use shallow history. Hard-coded future version `0.4.0` also assumes no earlier ontology change.

**Improve by:** put `proposal_id`, previous version/content hash, and compatibility classification in the ontology release metadata or a release manifest. Compare against the PR base artifact, not an assumed local prior commit. Select the next version at phase start rather than pre-authoring a number.

### H-17 — Object-view and investigation models are incomplete

P4 assumes existing actions can link claims/evidence to cases, but Spec 06 does not define those routes/actions. Hypotheses and tasks/leads lack storage/API specs, authorization, assignment, review history, status transitions, due dates, confidence, and collection requirements from GOAL.md §18/§31. T41's proposed Spec 09 covers object views, not the operational model.

**Improve by:** author an investigation-domain spec before UI work. Define case linking semantics, hypothesis versions and evidence basis, tasks/leads/owners/dates, comments/working-note classifications, approval rules, and audit/authz. Split model/API tasks from UI tasks so acceptance is testable.

### H-18 — Object views can leak case existence

P4's entity-360 page lists “cases the entity appears in.” A viewer may be allowed to see an open entity but not a restricted case. The docs do not state that case references are independently filtered and that counts cannot reveal hidden cases.

**Improve by:** treat every nested relationship as a separate authorized resource. Return only authorized cases, no hidden count, and no timing/ranking leak. Add this to the authz matrix and object-view descriptor contract.

### H-19 — Browser authentication/security requirements are too thin

T42 says Keycloak OIDC PKCE but omits token storage, refresh/rotation, logout, CSP, CSRF model, XSS protection, session timeout, multi-tab behavior, and authorization-code callback constraints.

**Improve by:** use a maintained client rather than implementing OIDC state management. `oidc-client-ts` supports browser OIDC/OAuth and PKCE ([project](https://github.com/authts/oidc-client-ts)). Specify memory/session storage policy, no local-storage tokens unless explicitly accepted, CSP/security headers, idle/absolute timeouts, logout/revocation, and end-to-end tests.

### H-20 — Generic forms/screens should use standards before custom descriptors

The plan proposes custom UI descriptors, Pydantic generation, action schemas, SDK schemas, and extraction schemas from the same DSL. This can become a custom schema ecosystem.

**Improve by:** map ontology structural output to JSON Schema 2020-12 with stable `$id`/version and use semantic validation as a second phase. JSON Schema explicitly distinguishes structural from semantic validation ([JSON Schema basics](https://json-schema.org/understanding-json-schema/basics)). For generic React forms, evaluate `react-jsonschema-form`, which generates forms from JSON Schema ([RJSF](https://rjsf-team.github.io/react-jsonschema-form/docs/)). Keep bespoke code for provenance, conflict display, and governed actions—the true domain value.

### H-21 — Geospatial precision and map delivery are underspecified

The ladder mixes epistemic precision (`exact`) with geometry representation (`centroid`, `area`) and administrative granularity (`city`, `country`). “Country never renders as a point” is not enough; geometry may be absent or generalized. Base-map licensing, offline/sovereign tiles, coordinate reference systems, antimeridian, invalid geometry, cache keys, and authorization-safe tile serving are absent.

**Improve by:** model claimed geometry, uncertainty/accuracy, administrative level, and derivation method separately. Specify CRS normalization and validation. Serve only authorization-scoped projection tables/functions; tile caches must include policy/snapshot scope or be private per authorized projection. Evaluate MapLibre's Martin instead of building a tile server; Martin already serves PostGIS vector tiles ([Martin docs](https://maplibre.org/martin/architecture/)). Do not allow auto-discovery/auto-publish of canonical tables.

### H-22 — Search quality goals are deferred too late to assess architecture

P6 postpones numeric precision/recall targets and query corpus design to T66, while ADR-012's OpenSearch trigger depends on them. P2 already claims transliterated basic search without a defined expectation. Search across names, aliases, claims, and full documents has different relevance/security metrics.

**Improve by:** define a small target table now: per language/script and resource type, precision@k, recall, latency, false-positive policy for identifiers, and authorized-result behavior. Specify and version one index/query pipeline that preserves original text and applies the same canonical Unicode normalization, whitespace/punctuation rules, script detection, and ICU transliteration-key generation at write and query time. Test canonically equivalent sequences, mixed scripts, initials, format/zero-width characters, and common transliteration variants. Unicode normalization exists specifically to give equivalent sequences a consistent form ([ICU normalization](https://unicode-org.github.io/icu/userguide/transforms/normalization/)); ICU transforms also have script- and context-dependent limitations ([ICU transforms](https://unicode-org.github.io/icu/userguide/transforms/general/)). Do **not** strip Sinhala or Tamil diacritics wholesale without labeled evidence: that can collapse distinct names rather than normalize equivalent encodings.

`pg_trgm` is a plausible retrieval signal and supports indexed similarity search ([PostgreSQL `pg_trgm`](https://www.postgresql.org/docs/current/pgtrgm.html)); the documentation should not assume either that it is sufficient or that it inherently fails on these scripts. Evaluate raw-script exact/prefix keys, normalized trigrams, and versioned transliteration keys against the same golden set. Use fictional or appropriately licensed test text. If the P6 golden set fires the OpenSearch trigger, the remediation belongs in P6 before its gate—not as a P9 surprise.

### H-23 — Analytic reproducibility and promotion are underspecified

P6 says rerunning the same inputs reproduces a finding, but dynamic object sets and projections are not immutable inputs. Method code/library versions, identity revision, ontology, authorization scope, random seed, and graph snapshot are not all required. Weighted-path semantics are undefined. A promoted assessment claim needs a source/basis model that does not exist.

**Improve by:** record an immutable run manifest: object-set definition version plus evaluated input digest/snapshot, projection version, identity revision, ontology, code and library versions, parameters, random seed, actor/purpose/authorization scope, and caveat version. Define every metric's graph/weight interpretation. Promotion should create a review suggestion referencing the finding and input claims, never invent a source record.

### H-24 — Watchlists do not implement the constitutional or GOAL lifecycle

P6 says an exact identifier landing in canon “fires” an alert. Article VII explicitly lists alerts as suggestions; GOAL.md §32 requires deduplication, policy/authority check, assignment, investigation, outcome, explanation, false-positive considerations, and legal restrictions. Scheduling/evaluation ownership is not defined.

**Improve by:** treat a detection as a typed alert suggestion with rule/version, inputs, authorization/legal basis, dedupe key, confidence/exactness, and triage lifecycle. Decide whether evaluation is on-write via outbox or scheduled; this affects the orchestration trigger. Never use real national identifiers in the OSINT profile.

### H-25 — P7's redaction rules contradict no-existence-leak rules

Spec 03 and UI principles say restricted information is absent and hidden counts are not shown. P7 T79 instead requires marked field redaction, and export previews show withheld categories/counts. Both can be valid in different contexts, but the policy is not defined. An explicit marker reveals that a sensitive field exists.

**Improve by:** define response modes by resource/action: omit completely for exploratory search/object views; marked redaction only when the caller is authorized to know the document/schema but not the value; counts only for disclosure officers with an explicit privilege. Test each mode, including nested fields and sort/filter behavior.

### H-26 — Compartments and judicial state have no underlying data model

The FGA `compartment` type exists, but no canonical compartment membership/resource assignment schema, outbox/rebuild rules, row assignment, or field assignment is specified. Sealed/expunged semantics, policy authority, retention/backups, and auditor/handler exceptions are unclear. T81 says handler-only identity while T82 says auditors can see sealed data; the precedence matrix is absent.

**Improve by:** add a security-label/compartment assignment model in PostgreSQL as source of truth, versioned grants, expiry, dual-control rules, and FGA projection. Define policy precedence for admin, auditor, handler, supervisor, break-glass, legal hold, seal, privilege, and expungement. Distinguish suppression/sealing from legally required destruction or crypto-shredding; do not promise reversible expungement without a legal policy decision.

### H-27 — Informant protection is materially weaker than GOAL.md

P7 proposes a compartment and pseudonym. GOAL.md additionally requires separate security domain/key, two-person disclosure approval, access alerts to an independent supervisor, and export disabled except formal workflow.

**Improve by:** either implement the full protected-source boundary or state that P7 provides only a synthetic compartment prototype. A flag/compartment in the same database is not equivalent to a separate encryption/security domain.

### H-28 — Disclosure packages should adopt a standard and need stronger delivery semantics

P7 invents a package manifest and hash format. Expiry, acknowledgement, encryption for recipient, signing-key custody/rotation, canonical serialization, malware handling, package revocation, recipient identity/grant representation, and delivery receipt are missing. A route lint cannot prove packages are the only bulk exfiltration path (CLI, DB access, logs, tiles, browser downloads, and backups also exist).

**Improve by:** base package layout/fixity on BagIt rather than a custom archive; RFC 8493 defines payload and tag manifests for reliable transfer ([BagIt RFC 8493](https://datatracker.ietf.org/doc/html/rfc8493)). Add Aegis metadata, detached digital signature, encryption, expiry, recipient grant snapshot, acknowledgement/receipt, and policy decision. BagIt provides integrity, not active-attack security, so signatures and trusted keys remain necessary. Maintain an egress inventory rather than only a route lint.

### H-29 — AI outputs cannot be made safe by citation presence alone

P8 treats every sentence having a claim ID as sufficient. A model can cite an unrelated claim, misstate the claim, or erase grading/contradiction in prose. Document summaries sometimes need source-span citations even when no claim exists; tasks inconsistently require claim IDs versus claim/source IDs.

**Improve by:** support claim and immutable source-span citations, validate that cited resources were in the authorized retrieval set, render grading/contradiction context, and sample for entailment/faithfulness. Clearly label summaries as generated suggestions. Decide whether saved summaries are derivatives, analytic notes, or review items; the current queue schema cannot represent them.

### H-30 — The AI evaluation gate is not scientifically sufficient

“Beats the Phase-1 Gemini pass on precision” can be gamed by proposing fewer claims, using the evaluation set during prompt design, or relying on a mutable model alias. It ignores recall, calibration, subgroup/language behavior, reviewer time, cost, and regression significance.

**Improve by:** freeze baseline outputs/config, keep train/dev/held-out test separation, use immutable provider/model identifiers where possible, report precision/recall/F1 by predicate and language, confidence intervals, reviewer minutes/accepted claim, cost, latency, abstention, and adversarial prompt-injection results. Require absolute minimums as well as improvement.

### H-31 — Production trigger evaluation is logically inconsistent

T109 says every trigger is evaluated against T108 measured numbers, but several triggers are facts, not performance metrics: a real second agency, multi-day approvals, number of scheduled pipelines, or existence of a continuous feed. If a trigger fires, T109 says the work is separately chartered, while the P9 exit says fired-and-delivered.

**Improve by:** give each trigger an evidence type, owner, observation cadence, decision deadline, and resulting work package. Separate “trigger fired” from “upgrade delivered.” A phase cannot require unbounded upgrade delivery without estimating/chartering it. Trigger review should occur continuously at the phase that observes the evidence, not only P9.

### H-32 — “Production” conflicts with the single-host and availability promises

GOAL.md calls initial production multi-AZ with 99.95/99.99 targets and independent audit; ADR-010 and P9 use hardened single-host Compose unless a trigger fires. A single host cannot meet those availability/DR properties.

**Improve by:** define deployment tiers: research/dev, single-host controlled pilot, and production/agency. Give each explicit SLO/RPO/RTO, threat assumptions, maximum data class, and prohibited uses. Do not call the Compose tier full production if it intentionally lacks HA, KMS, WORM replication, and sovereign-cell boundaries.

### H-33 — Dependency and build reproducibility are missing from the present baseline

`pyproject.toml` uses broad minimum versions and no lockfile is present. CI actions and service images use tags rather than immutable digests. Supply-chain scanning waits until P9.

**Improve by:** add a reviewed lockfile, dependency update policy, hashes/digests for release builds, SBOM, license policy, SAST/dependency/container scans, and signed release artifacts before real-person deployment. Seeded scanner tests should use fixtures/policy simulation rather than deliberately landing a live vulnerable dependency.

### H-34 — Audit event requirements and schema do not align

GOAL.md §39 requires agency, device, legal authority, data returned, export destination, reason, and result. Spec 02 audit has actor/session/purpose/case/action/resource/decision/detail; critical fields are optional JSON at best. Anonymous authentication failures also do not fit a non-null authenticated actor cleanly. Read auditing failure behavior is unspecified.

**Improve by:** define a versioned audit schema and mandatory fields per event class, authenticated and unauthenticated actor representation, returned-data digest/count policy without leaking protected content, request/trace ID, policy/model version, and fail-open/fail-closed behavior when audit storage is unavailable. Anchor audit completeness with database/session audit in addition to application events.

### H-35 — The roadmap omits major capabilities claimed by the north star

No phase owns several GOAL.md commitments: source data contracts/schema registry, malware/signature checks, collection requirements/plans, intelligence-report lifecycle and supervisor publication, collaboration/comments/review requests, legal policy packs, retention/disposition, originator control, correction/challenge, privileged-material workflow, disclosure acknowledgement, or full alert lifecycle. Communication/financial modules are explicitly deferred because feeds do not exist, which is sensible, but there is no trigger/backlog slot to validate those domain modules later.

**Improve by:** add a GOAL→roadmap traceability appendix classifying every capability as `scheduled`, `trigger-gated`, `explicitly out of scope`, or `north-star only`. Give every unscheduled binding requirement an owner/trigger. This is more honest than allowing GOAL.md to imply eventual coverage with no phase.

### H-36 — The platform core still depends on quarantined legacy code

`pyproject.toml` says only `aegis` is packaged and legacy is never shipped, but its own comments say projections reuse `legacy.pipeline.clustering`. The plan says legacy is importable in dev/CI but not shipped. These statements imply an installed wheel may lack a dependency needed by a documented core command.

**Improve by:** move reusable generic algorithms into the core now or package them explicitly until replacement. Document the precise deletion dependency. “Quarantined” should mean the core does not import it, not merely that the directory has a warning README.

### H-37 — One synchronous audit chain can serialize all audited traffic

ADR-015 deliberately appends each audit event to one synchronous hash chain in the action transaction, and the audit requirements include sensitive reads as well as writes. A single chain head is therefore a global ordering point for graph reads, search, case views, exports, and mutations. The claimed “hundreds per second” capacity is unmeasured and is difficult to reconcile with the Phase 1 review's roughly one-second migrated-claim result. The external estimate of a fixed 50–100 requests/second ceiling is not supportable without a workload and hardware benchmark, but the serialization risk itself is real and will appear with multi-user use, not only at P9.

**Improve by:** benchmark audit append throughput, lock wait, and p95/p99 latency before the P2/P4 multi-user gates, including concurrent audited reads. Define an SLO and overload/failure behavior. If the single head fails it, use independently verifiable per-tenant/case/time-partition chains with signed aggregate checkpoints, or synchronously append a minimal event to a durable buffer/outbox and chain/anchor it asynchronously. An asynchronous design is acceptable only if sensitive reads fail according to explicit policy when durable capture is unavailable, events cannot be dropped/reordered unnoticed, and all shards receive externally protected checkpoints. Do not create a weak, unanchored “read audit” merely because reads do not mutate canon; access history is itself security evidence.

### H-38 — JSONB literal storage lacks a typed query and canonicalization strategy

ADR-013's ontology-driven `claim.object_value` avoids a DDL migration for ordinary vocabulary changes, but dates, timestamps, decimals, booleans, identifiers, and geometry need canonical equality, ordering, validation, and index semantics. JSONB is not inherently unindexable: PostgreSQL supports GIN, expression, and `jsonpath` indexing ([PostgreSQL JSON types](https://www.postgresql.org/docs/current/datatype-json.html)). The real gap is that a JSON string representing a date or decimal is not a database `date` or `numeric`, so semantic validity and efficient range queries depend on repeated, consistent application casts unless another structure is specified.

**Improve by:** first enumerate and benchmark the P2–P6 query patterns, then choose one documented physical strategy: exactly-one typed literal columns with structural `CHECK` constraints; a normalized typed `claim_value` table; or JSONB as canonical input plus generated/expression-indexed typed projections for hot types/properties. PostgreSQL generated columns can maintain derived typed values, subject to expression restrictions ([PostgreSQL generated columns](https://www.postgresql.org/docs/current/ddl-generated-columns.html)). Whichever option is chosen, specify canonical date/timezone/decimal/unit/identifier serialization, invalid-value behavior, and index migrations. Keep predicate/domain/range vocabulary validation in the ontology layer; database structural typing is defense in depth, not a return to hand-written domain tables.

## Medium and documentation-quality findings

### M-01 — Status labels are stale or contradictory

- P2 charter says `ACTIVE (next phase)`; README says active; P2 task file says pending.
- Specs 02–06 remain “draft for Phase 1” after Phase 1 is declared complete.
- Ontology proposal/history READMEs describe CI enforcement as active even though P3 is future.
- Spec 07 says Phase 1 UI is behind auth, contradicting ADR-019.

**Recommendation:** add document metadata (`status`, `owner`, `last validated`, `applies from/to`, supersedes) and a CI link checker/status check. “Draft” should not be the authoritative implemented spec.

### M-02 — Product success criteria and ontology versioning disagree about migrations

Spec/constitution success says a new object type requires ontology + migration, while ADR-013 says routine ontology vocabulary changes require zero DDL and the plan says adding a type is a data change. P3 says an interface predicate should flow with zero hand-written domain code.

**Recommendation:** distinguish vocabulary-only additions, storage-shape additions, projection changes, and data backfills. State exactly when an Alembic/data migration is required.

### M-03 — Historical ontology interpretation needs a stronger release artifact

Claims store only a semver string. Historical versions are copied only on major bumps, and generated artifacts/templates/function code can change independently. Spec 01 already requires a data migration for a major version, but also says the loader must interpret historical versions “or” rows must have been upgraded. ADR-013 simultaneously says historical claims remain valid under their old ontology version. The documentation never chooses whether production runs one active registry or multiple registries keyed by claim version.

**Recommendation:** choose one operational model explicitly:

- **Eager upgrade/current-only runtime:** every incompatible release supplies a governed data migration, superseding claims or compatibility aliases/current views where immutable claim history forbids in-place rewriting; runtime loads only the current registry and the stored old version is audit metadata.
- **Multi-registry runtime:** load immutable release bundles by version/hash and define cross-version query translation plus a current canonical view.

In both models, stamp a content hash/release ID in addition to semver and publish an immutable ontology release bundle containing YAML, generated schemas, compatibility report, and migration references. Preserve every released artifact or guarantee reconstruction from signed Git tags/releases. “Make major migrations mandatory” alone does not resolve whether immutable historical claims are rewritten, superseded, aliased, or interpreted under an old registry.

### M-04 — Literal fallback creates unresolved identity debt

`affiliated_with` accepts entity or literal. Literals can never participate in entity resolution or graph links without later mutation/migration, and identical organization text can proliferate.

**Recommendation:** represent unresolved references explicitly as mention/entity-draft objects with resolution status, not indefinitely as arbitrary literals. Reserve literals for genuinely scalar values.

### M-05 — `source_record.status` and queue state machines are not fully constrained in the illustrated DDL

ADR-013 says fixed code-owned status state machines remain DB-constrained, but Spec 02's shown DDL does not include those checks or valid transition rules.

**Recommendation:** list state diagrams and transition ownership; make migrations authoritative but keep the spec accurate enough to review invariants.

### M-06 — `derivative` parent constraint is not XOR

The check allows both parent columns; Article IV describes a parent chain.

**Recommendation:** require exactly one immediate parent, while allowing multi-input analytic jobs through a separate input-link table.

### M-07 — `claim_relation` direction/canonicalization is undefined

Both corroboration and contradiction are conceptually symmetric, but reverse duplicates and self-links are not prohibited.

**Recommendation:** canonicalize pairs, forbid self-links, capture relation basis/source/actor/note, and define whether machine suggestions can propose but never directly write them.

### M-08 — IDs are described as “non-guessable enough” without a need

ULIDs reveal creation time and are not an authorization mechanism.

**Recommendation:** describe them as sortable identifiers only and ensure every lookup is authorized regardless of guessability.

### M-09 — Role definitions and phase references are stale

Security says supervisors seal records in P6 although sealing is P7; ADR-008 defers authorization time to Phase 6 although legal authority is P7. Investigator adjudication is “per config” without a configuration-policy spec.

**Recommendation:** correct living phase references and define role/action policy in one matrix.

### M-10 — “Someone who did not build it” is not a reproducible acceptance criterion

The tester, environment, prerequisites, allowed assistance, time box, data authorization, and success recording are undefined.

**Recommendation:** define a usability protocol: named persona, clean environment, written prerequisites, no verbal assistance, observable checkpoints, maximum duration, issue severity threshold, and signed result. Keep automated functional proof separate.

### M-11 — Basic search and full search overlap without a migration contract

P2 builds search over labels/aliases/mentions; P6 rebuilds broader search. Index ownership, endpoint compatibility, relevance behavior, and deletion of P2 paths are unspecified.

**Recommendation:** define P2 as the first implementation of a stable `SearchPort`/endpoint and P6 as an additive backend/index expansion, with compatibility and benchmark tests. Avoid parallel endpoints.

### M-12 — Cursor pagination waits too long

Spec 06 declares cursor pagination as a convention, but P4 says it is deferred. P2 queue/search can already grow, especially after extraction or ER.

**Recommendation:** add pagination and deterministic ordering in P2. This is not merely workspace polish.

### M-13 — Search success assertions use “strictly fewer” incorrectly

A lower-clearance user may legitimately receive the same results if all matching rows are open.

**Recommendation:** assert subset behavior generally and seed at least one restricted matching result for the strict-subset fixture.

### M-14 — Case-less OSINT is globally visible to roles without a future migration plan

Spec 03 intentionally allows case-less claims based on role + handling. Later case-scoped work may need to attach existing claims to cases without changing original scope or creating leaks.

**Recommendation:** define a general collection/workspace scope distinct from case, and a policy for referencing shared OSINT into cases without copying or widening it.

### M-15 — FGA revocation lag has no bound or fail-closed strategy

ADR-014 calls exposure “bounded” by best effort plus dispatcher latency, but no maximum lag/SLO exists; the current implementation reportedly lacks the inline delete. PostgreSQL is authoritative for direct `case_member` state while route authorization consults its asynchronous OpenFGA projection and row filters consult PostgreSQL. A delayed grant therefore fails closed, but a delayed revocation can still authorize route metadata or route-specific behavior even after protected rows disappear. This is an inconsistent decision, not merely a confusing user experience.

**Recommendation:** include authorization projection revision/lag in checks, reject sensitive requests when revocation state is stale, set a maximum lag alert, and make revocation tests blocking. For direct-membership routes, require current authoritative membership and a current FGA grant; for transitive ReBAC grants, identify and version the actual source relationship. Apply the same decision to route metadata and row data. Never fall back from an FGA denial to PostgreSQL merely because the projector may be lagging unless PostgreSQL implements the complete equivalent policy—such a fallback can bypass supervisor/custodian/compartment constraints.

### M-16 — Object-set algebra lacks snapshot semantics

Union/intersection/difference over caller-filtered dynamic sets can change between subqueries and can reveal information through timing/cardinality.

**Recommendation:** evaluate one request under one consistent database/projection snapshot and one authorization context; cap/obscure counts where policy requires; record snapshot in analytic runs.

### M-17 — Event-vs-edge rule is too absolute

“Time/place-bearing → event” would turn many ordinary time-bounded binary claims into events. “More than two parties” is useful guidance, not a complete ontology rule.

**Recommendation:** base the choice on whether the occurrence has identity/properties/provenance independent of a single pairwise assertion. Include examples and counterexamples; allow an event plus derived pairwise projection without duplicate canon.

### M-18 — Map privacy is scheduled after the map

GOAL.md requires privacy-aware generalization. P5 launches maps before P7 compartments/field filters.

**Recommendation:** require handling/property sensitivity and authorized generalization in P5; do not expose exact sensitive geometry and promise to fix it in P7.

### M-19 — Base-map and geocoder governance are absent

External tile/geocoding services may receive sensitive viewport/query data and may have licensing/data-residency constraints.

**Recommendation:** specify an offline/self-hosted default or an explicit approved external provider policy, cache/licensing attribution, and a prohibition on sending protected selectors to public geocoders.

### M-20 — Export “only sanctioned bulk path” is overstated

Graph endpoints, search pagination, tiles, API scripts, database access, logs, and backups are also bulk egress paths.

**Recommendation:** maintain an egress threat model/inventory and enforce limits/monitoring across all paths. Phrase packages as the sanctioned disclosure workflow, not a proof that other exfiltration is impossible.

### M-21 — Break-glass expiry needs request-time enforcement

Relying on a scheduled tuple deletion would inherit FGA lag and fail open.

**Recommendation:** store grant expiry in the canonical policy state and check it on every access; tuple cleanup is maintenance only. Require strong reauthentication and narrow resource/action scope.

### M-22 — P9 observability can mostly use standard instrumentation

Custom instrumentation for HTTP/database/client spans would be avoidable. OpenTelemetry provides Python zero-code instrumentation ([OpenTelemetry Python](https://opentelemetry.io/docs/zero-code/python/)).

**Recommendation:** start with auto-instrumentation/exporters, then add manual spans only for domain actions, policy decisions, projection versions, and job boundaries. Define telemetry redaction/high-cardinality rules so claim/entity IDs and excerpts do not leak into logs.

### M-23 — P9 performance triggers lack workload definitions

“Realistic corpus,” p95, and traversal-dominant are undefined. A benchmark without degree distribution, authorization filters, cache state, concurrency, query mix, hardware, and corpus version cannot fire an ADR reliably.

**Recommendation:** specify workload manifests and report p50/p95/p99, warm/cold, concurrent users, error rate, resource use, projection freshness, and policy-check cost. Keep the corpus generator fictional.

### M-24 — CI and documentation verification are narrower than claimed governance

Current CI runs pytest and ontology validation, but future documents assume codegen drift, proposal/semver compatibility, TypeScript, API security inventory, model registration, read-surface registration, and scanner gates.

**Recommendation:** add a roadmap table stating which CI gate exists now versus the phase that introduces it. Avoid present-tense claims in scaffold READMEs before implementation.

### M-25 — Git workflow contradicts binding agent rules

`docs/GIT_WORKFLOW.md` allows `[skip ci]` for trivial doc changes, while AGENTS.md forbids it. It also hard-codes Claude attribution and a “Generated with Claude Code” line for all agents.

**Recommendation:** make the no-skip rule consistent and parameterize AI provenance to the actual tool/agent. Binding rules should not require false attribution.

### M-26 — Windows quickstart is incomplete

The repository is being used on Windows, but root quickstart/Makefile assume `.venv/bin`, Bash, and GNU Make. Legacy docs provide separate Windows commands, creating an easier obsolete path than the governed path.

**Recommendation:** add supported PowerShell equivalents or an explicit WSL/Git Bash prerequisite for the platform quickstart. Ensure the governed workflow is the easiest documented workflow.

### M-27 — Real-data source policy is too coarse

The source list names publications generally, while claims need precise URL/title/date/access/version citations. “Most individuals are deceased, convicted, or charged” is not a sufficient privacy/accuracy basis and risks treating public reporting as permanent permission.

**Recommendation:** require claim-level source metadata, archived retrieval evidence where lawful, correction/retraction monitoring, data-review dates, and stricter treatment for living/non-convicted persons. Never let CI artifacts, screenshots, logs, or demo recordings contain the real corpus.

## Goal-to-roadmap alignment

| Goal area | Roadmap alignment | Review conclusion |
|---|---|---|
| Claims/provenance/grading | P1–P2 | Direction aligned; projection aggregation, grading schemes, basis links, and source history are incomplete. |
| Reversible identity | P2 | Correct priority; schema/task design cannot yet prove exact reversal, claims lack mention/identity-revision routing for splits, and deterministic auto-merge contradicts governance. |
| Evidence integrity | P1/P9 | Metadata exists, but WORM, external audit anchoring, complete backups, legal hold, and disposition are missing/late. |
| Authorization/no global graph | P1/P7 | Public exception and delayed field controls violate the stated rule. Purpose/legal authority is mostly recorded, not enforced. |
| Ontology-driven multi-domain platform | P3 | Interfaces/codegen are planned; actual module composition and a second-domain proof are absent. |
| Investigation workspace | P4 | UI is planned; investigation/report/collaboration domain models are incomplete. |
| Events/geo/time | P5 | Scheduled, but proposed canonical columns conflict with claims-only design and privacy controls arrive later. |
| Search/analytics/watchlists | P6 | Scheduled; authorization prefilter, snapshot semantics, alert lifecycle, and measurable targets need work. |
| Sharing/legal governance | P7 | Scheduled too late for foundational fields; export, expungement, informant, and compartment semantics are underspecified. |
| Controlled AI | P8 | Human-review intent aligns; data egress, runtime isolation, typed outputs, and evaluation rigor do not. |
| Production/scale | P9 | Operational baseline exists in outline; it is too late, single-host “production” conflicts with GOAL SLOs, and triggers are not consistently actionable. |
| Retention/policy packs/correction | None | Binding north-star requirements have no owner or phase. |
| Malware/signature/source contracts | None | Ingestion requirements have no roadmap tasks. |
| Intelligence reports/collection plans | None | Central intelligence-cycle capability is absent from tasks. |
| Collaboration/review requests/comments | None | Explicitly excluded at P4 and never scheduled. |
| Originator control/federation | Triggered after P9/P7 format | Reasonable to defer federation, but originator restrictions and package receipts need present data-model seams. |

## Phase-by-phase gate review

### P0 — Governance before code

**Verdict:** should not remain unqualified “complete.” The constitution is clear but not consistently applied. “Every feature idea traceable to an article” is not demonstrated by a traceability artifact, and many GOAL requirements have no phase.

**Repair:** create a constitution-conformance matrix and GOAL traceability appendix; record the public-route and algorithmic-write conflicts as unresolved, not completed governance.

### P1 — Claim store, evidence, RBAC, audit

**Verdict:** functionally delivered but governance-complete claim is unsupported. Public routes, missing field filtering, revocation lag, partial backup, mutable-version evidence, and lack of external audit anchor are known gaps.

**Repair:** relabel “foundation implementation complete; security exceptions open” or close the exceptions before P2.

### P2 — MVP identity/provenance

**Verdict:** not ready to start from the task list. Add UI ingestion/extraction, authenticated UI, pagination, identity ledger/candidate schemas, mention-attributed claim arguments with identity-aware projections, typed suggestion model, numeric ER/search quality criteria, and current security-debt tasks. Resolve whether Splink quality is a gate. Use fictional data for the blocking demo.

### P3 — Ontology v2

**Verdict:** over-scoped and overly custom. Module composition—the capability required by the platform mission—is missing, while generic functions/two SDK generators arrive before concrete need.

**Repair:** prioritize module composition, standard schemas/OpenAPI, and the minimum TS client for P4. Defer generic function/side-effect machinery until a consumer proves its shape.

### P4 — Workspace/object views

**Verdict:** aligned with product value but operational models and security details are missing. P2 creates redundant disposable UI work. As-of claims are stronger than the data model.

**Repair:** use a durable P2 shell; author investigation model/API specs; define nested auth and precise as-of semantics; correct legacy paths.

### P5 — Events/geo/time

**Verdict:** correct capability, incorrect storage boundary. Privacy and base-map/data-residency controls are incomplete.

**Repair:** claims-first canonical model with spatial projections; separate precision concepts; add authorization-safe tile/cache design and map privacy in the same phase.

### P6 — Search/object sets/analytics

**Verdict:** valuable, but depends on P5 under the roadmap's sequential rules and cannot call it soft. Dynamic set semantics and search post-filtering are unsafe. Alert lifecycle is too small.

**Repair:** strict dependency or explicit parallel DAG; pre-authorize search candidates; version/pin set semantics; immutable analytic run manifests; typed alert suggestions.

### P7 — Sharing/governance

**Verdict:** advanced controls belong here, foundational field/legal/retention controls do not. Informant, compartment, expungement, recipient grant, and package semantics need deeper design.

**Repair:** move minimum field/legal/retention enforcement earlier. Keep compartments, formal disclosure, break-glass, and judicial workflows here with a complete policy precedence matrix.

### P8 — Controlled AI

**Verdict:** review-queue intent is aligned, but the current queue/model cannot carry all output types and the plan governs truth promotion more than data disclosure.

**Repair:** typed producer contract, separate least-privilege runtime, approved-model/data-egress policy, source-span citations, robust multilingual held-out eval, and realistic reproducibility.

### P9 — Production

**Verdict:** too late for minimum hardening and ambiguous about upgrade delivery. DR scope is incomplete and single-host limitations are not reconciled with production claims.

**Repair:** pull minimum controls forward; define deployment tiers/SLO/RPO/RTO; make P9 a certification exercise; evaluate triggers continuously with evidence-specific rules.

## ADR-by-ADR assessment

| ADR | Assessment | Required follow-up |
|---|---|---|
| 001 Claims as primitive | Sound | Fix projection aggregation and assessment/multi-source basis model. |
| 002 PostgreSQL-first | Sound for current scale | Define benchmark workload, include auth cost, and avoid treating Neo4j as automatically primary when one query misses target. |
| 003 YAML ontology | Sound principle | Add module composition; narrow codegen ownership; correct superseded DDL claim in readers. |
| 004 Keycloak + OpenFGA | Reasonable | Purpose/legal authority are not enforced; add DB RLS defense and revocation-lag policy. |
| 005 Splink + clusters | Good adoption choice | Remove auto-merge; complete ledger/candidate schema; preserve mention attribution on claim arguments; version identity, normalization, and context snapshots. |
| 006 Modular FastAPI | Sound | Define job/process isolation for CPU work and least-privilege producer runtime. |
| 007 MinIO evidence vault | Insufficient for “immutable” | Enable Object Lock/legal hold; preserve versions/keys in DR; external integrity anchors. |
| 008 Bitemporal-lite | Acceptable only with narrower promise | Define exact as-of scope or extend identity/auth/source history. Correct stale phase reference. |
| 009 LLM suggestions | Sound | Make active runbooks comply; generalize typed suggestion envelope. |
| 010 Compose until trigger | Sound for dev/pilot | Do not equate with GOAL production HA; define deployment tier. |
| 011 Separate grading | Sound | Complete scheme maps and version source evaluations; no simplistic projection weight. |
| 012 PostgreSQL search first | Sound | Pre-filter authorization; targets now; fire upgrade in the phase that observes failure. |
| 013 App vocabulary validation | Reasonable tradeoff | Add versioned catalog/reference rows or other DB defense for non-app/restore paths; clearly distinguish vocabulary validation from typed literal storage/indexing. |
| 014 FGA outbox | Strong pattern | Revocation remains fail-open during lag; add bound, stale-state check, rebuild verification, and compartment/set tuple sources. |
| 015 Synchronous audit chain | Incomplete threat/performance model | External signed head, tail-truncation/rollback defense, concurrent-read benchmark, safe sharding/buffering escape hatch, and DB audit coverage. |
| 016 Legacy-free ontology | Good | Living ingestion/data docs still depend on legacy shapes; complete quarantine. |
| 017 Entity-or-literal predicates | Pragmatic migration bridge | Replace unresolved entity literals with explicit unresolved references before object views/ER. |
| 018 Identity tables in T8 | Historical sequencing acceptable | P2 must replace the minimal schema with a real revision ledger. |
| 019 Public open projection | Conflicts with constitution | Retire now or serve fictional static demo; do not normalize public-route exemptions. |
| 020 Python reference | Sound | Add dependency locking, performance/process model, and packaging independence from legacy. |
| 021 Foundry-informed v2 | Direction useful, scope imitative | Validate each abstraction against Aegis needs; adopt OpenAPI/JSON Schema/form generators; add actual module architecture. |
| 022 Roadmap v2 | Good structural intent | Exit-task deferrals and soft dependencies negate it; add DAG/traceability and realistic effort. |
| 023 Platform-first/replace legacy | Good goal, not yet true | Core still imports legacy and P2 extends disposable UI; add second-domain proof. |
| 024 Greenfield layout | Useful organization | Placeholder READMEs overstate future enforcement; living docs/paths remain stale; packaged core must not need unshipped legacy. |

## Assessment of the supplied external review

The additional review contained useful findings, but several explanations or proposed fixes were more absolute than the documentation supports. The following disposition is incorporated into this review rather than copied verbatim.

| Supplied finding | Disposition | Incorporated conclusion |
|---|---|---|
| Entity-resolution/claim disconnection | **Valid; new blocker (B-19).** | Raw entity IDs make merged projections stale, and merge-only canonical mapping cannot route claims after a split. Preserve mention evidence on entity-valued claim arguments and define identity-revision-aware projection/re-adjudication semantics. |
| Synchronous audit bottleneck | **Valid risk; numerical ceiling unproven.** | A single synchronous chain is a global serialization point. Benchmark before multi-user gates and define verifiable sharding or durable buffering; do not weaken read-access evidence by default. |
| JSONB loses type safety/indexing | **Partly valid.** | JSONB supports indexes, so “impossible to index” is incorrect. Semantic date/numeric/geo typing, canonicalization, and range-query strategy are nevertheless missing (H-38). Choose typed columns/table/generated projections from measured query needs. |
| PostgreSQL/OpenFGA double-bookkeeping | **Valid symptom; unsafe proposed fallback.** | Grant lag fails closed while revocation lag can produce inconsistent authorization. Version/fail closed on stale policy; never treat PostgreSQL direct membership as a fallback for a denied complex ReBAC decision unless it implements the whole policy. |
| Anonymous scraping/DoS | **Valid and already a blocker.** | B-01/B-14 cover the constitutional failure; loopback binding and rate/query/size limits are useful only as interim containment. |
| Sinhala/Tamil trigram limitations | **Partly valid and partly already planned.** | The plan already includes ICU transliteration keys, but lacks a precise, versioned normalization pipeline and early quality gate. Do not strip diacritics wholesale; test raw-script, normalized, and transliterated retrieval empirically (H-22). |
| Historical ontology versions | **Valid ambiguity; mandatory major migration already exists.** | The unresolved choice is current-only versus multi-registry runtime and how immutable old claims are superseded/aliased/interpreted, not simply whether major migrations are required (M-03). |
| Throwaway Phase 2 UI | **Valid duplicate of H-10.** | Jinja2 + HTMX is a reasonable minimal option and Spec 07 already permits it. Durable contracts and limited temporary scope matter more than mandating a framework by ADR. |

The four suggested ADRs should therefore be handled as follows:

1. **Mandatory major ontology migration:** do not add a duplicate ADR as written. Clarify or supersede the existing Spec 01/ADR-013 runtime-history contract after choosing one of M-03's two models.
2. **Typed claim value columns:** do not lock in a particular table shape before query-pattern benchmarks. Record an ADR if H-38's decision changes canonical storage; generated/indexed projections may be sufficient.
3. **Claim/mention identity routing:** accept in substance as a load-bearing ADR (or superseding amendment to ADR-005), but use the hybrid claim-argument design in B-19 rather than requiring every claim to be mention-only.
4. **Jinja2 + HTMX:** do not create an ADR merely to mandate it. It is already an allowed temporary implementation choice; promote it to an ADR only if server-rendered UI becomes a durable platform constraint.

## Adopt-before-build opportunities

These alternatives reduce custom maintenance without replacing the Aegis-specific core.

| Concern | Current/planned custom work | Prefer/evaluate | Boundary to retain in Aegis |
|---|---|---|---|
| Python/TS HTTP SDKs | Custom generators from ontology + API | FastAPI OpenAPI + OpenAPI Generator stable Python/`typescript-fetch` clients | Ontology-derived domain schemas/constants and authorization-aware examples. |
| Structural schemas/forms | Custom UI/action descriptors and form renderer | JSON Schema 2020-12 + RJSF/AJV | Semantic validation, provenance, conflict display, action policy. |
| Row authorization | Hand-appended SQL row filters | PostgreSQL RLS as defense in depth, with OpenFGA for relationships | Policy context construction, purpose/legal checks, audit. |
| Browser OIDC | Unspecified custom PKCE/session handling | `oidc-client-ts` or an established React wrapper | Aegis role/purpose UX and server authorization. |
| Vector tiles | Custom PostGIS tile endpoint | MapLibre Martin over restricted projection functions/tables | Authorization-scoped projection creation and cache policy. |
| Disclosure package layout | Custom archive/manifest | BagIt RFC 8493 plus signature/encryption profile | Aegis legal basis, handling, redaction, recipient/receipt semantics. |
| Provenance vocabulary | Bespoke envelope/link names | W3C PROV mapping | Aegis claim/evidence invariants and UI. |
| API edge-case testing | Hand-authored endpoint cases only | Schemathesis generates property-based tests from OpenAPI ([Schemathesis](https://schemathesis.readthedocs.io/en/stable/)) | Multi-user auth matrix, domain invariants, no-leak assertions. |
| Observability | Manual instrumentation everywhere | OpenTelemetry auto-instrumentation + standard exporters | Domain action/policy/projection spans and redaction. |
| Evidence immutability | Versioning + custom hash assumptions | MinIO Object Lock/legal holds + signed external checkpoints | Custody workflow, evidence metadata, policy. |
| Database audit coverage | App audit only | pgAudit as defense in depth | Semantic action/read/export audit and hash/signature checkpoints. |

Do not adopt a tool merely because it exists. Run a small spike against the authorization and sovereignty constraints. In particular, a generic tile server must never auto-publish canonical tables, and generic SDK generators do not implement Aegis authorization semantics by themselves.

## Concrete roadmap repair

### Step 0 — Documentation/governance repair before T17

1. Resolve Article VI exceptions: retire/segregate anonymous real-data routes; decide field redaction semantics.
2. Resolve Article VII: remove auto-merge, auto-accept, and `system_claim`, or amend the constitution explicitly.
3. Replace “exit boxes checked or deferred” with hard-gate semantics.
4. Publish GOAL→roadmap and constitution→feature traceability matrices.
5. Correct living statuses, paths, draft labels, Git rules, and active ingestion/backup runbooks.

### Step 1 — P2 prerequisite design

1. Finalize identity decision/revision, candidate, negative-constraint, concurrency, claim-argument mention-attribution, and canonical projection schemas.
2. Finalize typed suggestion envelope and per-kind action dispatch.
3. Add minimum legal authority/collection policy, retention class, handling inheritance, field filtering, and revocation-lag rules.
4. Finalize route-by-route authorization matrix and claim/value provenance API.
5. Define numeric ER/search/demo acceptance and fictional datasets.

### Step 2 — Correct P2 task list

Suggested additional/reworked tasks:

- **T17a:** identity ledger/candidate/claim-argument attribution schema migration and invariants, including merge/split projection tests.
- **T17b:** typed suggestion envelope and queue migration.
- **T17c:** authenticated MVP shell plus UI source landing/extraction/status.
- **T17d:** field-level filtering, public-route retirement, revocation safety.
- Move cursor pagination into P2.
- Change T18 from auto-merge to deterministic candidate generation.
- Make T19/T26 quality thresholds numeric and blocking.
- Make T27's automated gate fictional/local; add authorized real-corpus smoke test separately.
- Change T28 so no headline gate can be deferred.

### Step 3 — Rebalance P3/P4

1. P3a: ontology module composition, shared interfaces/properties, JSON Schema/OpenAPI contract, TS client generation, compatibility checks.
2. P4: durable workspace and full investigation model.
3. P3b or later: generalized functions/actions/side effects when P5/P6 provide real requirements.
4. Generate transport clients from OpenAPI; do not invent a second API schema in the ontology.

### Step 4 — Pull minimum security/operations forward

Before any non-local or non-solo use: TLS, safe secret handling, locked dependencies, body/rate limits, security headers, encrypted verified backup, MinIO Object Lock, field authorization, basic audit anchoring, and health/telemetry. Keep P9 for production certification and scale triggers.

### Step 5 — Add missing roadmap ownership

Create explicit backlog/trigger entries for retention and policy packs, source contracts/malware/signature validation, intelligence-report lifecycle, collection requirements, collaboration/review requests, privileged material, correction/challenge, originator controls, and full alert lifecycle. If these are deliberately excluded, say so in the product scope rather than leaving them as implied promises.

## Acceptance-criteria standard to apply to every future task

Each task should state:

1. **Given state/data:** fictional fixture, ontology version, identity revision, authorization roles/relationships, and service availability.
2. **Action:** exact API/UI/CLI operation and actor/purpose.
3. **Observable result:** response/state/audit/projection and maximum completion time.
4. **Negative cases:** unauthorized, malformed, duplicate, concurrent, stale-version, and partial-service failure.
5. **Data invariants:** what must remain unchanged; how rollback/replay works.
6. **Security evidence:** allow and deny tests, no existence/count/timing leak where applicable.
7. **Performance bound:** only where meaningful, with workload/hardware definition.
8. **Verification owner/artifact:** automated test, manual protocol, screenshot-free log, or signed review.
9. **Gate status:** blocking and non-deferrable, or explicitly non-blocking with target owner/phase.

Avoid acceptance language such as “works,” “correct,” “cleanly,” “realistic,” “visually distinct,” or “without tribal knowledge” unless a measurable protocol defines it.

## Final priority order

1. **Constitutional consistency:** B-01, B-02, B-06.
2. **MVP feasibility and data integrity:** B-03, B-04, B-05, B-11, B-12, B-19.
3. **Minimum security/legal/evidence baseline:** B-08, B-09, B-10, B-14, B-16.
4. **Platform architecture correction:** B-07, B-13, H-11–H-15.
5. **Operational documentation safety:** B-15 and all stale status/path/runbook findings.
6. **Measured scalability/query design:** H-22, H-37, H-38 before their first multi-user/query-heavy gates.
7. **Later-phase redesign:** B-17, B-18, P5–P9 findings.

Once the first three groups are resolved, Phase 2 can be a credible MVP gate rather than a demo assembled around hidden exceptions. The core product idea remains strong; the required work is to make the documentation obey its own principles and make each phase's task list sufficient to prove what the phase claims.
