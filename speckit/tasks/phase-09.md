# Phase 9 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them; narrower dependencies are noted in the task text. Reference specs in
parentheses. Numbering continues from Phase 8 (T101).

> **Status: PRE-AUTHORED, NOT ACTIVE.** The mandatory-baseline tasks may begin any
> time after P4 — this charter gates the *exit*, not the start; observability and
> DR automation are welcome early. The trigger-table review (T109) needs the full
> surface for honest measurement. Authored 2026-07-18 ahead of phase start; T102
> re-validates this plan against the as-built system before any other task starts.
> Charter: `../phases/phase-09-production.md` · specs: `../specs/15-operations.md`
> (authored by T102), `../plan.md` §5 (prod-profile addendum).

## Milestone A — Observability

**T102. ⛓ Spec 15 + the SLO/alert catalog** (charter §Specs) — re-validate this
plan against the as-built system; author `specs/15-operations.md`: **SLO targets**
(API availability + latency, projection freshness), the **alert catalog** (each
alert names its runbook), the **runbook index**, and the **benchmark-harness**
definition; add the prod compose-profile details to plan §5. The catalog is sized
to the deployment — few alerts, each actionable (the solo-operator risk).
AC: spec 15 exists and defines SLOs, the alert catalog, the runbook index, and the
benchmark harness; plan §5 gains the prod-profile section; every alert in the
catalog names a runbook; divergences from this plan are ADR'd.

**T103. ⛓ OTel wiring + dashboards + SLOs + alerts** (specs/15; needs T102) —
OpenTelemetry traces/metrics/logs from aegis-api and workers, with the existing
structlog logs gaining **trace correlation**; Prometheus + Grafana dashboards
(request latency, action rates, queue depth, projection staleness, audit-chain
verification age); alert rules with runbook links firing within the SLO window.
AC: dashboards are live and show the charter's signals; an induced fault (killed
DB, stopped FGA) is visible in alerts within the SLO window and its runbook
resolves it (charter exit №1); logs carry trace IDs; every alert links to a
runbook.

## Milestone B — Hardening

**T104. ⛓ TLS, secrets & prod compose profile** (specs/15; charter §Security) —
TLS everywhere in compose; secrets moved out of `.env` into compose secrets (Vault
stays trigger-gated); a hardened **prod compose profile** distinct from the loose
dev profile, both exercised in CI; a CIS-style host checklist.
AC: the prod profile serves over TLS with secrets sourced from compose secrets,
not `.env`; dev ergonomics are unchanged under the dev profile; CI runs both
profiles; the host checklist is filled and any deferrals are ADR'd.

**T105. Dependency/container scanning + auth hardening** (specs/15; needs T104) —
dependency and container-image scanning wired as a CI gate; JWKS / token-lifetime
review; rate limiting on auth endpoints; supply-chain scanning recorded.
AC: CI fails on a seeded vulnerable dependency and a seeded vulnerable image layer;
auth endpoints reject beyond their rate limit; token lifetimes and JWKS rotation
are reviewed and recorded; the scan gate is documented.

## Milestone C — DR

**T106. ⛓ Backup automation** (specs/15; extends T15) — the Phase-1 backup drill
becomes scheduled and verified: automated `pg_dump` + MinIO mirror on a cadence,
with retention and an off-host copy per spec 15.
AC: a scheduled backup produces a restorable `pg_dump` and a MinIO mirror;
retention prunes correctly; a missed backup is itself an alert (T103 catalog); the
schedule is asserted, not remembered.

**T107. Restore rehearsal automation + verification** (specs/15; needs T106) —
restore rehearsal as scheduled automation: restore → `aegis audit verify` →
projection rebuild → snapshot compare, all green, run unattended; DR rot is caught
because the rehearsal is asserted in CI/cron, not remembered.
AC: the scheduled restore rehearsal has run ≥ twice unattended with all four steps
green each time (charter exit №2); a corrupted-backup fixture fails the rehearsal
loudly; the verification includes the audit-chain verify and a projection rebuild
against the restored copy.

## Milestone D — Performance

**T108. ⛓ Corpus generator + benchmark harness** (specs/15; charter §Performance)
— a realistic-corpus generator and a benchmark harness measuring graph-traversal
p95, search latency, and action throughput — the numbers that arm the trigger
table, produced by a harness, not anecdotes.
AC: the harness publishes graph-traversal p95, search latency, and action
throughput on a realistic corpus; runs are repeatable and versioned; the measured
numbers are the ones the trigger table reads (e.g. ADR-002's CTE p95 > 2 s).

**T109. Trigger-table review against measured numbers** (charter §Trigger-gated;
needs T108) — evaluate every trigger row in the charter / decisions.md against the
T108 measurements: each row is either **fired-and-delivered** or **documented
unmet** with its measured value; nothing ships on ambition (Article XII).
AC: every trigger row (Neo4j, OpenSearch, Dagster, Iceberg/Trino, Kubernetes,
Temporal, Kafka, Vault/KMS, federation) is dispositioned against a measured number
(charter exit №4); an unmet trigger is recorded with its value and revisit
condition; any fired trigger's delivery is chartered as its own work, never
smuggled in here.

## Milestone E — Pen-test & runbooks

**T110. Pen-test checklist + exercise** (specs/15; charter §Security; needs T104) —
execute the pen-test checklist: authz-matrix fuzzing, IDOR sweep across `/v1/*`,
audit-evasion attempts, export-path leak tests (reusing the P7 exclusion matrix);
findings triaged blocking/deferred with ADRs.
AC: the checklist is executed and findings triaged; no unresolved **blocking**
finding remains at phase close (charter exit №3); each deferred finding has an ADR
with a revisit condition; the IDOR sweep covers every `/v1/*` route.

**T111. Operational runbooks** (specs/15; charter §Runbooks) — the runbook set:
deploy, upgrade (including ontology migration), incident, restore, key rotation,
user/role management; each alert in the T102 catalog resolves to a runbook.
AC: every runbook in the spec 15 index exists and is executable by someone who did
not build the system; the ontology-migration runbook covers a major bump with
history copy + migration script; every alert links to a runbook that resolves it.

**T112. Cold-start deploy drill** (charter exit №5; needs T104, T106, T111) — the
owning task for the headline criterion: a cold-start deploy from the runbook —
fresh host → serving, with restored data — succeeds without tribal knowledge;
captured as evidence for the ops runbook.
AC: a fresh host reaches a serving, data-restored state from the runbook alone,
with no undocumented step (charter exit №5); the drill is repeatable; any
tribal-knowledge gap discovered is folded back into the runbook.

**T113. Phase exit review** — walk the charter's exit criteria; confirm the
mandatory baseline is complete and every trigger row is dispositioned; update
speckit docs where reality diverged; append ADRs; write
`../reviews/phase-09-exit-review.md`; tag `phase-9-production` per the git
workflow.
AC: all exit boxes checked or explicitly deferred with reason; the baseline is
complete and each trigger row is fired-and-delivered or documented-unmet.

## Explicit non-goals for Phase 9

Anything in the trigger table whose trigger has not fired; multi-region;
compliance certifications (CJIS-style mappings stay documented aspirations, not
deliverables); the federation *protocol* — only its P7 disclosure-package payload
format exists, and the protocol (originator control across organizations, signed
exchange, federated queries) is chartered when the second-agency trigger fires;
MLflow / model-registry infra (P8 trigger territory).
