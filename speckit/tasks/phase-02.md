# Phase 2 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them. Reference specs in parentheses. Numbering continues from Phase 1 (T16);
lettered subtasks keep the global T-numbering stable for pre-authored P3+ files.

> **Status: COMPLETE 2026-07-20 — ★ MVP GATE PASSED.** Rewritten 2026-07-18
> (ADR-033) after the external-review
> disposition (`../reviews/2026-07-18-external-review-disposition.md`). Phase 2
> closes with the **★ MVP gate** — see the charter. Gate criteria are
> non-deferrable (ADR-025). The Phase 1 closure addendum (T16a–T16d), which
> gated Milestones B–D, closed 2026-07-18 (PRs #11–#14). **Milestones A and
> B are complete** (T17a–T17d, PRs #17–#20; T17–T20, PRs #22–#26).
> **Milestone C is complete 2026-07-19**: T21 (PRs #27, #29), T22, T23a,
> T23b, T23c and T24a–T24c are complete. The Phase 2 API surface is complete —
> no route spec 06 declares for this phase is unimplemented. Milestone D T25,
> T26–T28 are complete. Exit evidence and carryovers are recorded in
> `../reviews/phase-02-exit-review.md`; Phase 3 remains inactive until its T29
> re-validation is explicitly started.

## Milestone A — Design pack (⛓ blocks B–D; specs rewritten before code) — **COMPLETE 2026-07-18**

Delivered T17a–T17d as four PRs. Specs rewritten: `../specs/05-entity-resolution.md`
(full), `../specs/02-data-model.md` §1 seams / §2 ledger / §3 + §3.1 claim
arguments / §3.2 typed envelope / §7 + §7.1 projection v2 / §8 indexes,
`../specs/04-ingestion.md` §4, `../specs/06-api.md` (full — the authoritative
authorization matrix). Design decisions taken during the pack, recorded in the
PR bodies rather than as new ADRs because none changed a chartered deliverable:
scoped (not global) optimistic concurrency on the parent revision; the anchor
requirement as an actions-layer invariant rather than a CHECK; `edge_projection`
as a table rather than a matview, since time segmentation is not a `GROUP BY`;
no `entity_draft` kind — entity creation folds into `claim_draft` acceptance;
`POST /v1/entities/{id}/split` folded into `POST /v1/identity/decisions`.

Milestone B may now start. Note that ADR-033 §2's prose enumerates the pack as
"identity ledger, claim arguments, typed envelope, projection semantics", which
reads as if T17d were projection semantics; the charter and this file agree that
projection semantics belong to T17b and T17d is the authorization matrix. The
four deliverables are unchanged — only ADR-033's wording is loose.

**T17a. ⛓ Identity decision ledger design** (ADR-028; rewrites specs/05 + specs/02 §2)
— schema for `identity_decision` (kind, actor, evidence note, inputs, parent
revision → new revision, transaction time), revision-keyed
`identity_membership` with a partial-unique **one-active-membership-per-mention**
invariant, `er_candidate` (producer, settings version, feature breakdown,
disposition), versioned negative constraints, optimistic concurrency on the
parent revision, `entity_canonical_map` as a rebuildable projection of the
ledger (cycle/tombstone rules), `merged_into` as ledger metadata (not a claim).
Migration plan from the Phase-1 tables.
AC: specs/05 and specs/02 §2 rewritten and reviewed; migration plan covers
existing one-mention clusters; reversal test *plan* enumerates multi-merge,
partial split, concurrent decision, and late-mention cases.

**T17b. ⛓ Claim arguments & projection semantics design** (ADR-029, ADR-030;
rewrites specs/02 §3 + §7) — optional `subject_mention_id`/`object_mention_id`
anchors (required for extracted/reported claims), identity-revision stamp at
`recorded_at`, projection resolution through the active revision (pinnable for
as-of), unanchored-claim rule (splits route them to re-adjudication), honest
aggregation: interval sets / time-segmented edges, support summary (grading
refs, contradiction + corroboration counts, method + version), `record_count`
naming, projection stamps (identity revision, ontology version, builder
version).
AC: specs/02 §3/§7 rewritten and reviewed; blocking-test plan covers
merge-collapse, split-restore-without-claim-rewrite, ambiguous-unanchored →
review queue.

**T17c. ⛓ Typed suggestion envelope design** (ADR-031; rewrites specs/02 queue
section) — `suggestion_kind` closed list (P2 kinds: `claim_draft`,
`identity_candidate`, `claim_relation`), per-kind payload schemas generated
from target-action parameters, producer identity/version, idempotency key,
supersession/expiry, typed result reference, acceptance dispatching through
the declared action; data migration for existing Phase-1 queue rows; the
review **inbox** defined as a UI composition over queue + `er_candidate`.
AC: spec rewritten and reviewed; every P2 kind names its target action and
result type; migration plan for live rows exists.

**T17d. Route authorization matrix & governance seams** (B-14, B-08; updates
specs/06) — authoritative route-by-route table: role gate, FGA relation,
row/field filters, purpose requirement, no-existence-leak behavior, rate/body
limits; `POST /v1/projections/rebuild` restricted to a controlled job/admin
action; generic claim-provenance endpoint for property values; nullable
governance seam columns specced (`source_record.collection_policy_ref`,
`retention_class`, authority validity fields — enforced P7).
AC: specs/06 has the matrix for every route P2 ships; each row names its
tests; seam columns in the T18 migration plan.

## Milestone B — Identity core — **COMPLETE 2026-07-19**

Delivered T17 (PRs #22, #23), T18 (#24), T20 (#25), T19 (#26). Milestone C may
now start. T20 was taken **before** T19 because both T18's and T19's remaining
acceptance criteria depend on `adjudicate_identity` and its negative
constraints; no chartered deliverable changed, only the order.

T17 ships as two PRs, matching the two halves of its title: the **ledger
migration** (schema, baseline, envelope, seams) and then **mention extraction
& backfill** (offsets/script/language, entity folding, claim anchors). The
migration must land first because the extraction writes into its columns.

**T17. ⛓ Ledger migration + mention extraction & backfill** (specs/05 §1–2) —
implement the T17a/T17b/T17c/T17d schemas in one Alembic series; populate
`mention` rows (raw_text, norm_key, offsets, language/script when known —
H-06 minimum) from existing and newly landed source records; verify the legacy
one-mention clusters as revision 0 of the ledger; backfill claim
identity-revision stamps.
AC: migrations up/down clean; every entity has ≥ 1 mention; one-active-
membership invariant enforced by the DB; idempotent re-run; Phase-1 tests
green on the new schema.

**COMPLETE.** *Mention-extraction half landed*: extraction persists mentions
(with offsets where the name is verifiably a span, and ISO 15924 script),
`aegis.er.normalize.norm_key` replaces the prototype's `slugify` — which folded
every Sinhala and Tamil name to the literal `"unknown"`, so all of them shared
one blocking key — entity creation folds into `claim_draft` acceptance, the
ADR-029 anchor requirement is enforced in the actions layer, legacy claims are
anchored where their mention is in the claim's own record, and
`aegis identity backfill-anchors` handles the rest heuristically, reporting
what it left unanchored.

*Ledger-migration half landed* (`0007_identity_ledger.py`). Decisions taken
while implementing: the T17d governance seams ship here rather than in T24a,
since T17 owns the single Alembic series and T24a then has nothing to migrate;
retiring `merged_into` is a **major** ontology change under specs/01 §4
(`0.4.0 → 1.0.0`, prior file archived), not the minor bump specs/05 §7 first
said; `new_id` moved to `aegis/actions/ids.py` to break the import cycle
`actions → er.ledger → actions`; `identity_candidate` acceptance raises an
error naming T20 rather than silently accepting, because a kind no code path
can accept is the exact Phase-1 defect ADR-031 exists to remove.

**T18. Deterministic ER → pre-verified candidates** (specs/05 §2.1, ADR-027) —
rule engine emitting **candidates** (never merges) for exact registry
identifiers (NIC when lawfully present, vehicle registration + jurisdiction,
passport + country) with issuer/validity conflict checks (H-07);
same-norm_key-within-one-document also a candidate, ranked top-of-queue with
`producer='rule:<name>'`; batch-confirm flow specced for the adjudication UI.
AC: a fixture NIC pair produces a pre-verified candidate, not a membership
change; confirming it in one human action creates a ledger decision with the
human as `decided_by`; cross-document same-slug never lands above the
pre-verified band.

*Candidate-generation side landed* (`aegis/er/rules.py`, `aegis/er/settings.py`,
`aegis identity run-rules`). Decisions: the engine names no identifier — it
iterates predicates the ontology declares `identifier: true`, so the core stays
domain-neutral (Article XIV) and the ontology gains that flag plus `has_nic`,
`registered_as`, `reachable_on` as an additive **1.1.0** bump. **Passport rules
are not implemented**: the ontology declares no passport property, and adding
domain vocabulary without a competency question belongs in the P3 proposal
process, not in a rule engine. Issuer and validity conflict checks (H-07) read
the claim's existing `jurisdiction` and `valid_from`/`valid_to` rather than new
columns. Rule candidates carry `score = NULL` — a fabricated 1.0 would be
indistinguishable from a model that was certain.

**The second AC clause — "confirming it in one human action creates a ledger
decision" — is T20's**, since `adjudicate_identity` lands there. T19's AC ("a
rejected pair is never re-emitted") depends on T20's negative constraints the
same way, so **T20 is implemented before T19**; the rule engine's suppression
path is already proven against a hand-written constraint. No chartered
deliverable changes, so no new ADR — only the order within Milestone B.

**T19. Splink pipeline** (specs/05 §2.2) — DuckDB backend; transliteration-aware
features (ICU Latin key + raw-script key, Jaro-Winkler + token-set, alias
cross-match, affiliation overlap, DOB conflict as negative evidence);
graph-context feature computed from a **versioned projection snapshot**
recorded with each run (H-07); blocking rules; candidates above threshold land
in `er_candidate` with per-feature waterfall weights; settings versioned in
`aegis/er/settings.py`; negative constraints consulted before emission.
AC: the seeded Sinhala/English transliteration pair scores above threshold with
per-feature weights persisted; a rejected pair is never re-emitted; the run
records its settings version + graph snapshot id.

**COMPLETE** (`aegis/er/splink_job.py`, `features.py`, `translit.py`). The
seeded pair scores **0.963** against a 0.80 threshold while the hard negative
is not proposed at all. Decisions: **PyICU is not a dependency** — it would
romanize better, but its wheels are unreliable on the platforms this runs on,
so `unidecode` + `jellyfish` metaphone are used and §6's harness decides
whether that is good enough; the raw-script key is kept alongside the Latin one
so a lossy romanization cannot manufacture agreement invisibly. **Weights are
declared, not trained** — EM on a corpus this size converges to whatever the
corpus contains and would be neither reproducible nor explainable, so every
level carries an explicit starting probability versioned in
`aegis/er/settings.py`. Ontology **1.2.0** adds `born_on`: date of birth is a
comparison level rather than an identifier rule, because agreement is weak
evidence while a conflict is strong. The graph snapshot id is a content digest
of the association graph, so it moves when the graph does.

**T20. ⛓ Adjudication actions over the ledger** (specs/05 §3) —
`confirm_match`, `reject_match`, `split_entity`, `mark_unresolved` as
`adjudicate_identity` (evidence note required; dual-control hook honored);
each decision creates a revision with optimistic concurrency; rejects write
negative constraints; single transaction with audit; `entity_canonical_map`
rebuild hook.
AC: merge → intervening claim edits → split restores mention-attributable
state exactly; a decision against a stale revision is rejected and
re-presented; every decision carries a human actor + note in audit.

**COMPLETE** (`aegis/er/adjudication.py`, `aegis/er/canonical.py`,
`ActionService.adjudicate_identity`). All seven reversal cases of specs/05 §8
are green. Decisions taken: split re-adjudication queues a **`claim_draft`**
carrying `supersedes`, not the `claim_relation` kind specs/02 §3.1 originally
named — `link_claims` records corroborates/contradicts and cannot express
"this claim belongs to the other entity", while a draft can and satisfies
rule 5 by construction; specs/02 §3.1 is corrected accordingly. The ontology's
`roles` and `dual_control_for` are now enforced at the write via
`ActionContext.roles` / `second_actor`, closing the gap specs/05 §3.4 named.
A split that moves every mention is refused as a rename. The canonical map is
rebuilt by replaying decisions in revision order rather than reading current
memberships — only the replay stays deterministic when a merged entity's
mentions are later scattered across a split.

## Milestone C — Workspace & governed UI loop — **COMPLETE 2026-07-19**

**T21. ⛓ Projection rebuild v2 + "why connected?" API** (ADR-029, ADR-030;
specs/06) — `edge_projection` resolves entity arguments through the active
identity revision; time-segmented aggregation; support summary; projection
stamps; core stops importing `legacy.pipeline.clustering` (H-36 — move/vendor
Leiden into `aegis/analytics/`); why-connected endpoint returns the claims,
gradings, sources, relations, and the identity-decision line behind any edge.
AC: merge collapses nodes/edges and split restores them with zero claim-row
rewrites (blocking test); a disjoint-interval fixture yields segmented edges,
not one continuous edge; every edge resolves to ≥ 1 source record; `aegis`
package imports nothing from `legacy.*`.

**COMPLETE.** T21 shipped as two PRs, matching the two halves of its title:
the **rebuild** (#27) and the **why-connected API** (#29).

*Rebuild half landed* (migration `0008_edge_projection_v2.py`,
`aegis/projections/edges.py`). The Phase-1 materialized view is replaced by a
table, because one row per maximal interval is not a `GROUP BY`.

Two latent bugs surfaced, both found by the §7.1 blocking cases rather than by
review, and both fixed here:

- **Symmetric predicates did not collapse on merge.** Symmetric arguments are
  order-normalized at *write* time, but identity resolution happens later and
  can reverse a pair — so after a merge, two claims describing one undirected
  edge pointed opposite ways and projected as two mirror-image edges. The
  builder re-normalizes after resolution.
- **`_unattributable_claims` (T20) missed most of what rule 4 covers.** It
  scanned only the subject side for the split entity's literal id, so it
  silently found nothing for claims naming the entity as their *object*
  (≈ half of them, given symmetric normalization) and nothing at all in the
  merge-then-split case — where the claim names the **absorbed** id, not the
  survivor. It now covers both argument positions and every id resolving to
  the split entity; the queued draft repoints whichever end named it.

Decisions taken while implementing: resolution goes **through the mention
anchor first**, falling back to `entity_canonical_map` only when unanchored —
the anchor is what makes a split *restore* edges rather than merely add new
ones, and the map alone cannot follow a split (specs/02 §7 updated); `edge_id`
is a **content digest**, so a rebuild is idempotent in identity as well as
content and two builds are diffable; the SQL `projection_weight()` is dropped
while `handling_code_rank()` stays, since the v2 builder and the row filters
both key off it; the display weight survives only in the legacy emitter, which
is where ADR-030 wants a display score — computed from visible claims, at the
point of rendering.

`new_id` moved again, from `aegis/actions/ids.py` to **`aegis/ids.py`**: T17's
split did not actually break the `actions → er.ledger → actions` cycle, because
importing `aegis.actions.ids` still executes the package `__init__`. The cycle
stayed latent only because `actions` happened to be imported first, and
importing `aegis.projections` first tripped it.

**Legacy severance (H-36).** `clustering.py` (Leiden) → `aegis/analytics/`,
`neo4j_export.py` → `aegis/projections/cypher.py`; the exporter's layer
whitelist was a legacy `LayerType` enum and is now a **structural** identifier
check, which is domain-neutral (Article XIV) and strictly stronger. The AC as
written — "imports nothing from `legacy.*`" — is met for everything ADR-023
does not exempt; the two survivors are the one-time migration adapter and the
governed wrapper around the prototype extraction passes, which ADR-023 exempts
by name and `legacy/README.md` schedules against later work (extraction v2).
Rather than narrow the AC in prose, `tests/component/test_core_independence.py`
enumerates both exemptions and fails on any third, and separately forbids
`legacy` imports anywhere under `projections/` or `analytics/` — so the H-36
finding itself can never be re-covered by a future exemption. The dependency
arrow is also inverted: `legacy/` entry points now import the vendored modules
from `aegis`, never the reverse.

*Why-connected half landed* (`aegis/queries/provenance.py`,
`aegis/api/routes/provenance.py`). Three routes: `why-connected/{other}`,
the **generic** `claims/{id}/provenance` (B-14 — property values need
provenance too, not only edges), and `entities/{id}/identity-history`.
Decisions: authorization conditions are pushed **into** the query rather than
filtering the response, so the counts and identity line are computed over
exactly what the caller may see — a panel reporting evidence it then refuses to
show would leak the claims' existence; the edge is **undirected** and resolves
through the canonical map, because a claim written before a merge names the
absorbed id and asking about the survivor would otherwise answer "no evidence"
for an edge the graph is actively drawing; `contradiction_count` counts
**distinct relations**, since two claims contradicting each other are one
disagreement; and the 200-claim cap is disclosed as `truncated` so a thin panel
is never mistaken for thin evidence.

**Test-suite performance (found during T21, fixed in #28).** The integration
suite took **1:59:59** locally against 52s on Linux CI. On Windows `localhost`
resolves to `::1` first while the compose ports publish IPv4 only, so every
connection waited ~2s for the IPv6 attempt to fail: **2.05s per connection
against 0.01s via `127.0.0.1`**. Local defaults moved to the literal loopback
address and the same 244 tests now run in **37s** — no test changed.
`keycloak_url` is a named exception: it is the OIDC *issuer identity* and must
match the `iss` claim Keycloak mints, so an IP there 401s every request.
`tests/unit/test_config_defaults.py` guards both halves.

**T22. ⛓ Workspace shell + legacy retirement** (ADR-032, ADR-026; specs/07) —
`ui/`: React 18 + TypeScript + Vite; Keycloak OIDC PKCE via
`oidc-client-ts`/`react-oidc-context` (tokens in memory, no localStorage;
logout + refresh handled by the lib); OpenAPI-generated typed client (stable
operation IDs added to FastAPI routes); app layout (nav, auth guard, error
envelope handling); CSP + security headers on the serving path; CI:
type-check + build + one smoke e2e. **Same change:** legacy explorer,
`/api/*` routes, and the `public_route` lint exemption deleted; graph view
(Cytoscape-in-React) reads `/v1/graph/*`.
AC: unauthenticated visit → login redirect → authenticated shell; graph
renders from governed routes; repo grep finds no `public_route` marker and no
`legacy/app` serving path; UI CI job green.

**COMPLETE.** All four AC clauses verified against the live stack, not only
against stubs: a real browser reached Keycloak, signed in as `dev-analyst`, and
returned to a shell that drew the graph from `POST /v1/graph/expand` with a real
bearer token, no CSP violations, and nothing in web storage.

*Governed graph routes* (`aegis/queries/graph.py`, `aegis/api/routes/graph.py`).
`expand` and `paths` replace the anonymous bulk dump. Decisions:

- **Authorization is a correlated `EXISTS` over `claim_filters`, not a filter on
  `edge_projection.handling_rank`.** The stored rank is the *maximum* over
  supporting claims, so filtering on it would hide an edge whose open claim the
  caller is entitled to see. The support summary is then rebuilt from the
  visible claims only — via the builder's own `support_summary`, so the graph
  view and the provenance panel cannot drift apart — and the corroboration and
  contradiction counts are recomputed over visible relations. That last part has
  a cost worth naming: a contradiction the caller may not read is invisible, so
  an edge can look less contested than it is. specs/03 §4 and specs/07 §5
  already chose absence over teasing, and P7's marked-redaction mode (H-25) is
  where it gets revisited.
- **Empty seeds are a distinct mode, not an error**: the *bounded overview*,
  capped by the same element budget as any expansion. The canvas needs a way to
  open before entity search exists (T23c), and a bound is what separates an
  overview from the surface ADR-026 retired.
- **`paths` returns shortest routes only.** "Every route under five hops"
  between two well-connected people is a combinatorial answer no reader can
  audit, and an unauditable path is machine-produced insinuation (Article IX).

Two defects were caught by their own tests rather than by review. The element
budget was applied to *edge rows* in the overview and to *nodes + edges* in the
walk, so `max_elements=2` returned six elements from the one mode that exists to
be bounded — both now share a `_Budget`. And the SPA fallback answered every
unmatched path with `index.html`, turning a call to a retired `/api/*` route
into HTML with status 200; API prefixes now never fall back, and `/api` stays
reserved so it keeps 404-ing forever.

*Legacy retirement.* `legacy/app/` deleted, `/api/*` deleted, `public_route` and
its lint branch deleted — `find_ungated_routes` now has no exemption to grant,
and `test_route_gating.py` fails if the symbol returns. The one thing served
without a token is the workspace *bundle*: a static mount with no dependency
graph and no database access, which the lint structurally cannot inspect, so the
same test pins it as the only mount the app may carry. T16a's per-IP rate limit
died with the routes it contained and was replaced by a **per-caller default on
every route**, keyed on a digest of the bearer token — the `sub` inside it is
attacker-chosen until the gate validates it, and the limiter runs first.

*Workspace* (`ui/`). Vite + React 18 + TS, `openapi-typescript` + `openapi-fetch`
against a committed `ui/openapi.json`, so the UI build needs no running API and
`tests/contract/test_openapi.py` can fail on drift. Every route gained an
explicit camelCase `operation_id`: FastAPI's default embeds the Python function
name, so an ordinary refactor would silently rename a client method.

Three things the live-stack verification found that no stub could:

- **Keycloak realm scopes.** This realm's `clientScopes` list *replaces*
  Keycloak's built-ins, so `profile` and `email` do not exist in it and the
  conventional `scope: "openid profile email"` failed the entire authorize
  request with `invalid_scope`. The workspace asks for `openid` alone; every
  claim it reads is minted by the `aegis` scope's mappers.
- **Token clock skew.** The dev stack's Keycloak container runs ~2s ahead of the
  host, and `jwt.decode` allowed zero leeway, so freshly minted tokens were
  rejected as "not yet valid". Zero leeway looks stricter but only means the
  platform stops working whenever the IdP is a different host (RFC 7519
  §4.1.4); validation now allows a configurable 60s.
- **React effect ordering.** Handing the token down from a provider effect put
  it in place *after* the first query had already fired, because child effects
  run before parent effects — every initial request went out unauthenticated.
  The API client now asks the `UserManager` for the token per request, which
  also means a silently renewed token is used immediately.

The smoke journey (`ui/e2e/`) runs against the built bundle under a copy of the
production CSP, stubbing Keycloak and the API at the network boundary so
`oidc-client-ts` still runs its real PKCE state machine. It is deliberately not
the demo loop: that is T25/T27's blocking gate against a live stack.

**T23a. Source landing & extraction UI** (B-04; specs/04) — upload/paste with
required provenance fields, source picker/creation, landing status
(landed/quarantined + reason), derivative + extraction progress (sync or job
status — decided here), idempotent re-upload feedback ("already landed"),
quarantine release for supervisors, extraction trigger per record.
AC: browser e2e — land a fixture PDF and a pasted text from the UI, see
suggestions appear in the queue; re-upload shows the no-op; quarantined
fixture shows its reason; every action authorized + audited.

**COMPLETE.** All AC clauses verified: the Playwright journey lands a PDF and a
pasted note, extracts, and reads the queued count back from `/v1/review-queue`;
re-uploading identical bytes reports `already_landed` and the register does not
grow; a same-name/different-bytes upload shows its version-conflict reason and
offers release instead of extraction. Authorization and audit are proven in
`tests/integration/test_ingest_routes.py` (29 cases), and the whole chain was
run against the live stack — real MinIO, real PostgreSQL — through the CLI.

*The derivative stage did not exist.* This is the gap the task's own AC
exposed: `aegis ingest extract` refused anything that was not `text/*` with
"produce a text derivative first", and nothing had ever written the
`derivative` table, so "land a fixture PDF … see suggestions" was
unreachable. `aegis/ingestion/derivatives.py` implements spec 04 §1 stage 3 —
written natively rather than by importing `legacy.pipeline.pdf_loader`, because
the quarantine is replaced, never extended (ADR-023). Two refusals are
deliberate: an unregistered media type is named rather than guessed at, and a
PDF with no text layer says it needs OCR rather than running a pass that
proposes nothing and blames the extractor.

*Synchronous, bounded — ADR-034.* The task said "sync or job status — decided
here". Synchronous, because P2 has no worker and a job queue buys a status
model, a retry policy and a stuck-job state in exchange for latency nobody
feels yet. What makes that safe is two bounds with two meanings that were worth
not collapsing: `ingest_oversize_bytes` **quarantines** (the artifact lands and
is withheld — spec 04 §3), `ingest_max_bytes` **refuses** `413` (we will not
buffer it). Quarantine reasons accumulate, so fixing one and re-landing does
not reveal the next.

*The fixture PDF is generated, not committed.* `*.pdf` is gitignored repo-wide
and AGENTS.md forbids committing binaries, so `tests/support/pdf.py` writes a
real 996-byte PDF — correct xref table, standard-14 font — whose text
round-trips through pdfplumber exactly. It is readable as source, which is how
a reviewer checks it against the data-ethics rubric instead of taking a binary
on trust. ALPHA and BRAVO overlap at one facility and CHARLIE is held
elsewhere, so "1 suggestion" asserts the co-location *rule* rather than a row
count.

*`GET /v1/ontology/vocabulary` (specs/06 §2.7)* was added because the intake
form needs handling codes and source types, and writing either into the bundle
would have created a second domain artifact that keeps working, and keeps being
wrong, after the ontology moves (Article XI). Its test compares against the
loaded ontology, not a literal, for the same reason.

Two defects came from the work's own tests rather than review. The signin
callback rewrites the URL with `replaceState`, which fires no event — so the
app, having mounted at `/auth/callback`, rendered the *fallback* view at the
right address; every sign-in ignored where the user was going. That is the same
shape as T22's token-ordering bug: state changed outside React's knowledge.
And the first layout put the outcome banner under a seven-field form, where the
one piece of feedback this screen exists to give fell below the fold; it now
sits above the register, next to the record it produced.

The visual rule the screen establishes: **only the exceptional state is
marked**. A left rail means "this needs you" — the same device already used for
a graph notice — and an ordinary record keeps the geometry without the colour,
so a mark still means something. Quarantine uses caution bronze, never a
failure colour: a governance hold is not an alarm (spec 07 §5).

**T23b. Review queue & adjudication UI** (ADR-031; specs/04 §4) — **COMPLETE
2026-07-19** — typed inbox (queue + `er_candidate`), filters by
kind/producer/status/document; accept / edit-then-accept / reject with reason;
assertion-type picker on accept (plan §4.2); producer metadata (model, prompt
hash, rule, score waterfall) rendered per kind; identity candidates:
pre-verified batch-confirm flow + full waterfall view; bulk-reject for
hallucinated entities.
AC: a Gemini-pass suggestion accepted in the UI appears in the rebuilt
projection and a rejected one never does; a Splink candidate is confirmed
end-to-end from the browser and the graph reflects the merge; batch-confirm
writes one human-actored decision per pair.

Like T23a, the UI task exposed a missing layer under it. `adjudicate_identity`
had shipped in T20 as an *action* and nothing exposed it over HTTP, so spec 06
§2.2's three routes existed only on paper — the AC's "confirmed end-to-end from
the browser" was unreachable. They are implemented here to the matrix as
written, so no ADR: `GET /v1/identity/candidates`,
`POST /v1/identity/candidates/batch-confirm`, `POST /v1/identity/decisions`.

Three design points settled in the building:

- **The decision body is a discriminated union, not a bag of optional fields.**
  The modes genuinely differ — only reject carries an `evidence_basis`, only
  split names an entity and the mentions leaving it — so the OpenAPI document
  says which arguments a mode takes instead of leaving each client to discover
  it by 422.
- **The candidate listing reports the revision it was read at.** A decision's
  `parent_revision_id` is meant to be *the state the analyst was looking at*;
  fetching it from a separate lookup would let a client send a revision newer
  than the screen it decided from, which is the exact race spec 05 §2 exists to
  catch. That envelope is also what T24c's cursor will need.
- **`assertion_types` joins the vocabulary route.** It is platform epistemics
  rather than ontology vocabulary (Article XIV), so it comes from a code-owned
  constant — but it still must not be a second copy in the bundle.

Two defects the tests found. A stale-scope conflict surfaced as **422 with the
intervening decisions flattened into a string**, because the service wrapped
every `AdjudicationError` into `ActionValidationError`; spec 06 requires 409
with them in the body, and the existing test could only assert on substrings
because the structure had already been destroyed. `StaleRevisionError` now
propagates and snapshots its decisions rather than holding ORM rows — it is
raised exactly when the transaction that loaded them is rolling back. And the
batch-confirm result was owned by the panel that produced it, so confirming the
last pre-verified pair emptied the band, unmounted the panel, and took the
result banner with it: the reviewer clicked Confirm and saw nothing.

The rule the review screens add to T23a's: **only the exceptional state is
marked** extends to evidence, not just status. A candidate's waterfall runs in
both directions from a centre line, because a Bayes factor below 1 argues
*against* the match — a one-directional bar would show only the half that
agrees, and a single score would hide the disagreement entirely. Bronze for the
column that argues against, never the failure colour: it is a judgement about
evidence, not something that went wrong.

**T23c. Provenance panel, contradiction surfacing & entity search** (specs/06,
ADR-012 minimal) — edge/node click opens the why-connected panel (all three
grading dimensions per claim, sources, contradiction/corroboration badges;
conflicting property claims render side by side — Article VIII);
`GET /v1/search/entities?q=` with `pg_trgm` over names/aliases/mention
norm_keys, authorization-filtered, cursor-paginated; search box focusing the
graph.
AC: every rendered edge opens the panel; seeded contradictory DOB claims both
render with a visible `contradicts` badge; a transliterated query variant
finds the seeded entity; results respect handling + case filters.
**COMPLETE 2026-07-19.**

Two spec-declared routes were missing under this task, and one was wrong.

`GET /v1/search/entities` and `POST /v1/projections/rebuild` were both declared
in spec 06 and unimplemented — the last two on the Phase 2 surface. A route diff
against the live app found them; the four other unimplemented rows are deferred
by the spec's own non-goals (analytics and findings promotion are P6, exports
P7) and were left alone rather than built ahead of their phase gate.

The wrong one was `GET /v1/entities/{id}`, which filtered on `subject_id`
without resolving through the canonical map while `why_connected` resolved and
documented why. After any adjudicated merge, claims written against the
absorbed id vanished from the surviving entity's own detail view — evidence
lost to a merge, which Article V exists to prevent. Fixed with the same
resolution `why_connected` uses (ADR-036).

Three design points settled in the building:

- **The contradiction AC belongs to a node, not an edge.** "Conflicting property
  claims render side by side" is about two dates of birth, which are a property
  of one entity; `why-connected` answers about a *pair* and has no node
  equivalent. So the panel has two modes over two routes, and the node mode
  needed `GET /v1/entities/{id}` to carry claim relations at all — it returned
  grouped claims with no way to know the store recorded them as contradicting
  (ADR-036). Grouping is what puts them side by side; `contradicted_by` is what
  lets the badge exist.
- **Selecting a node opens its claims instead of re-seeding the canvas.** T22
  wired node clicks straight to the seed, so clicking to read re-laid out the
  graph under the reader. Focusing is offered inside the panel instead, which
  keeps it a decision rather than a side effect. An e2e case pins it.
- **"1 concurrent" is a lock, not a rate limit.** Spec 06 §2.6 caps the rebuild
  at one at a time. The risk is not request volume — the rebuild is idempotent,
  so two produce the same table — it is two full scans of the claim store
  contending over the same rows, which an admin triggers by double-clicking. A
  transaction-scoped Postgres advisory lock refuses the second with 409 and
  releases on rollback, so a failed rebuild cannot wedge the route.

*Search.* Delivered against ADR-035's stored transliteration keys. Ordering is
deterministic (`-score, label, entity_id`) so T24c can add cursors without
changing what the route returns. Cursor pagination itself is T24c's row, which
names search among the routes it covers, so it is not duplicated here.

**T24a. Field-level sensitivity filtering** (specs/03 §4; hard gate) —
property `sensitivity` from the ontology enforced on every read path (absent,
not marked — the P7 marked-redaction mode is a different, later policy);
governance seam columns from T17d land in the schema.
AC: a `sensitivity: restricted` property is absent for a low-clearance caller
on every shipped route (matrix test); no count/existence leak; seam columns
exist and are nullable.

**T24b. Authorization matrix tests** (T17d; specs/06) — the matrix becomes an
executable test suite: (role × handling × membership × field-sensitivity) per
route, allow and deny cases, 404-on-unauthorized single GETs, rebuild
restricted; the deny-by-default lint runs with zero exemptions.
AC: matrix suite green in CI; lint green with the exemption branch deleted;
a seeded restricted row proves strict-subset search behavior (M-13).

**T24c. Cursor pagination** (specs/06 conventions; M-12) — ULID-ordered cursor
pagination + deterministic ordering on queue, search, entities, audit list
routes.
AC: stable iteration under concurrent inserts; UI list views page correctly.

**COMPLETE 2026-07-19.** Field sensitivity is enforced where claims enter a
read query, so an over-clearance property disappears together with its value,
relations, provenance, graph support, search candidacy and counts. Identifier
predicates resolve sensitivity from their subject type's ontology-declared
identifier property; a type whose display title is restricted is omitted
rather than returned as an id-shaped hint. Review suggestions and ER candidates
apply the same rule before pagination. The T17d governance columns remain
nullable and inert as designed, but landing now stores and returns collection
policy, retention class and legal-authority validity in those columns and the
workspace displays them.

The authorization matrix is executable at two layers: a contract test pins the
role and purpose policy for all 37 shipped operations with no unlisted route,
while PostgreSQL integration cases exercise handling, membership, retraction,
field sensitivity, 404/no-count behavior and the admin-only rebuild. Opening a
case now enforces the matrix's previously documentary purpose requirement.

All P2 collections named by spec 06 use opaque route-scoped keyset cursors:
review queue, identity candidates, entity search, sources, source records and
audit. Each request rebuilds authorization filters; no cursor carries authority
or total count. Ordering keeps the ULID as its final tie-breaker, the
source-record regression inserts a row between pages to prove stable iteration,
and the workspace's queue, candidate, search and record lists expose bounded
"Load more" flows. No ADR was needed: the implementation follows specs/03 and
06 without changing a load-bearing decision.

## Milestone D — MVP close-out

**T25. Fictional demo fixture** (H-09) — deterministic, fully local fixture
corpus (`data/sample/mvp/`): documents seeding known entities, a
transliteration pair, a distinct same-name pair, a contradiction, a restricted
field, and a quarantine case; loads via `aegis ingest` in one command; reset
path (restore baseline, rebuild projections).
AC: fixture load → demo loop is reproducible offline with no hosted-model
dependency (extraction runs structural pass; a cached LLM-output fixture
exercises the semantic path); CI smoke runs the loop headlessly.

**COMPLETE 2026-07-19.** `data/sample/mvp/` is a ten-document, manifest-driven
fictional corpus loaded by one `aegis ingest mvp` command. It carries the
Sinhala/English Nimal Perera pair with corroborating fictional evidence, two
distinct Ruwan Silva records with conflicting identity features, two preserved
DOB claims for one Maya Fernando entity linked as `contradicts`, an open row
whose `has_nic` property is ontology-restricted, deterministic structural and
semantic suggestions, and an intentional same-filename version conflict that
lands quarantined. No artifact represents a real person or event.

The semantic cache is not the old hard-coded mock. It is a validated
`aegis.cached-semantic/v1` envelope containing the model label, the exact
prompt digest and the structured result. Prompt drift fails rather than
quietly replaying an answer produced for different instructions; the review
queue visibly labels the producer `cached:*` and vaults the exact cache bytes.
Machine outputs still stop at `suggested` — the headless smoke accepts one
structural suggestion as `user:mvp-reviewer`, then rebuilds the canonical map
and edge projection and proves the claim appears.

`aegis ingest mvp --reset --yes` restores revision 0 and rebuilds empty
projections only on a loopback database containing fixture-only records,
sources and no cases. It refuses mixed state and points the operator to the
governed backup/restore path instead of selectively deleting canonical or
audit history from a real store. The loader itself is fully idempotent. CI
runs the seven-case PostgreSQL smoke explicitly via `make test-mvp`; the T27
browser-driven gate remains the next consumer of this corpus. No ADR was
needed: T25 implements H-09 and the existing ingestion/review decisions.

**T26. ER evaluation harness with numeric gates** (specs/05 §5; H-08) — golden
set (fictional: transliteration pairs incl. Sinhala script, hard negatives,
common names, missing fields); CI computes pairwise precision/recall and
review-load (candidates per 1,000 mentions); **blocking thresholds recorded in
the spec at first passing run** (starting floor: precision ≥ 0.95 on
pre-verified rules, recall ≥ 0.7 on the seeded transliteration set; tune with
evidence, change only with the eval diff); Splink settings changes show their
eval results in the same PR.
AC: CI publishes the numbers and fails below threshold; the seeded distinct
pair stays unmerged in the full pipeline run; no real-person identifiers in
CI fixtures.

**COMPLETE 2026-07-20.** `aegis identity evaluate` validates the versioned
`aegis.er-golden/v1` corpus and calls the same pure identifier matcher and
Splink scoring boundary as the live producers. The first passing
`rules-v1`/`splink-v1` run records **1.000 pre-verified precision** (1 TP,
0 FP), **1.000 seeded transliteration recall** (2/2), and **33.33 candidates
per 1,000 mentions** (2 candidates over 60 mentions), against the ratified
0.95 / 0.70 / 50 gates in spec 05 §6. The corpus includes the Sinhala/English
Nimal pair, a second spelling/transliteration pair, distinct common-name Ruwan
Silva records with conflicting DOBs, missing optional fields, and deterministic
hard negatives. Every identifier is an obvious `FIXTURE-ID-*` placeholder and
the schema refuses any other identifier value.

`make test-er-evaluation` writes `output/er-evaluation.json`, asserts success,
failure and schema-drift paths, then runs the PostgreSQL full-fixture regression
proving both Ruwan mentions remain in distinct active entities and that no
identity decision is written. CI uploads the report on success or failure and
then runs the complete integration suite. No settings change or ADR was needed:
T26 ratifies the existing spec 05 floors and `splink-v1` behavior with numeric
evidence.

**T27. MVP demo runbook + real-corpus smoke** — `docs/MVP_DEMO.md`: scripted
walkthrough of the full loop **on the T25 fixture** (the ★ gate); separate
appendix: authorized real-OSINT manual smoke (operator-run, no captured
sensitive output, provider/egress notes, cleanup path).
AC: a person who didn't build the system completes the fixture loop in one
sitting following only the document; the real-corpus smoke is documented as
manual and non-blocking; drift between doc and product fails the phase review.

**COMPLETE 2026-07-20.** `docs/MVP_DEMO.md` is a 30–45 minute operator path on
a disposable database. A fresh browser run against the served production
bundle landed `remand-register.txt`, ran structural extraction, accepted its
proposal as a named analyst, switched to the local admin, rebuilt one edge,
and observed the graph refresh. The same run loaded the rest of the T25 fixture,
adjudicated the Sinhala/English Nimal candidate at 0.99, rebuilt at identity
revision 1, found one Nimal result and two distinct Ruwan Silva results. The
runbook separately checks the Maya contradiction, restricted-field absence,
and three-dimensional edge provenance.

The live role handoff found that an existing Keycloak volume could sign in but
rejected the bare-origin post-logout redirect. The realm now declares exact
bare origins beside its callback URIs, and `infra/bootstrap.sh` idempotently
synchronizes the browser client because Keycloak realm import is create-only.
The graph also had no UI path to its already-shipped admin rebuild route;
`GraphView` now gives only an admin a rebuild action, reports the exact build
stamp, and refetches the graph. Hermetic browser cases pin both the analyst
absence and admin success/refresh paths; the contract suite pins the runbook's
commands, labels, roles, fixture expectations, cleanup, logout origins, and
manual real-data boundary. The OSINT appendix is explicitly manual,
non-blocking, local-structural by default, no hosted egress, no captured
sensitive output, and requires cleanup. No ADR was needed: both fixes make the
workspace conform to ADR-032 and the existing admin-only route matrix.

**T28. Phase exit review** — walk the charter's gate criteria (non-deferrable,
ADR-025); verify the constitution-conformance spot-check (Articles VI/VII
tests); update speckit docs where reality diverged; append ADRs for changed
decisions; write `../reviews/phase-02-exit-review.md`.
AC: every gate criterion checked; non-blocking deliverables carried over with
owner + target phase recorded; statuses updated everywhere (M-01).

**COMPLETE 2026-07-20.** The Phase 2 exit review checks all five
non-deferrable charter criteria and all fourteen constitutional articles,
with named Article VI/VII tests and the T27 live operator record. No gate is
deferred. The review records the manual real-OSINT smoke, P7 governance-seam
enforcement, P8 legacy extraction retirement, and the independent pilot gate
with explicit owners and targets; none is a hidden Phase 2 criterion. Reality
matches ADR-025…ADR-036, so no new ADR was required. Status surfaces now mark
Phase 2 complete and Phase 3 ready for—but not yet in—T29 re-validation. The
package advances to 0.2.0 and the merged review is tagged `phase-2-mvp` under
the repository release workflow.

## Explicit non-goals for Phase 2

Object views/cases/hypotheses/timeline (P4), ontology modules/interfaces and
the ontology-generated SDK (P3 — P2 uses the OpenAPI-generated client),
PostGIS geometry and events (P5), full multilingual FTS, object sets and
watchlists (P6), compartments and disclosure packages (P7), new LLM
capabilities beyond the existing extraction producers (P8), UI polish beyond
function (P4).
