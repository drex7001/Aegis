# Spec 08 — Ontology v2: module composition, semantic layer, actions v2, change management, contracts

Status: **final for Phase 3 (T29, 2026-08-17)** — re-validated against the
Phase 2 as-built system, narrowed by ADR-033, and amended by ADR-037…040. ·
Constitutional basis: Articles VII, X, XI, XII, XIV · GOAL.md §7.8–7.10 ·
ADR-021, ADR-027, ADR-033, ADR-037, ADR-038, ADR-039, ADR-040 · Extends
spec 01 (which remains the v1 reference for every section this file does not
change)

## 0. What changed at finalization (T29)

The draft was written before Phase 2 shipped. Walking it against the as-built
system found six divergences; each is dispositioned here and, where it changes
a load-bearing decision, in an ADR.

| # | Draft said | As-built reality | Disposition |
|---|---|---|---|
| D1 | Three codegen targets "exist (P1)": `aegis/ontology/_generated/models.py`, `infra/fga/_generated.fga`, `aegis/api/_generated/ui_meta.json` | None exists. The CLI has only `aegis ontology validate`; `infra/fga/model.fga` is hand-written and declares **no domain object type**; the UI reads vocabulary from `GET /v1/ontology/vocabulary` | ADR-038 — codegen is built per consumer. P3 ships one target (§8). Spec 01 §5 corrected. |
| D2 | P3 generates a TS client into `sdk/ts/`, and `ui/` migrates off its "P2-era" client | `ui/src/api/schema.d.ts` is **already** generated from the committed OpenAPI document by `openapi-typescript`, consumed through `openapi-fetch`, with a CI drift gate | ADR-039 — generation stays in `ui/`; `sdk/ts/` waits for an out-of-repo consumer. The P3 delta is ontology constants + typed errors. |
| D3 | RFC 7807 is the error format | True at runtime, **absent from the contract**: all 37 operations document only `200`/`201`/`204`/`422`, so `ui/src/api/client.ts` hand-writes `ProblemDetail` and `StaleRevisionProblem` | ADR-039 — the envelope becomes part of the OpenAPI document (spec 06 §7). |
| D4 | Modules carry versions; `ontology_version` unchanged | `claim.ontology_version` and `edge_projection.ontology_version` are single scalars on immutable rows | ADR-037 — the scalar is the **composition version**; per-module versions live in the release metadata. |
| D5 | `submission_criteria` failures are "audited denials, not silent 403s" | The actions layer gates on ontology `roles` **only for `adjudicate_identity`** (every other call passes no `ActionContext`), and `ActionService._audit` hard-codes `decision="allow"` — it cannot record a denial | ADR-040 — T34 also closes the role-enforcement gap and adds the denial-audit path. |
| D6 | §5 `functions` with `derived_record` mode; §8 Python SDK | ADR-027 removed every machine-write mode; ADR-033 moved functions execution, the side-effect engine, and the Python SDK to their consumer phases | Moved verbatim to the **future-consumers appendix** (§11), each with its trigger phase. |

Two further observations that change no decision but bound the work: the
`computed: true` flag on `co_located_in_prison_with` still has no engine behind
it (it stays a marker until P5/P6, §11.1), and `record_claim`'s real request
surface is 19 fields, not the draft's illustrative 4 — which is what §6.2's
closed type list is sized against.

## 1. Purpose

Phase 3 turns `ontology/aegis.yaml` from a single vocabulary file into a
**composition** of modules, and gives the workspace a typed contract over it.
After this phase Article XIV has a mechanism behind it: a domain is a module,
and a second domain loads with zero core-code change.

Everything here is **additive** to the v1 DSL. A v1-shaped file still validates,
so the modularization bump is minor (§7.4).

**Scope discipline (ADR-033).** Every retained feature below names the consumer
that needs it. Anything without one is in §11 with the phase that will pull it
in. Nothing in this spec executes machine-authored writes into canonical
tables — there is no such mode (ADR-027, Article VII).

## 2. The composition

### 2.1 Shape

`ontology/aegis.yaml` remains **the** artifact Article XI names, but its content
becomes a manifest over module files:

