# Spec 09 — Investigation domain & the object-view contract

Status: **final** (authored 2026-08-17 by T41, the blocking re-validation that
opens Phase 4) · Charter: `../phases/phase-04-workspace-object-views.md` ·
Constitutional basis: Articles VI, VIII, X, XI, XIV · GOAL.md §18, §29–30 ·
Findings closed here: H-17, H-18, H-19 (remainder), B-11 · ADR-043, ADR-044,
ADR-045

This spec has two halves and H-17 is the reason they are in that order:

1. **The operational model** (§2–§5) — cases, hypotheses, tasks and leads as
   storage, actions and authorization. Written **before** any screen, so
   acceptance is testable without a browser.
2. **The object-view contract** (§6–§7) — what a generic, ontology-driven
   entity page renders and where its descriptors come from.

Phase 4 builds nothing outside these two halves; §9 lists what it deliberately
does not build.

---

## 0. What re-validation changed

The Phase 4 plan was pre-authored 2026-07-17, before Phase 3 existed. T41 walked
it against the P3-as-built system. Five divergences, each dispositioned rather
than absorbed silently:

| # | The plan said | As built | Disposition |
|---|---|---|---|
| D1 | Generic screens render from a generated `ui_meta.json` (spec 07 §3) | P3 already generates `ui/src/api/ontology.ts` — typed, drift-gated, imported directly. A second runtime artifact would be a second copy of the same facts with a weaker guarantee | **ADR-043** — the descriptor *is* the generated TypeScript module; extend it, do not add `ui_meta.json`. Spec 07 §3 corrected. Closes the P3 carryover "UI-descriptor codegen" |
| D2 | "Claims and evidence linkable to cases" (charter deliverable 3) | `claim.case_id` and `evidence_item.case_id` already exist — and `claim_filters` uses `claim.case_id` as an **access** predicate. Making it re-assignable would let a link widen who can read a recorded claim | **ADR-044** — `case_id` is the immutable *recording scope*; a case *reference* is a separate, non-authorizing link. Two concepts, two tables |
| D3 | T47 AC: "creation without a missing-info note is rejected by the action's submission criteria" | A missing parameter is rejected by `required: true` and the generated request model — not by a criterion. And a *blank* note passes `required` | A fourth criterion, `required_text_is_substantive` (§3.4), makes the AC literally true and closes the blank-string hole |
| D4 | Spec 07 §6 lists an **audit console** as a Phase 4 view | The P4 charter's deliverables and T41–T53 contain no such task; `GET /v1/audit` exists and is auditor-gated | **ADR-045** — the console lands in P7, where "reviewable as one query" is a gate criterion and sealing/break-glass give it its first real reader. Spec 07 §6 corrected |
| D5 | H-19 "remainder" was assumed to be mostly open | P2 shipped memory tokens, sessionStorage PKCE state, CSP with `script-src 'self'`, silent renew, and bearer-only auth. Genuinely open: **the realm declares no session timeouts at all**, multi-tab behaviour is unstated, and the CSRF model is nowhere written down | §10 — three small, testable items folded into T42, not a new task |

Two further things the plan assumed and reality confirms, recorded so nobody
re-checks them: `?asOf=` **already** filters `recorded_at`/`retracted_at`
exactly as B-11 requires (`aegis/authz/filters.py`), and `claim_filters`
**already** hides case-scoped claims from non-members. What B-11 is missing is
the response stamp and `?asOfRevision=`, not the snapshot itself (§7).

---

## 1. Scope

An **investigation** is not an object type. It is the operational plane: the
case that scopes work, the hypotheses that state what is believed, and the tasks
and leads that record what to do next. None of it is domain vocabulary — a
`border-cargo` deployment gets the same cases, hypotheses and tasks — so all of
it is **platform**, owned by `ontology/modules/platform.yaml` and by tables in
`aegis/store` (Article XIV).

The distinction that governs the whole spec:

- A **claim** is an assertion about the world, attributed to a source, graded,
  and never edited (Article I).
- A **hypothesis** is an assertion about *our own reasoning* — what an analyst
  currently believes and what would change their mind. It is not evidence, it
  is never a source, and it may never be projected into the graph.

Confusing the two is how "association is not guilt" (Article IX) fails in
practice, so they share no table, no route prefix, and no projection.

---

