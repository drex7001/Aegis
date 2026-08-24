# Spec 03 — Security: Identity, RBAC + ReBAC, Audit

Status: implemented in Phase 1 (v1 reference), extended by Phase 7 (T78 —
§§6–13 are new or promoted). Amendments in force: governed `/v1/*` routes have
no anonymous exemption and the legacy `/api/*` surface was **deleted** at P2 T22
(ADR-026); **field-level sensitivity filtering** (§4 step 5) shipped at P2 T24a
in its **omit** mode and is generalized into the response-mode policy of §6;
**revocation staleness bound** documented by T16b. Phase 7's re-validation
divergences are recorded in `13-disclosure-packages.md` §0. · Constitutional
basis: Articles IV, VI, VIII, X · GOAL.md §21–24, §27 · ADR-061…ADR-066

RBAC is a **hard product requirement from Phase 1** — enforced even while one person
holds every role.

## 1. Identity (Keycloak)

- Realm `aegis`, OIDC; the API validates bearer JWTs via JWKS.
- Realm roles = global RBAC roles (below). Custom claim `clearance` = handling-code
  level (integer index into the ontology's ordered `handling_codes`).
- Local accounts now; the same OIDC seam later plugs into an agency IdP (ADR-004).

### 1.1 Session lifetimes (T42, closing H-19)

Declared in `infra/keycloak/aegis-realm.json`, not inherited. The realm set none
of these until T42, so it ran on whatever the running Keycloak version happened
to default to — which is not a policy, it is an accident that happened to be
reasonable. `tests/contract/test_session_policy.py` fails if any is dropped.

| Setting | Value | Why |
|---|---|---|
| `ssoSessionIdleTimeout` | 30 min | Long enough that a break does not lose work |
| `ssoSessionMaxLifespan` | 8 h | A machine left signed in overnight is not still authorized in the morning |
| `accessTokenLifespan` | 5 min | Bounds what a captured token is worth; the workspace renews from the refresh token, so the user never sees it |
| `clientSessionIdleTimeout` / `clientSessionMaxLifespan` | 30 min / 8 h | The same bounds applied per client, so a long-lived SSO session cannot outlive them |

The `RememberMe` variants are pinned to the same numbers rather than left
unset — an unset value there silently reverts to the default and quietly
undoes the policy for anyone who ticks the box.

These bound the **SSO session**, not the API. Aegis validates a bearer token on
every request and issues no session of its own, so signing out of Keycloak does
not retroactively invalidate an access token already minted; the five-minute
lifespan is what bounds that window.

### 1.2 There is no ambient credential — the CSRF model (T42, closing H-19)

Every governed route authenticates with `Authorization: Bearer <jwt>`
(`HTTPBearer`, `aegis/api/auth.py`). Aegis sets **no** authentication cookie,
reads none, and has no session store. A cross-site form post or image tag
therefore carries no authority: the browser attaches cookies automatically, and
an `Authorization` header never.

This is why the API needs no CSRF token, no double-submit cookie, and no
`SameSite` policy of its own — the class of attack is absent rather than
mitigated. It is also a property that a single well-meaning change could remove,
so it is asserted rather than assumed:
`tests/contract/test_session_policy.py` fails if any route declares a cookie
security scheme or reads a cookie parameter.

The workspace holds tokens in memory and the PKCE verifier in `sessionStorage`
(spec 07 §2). Neither is reachable cross-origin, and neither is sent
automatically.

### 1.3 Multi-tab behaviour

Each browser tab holds its own in-memory user store, and `monitorSession` is
off. Two consequences, stated because they are consequences of a decision and
not oversights:

- **Signing out in one tab does not sign out the others.** They keep working
  until their access tokens expire (≤ 5 min) and their refresh fails.
- **A reload re-authenticates** through the SSO session rather than restoring a
  token, because tokens are never persisted (spec 07 §2).

The alternative — a shared, persisted token store — is what "tokens never leave
memory" exists to forbid, so this is the accepted cost, bounded by the token
lifespan above.

## 2. Roles (RBAC)

| Role | May (summary) | May not |
|---|---|---|
| `analyst` | record/retract claims, review suggestions, adjudicate identities, run analytics, manage own cases | manage users, alter audit, seal records |
| `investigator` | record claims, register evidence, custody events, case work | adjudication of identities (Phase 2 opens per-config) |
| `evidence_officer` | evidence registration, custody transfers | claim writes |
| `supervisor` | everything analyst can + approve assessments, seal records (§8), manage case membership, disclosure grants and packages (spec 13) | alter audit |
| `auditor` | read audit log, read anything **including retracted/sealed** for review — but never a compartment they are not a member of (§9) | any write except audit annotations |
| `admin` | users, roles, ontology deploys, infra | **read intelligence content** (GOAL.md §39: admins ≠ content access) |

Role checks come from the JWT; they answer "*can this kind of user ever do this?*"

## 3. Relationships (ReBAC — OpenFGA)

FGA answers "*may this user do it to this object?*" `infra/fga/model.fga`:

```
model
  schema 1.1

type user

type case
  relations
    define supervisor: [user]
    define investigator: [user]
    define analyst: [user]
    define member: investigator or analyst or supervisor
    define can_view: member or auditor_grant
    define can_edit: investigator or analyst or supervisor
    define can_approve: supervisor
    define auditor_grant: [user]        # explicit, logged auditor attachment

type compartment                         # Phase 7; type exists from day one
  relations
    define member: [user]
    define can_view: member

type evidence_item
  relations
    define case: [case]
    define custodian: [user]
    define can_view: can_view from case
    define can_transfer: custodian or can_approve from case

type hypothesis                          # T43; spec 09 §5
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

- **Hypotheses and tasks have no authorization of their own.** Each belongs to
  exactly one case and derives both permissions from it, exactly as
  `evidence_item` does — there is no direct user grant, so a hypothesis cannot
  be shared past its case. Their routes answer **404 for a non-member on writes
  as well as reads**: a 403 on a write discloses that the case exists just as
  surely as one on a read (spec 09 §5 rule 1).
- What runs at request time is a check on the **parent case**: the route loads
  the row, reads its `case_id`, and asks `can_view`/`can_edit` on `case:{id}` —
  which is precisely what the derivations above compute, so no tuple is written
  per hypothesis or task and none is needed. The types are declared for the same
  reason `compartment` is: when a direct check becomes meaningful (P7 sealing,
  per-resource compartments) the model is already there and already means this.
- **`compartment` goes live in Phase 7, but not as a row filter.** Its tuples are
  a projection of `compartment_member` and answer route-level questions ("may
  this user administer compartment C"). Which *rows* a caller may read is decided
  in Postgres, inside `claim_filters`, from canonical membership — ADR-062, §7.2.
  The reason is M-15: the outbox is asynchronous, so a revocation still draining
  would otherwise authorize reads that canonical state already refuses.
- A **case reference** (`case_reference`, ADR-044) has no FGA type because it
  confers nothing. `claim.case_id` remains the claim's immutable recording
  scope and the only case field `claim_filters` consults; referring to a claim
  from a case never re-scopes it, and reference lists are built from targets
  the caller can already read.

- Postgres is the **source of truth**; FGA tuples are a projection of `case_member` /
  evidence rows (ADR-014, Article XIII). Mutating actions write the row and an
  `authz_outbox` entry (specs/02 §4) in one Postgres transaction; a dispatcher drains
  the outbox into idempotent FGA writes/deletes, and `aegis authz rebuild` re-derives
  the full tuple set from Postgres. Grants fail closed while the outbox drains;
  revocations additionally attempt an inline best-effort FGA delete **after** the
  Postgres transaction commits. An inline FGA failure does not undo or misreport the
  canonical revocation; its queued delete remains the convergence guarantee.
- The API's in-process dispatcher starts a batch immediately at startup and then on a
  fixed start-to-start interval. The default
  `AEGIS_AUTHZ_OUTBOX_INTERVAL_SECONDS=5` (batch size 100) gives a maximum **polling**
  staleness of 5 seconds when FGA is healthy and no earlier row blocks the ordered
  drain; the delete request's processing time is additional. T16b's deterministic
  cadence probe scales the interval to 50 ms and requires the next attempt within
  200 ms; it passed on 2026-07-18. Every successful batch logs
  `max_delete_staleness_seconds`, measured from outbox insertion to FGA convergence.
  There is deliberately no false finite end-to-end bound while FGA is unavailable or
  an older outbox row is blocked: recovery begins on the first healthy ordered drain,
  and operators use that logged maximum to detect a breached revocation window.
- Claims/evidence inherit case scoping; **case-less claims** (general OSINT pool) are
governed by role + handling code only — an explicit, documented choice for the
  OSINT deployment; agency deployments can require `case_id NOT NULL` by config.

## 4. Enforcement pipeline (every request)

```
JWT → user ctx (id, roles, clearance)
  → route dependency authorize(roles, purpose_required)  → deny? 403 + audit
  → object-level FGA check in the handler that knows the object → deny? 404
  → effective policy state (§9): clearance, member cases, compartments,
        active break-glass elevation (§10) — all read from Postgres, per request
  → query layer row filters (always appended, never optional):
        handling_rank(row) <= effective.clearance
        case scoping (member cases ∪ case-less rows)
        compartment scoping (§7)        — no compartment, or caller is a member
        judicial state (§8)             — sealed excluded unless auditor
        field sensitivity               — a claim above clearance is not a row
        retracted_at IS NULL            (unless auditor)
  → response mode (§6): omit | marked | counts, per resource class
  → audit(decision, purpose)
```

Rules:
1. **Deny by default** — a route without an `authorize` dependency fails CI (lint).
2. Enforcement is in actions/queries, never only the UI (GOAL.md §23.3).
3. **A row the caller may not read is absent from the scan, not removed from the
   answer** (B-17). Anything that selects candidates composes the filters; search
   and object sets share `visible_entity_ids` for exactly this reason.
4. No count/existence leaks by default: filtered-out rows are invisible, not
   "3 hidden results" (GOAL.md §30). §6 is the *narrow, enumerated* set of places
   that rule is relaxed, and why.
5. Sensitive reads (handling ≥ `restricted`, exports, audit queries) require a
   `purpose` string, stored in the audit event (GOAL.md §12.4, scaled). From
   Phase 7 the purpose is a **vocabulary term**, not free text (§13, ADR-065).
6. **Postgres decides rows; FGA decides routes.** FGA is an asynchronous
   projection (ADR-014), so a lagging revocation must never be the thing standing
   between a caller and a row (M-15, ADR-062).

### 4.1 What "field-level filtering" means when a property is a claim

Step 5 shipped at P2 T24a and is not deferred debt. Its implementation is worth
stating precisely, because the usual mental model — "null out a column" — does
not apply here.

Aegis stores properties **as claims**. `aegis/authz/filters.py` resolves a
predicate to the ontology sensitivity it carries (declared first, ADR-047; then a
documented heuristic), collects every predicate above the caller's clearance, and
adds `NOT (claim.predicate IN forbidden)` to `claim_filters`. The consequence is
that a sensitive property does not arrive as a redacted field — it does not
arrive as a **row**, which takes its value, its predicate, its grading, its
relations and its provenance out together.

`hidden_entity_types` closes the matching hole for display titles: an entity
whose *title* property is above the caller's clearance cannot be returned as an
id-shaped node with a missing name, because that would disclose the field's
existence. Claims touching such an entity are absent.

This is the **omit** mode. §6 defines when a resource class gets one of the other
two instead.

## 5. Audit (Article X)

Schema in specs/02 §5. Behaviors:

- Both allows and denies are logged; denials include the failed check.
- `aegis audit verify` recomputes the hash chain; scheduled + on-demand.
- Auditor UI/API can filter by actor, case, action, time — but querying audit is
  itself audited.
- Export events record destination and a manifest hash of what left the system.

## 6. Response modes (H-25, ADR-061)

H-25 found a contradiction that was real: §4 rule 4 says a withheld row is
absent, and the pre-amendment P7 plan said a withheld field is marked. Both are
right somewhere and neither is right everywhere, and until now the policy that
chooses between them did not exist.

There are exactly three modes. There is no fourth, and adding one is a spec
change, not a configuration change.

| Mode | The caller learns | Shape |
|---|---|---|
| `omit` | nothing — the row or claim is not there | absence |
| `marked` | that a claim of *this predicate* exists and they may not read it | `{predicate, withheld: true}` |
| `counts` | how many were withheld, by reason | `{reason, resource, count}` |

### 6.1 What a marker may carry (ADR-061)

A marker names **the predicate and nothing else**. Not the value, not the count,
not the grading, not the claim id, not the source, not the time. The reason is
that each of those is separately disclosive: a count tells you how many aliases a
person has, a grading tells you how well corroborated the thing you cannot read
is, and an id is a handle to ask a different surface about.

The shape is the one that already exists. `aegis/sets/sharing.py` returns
`{property, op, value: null, withheld: true}` for an object-set filter above the
reader's clearance (T70), and the policy adopts it rather than inventing a second
vocabulary for the same idea.

**A marker is a disclosure and is only ever used where policy says so.** Marking
`has_nic: withheld` on a person's object view tells the reader that person has a
national identifier on file — which is information. That is why `marked` is
assigned per resource class below, and why the default stays `omit`.

### 6.2 The policy table

Per resource class and read action. This table is the specification; the
implementation reads it from one place and a contract test asserts every read
surface in §12 resolves to a row in it.

| Resource class | Mode | Why |
|---|---|---|
| Search results | `omit` | Exploratory. A marker here is a search index of what exists but is hidden |
| Graph expansion / paths | `omit` | An edge held up by one open and one restricted claim must look exactly like an edge held up by the open claim alone |
| Object views (entity 360) | `marked` | The caller is authorized to know the *schema* of the object they are looking at — this is H-25's exact test — and an unmarked gap reads as "nothing recorded", which is a different and false statement |
| Claim detail / provenance | `omit` | The row either is readable or is not; there is no schema to disclose separately |
| Object-set definitions | `marked` | Shipped at T70; removing a node would misdescribe the set, whose evaluation still uses it |
| Geo features | `marked` | The withheld-geometry carryover from P5. A place with a claim you may not read is not a place with no geometry |
| Timeline | `omit` | Same argument as search: a marked gap on a time axis is a pointer to when something happened |
| Analytics findings | `omit` | A finding is computed from the claims the caller may read; there is no partial finding to mark |
| Alerts | `omit` | Already the rule (T75): an alert whose firing claims are unreadable is absent, not redacted |
| Audit records | `marked` | The auditor is authorized to know that an event occurred even where its detail is compartmented |
| Disclosure packages | `counts` (grant-selectable) | The recipient is a disclosure counterparty assessing completeness — spec 13 §10 |
| Export previews | `counts` | Categories and counts, never values (GOAL.md §24) |

**`counts` exists in two places only**, both of them disclosure, both of them
requiring an explicit grant or the supervisor role. It is not available to
ordinary reads at any clearance.

### 6.3 Nested fields, sorting and filtering (H-25)

Three rules that are easy to get right in the renderer and wrong in the query:

1. **A nested field inherits the mode of its parent resource class**, never its
   own. A claim rendered inside an object view is marked; the same claim fetched
   from `/v1/claims/{id}` is absent. The mode is a property of the surface, not
   of the row.
2. **Withheld content never participates in sorting.** Sorting a list by a field
   the caller cannot read leaks its ordering, which for a small list leaks the
   value. A sort key above the caller's clearance is rejected with 422, not
   silently ignored — silently ignoring it returns a differently-ordered list
   that looks like an answer.
3. **Withheld content never participates in filtering, and a filter on it is
   rejected the same way.** `?predicate=has_nic` from a caller who may not read
   `has_nic` is a 422. Returning an empty list would be an oracle: empty means
   "none", and the caller cannot tell it from "none you may see".

## 7. Compartments (H-26, ADR-062)

The FGA `compartment` type has existed since Phase 1 and has never been queried.
Phase 7 makes it live — and the first decision is that **FGA is not where a
compartment is enforced**.

### 7.1 Canonical model

Postgres is the source of truth (Article XIII, ADR-014):

| Table | Holds |
|---|---|
| `compartment` | id, name, description, `created_by`, `created_at`, `closed_at` |
| `compartment_member` | compartment, user, role (`member`/`handler`), `granted_by`, `granted_at`, `expires_at`, `revoked_at`, reason |
| `compartment_assignment` | compartment, `resource_type`, `resource_id`, `assigned_by`, `assigned_at`, `removed_at` |

Grants are **versioned and expiring**: a membership row is never updated in
place, so "who could see this on the day it was disclosed" is answerable. An
expired membership is inert without anything having to run — `expires_at` is
compared at request time, exactly as break-glass is (§10).

### 7.2 Enforcement

Compartment scoping is a condition inside `claim_filters`, composed **with** the
handling-code condition and never instead of it:

```
NOT EXISTS (assignment for this claim)
  OR  assignment.compartment IN (caller's current, unexpired memberships)
```

Three properties fall out of writing it this way:

- **Default off.** With no compartments defined, the `NOT EXISTS` is true for
  every row and the entire existing test suite passes unchanged. That is T80's
  acceptance criterion and it is a structural consequence, not a promise.
- **Composes, never replaces.** A compartment member still cannot read above
  their clearance, and a cleared non-member still cannot read the compartment.
  Both conditions are `AND`-ed; neither is an escape hatch for the other.
- **Absent from the scan.** A compartmented row is filtered where candidates are
  chosen, so it is invisible to search, sets, analytics, projections and exports
  by the same mechanism, rather than by nine separate mechanisms (§12).

### 7.3 The FGA projection, and what it is for

`compartment_member` rows project to FGA tuples through the existing
`authz_outbox`, and `aegis authz rebuild` re-derives them. The projection exists
so **route-level** checks — "may this user open the compartment admin screen for
compartment C" — can be expressed the same way case checks are.

It is never consulted for a row. ADR-062 is the decision and M-15 is the reason:
the outbox is asynchronous, and a revocation that has not yet drained would
otherwise authorize reads that canonical state already refuses.

### 7.4 The informant pattern (T81) and what it is not (H-27)

A protected source is modelled as **two objects**: a pseudonym entity, which is
what every ordinary surface sees, and an identity entity, which is assigned to a
handler compartment. The link between them is a claim **inside the compartment**,
so it is filtered by §7.2 like any other compartmented row — the linkage is not a
special case, it is a row.

Consequences, all tested with synthetic data regardless of whether real informant
data ever exists:

- Every role except a compartment handler sees the pseudonym. **Including
  `admin`** — GOAL.md §39 already says administrators are not content readers,
  and this is the sharpest instance of it.
- No projection, no search index and no export contains the linkage, because none
  of them bypasses `claim_filters`.
- The audit trail records **that** the linkage was read, by whom and why, without
  restating the identity in `audit_log.detail`.

**This is a compartment prototype, not GOAL.md §21's protected-source boundary
(H-27).** A separate security domain with separate keys, two-person disclosure
approval, alerting to an independent supervisor, and export disabled except by
formal workflow all remain north-star. A flag in the same database, protected by
the same filters, defended by the same process, is not an equivalent control, and
this spec does not claim it is.

## 8. Judicial states: sealed and expunged (GOAL.md §22, ADR-063, ADR-064)

### 8.1 What a seal attaches to

`seal_record` has been declared in the platform ontology since 0.3.0 with
`resource_id: {type: identifier}` and no statement of what kind of resource. It
takes both, because they mean different things:

| Sealing a… | Reaches |
|---|---|
| `source_record` | the record, its derivatives, and **every claim recorded from it** |
| `claim` | that claim only — never its siblings from the same record |

A `judicial_state` table holds `(resource_type, resource_id, state, reason,
authority_ref, sealed_by, sealed_at, unsealed_by, unsealed_at)`. State is
`sealed` or `expunged`; absence is the normal case and costs nothing.

### 8.2 Excluded at source, never at render

A sealed row is excluded in `claim_filters` — the same place compartments and
handling codes are — and therefore in every projection **rebuild**, because
projections are built from claims (Article XIII). This is the difference between
"the map does not draw it" and "the map never received it", and only the second
survives someone writing a tenth read surface.

The auditor role sees sealed rows, with full history, and the read is audited
with a purpose. That is the one exception, it is a role, and it is the same
exception that already exists for retracted claims.

**A projection rebuilt after a seal contains no trace of the record** — not a
row, not an id, not a count. Tested by rebuilding and diffing, not by reading the
render path.

### 8.3 Expungement is destruction, and it is not reversible (H-26, ADR-064)

The charter said "reversible only by policy". That phrase is retired here.
Reversible destruction is not destruction; if the bytes are still recoverable it
is suppression, and suppression is what §8.2 already provides.

So the two are separated:

| | Sealing | Expungement |
|---|---|---|
| Content | retained | destroyed — claim values, excerpts, and vault objects |
| Reversible | yes, by the same authority | **no** |
| Auditor sees content | yes | no — the content is gone |
| What remains | everything | a **tombstone**: ids, timestamps, the authority, the actor, the hash chain |
| Precondition | supervisor + reason | supervisor + reason + a named `authority_ref` that resolves to a valid legal authority (§13) |

The tombstone is what keeps Article X true: the audit chain must still verify
after an expungement, so the audit rows are not deleted and the chain is not
re-computed. An expungement removes content; it does not remove the record that
content once existed and was destroyed on a stated authority.

**Expungement without its precondition is rejected and the attempt is audited.**
It is never a default, never a cascade of a retraction, and never something a
scheduled job does — including retention disposition (§13.3), which proposes and
never destroys.

## 9. The precedence matrix (H-26)

When two rules disagree about one row, this table decides. It is written as
tests, not as prose in a review.

| Situation | Outcome |
|---|---|
| Handling code above clearance | **Deny.** No role overrides clearance except as §10 elevates it |
| Compartment, caller not a member | **Deny**, at every clearance, including `admin` and `supervisor` |
| Compartment, caller a member, handling above clearance | **Deny** — compartments compose, never substitute |
| Sealed, caller not `auditor` | **Deny** |
| Sealed, caller `auditor` | **Allow**, audited, purpose required |
| Sealed **and** compartmented, caller `auditor` but not a member | **Deny.** A seal exception is not a compartment exception |
| Expunged, any caller | **Deny** — there is nothing to allow |
| Legal hold active | **Blocks disposition and expungement**; does not widen any read |
| Break-glass active (§10) | Raises clearance within its scope; **never** grants a compartment, and never unseals |
| `admin` role | Never a content read. Administers users, roles, ontology, infra |
| `auditor` role | Reads retracted and sealed content; **no** write except audit annotations; not a compartment member by virtue of the role |
| Handler (compartment role) | Reads the compartment's rows at their own clearance; holds no other elevation |

Two rules stated in the negative, because both are the tempting shortcut:

- **No role is a superuser.** There is no combination of roles that reads
  everything, and the matrix has no row that says so.
- **Elevations do not compose into one.** Break-glass plus auditor is
  break-glass and auditor, each within its own scope; it is not a third, wider
  thing.

## 10. Break-glass (M-21, ADR-066)

Emergency access, as a **canonical, time-boxed, reasoned elevation**.

`break_glass_grant` holds `(grant_id, user, scope, reason, requested_at,
expires_at, revoked_at, reviewed_by, reviewed_at, review_outcome)`.

- **A reason is mandatory** and is a substantive one — the same
  `required_text_is_substantive` criterion the actions layer already applies
  elsewhere (spec 08 §6.4). "urgent" is rejected.
- **Scope is narrow and explicit**: a clearance ceiling, and optionally a case.
  Never a compartment (§9), never a seal exception.
- **Expiry is enforced at request time from Postgres.** The effective policy
  state in §4 is computed per request, and an expired grant contributes nothing.
- **No FGA tuple is ever written** (ADR-066). M-21 asked that tuple cleanup be
  maintenance rather than enforcement; going further and writing none at all
  means there is no stale tuple to fail open, and the exit test proves it by
  seeding one by hand and still being denied.
- **Every use notifies the auditor** and creates a mandatory review record. An
  unreviewed use is surfaced at phase close and by §11's queries.
- **Declaration and use are both audited**, with the grant id on every request
  that used it, so "what did this elevation actually read" is one query.

## 11. Insider-threat queries & the auditor console (T87, ADR-045)

The auditor's oversight kit is a set of standing queries over `audit_log`,
surfaced in a workspace screen reachable only by the `auditor` role. ADR-045
moved this console out of Phase 4 and named Phase 7; this is where it lands.

| Query | Signal |
|---|---|
| Bulk reads | Read volume per actor per window, above a configured threshold |
| Off-case access | Reads of case-scoped rows by an actor with no membership in that case |
| Repeated subject lookups | The same entity read repeatedly by one actor with no case linkage |
| Export anomalies | Package size, count, or handling ceiling outside the actor's norm |
| Break-glass | Every declaration; unreviewed uses first |
| Unacknowledged disclosures | Packages past their acknowledgement interval (spec 13 §8) |

Two constraints on the whole kit:

- **The queries read audit metadata, never protected content.** An oversight tool
  that displayed the rows an analyst read would be a way to read them.
- **Querying audit is itself audited** (§5), including from this screen. The
  auditor is inside the system, not above it.

## 12. The read-surface inventory (T78)

The frozen list of every path by which data leaves the store. **A read surface
not on this list is a defect.** Every exclusion test in this phase is driven by
it, and T88's matrix is this list × {compartmented row, sealed record, restricted
field}.

### 12.1 API read surfaces

| Surface | Route(s) | Filter path | Mode (§6.2) |
|---|---|---|---|
| Entity object view | `GET /v1/entities/{id}` | `claim_filters` | `marked` |
| Entity cases / identity history / why-connected | `GET /v1/entities/{id}/…` | `claim_filters` | `omit` |
| Claim detail | `GET /v1/claims/{id}` | `claim_filters` | `omit` |
| Provenance | `GET /v1/claims/{id}/provenance` | `claim_filters` | `omit` |
| Search | `GET /v1/search` | `visible_entity_ids` + `claim_filters` | `omit` |
| Graph expand / paths | `POST /v1/graph/*` | `claim_filters` (correlated EXISTS) | `omit` |
| Analytics run / findings | `POST /v1/analytics/*`, `GET /v1/findings*` | `claim_filters`, `visible_entity_ids` | `omit` |
| Object sets — definition | `GET /v1/object-sets/{id}` | `redact_definition` | `marked` |
| Object sets — evaluation | `POST /v1/object-sets/{id}/evaluate` | `claim_filters` | `omit` |
| Geo features | `GET /v1/geo/locations`, `/v1/geo/events` | `claim_filters` | `marked` |
| Timeline | `GET /v1/timeline` | `claim_filters` | `omit` |
| Alerts | `GET /v1/alerts` | claim-derived visibility | `omit` |
| Watchlists | `GET /v1/watchlists` | owner-scoped | `omit` |
| Cases, hypotheses, tasks | `GET /v1/cases…`, `/v1/hypotheses…`, `/v1/tasks` | FGA on the parent case | `omit` |
| Source records & derivatives | `GET /v1/source-records…` | record handling + judicial state | `omit` |
| Sources | `GET /v1/sources` | none today — a `source` row carries no handling code; its **records** do | `omit` |
| Evidence | `GET /v1/evidence/{id}` | FGA on the case + custody | `omit` |
| Review queue | `GET /v1/review-queue` | record handling code | `omit` |
| Identity candidates | `GET /v1/identity/candidates` | `claim_filters` | `omit` |
| Ontology vocabulary | `GET /v1/ontology/vocabulary` | none — schema, not content | n/a |
| Audit | `GET /v1/audit` | auditor role + purpose | `marked` |
| Disclosure preview | `POST /v1/disclosure/preview` | grant + `claim_filters` | `counts` |
| Disclosure package | `POST /v1/disclosure/packages/{id}/export` | grant + `claim_filters` | `counts` |

### 12.2 Non-API egress (M-20)

These are not routes and no lint sees them. They are listed because pretending
they do not exist is what M-20 objected to.

| Path | Who can reach it | Constraint |
|---|---|---|
| CLI (`aegis …`) | Anyone with a shell on the host and database credentials | Operator-trust boundary, not an authorization boundary. Documented, not claimed to be enforced |
| Direct Postgres access | Same | Least-privilege app role; DDL and audit writes separated (§14) |
| Object store (MinIO) | Same | Bucket policies deny public; versioning on; Object Lock at the pilot gate |
| Backups | Operator | Encrypted at rest; restore drill; contains everything, including sealed rows |
| Application logs | Operator | **Never log claim values, excerpts, or geometry.** Asserted by a test over the logging helpers |
| Projection tables | Anything with database access | Rebuildable caches; sealed and compartmented rows are excluded at build (§8.2) |
| Workspace bundle (`ui/dist`) | Any authenticated user | Static assets only; contains no data |
| OpenAPI document | Any authenticated user | Schema, not content |

### 12.3 The lint's narrower job

A CI test enumerates the application's routes and fails when a route that
returns records is not registered in §12.1. It found its first gap the day it
was written: `GET /v1/sources` was not on the list, because the list was written
by reading the interesting surfaces rather than by reading the router. This does not prove packages are the
only bulk path (§9 of spec 13 explains why nothing could). It proves the smaller
and still worthwhile thing: **a new read surface cannot be added silently**, and
T88's matrix therefore cannot go stale without CI noticing.

## 13. Governance enforcement — legal authority, purpose, retention (B-08)

P2 T24a placed the seams and left them inert, "stored and displayed, never
consulted by a read path or a filter". Phase 7 consults them.

### 13.1 Legal authority is a governance record, not an ontology object (ADR-065)

A `legal_authority` table holds `(authority_id, kind, reference, description,
valid_from, valid_to, recorded_by, recorded_at)`. `source_record.authority_ref`
and `collection_policy_ref` resolve into it; `watchlist_alert.authority_ref` and
spec 13's `legal_basis` resolve into the same table.

It is deliberately **not** an ontology object type. An ontology object is an
entity whose attributes are claims — gradeable, retractable, contradictable, and
governed by the very filters this record governs. A control that can be
contradicted by a source is not a control.

**Fail closed on expiry.** A read that depends on an authority whose window has
closed is denied, not degraded — with the denial audited and naming the expired
authority. What was recorded while the authority was valid stays recorded and
stays readable: Article I means we do not rewrite history when a policy lapses,
and spec 13 §7 carries the same honesty into a package.

### 13.2 Purpose becomes a vocabulary (ADR-065)

`purpose` is a required string on sensitive reads today and is not checked
against anything. Phase 7 adds a `purposes` registry to the **platform ontology
module** — a minor version bump through the P3 proposal workflow — and the
`authorize` gate rejects a purpose outside it.

This is what T85's "the ontology gains the object via the proposal workflow"
should have said: the vocabulary is platform governance (Article XIV), and it is
the thing policy actually evaluates. A grant permits purposes; an authority
permits purposes; a mismatch is a denial with both sides named.

### 13.3 Retention classes and disposition

`source_record.retention_class` resolves to a class with a review interval and a
disposition rule. The workflow is **proposal only**:

- A scheduled evaluation produces a **disposition queue** of records past their
  review date. It destroys nothing.
- A supervisor dispositions each one: retain (with a new review date), seal, or
  expunge (§8.3, with its authority precondition).
- **A legal hold blocks disposition entirely**, and the hold is visible on the
  queue entry with its authority.

Automatic destruction is not implemented and is not a configuration option. H-26
asked that legally-required destruction be a named policy decision rather than a
default, and the honest implementation of that is a human in the loop.

### 13.4 The deployment policy profile

A `docs/POLICY_PROFILE.md` states, per control, whether the solo-OSINT profile
relaxes it and why: compartments default off, no informant data exists, one
person holds every role, break-glass is available but has no second person to
notify, signing keys live on the same host as the application. The point is that
"relaxed" is written down, so a pilot deployment inherits a list to close rather
than an assumption to discover.

## 14. Secrets & data protection (Phase 1 practical baseline)

- `.env` for dev; compose secrets for services; no credentials in git (existing
  `.gitignore` discipline).
- Postgres: app role with least privilege (no DDL at runtime; INSERT-only on
  `audit_log`); separate migration role.
- MinIO: separate buckets `raw-landing`, `evidence`, `exports`; bucket policies deny
  public; versioning on.
- Backups encrypted at rest (age/gpg) — the vault contains real names from public
  reporting; treat as `restricted` by default.
- TLS termination when the API leaves localhost (caddy/traefik in compose).

## 15. Threats considered (scaled STRIDE pass)

| Threat | Control |
|---|---|
| UI bypass straight to DB | enforcement in query layer + DB roles, not UI |
| Audit tampering | hash chain + INSERT-only grants + verify job |
| Wrong-merge poisoning (integrity) | Article V reversible clusters + adjudication audit |
| LLM prompt-injected fake claims | Article VII review queue; producer metadata shows model + source record |
| Credential theft | short JWT lifetimes, Keycloak brute-force protection, localhost binding in dev |
| Data exfil via exports | export action + manifest + audit; watermarking later (GOAL.md §23.7) |