```yaml
# ontology/aegis.yaml — the composition manifest
version: 1.3.0                 # the COMPOSITION version (see §2.4)
namespace: aegis.lk
composition:
  - module: platform
    path: modules/platform.yaml
    version: "1.0.0"           # exact version this composition pins
  - module: criminal_network
    path: modules/criminal-network.yaml
    version: "1.0.0"
    enabled: true              # default true
```

A module file carries its own header plus ordinary v1 sections:

```yaml
# ontology/modules/criminal-network.yaml
module:
  name: criminal_network
  namespace: aegis.lk/criminal-network
  version: 1.0.0
  label: Criminal-network analysis
  imports:
    - module: platform
      version: ">=1.0.0,<2.0.0"    # PEP 440 specifier (§2.3)

categories: {...}
object_types: {...}
predicates: {...}
```

### 2.2 The platform/domain split

The split is not cosmetic — it is where Article XIV becomes checkable.

| Module | Owns | Why |
|---|---|---|
| `platform` | `handling_codes`, `grading` (scales + external schemes), `source_types`, all platform `actions` with their parameters, and (from T32) the starter `shared_properties` + `interfaces` | Governance and epistemic vocabulary. How a claim is graded, handled, sourced, and written is core, not domain — the same reason `assertion_types` is a code-owned constant rather than ontology vocabulary (spec 06 §2.7). |
| `criminal_network` | `object_types` (person, organization, location, vehicle, phone_number), all `predicates`, `categories` | Domain vocabulary. Everything a second domain would replace. |

The union of the two module files equals today's `aegis.yaml` section-for-section.
T30 is a **pure reorganization**: the composed registry must be byte-identical
under §7.2 normalization, which is the strongest available proof that no
vocabulary changed.

### 2.3 Imports and version constraints

- A module may reference a name only if it declares the name's owning module in
  `imports` (or owns the name itself). A reference without a declared import is
  a validation error naming both modules and the offending path — charter exit
  criterion 3.
- Constraints use **PEP 440 specifier syntax**, parsed with
  `packaging.specifiers.SpecifierSet` (Article XII — adopt before build; the
  library is already a transitive dependency, and semver strings are valid PEP
  440 versions). Inventing a constraint grammar for one repo is not justified.
- The composition manifest pins an **exact** version per module; the module's
  own `imports` express the compatible **range**. Loading fails if the pinned
  version does not satisfy every importer's range, or if the pinned version
  disagrees with the module file's own `module.version`.
- Import cycles are a validation error.

### 2.4 Names, namespaces, and why names are not prefixed

**Names stay globally unique and unprefixed** — in the registry, on the wire,
and in `claim.predicate`. The `namespace` is metadata: it identifies a name's
origin in errors, release metadata, and generated-client grouping.

A cross-module name collision is a **validation error**, never silent shadowing.

The alternative — lexically prefixing names (`criminal_network:member_of`) —
was rejected: every recorded claim stores its bare predicate as TEXT
(`claim.predicate`, spec 02), so prefixing would rewrite immutable rows or
require a translation layer on every read. Article XI's guarantee is that
exactly one artifact declares a name; global uniqueness delivers that directly,
and collision-as-error delivers it *loudly*. Two domains that genuinely need
the same word need a proposal (§7), not a prefix.

### 2.5 `ontology_version` under composition (ADR-037)