## 2. Cases

### 2.1 The record (as built, unchanged)

`case_file` — `case_id`, `title`, `status ∈ {open, closed, sealed}`, `purpose`,
`handling_code`, `opened_by`, `opened_at`, `closed_at`. `sealed` is declared
and **not implemented**: sealing is P7 (spec 03), and P4 must not add a code
path that pretends otherwise.

### 2.2 Membership and authorization (as built, unchanged)

`case_member (case_id, user_id, role)` is canonical; OpenFGA is its projection
(ADR-014). The FGA `case` type already defines `supervisor`, `investigator`,
`analyst`, `auditor_grant`, `member`, `can_view`, `can_edit`, `can_approve`.

Two rules that Phase 4 must not weaken:

- **Non-membership is 404, never 403.** `fga_check_or_404` is the only
  acceptable gate on a case-scoped read. A 403 tells the caller the case exists.
- **The write side reads the canonical row.** `actor_is_case_member` consults
  `case_member` inside the write's transaction, not FGA (ADR-014, spec 08 §6.3).

### 2.3 Recording scope vs. case references (ADR-044)

`claim.case_id` is the claim's **recording scope**: it is set when the claim is
recorded, it is immutable, and `claim_filters` turns it into an access
predicate — a claim scoped to a case is visible only to that case's members.
Nothing in Phase 4 may reassign it. Re-scoping a recorded claim would either
widen who can read it or silently remove it from someone's view, and both are
governance events with no audit story.

A **case reference** is the other thing the charter's phrase "linkable to cases"
can mean, and the one an analyst actually wants: *this investigation refers to
that claim / entity / evidence item.* It is a link, and it **grants nothing**.

```
case_reference
  case_id      TEXT NOT NULL  FK case_file
  target_type  TEXT NOT NULL  CHECK IN ('claim', 'entity', 'evidence_item')
  target_id    TEXT NOT NULL
  note         TEXT
  linked_by    TEXT NOT NULL
  linked_at    TIMESTAMPTZ NOT NULL
  detached_at  TIMESTAMPTZ            -- unlink is a tombstone, never a DELETE
  PRIMARY KEY (case_id, target_type, target_id)
```

Consequences, stated because they are the point:

- Linking a claim to a case does **not** let that case's members read it. The
  claim is still read through `claim_filters`. A member who cannot see the
  target sees the reference resolve to nothing — the row is filtered like any
  other, and the reference list is built from targets the caller can already
  read (§6.5).
- Because references grant nothing, linking is an ordinary case-scoped write
  (`analyst`, `investigator`, plus `actor_is_case_member`) rather than a
  privilege operation.
- `evidence_item.case_id` keeps its existing meaning — evidence custody is
  scoped to one case by FGA (`can_view from case`) — and is likewise not
  reassignable in P4.

### 2.4 Routes

Added by T43/T46. `R` = realm roles, `F` = FGA relation.

| Route | R | F | Notes |
|---|---|---|---|
| `GET /v1/cases` | — | per row | **Only cases the caller can view.** Cursor-paginated, no total count (spec 06 §4). Ordered by `case_id` — never by activity, which would rank hidden cases into the gaps |
| `POST /v1/cases/{id}/close` | supervisor | `can_approve` | audited; sets `status='closed'`, `closed_at`. Never deletes |
| `GET /v1/cases/{id}/members` | — | `can_view` | members of a case you can view; 404 otherwise |
| `POST /v1/cases/{id}/references` | analyst, investigator | `can_edit` | the §2.3 link |
| `DELETE /v1/cases/{id}/references/{target_type}/{target_id}` | analyst, investigator | `can_edit` | tombstone, not delete |
| `GET /v1/cases/{id}/references` | — | `can_view` | targets are re-authorized individually (§6.5) |

Existing case routes (`POST /v1/cases`, `GET /v1/cases/{id}`,
`POST|DELETE .../members/...`) are unchanged. Spec 06 §2.5 gains these rows in
the same commit that adds the routes.

---

## 3. Hypotheses

### 3.1 Versions are records, not a counter

H-17 asks for hypothesis *versions*. A version counter plus an audit row would
mean the earlier statement is only recoverable by parsing audit payloads, which
is the "history you cannot query" failure the identity ledger was built to
avoid (ADR-028). So the hypothesis splits the same way:

