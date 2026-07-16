# Spec 03 — Security: Identity, RBAC + ReBAC, Audit

Status: draft for Phase 1 · Constitutional basis: Articles VI, X · GOAL.md §23

RBAC is a **hard product requirement from Phase 1** — enforced even while one person
holds every role.

## 1. Identity (Keycloak)

- Realm `aegis`, OIDC; the API validates bearer JWTs via JWKS.
- Realm roles = global RBAC roles (below). Custom claim `clearance` = handling-code
  level (integer index into the ontology's ordered `handling_codes`).
- Local accounts now; the same OIDC seam later plugs into an agency IdP (ADR-004).

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

type compartment                         # Phase 6; type exists from day one
  relations
    define member: [user]
    define can_view: member

type evidence_item
  relations
    define case: [case]
    define custodian: [user]
    define can_view: can_view from case
    define can_transfer: custodian or can_approve from case
```

- Postgres is the **source of truth**; FGA tuples are a projection of `case_member` /
  evidence rows (ADR-014, Article XIII). Mutating actions write the row and an
  `authz_outbox` entry (specs/02 §4) in one Postgres transaction; a dispatcher drains
  the outbox into idempotent FGA writes/deletes, and `aegis authz rebuild` re-derives
  the full tuple set from Postgres. Grants fail closed while the outbox drains;
  revocations additionally attempt an inline best-effort FGA delete.
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
        sealed exclusions               (Phase 6)
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

## 6. Insider-threat & break-glass (Phase 6, designed now)

- Standing queries over `audit_log`: bulk reads, off-case access patterns, repeated
  lookups of the same person without case linkage, export volume.
- Break-glass: a special action granting time-boxed elevated access with mandatory
  reason + automatic supervisor/auditor notification + forced review record.
  The schema supports it from Phase 1 (`audit_log.detail`), the flow ships in P6.

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
