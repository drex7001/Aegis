# Spec 03 — Security: Identity, RBAC + ReBAC, Audit

Status: implemented in Phase 1 (v1 reference) — amendments in force: governed
`/v1/*` routes have no anonymous exemption, while the legacy read-only
`/api/*` surface remains a contained **temporary exception** until P2 T22
(ADR-026); **field-level sensitivity filtering** (§4 step 5) is a hard P2 gate
criterion (T24a), not deferred; **revocation staleness bound** documented by
T16b. · Constitutional basis: Articles VI, X · GOAL.md §23

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
| `supervisor` | everything analyst can + approve assessments, seal records (P6), manage case membership | alter audit |
| `auditor` | read audit log, read anything **including retracted/sealed** for review | any write except audit annotations |
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
  → route dependency authorize(action, object) → role gate + FGA check   → deny? 403 + audit
  → query layer row filters (always appended, never optional):
        handling_rank(row) <= user.clearance
        case scoping (member cases ∪ case-less rows)
        retracted_at IS NULL            (unless auditor)
        sealed exclusions               (Phase 7)
  → field filters: property sensitivity (ontology) > clearance ⇒ field omitted
  → audit(decision, purpose)
```

Rules:
1. **Deny by default** — a route without an `authorize` dependency fails CI (lint).
2. Enforcement is in actions/queries, never only the UI (GOAL.md §23.3).
3. Search returns ids; hydration re-applies filters (GOAL.md §11.6).
4. No count/existence leaks: filtered-out rows are invisible, not "3 hidden results"
   (GOAL.md §30).
5. Sensitive reads (handling ≥ `restricted`, exports, audit queries) require a
   `purpose` string, stored in the audit event (GOAL.md §12.4, scaled).

## 5. Audit (Article X)

Schema in specs/02 §5. Behaviors:

- Both allows and denies are logged; denials include the failed check.
- `aegis audit verify` recomputes the hash chain; scheduled + on-demand.
- Auditor UI/API can filter by actor, case, action, time — but querying audit is
  itself audited.
- Export events record destination and a manifest hash of what left the system.

## 6. Insider-threat & break-glass (Phase 7, designed now)

- Standing queries over `audit_log`: bulk reads, off-case access patterns, repeated
  lookups of the same person without case linkage, export volume.
- Break-glass: a special action granting time-boxed elevated access with mandatory
  reason + automatic supervisor/auditor notification + forced review record.
  The schema supports it from Phase 1 (`audit_log.detail`), the flow ships in P7.

## 7. Secrets & data protection (Phase 1 practical baseline)

- `.env` for dev; compose secrets for services; no credentials in git (existing
  `.gitignore` discipline).
- Postgres: app role with least privilege (no DDL at runtime; INSERT-only on
  `audit_log`); separate migration role.
- MinIO: separate buckets `raw-landing`, `evidence`, `exports`; bucket policies deny
  public; versioning on.
- Backups encrypted at rest (age/gpg) — the vault contains real names from public
  reporting; treat as `restricted` by default.
- TLS termination when the API leaves localhost (caddy/traefik in compose).

## 8. Threats considered (scaled STRIDE pass)

| Threat | Control |
|---|---|
| UI bypass straight to DB | enforcement in query layer + DB roles, not UI |
| Audit tampering | hash chain + INSERT-only grants + verify job |
| Wrong-merge poisoning (integrity) | Article V reversible clusters + adjudication audit |
| LLM prompt-injected fake claims | Article VII review queue; producer metadata shows model + source record |
| Credential theft | short JWT lifetimes, Keycloak brute-force protection, localhost binding in dev |
| Data exfil via exports | export action + manifest + audit; watermarking later (GOAL.md §23.7) |