```
hypothesis                       -- immutable identity
  hypothesis_id  TEXT PK
  case_id        TEXT NOT NULL  FK case_file
  opened_by      TEXT NOT NULL
  opened_at      TIMESTAMPTZ NOT NULL
  handling_code  TEXT NOT NULL DEFAULT 'open'

hypothesis_revision              -- append-only; the latest row is the current state
  hypothesis_id  TEXT NOT NULL  FK hypothesis
  version        INT  NOT NULL
  statement      TEXT NOT NULL
  status         TEXT NOT NULL  CHECK IN ('open','supported','refuted','withdrawn')
  missing_info   TEXT NOT NULL  -- §3.3
  note           TEXT           -- why this revision exists
  authored_by    TEXT NOT NULL
  authored_at    TIMESTAMPTZ NOT NULL
  PRIMARY KEY (hypothesis_id, version)
```

The `hypothesis` row carries nothing that can change. Current state is
`max(version)`. `status` is a label on a revision, so "when did this become
refuted, and who said so" is one query and not an audit excavation.

A hypothesis is **always** scoped to a case. There is no global hypothesis.

### 3.2 Evidence basis

```
hypothesis_claim
  hypothesis_id  TEXT NOT NULL  FK hypothesis
  claim_id       TEXT NOT NULL  FK claim
  stance         TEXT NOT NULL  CHECK IN ('supports','contradicts')
  note           TEXT
  linked_by      TEXT NOT NULL
  linked_at      TIMESTAMPTZ NOT NULL
  detached_at    TIMESTAMPTZ
  PRIMARY KEY (hypothesis_id, claim_id, stance)
```

`supports`/`contradicts` and not `claim_relation`'s
`corroborates`/`contradicts`: a claim corroborating another claim is a
statement about two observations of the world; a claim supporting a hypothesis
is a statement about our reasoning. Reusing the vocabulary would make the two
indistinguishable in a query, and only one of them may ever reach a projection.

The same claim may appear under both stances — recorded by different analysts,
or by one analyst who thinks it cuts both ways. That is not a conflict to
resolve; the primary key admits it on purpose (Article VIII).

Reading the basis applies `claim_filters` to the claims, so a member who cannot
read a linked claim gets a shorter list, not an error.

### 3.3 The missing-information note is required, and blank is not a note

`missing_info` is `NOT NULL` on every revision and `required: true` on both
actions. GOAL.md §18's whole point is that a hypothesis states what would change
it; a hypothesis with no missing-information note is the vibe the charter's risk
table names.

`required: true` alone rejects an absent field. It does not reject `""` or
`"   "`. Phase 4 therefore registers a **fourth submission criterion**:

> `required_text_is_substantive` — every parameter the action declares as
> `{type: text, required: true}` must contain at least one non-whitespace
> character.

It is declarative, general, and applies only to actions that declare it, so no
Phase 1–3 action changes behaviour. Registering it in
`aegis.ontology.registries.SUBMISSION_CRITERIA` and `aegis.actions.criteria`
makes T47's acceptance criterion literally true: creation without a
missing-information note is refused by the action's submission criteria, and
the refusal is an audited denial (spec 08 §6.4).

### 3.4 Actions

Declared in `ontology/modules/platform.yaml`; each is audited (Article X) and
carries `submission_criteria: [actor_holds_action_role, actor_is_case_member,
required_text_is_substantive]`.

| Action | Roles | Parameters |
|---|---|---|
| `open_hypothesis` | analyst, investigator | `case_id` (ref case, req), `statement` (text, req), `missing_info` (text, req), `hypothesis_id` (identifier), `handling_code` (default `open`) |
| `revise_hypothesis` | analyst, investigator | `hypothesis_id` (ref hypothesis, req), `note` (text, req), `statement` (text), `status` (enum), `missing_info` (text) |
| `link_hypothesis_claim` | analyst, investigator | `hypothesis_id` (req), `claim_id` (ref claim, req), `stance` (enum, req), `note` (text) |
| `unlink_hypothesis_claim` | analyst, investigator | `hypothesis_id` (req), `claim_id` (req), `stance` (req), `reason` (text, req) |

`revise_hypothesis` copies forward whatever it is not given, so a revision that
only moves the status still records the statement and missing-info that were
current — a revision row is a complete snapshot, never a diff.