`claim.ontology_version` and `edge_projection.ontology_version` keep their
meaning and their existing values: they store the **composition version**
(`aegis.yaml`'s `version`). Per-module versions are recorded once per release
in the release metadata (§7.2), which is what a historical row is resolved
through.

This is what makes T30 non-breaking: a claim stamped `1.2.0` still means what
it meant, and `1.3.0` is the composition that reorganized the files.

### 2.6 Enable/disable

`enabled: false` omits a module's vocabulary from the composed registry.

- Disabling a module that an **enabled** module imports is a validation error.
- Disabling is an **authoring-time** control, not a data control. It does not
  delete, hide, or reinterpret claims already recorded under the module's
  vocabulary — those rows are immutable (ADR-013).
- Because of that, the API **refuses to start** when a disabled module's
  predicates or object types appear in recorded claims. `aegis ontology
  validate` runs offline and cannot see the database, so it reports the
  disabled vocabulary and the startup check enforces the rule.

The consumer is T31: the second-domain fixture is enabled for its own test run
and disabled everywhere else, and "disabling removes its vocabulary from
validation" is the assertion that proves the switch is real.

### 2.7 Loader output

The loader resolves the manifest into one `Ontology` registry with the same
public surface Phase 1–2 code already uses (`object_type()`, `predicate()`,
`action()`, `identifier_predicates()`, `handling_rank()`, `normalize_grade()`).
Twelve modules under `aegis/` consume that surface today and none may change —
that is the T30 acceptance criterion.

Added surface, all additive: `modules` (name → manifest entry),
`owner_module(name)`, and per-name `owner` metadata on the composed registry.

**Type ownership is derived, not declared.** The module that declares a name
owns it. A hand-maintained `owns:` list in the manifest would be a second
source of truth that drifts from the sections beside it; the composed registry
records `owner_module` per type so the information is available without being
separately maintained.

## 3. `shared_properties`

*Consumer: T33 codegen metadata; P4 object views render shared properties once;
T39's end-to-end proof.*

A property defined once, referenced by many object types — one definition of
type, sensitivity, conflict policy, and display.

```yaml
shared_properties:
  alias:
    type: text
    many: true
  registered_identifier:
    type: identifier
    sensitivity: restricted
  notes:
    type: text

object_types:
  person:
    properties:
      name:    {type: text, required: true}
      aliases: {shared: alias}          # reference, not redefinition
      nic:     {shared: registered_identifier}
```

Validator: a `shared:` reference may not override `type` or `sensitivity`
(display hints may be specialized); the referenced name must be owned by this
module or an imported one. Rule of three (GOAL.md §7.9): the third duplicated
inline property definition should become a shared property — enforced in
review, not by the validator.

## 4. `interfaces`

*Consumer: T39 (a new predicate lands on an interface and reaches the client
with no domain code); P4 object views; P6 object sets.*

Named shapes over object types — polymorphism for predicates, workflows, and
generated types. Composition over wide types.

```yaml
interfaces:
  party:                       # person-or-organization
    members: [person, organization]
    properties: [alias]        # shared properties every member must carry
  identifiable:
    members: [person, vehicle, phone_number]
    properties: [registered_identifier]
```

- `members` is explicit (no structural inference); adding a member is a minor
  bump.
- Predicates may target interfaces: `subject: [party]` expands to member types
  at validation time. The **expansion is what is stored** — a claim records the
  concrete predicate and concrete entity types, never the interface — so
  interfaces add no new value to `claim`.
- An interface and its members may live in different modules, subject to §2.3.
- Validator (§9): members exist; every member carries the interface's required
  shared properties; no interface cycles; an interface is not also an object
  type name (§2.4 uniqueness).

Members and interfaces are emitted as constants by the generated client (§8) so
the UI can group by interface without a second list.

## 5. `functions` — moved out

The v1 `computed: true` predicate flag stays as a marker. The functions layer —
declaration, registry allowlist, execution, attribution, and derived-record
tables — is **not in Phase 3** (ADR-033). It lands with its first consumer,
P5/P6 derived records; the full draft design is preserved in §11.1.

## 6. `actions` v2

*Consumer: T37's generated call signatures; P4's ontology-driven forms; the
charter's criterion-denial exit test.*

The v1 schema (`roles`, `audit`, `dual_control_for`) extends with declared
parameters and submission criteria. Both are declared here and **enforced in
`aegis/actions/`** (ADR-040) — not at the API layer alone, which is where the
enforcement gap D5 found lives today.

```yaml
actions:
  record_claim:
    roles: [analyst, investigator]
    audit: true
    parameters:
      subject_id:             {type: ref, to: entity, required: true}
      predicate:              {type: predicate, required: true}
      object_id:              {type: ref, to: entity}
      object_value:           {type: literal}
      record_id:              {type: ref, to: source_record, required: true}
      assertion_type:         {type: assertion_type, default: reported}
      handling_code:          {type: handling_code, default: open}
      credibility_scheme:     {type: grading_scheme}
      credibility_normalized: {type: grade, dimension: credibility, default: cannot_judge}
      verification_status:    {type: grade, dimension: verification, default: unverified}
      analytic_confidence:    {type: grade, dimension: analytic_confidence}
      case_id:                {type: ref, to: case}
      valid_from:             {type: date}
      valid_to:               {type: date}
      excerpt:                {type: text}
      collection_method:      {type: enum, values: [extracted, curated, manual, imported]}
      credibility_original:   {type: text}
      jurisdiction:           {type: text}
      location_text:          {type: text}
    submission_criteria:
      - actor_holds_action_role
      - actor_is_case_member
    side_effects:
      - refresh_projection: edge_projection      # parsed and stored; not executed (§6.4)
```

### 6.1 What `parameters` are

`parameters` declare an action's **public request contract** — what an API or
SDK caller may send. They are not the service function's Python keyword
surface: `ActionService._create_claim` also takes mention anchors and
resolution hints that acceptance dispatch supplies internally, and those are
not caller input.

- The declaration generates the action's request model; an **undeclared
  parameter is rejected** by that model.
- `required` and `default` mirror what the hand-written `ClaimIn` encodes
  today, so T34 is a migration of an existing contract, not a new one.
- Platform actions are declared in the **platform module** (§2.2), which is why
  a domain module can never widen the claim envelope.

### 6.2 The closed parameter type list

The validator rejects any type not in this list. It is sized against the real
Phase 2 request bodies (`aegis/api/schemas.py`), not an illustration.

| Type | Modifier | Validated against |
|---|---|---|
| `text` | — | non-empty string when `required` |
| `identifier` | — | opaque identifier string |
| `ref` | `to:` — one of `entity`, `claim`, `case`, `source_record`, `evidence_item`, `suggestion`, `mention`, `user` | row exists at write time |
| `predicate` | — | a predicate in the composed registry |
| `object_type` | — | an object type in the composed registry |
| `literal` | — | a claim object value; the predicate decides its shape (spec 02 §6) |
| `handling_code` | — | `handling_codes` (platform module) |
| `source_type` | — | `source_types` (platform module) |
| `grade` | `dimension:` — one of the four grading dimensions | that dimension's declared values |
| `grading_scheme` | — | a key of `grading.schemes` |
| `assertion_type` | — | the code-owned platform constant (Article XIV) |
| `enum` | `values:` — non-empty closed list | membership |
| `bool` / `int` / `decimal` | — | type coercion |
| `date` / `timestamp` | — | ISO 8601; timestamps must be timezone-aware |
| `json` | `schema:` — a code-side schema id | the named schema (suggestion payloads only) |

`json` exists for exactly one thing: `submit_suggestion.payload`, whose shape is
per-kind and **code-owned** (ADR-031 §1 — `suggestion_kind` is a closed,
code-owned list because each kind is a dispatch branch). Declaring a `json`
parameter without a registered `schema:` is a validation error, so it cannot
become an escape hatch.

### 6.3 The submission-criteria registry

`submission_criteria` name predicates evaluated by the actions layer against
(actor, context, target state). The validator rejects a name that is not
registered in code, so a criterion can never be declared before it can be
enforced.

P3 registers exactly three, each making an **existing** policy declarative
rather than inventing a new one:

| Criterion | Meaning | Today |
|---|---|---|
| `actor_holds_action_role` | the actor holds one of the action's `roles` | enforced at the API layer for every action, and in `_require_action` only when an `ActionContext` carrying roles is passed — which happens for `adjudicate_identity` alone (D5) |
| `actor_is_case_member` | when the target is case-scoped, the actor has the case relation the action needs | enforced at the API layer via `fga_check_or_404` |
| `second_approver_present` | a distinct second actor is present where `dual_control_for` fires | already implemented in `_require_action`; restated as a criterion so all three read the same way |

Criteria that future phases need — `target_not_sealed` (P7 sealing),
`within_legal_authority` (P7 legal-authority objects) — are **not declared
now**. The phase that implements the check adds the registry entry and the
declaration in the same change.

### 6.4 Failures are audited denials

A criterion failure writes an audit row with `decision="deny"`, the actor, the
action, the failed criterion, and the target — the same shape the API layer
already writes for `authz.deny` (`aegis/api/deps.py`). This is **new
behavior**: `ActionService._audit` writes `decision="allow"` unconditionally
today, and `_require_action` raises before any audit row exists (D5). T34 adds
the path; the charter's exit criterion is the test that proves it.

### 6.5 `side_effects` parse but do not run

`side_effects:` keys are validated for shape and stored on the composed
registry. **No engine executes them in P3.** The existing hard-coded refresh
paths stay exactly as they are. The generalized outbox lands with the first
action that genuinely needs one (§11.2).

## 7. Change management

### 7.1 Proposals

A change starts as `ontology/proposals/NNN-short-title.md`: motivation, the YAML
diff, the **competency questions** the change answers (GOAL.md §7.9), and a
migration plan when the bump is major. Review happens on the PR; approval merges
the proposal and the bump together. Proposal `001` backfills the modularization
bump itself (T35).

### 7.2 The release artifact

Comparison is against a **committed artifact**, never git archaeology (H-16).
Two files, both regenerated and CI-checked for drift:

- `ontology/history/composed-<composition-version>.json` — the normalized
  composed registry: all modules resolved into one document, canonical JSON
  (sorted keys, no insignificant whitespace), interfaces **unexpanded** so the
  declaration is what is compared.
- `ontology/release.json` — metadata for the current version: composition
  version, per-module names + versions + namespaces, proposal id,
  compatibility class (`major` | `minor` | `patch`), this artifact's content
  hash, and the previous version + its content hash.

A composed artifact is written on **every** bump, not only major ones. Spec 01
§4 already requires that historical `ontology_version` values stay
interpretable, and a minor bump changes what a version means just as a major one
does; keeping only major snapshots leaves the majority of stamped values
unresolvable. Major bumps additionally copy the module YAML sources, as today.

### 7.3 CI gates

1. **Version monotonicity** per module and for the composition.
2. **Compatibility diff** — the new composed registry against
   `history/composed-<previous>.json` named by `release.json`: a `minor` or
   `patch` bump that removes or renames an object type, predicate, action,
   interface, shared property, or enum value fails. Pure filesystem comparison;
   no git history is read.
3. **Proposal reference** — `release.json.proposal` must name an existing file
   in `ontology/proposals/`.
4. **Major bumps** carry the history copy and the migration script.
5. **Codegen drift** — regenerating the composed artifact, `release.json`, and
   the generated client constants (§8) must produce no diff.

### 7.4 Semver under composition

Spec 01 §4 rules are unchanged and now apply at two levels: each module carries
its own semver, and the composition carries its own. The composition's
compatibility class is the **strongest** class among its modules' changes, plus
its own manifest changes (adding a module is minor; removing or disabling one
whose vocabulary is in use is major).

The T30 modularization is **minor** (1.2.0 → 1.3.0): sections move between
files, the composed registry is unchanged, nothing is removed or renamed.

## 8. Codegen targets (ADR-038 — supersedes spec 01 §5)

Spec 01 §5 and this spec's draft both described three committed codegen targets
"used by" Phase 1 code. None was ever built (D1). Rather than restore them
wholesale, each target is built by the phase whose consumer needs it.

| Target | Output | First consumer | Phase | Status |
|---|---|---|---|---|
| Composed registry + release metadata | `ontology/history/composed-*.json`, `ontology/release.json` | change-management gates (§7.3) | **P3 (T35)** | to build |
| Ontology constants for the client | `ui/src/api/ontology.ts` (predicates, object types, interfaces, categories, handling codes, source types, per-name owner module) | the workspace, replacing the ad-hoc reads of `GET /v1/ontology/vocabulary` | **P3 (T37)** | to build |
| Pydantic action request models | `aegis/actions/_generated/requests.py` | actions v2 parameter enforcement (§6.1) | **P3 (T34)** | to build |
| UI descriptors | `aegis/api/_generated/ui_meta.json` | ontology-driven generic screens (spec 07 §3) | **P4** | deferred — no P3 consumer |
| FGA object-type stubs | `infra/fga/_generated.fga` | a domain type acquiring an FGA relation | **P7** | deferred — `model.fga` declares no domain type today, so the generator would emit nothing |
| Python SDK | `sdk/python/aegis_sdk/` | P8 AI producers | **P8** | deferred (ADR-033) |

`aegis ontology generate` is introduced in P3 and emits only the three P3 rows.
Generated files are committed; CI fails if regeneration diffs (spec 01 §5
discipline unchanged, now with generators that exist).

**DB constraints remain a non-target** (ADR-013): vocabulary columns stay TEXT
and are validated at write time. Ontology changes never trigger DDL.

## 9. Validation rules added to the loader

Numbering continues spec 01 §6 (rules 1–7 unchanged, now applied to the
composed registry).

8. **Composition** — every manifest entry resolves to a file; the pinned version
   equals the module file's `module.version`; module names and namespaces are
   unique.
9. **Imports** — every import names a module in the composition; the pinned
   version satisfies the importer's specifier; no import cycles.
10. **Cross-module references** — a name referenced by a module is owned by it
    or by a declared import; the error names both modules and the YAML path.
11. **Collisions** — no name is declared by two modules (§2.4); the error names
    both.
12. **Enable/disable** — a disabled module is not imported by an enabled one
    (§2.6).
13. **Shared properties** — `shared:` references resolve; no `type` or
    `sensitivity` override.
14. **Interfaces** — members exist; every member carries the interface's
    required shared properties; no cycles; predicates targeting interfaces
    expand to a non-empty valid member set.
15. **Action parameters** — types come from the closed list (§6.2); modifiers
    are present and valid for the type; `json` names a registered schema.
16. **Submission criteria** — every name is registered in the actions-layer
    registry (§6.3).
17. **Side effects** — well-formed shape; names registered (§6.5). Declaring
    one does not schedule one.
18. **Backwards compatibility** — v2 sections are optional. A v1-shaped single
    file still validates, which is what keeps the bump minor (§7.4) and lets
    the fixture modules in `tests/` stay small.

Every violation is reported with the module name and the YAML path that caused
it, and all violations are collected before raising — the spec 01 discipline,
extended with the module coordinate.

## 10. What this spec deliberately excludes

Object sets (P6 — consumption layer, own spec file), object views (P4),
Foundry-style live branching (proposals suffice for one repo), per-property
ABAC beyond `sensitivity` (P7), OPA integration, dynamic/remote module loading
or any module registry beyond files in this repo, and new domain predicates
beyond the worked examples.

## 11. Future consumers (ADR-033 — designed, not built here)

Each section below is retained design, not Phase 3 scope. The trigger phase is
the phase whose first real consumer pulls it in; until then nothing in
`aegis/` implements it, and the validator does not accept its keys.

### 11.1 `functions` — trigger: P5/P6 derived records

Declared, versioned derivations over the ontology — the kinetic-layer analog of
Foundry functions, constrained by Article VII.

```yaml
functions:
  derive_prison_co_location:
    version: 1
    inputs:
      - claim_pattern: {predicate: remanded_in, object: location}
    output:
      predicate: co_located_in_prison_with
      mode: derived_record      # suggestion (default) | derived_record
    trigger: rebuild            # rebuild | on_write
    implementation: prison_overlap_v1   # registered id from a code-side allowlist (H-13)
```

- **Attribution.** Every output row records source_type `algorithmic`, function
  name + version, and input claim IDs. Anonymous derivation is a defect.
- **Mode (ADR-027).** `suggestion` (default) routes through the review queue.
  `derived_record` writes into **rebuildable derived tables**
  (projections/findings, Article XIII), typed and displayed as derived — never
  rows in `claim`. There is no machine path into canonical tables, and no
  `system_claim` mode exists. Reproducibility is canonical-digest equality over
  inputs + config + output, not byte-identical DB rows (H-14).
- **Supersedes `computed: true`.** The v1 flag remains a marker; today
  `co_located_in_prison_with` carries it with no engine behind it, and that
  stays true until this section lands.
- **Implementation allowlist (H-13).** The ontology selects a *registered*
  function id + version from a code-side registry with declared capabilities
  and input/output schemas; arbitrary import paths are rejected, so an ontology
  deployer cannot select unreviewed code.

### 11.2 Side-effect execution — trigger: the first action that needs one

Post-commit execution via the outbox pattern (ADR-014 precedent); failures
never roll back the action — they retry. In P3 the declarations parse and are
stored (§6.5) and the existing hard-coded refresh paths run instead.

### 11.3 Python SDK — trigger: P8 producers

`sdk/python/aegis_sdk/`: typed object/interface models, predicate constants,
action call wrappers generated from `parameters`, query builders. Auth: tokens
scoped to app grant ∩ user permission (GOAL.md §7.8). Its first consumer is P8's
AI producers, which must be able to write typed suggestions and nothing else.

### 11.4 A published `sdk/ts/` package — trigger: an out-of-repo consumer

The generated TypeScript surface stays inside `ui/` while `ui/` is its only
consumer (ADR-039). Extracting it into a versioned package is packaging work
with no P3 beneficiary; the first consumer outside this repository is the
trigger.