`hypothesis` joins `REF_TARGETS` in `aegis/ontology/loader.py` alongside
`investigation_task` (§4). Both are platform concepts, so this is not a domain
name entering the core.

### 3.5 Routes

| Route | R | F | Notes |
|---|---|---|---|
| `POST /v1/hypotheses` | analyst, investigator | `can_edit` on the case | 404 if the case is not viewable |
| `GET /v1/hypotheses?case={id}` | — | `can_view` | case required; there is no global list |
| `GET /v1/hypotheses/{id}` | — | `can_view` via its case | current revision + full revision history + both stances |
| `POST /v1/hypotheses/{id}/revisions` | analyst, investigator | `can_edit` | `revise_hypothesis` |
| `POST /v1/hypotheses/{id}/claims` | analyst, investigator | `can_edit` | link |
| `DELETE /v1/hypotheses/{id}/claims/{claim_id}/{stance}` | analyst, investigator | `can_edit` | tombstone |

`GET /v1/hypotheses/{id}` returns `supporting` and `contradicting` as two
**always-present** arrays. An empty array is rendered as "no contradicting
evidence recorded" (§6.4) — never omitted, never collapsed. Article VIII is a
rendering obligation, not a data-availability accident.

---

## 4. Tasks and leads

Lightweight and deliberately dumb: plan §2's workflow-engine trigger stays
untouched.

```
investigation_task
  task_id        TEXT PK
  case_id        TEXT NOT NULL  FK case_file
  kind           TEXT NOT NULL  CHECK IN ('task','lead')
  title          TEXT NOT NULL
  detail         TEXT
  status         TEXT NOT NULL  CHECK IN ('open','in_progress','blocked','done','dropped')
  owner          TEXT           -- nullable: unassigned is a real state
  due_date       DATE
  hypothesis_id  TEXT           FK hypothesis   -- a lead may pursue one
  created_by     TEXT NOT NULL
  created_at     TIMESTAMPTZ NOT NULL
  updated_at     TIMESTAMPTZ NOT NULL
  closed_at      TIMESTAMPTZ
```

A **task** is work to do; a **lead** is a line of enquiry worth pursuing. One
table, one `kind`, because the only difference is the word — separate tables
would be two schemas kept in sync for a label.

**No transition graph.** Any status may follow any other. Each change is an
audited action carrying the old and new value, which is what makes the history
answerable; a state machine here would be a rule with no rule-maker. `closed_at`
is set when the status becomes `done` or `dropped` and cleared if it leaves
them.

| Action | Roles | Parameters |
|---|---|---|
| `open_task` | analyst, investigator | `case_id` (req), `title` (text, req), `kind` (enum, default `task`), `detail`, `owner`, `due_date`, `hypothesis_id`, `task_id` |
| `update_task` | analyst, investigator | `task_id` (ref investigation_task, req), `status` (enum), `owner` (text), `due_date` (date), `detail` (text), `note` (text) |

| Route | R | F |
|---|---|---|
| `POST /v1/tasks` | analyst, investigator | `can_edit` on the case |
| `GET /v1/tasks?case={id}` | — | `can_view` |
| `POST /v1/tasks/{id}` | analyst, investigator | `can_edit` |

---

## 5. Authorization

Hypotheses and tasks have **no authorization of their own**. Both belong to
exactly one case, and the case is the resource. The FGA model gains:

```
type hypothesis
  relations
    define case: [case]
    define can_view: can_view from case
    define can_edit: can_edit from case

type investigation_task
  relations
    define case: [case]
    define can_view: can_view from case
    define can_edit: can_edit from case
```

This mirrors `evidence_item`, which already derives `can_view` from its case.
Hand-written, like every other platform type — the FGA-stub generator (P3
carryover, P7 owner) exists for *domain* object types and still has nothing to
emit.

**What runs at request time is a check on the parent case.** A route loads the
row, reads its `case_id`, and asks `can_view`/`can_edit` on `case:{id}` — which
is exactly what the derivations above compute, so no tuple is written per
hypothesis or task and none is needed. The types are declared for the same
reason `compartment` has been declared since P1: when a direct check becomes
meaningful (P7 sealing, per-resource compartments), the model is already there
and already means this. Stated because a declared-but-unqueried type is easy to
mistake for enforcement that is happening.

Every new route appends a row to `tests/contract/test_authorization_matrix.py`,
whose assertion is exact equality: a route added without a matrix row fails the
fast suite. That is the mechanism, not a convention.

**Rules that hold for every route in this spec:**

1. A caller who is not a member of the case gets **404** from every
   hypothesis, task, and reference route — including writes, so a `403` never
   discloses that the case exists.
2. No list route returns a total count (spec 06 §4, default 4).
3. Ordering on every authorization-filtered list is by primary key, so removing
   hidden rows cannot be detected as a gap in a ranking.

---

## 6. The object-view contract

### 6.1 Descriptors are the generated TypeScript module (ADR-043)

Spec 07 §3 said generic components render from `ui_meta.json`. Phase 3 shipped
`ui/src/api/ontology.ts` — generated by `aegis ontology generate`, guarded by
`--check` in CI, imported as ordinary typed constants. Building a second
artifact with the same content would mean two generators, two drift risks, and
a runtime fetch that cannot be type-checked.

The descriptor contract is therefore **the generated module, extended**. It is
still "fetched, never hard-coded" in the sense Article XI means: no human types
a domain name into `ui/src`. The distinction the workspace has to respect is
between *generated* and *hand-written*, and the sweep in
`tests/contract/test_second_domain.py` already enforces it.

The one thing a build-time constant cannot know is that the **server** moved.
That is what §6.3 is for.

### 6.2 What the generator emits

`typescript_constants` gains, for every object type:

```ts
export const OBJECT_TYPES = {
  person: {
    label: "Person",
    implements: ["identifiable", "party"],
    module: "criminal_network",
    display: { title: "name", subtitle: "aliases" },
    properties: {
      name:          { label: "Name", type: "text", required: true,  many: false, sensitivity: null,        conflicts: null,       shared: null },
      aliases:       { label: "Aliases", type: "text", required: false, many: true, sensitivity: null,       conflicts: null,       shared: "alias" },
      date_of_birth: { label: "Date of birth", type: "date", required: false, many: false, sensitivity: null, conflicts: "preserve", shared: null },
    },
  },
} as const;
```

and, for every predicate, a `label`.

**Labels.** `ObjectTypeSpec.label` and `CategorySpec.label` already exist.
`PredicateSpec` and `PropertySpec` gain an **optional** `label`; where it is
absent the generator humanizes the name (`date_of_birth` → "Date of birth",
`affiliated_with` → "Affiliated with"). The humanization lives in the generator,
never in React, so a name that humanizes badly is fixed by declaring a label in
the ontology — a proposal and a version bump, like any other vocabulary change —
and no UI code moves. Adding an optional field is an additive ontology change
(spec 08 §7.3).

**What is deliberately not emitted:** anything about layout, ordering, widths,
icons, or which tab a property belongs on. A descriptor describes the ontology.
The moment it starts describing a screen it becomes a second UI codebase written
in YAML, which is the "custom schema ecosystem" H-20 warns about.

### 6.3 The ontology-version banner (closes a P3 carryover)

`ONTOLOGY_VERSION` is compiled into the bundle. `GET /v1/ontology/vocabulary`
returns the server's. When they differ, the workspace shows a persistent,
non-blocking banner naming both versions and saying that labels and vocabulary
may be stale.

Non-blocking on purpose: the server is authoritative for every value that
matters, so a stale bundle renders *correct data with possibly outdated labels*.
Refusing to render would turn a cosmetic drift into an outage.

### 6.4 What the object view renders

One component, driven entirely by §6.2, for any object type in any module.

| Region | Source | Rule |
|---|---|---|
| Title / subtitle | `entity.label`, over the type's descriptor label and id | **Corrected at T44.** This section first said the heading resolves `display.title`/`display.subtitle` against claim-derived properties. It cannot: those name *properties* and the response is keyed by *predicate*, and the ontology declares no mapping between the two — the server's own correspondence (`aegis/authz/filters.py`) is a documented heuristic, not a contract. So the heading is `entity.label`, which search, the graph and the projection already show and which `hidden_entity_types` already makes clearance-aware; the subtitle is the type's label (linked to its schema page) beside the entity id. `display` still governs the **type** page (T42), which renders a schema rather than an instance, and where the property names are exactly what a reader wants |
| Properties | `GET /v1/entities/{id}` → the entries whose predicate has a **literal** object | Each value carries all three grading dimensions (Article III). **Conflicting values render side by side**, both with their `contradicted_by` badge — two dates of birth are two dates of birth (Article VIII, `conflicts: preserve`). Never a "primary" value with the rest hidden behind a disclosure |
| Links | the entries whose predicate has an **entity** object, grouped by `PREDICATES[p].category` | The response returns one map; only the descriptors know which half is which. Category label and colour come from `CATEGORIES`. An uncategorized predicate groups under "Other" rather than vanishing |
| Sources | the source record behind each claim | Every value is one click from its provenance (§6.6) |
| Timeline strip | claim `event_time_earliest`/`latest`, `valid_from`/`to`, `recorded_at` | Uncertain and exact render differently (§7) |
| Cases | `GET /v1/entities/{id}/cases` | §6.5 |

Everything above comes through the generated client. A value that a screen
computes for itself is a defect, because it is a value that will not exist for
the next object type.

### 6.5 Case references without an existence leak (H-18)

The naive implementation — list the cases whose claims mention this entity, then
filter — is a leak waiting for a timing measurement. The rule is stronger:

> The case list is **derived only from rows the caller can already read**, then
> intersected with `can_view` on each case.

Concretely, `GET /v1/entities/{id}/cases`:

1. selects distinct `case_id` from claims about the entity **through
   `claim_filters`** — which already drops case-scoped claims the caller is not
   a member of — and from `case_reference` rows targeting the entity;
2. checks `can_view` on each surviving case id, dropping failures;
3. returns titles and ids, ordered by `case_id`.

And what it never does:

- no total, no "N more", no "some results hidden" (spec 03 §4, spec 07 §5);
- no ordering by relevance, recency or claim count — hidden rows must not be
  detectable as gaps in a ranking;
- no distinction, in status code or in latency shape, between "this entity is in
  no cases" and "this entity is in cases you cannot see". Both are an empty
  array from a `200`.

Step 2 is not redundant with step 1. A claim with `case_id IS NULL` is readable
by anyone, and a `case_reference` can point at it from a restricted case; without
the `can_view` intersection, an open claim would advertise a case the caller may
not know about. That is exactly H-18's scenario, and it is a test, not a note:
`tests/integration/test_object_view.py` seeds a restricted case referencing an
open entity and asserts the response is byte-identical to the no-case response.

### 6.6 Provenance drill-down

No new endpoint. Every value and every link resolves through the P2 surfaces
consumed as-is: `GET /v1/claims/{id}/provenance` and
`GET /v1/entities/{id}/why-connected/{other}`. If the object view needs
provenance data those routes do not return, that is a P2 regression to fix in
those routes, not a reason for a seventh endpoint.

---

## 7. Time and as-of (B-11, narrowed)

The promise, stated exactly, because the whole finding was that it had been
overstated:

> **As-of is a claim-recording snapshot.** `?asOf=<ts>` returns the claims that
> had been recorded and not retracted at that instant. It does **not** restore
> labels, source evaluations, grading, policy, projections or the ontology as
> they were.

Already built (`aegis/authz/filters.py`): `recorded_at <= ts AND (retracted_at
IS NULL OR retracted_at > ts)`, with the auditor variant. Phase 4 adds the three
things that make it honest:

1. **`?asOfRevision=<id>`** pins the identity revision used to resolve entity
   arguments. Spec 06 §3 has specified it since P2; nothing implements it.
   Without it, reads resolve through the **active** revision — identity as it is
   *now* — which is almost never what a historical question means.
2. **A response stamp** on every as-of-capable read:
   `{ as_of, identity_revision_id, ontology_version }`. `identity_revision_id`
   is echoed whether or not it was pinned, so the caller always knows which
   identity the answer used.
3. **A persistent banner** stating what is and is not held constant, in the
   words of the promise above. It is present whenever `asOf` is set — it is not
   dismissible, because a snapshot the reader has forgotten they are in is worse
   than no snapshot.

**Uncertainty rendering.** A claim carrying `event_time_earliest` and
`event_time_latest` renders as an interval; equal values render as an instant;
a missing pair renders as "time not stated" and never as `recorded_at`. The
recording time is a different fact and appears in its own column.

Landed at T45 in the object view's strip (`views/claims/TimelineStrip.tsx`),
which T49 grows into the full timeline. Three consequences of the rule, worth
stating because each is a thing the strip deliberately does *not* do: an
interval is never collapsed to its midpoint, an instant is drawn as a hairline
rather than a proportional bar so it cannot read as a very short interval, and
an untimed claim is listed below the axis with the reason rather than dropped.
`valid_from`/`valid_to` are the fallback when no event time is stated — a
validity window is also a statement about the world — but `recorded_at` never
is.

---

## 8. Test obligations

Each is a gate on a specific failure, not coverage for its own sake.

| Obligation | Layer | Proves |
|---|---|---|
| Every new route has a matrix row | contract | Article VI — the matrix asserts exact equality |
| Non-member gets 404 from every hypothesis/task/reference route, read **and** write | integration | §5 rule 1, no existence leak |
| A restricted case referencing an open entity produces a response identical to the no-case case | integration | H-18 |
| `open_hypothesis` with a whitespace-only `missing_info` is denied, and the denial is audited | integration | §3.3, spec 08 §6.4 |
| A revision records the full state, and history returns every version in order | integration | §3.1 |
| The same claim under both stances round-trips | integration | Article VIII |
| An as-of read excludes a claim recorded after the timestamp and carries all three stamps | integration | B-11 |
| A second-domain object type renders through the generic view with no new React | contract + e2e | Article XIV, charter exit 4 |
| The generated descriptors contain `display` and per-property labels for every object type | contract | §6.2 |
| Version mismatch between bundle and server raises the banner | e2e | §6.3 |
| No `public_route`-style exemption exists anywhere | contract | charter exit 5 |

Fixtures are fictional and deterministic (`data/sample/`), per the testing
rules. No real person appears in a hypothesis fixture — a fictional dataset is
the only honest place to write "we believe X did Y".

---

## 9. Exclusions

Phase 4 does not build, and no task may quietly add:

- **Comments, presence, review requests, collection requirements** — GOAL.md
  §31 collaboration stays north-star until a real second analyst exists.
- **A workflow engine, approval chains, or SLAs** on tasks (plan §2 trigger).
- **Sealing enforcement** — `case_file.status = 'sealed'` is declared and inert
  until P7.
- **Full multi-axis bitemporality** — §7 is the whole promise.
- **Hypothesis→claim promotion** — a hypothesis never becomes a claim in P4;
  finding promotion is P6 and goes through the review queue (Article VII).
- **Any projection of hypotheses or tasks.** They are operational state, not
  knowledge, and the graph must not render them.
- **The audit console** — P7 (ADR-045).
- **`ui_meta.json`** — ADR-043.

---

## 10. The H-19 remainder

P2 answered most of H-19 and spec 07 §2 records it: `oidc-client-ts` rather than
a hand-rolled state machine, tokens in an in-memory store, PKCE state in
sessionStorage because it must survive a redirect, refresh-token renewal (so the
CSP can say `frame-src 'none'`), `script-src 'self'` with no `unsafe-inline` and
no `unsafe-eval`, and logout through `signoutRedirect`.

Three items are genuinely open, and all three are small enough to land in T42:

1. **Session timeouts are not declared.** `infra/keycloak/aegis-realm.json`
   sets no `ssoSessionIdleTimeout` and no `ssoSessionMaxLifespan`, so the realm
   runs on Keycloak's defaults. H-19 asks for *specified* idle and absolute
   timeouts. Declare them explicitly and assert them in a contract test, so a
   later realm edit that drops them fails rather than degrades quietly.
2. **The CSRF model is nowhere written down.** It is sound —
   authentication is bearer-only (`HTTPBearer`), there is no cookie and no
   ambient credential, so a cross-site request carries no authority — but an
   unwritten security property is one a future change can remove without anyone
   noticing. Spec 03 gains the sentence and a test asserts no route accepts a
   cookie-borne identity.
3. **Multi-tab behaviour is unstated.** `monitorSession: false` and an
   in-memory user store mean each tab holds its own session; signing out in one
   tab does not sign the others out until their tokens expire. That is a
   deliberate consequence of "tokens never leave memory", and it should be
   written down rather than discovered.

None of these blocks a gate criterion. All three are verification debt, which is
the only kind of debt this project accepts on the record.
