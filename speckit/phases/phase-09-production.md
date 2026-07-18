# Phase 9 Charter — Production certification & scale-out

Status: charter (amended 2026-07-18, ADR-033 — the minimum operating baseline
moved to the roadmap's **pilot gate**; this phase certifies production) ·
tasks pre-authored: `../tasks/phase-09.md` (T102–T113; re-validated by T102 at
phase start, which also dispositions the 2026-07 review findings tagged P9:
B-16 full scope, H-31, H-32, H-33 remainder, H-37, M-22, M-23) ·
Constitutional basis: Articles X, XII, XIII · GOAL.md §33–35, §39 · absorbs
the v1 "P7 scale-out options" (ADR-022)

## Objective

Aegis runs as a certified, observable, recoverable service — and grows only
along measured pressure. The **pilot gate** (roadmap §Pilot gate) is a
prerequisite deployment gate satisfied whenever the first non-local/second-
user deployment happens; this phase is **production certification**: SLOs,
complete observability, automated DR over the full recovery boundary,
performance baselines, pen-test, and the **trigger-gated upgrade table**
where nothing ships until its documented trigger fires.

**Deployment tiers (H-32, binding).** dev → pilot (hardened single host,
pilot gate passed; availability limits documented) → production/agency (this
phase's certification; GOAL.md's multi-AZ/HA targets apply only here —
single-host compose is never called production).

## Architecture layers touched

- **Operations:** observability, SLOs, backup/DR automation, runbooks, CI/CD
  hardening.
- **Security:** hardening pass, secrets management, dependency/supply-chain
  scanning, pen-test checklist.
- **Scale (conditional):** the trigger table — storage, search, orchestration,
  deployment, federation.

## Deliverables — mandatory baseline

1. **Observability**: OpenTelemetry traces/metrics/logs from aegis-api and
   workers; Prometheus + Grafana dashboards (request latency, action rates,
   queue depth, projection staleness, audit-chain verification age); structured
   logs already exist (structlog) — they gain trace correlation.
2. **SLOs + alerting**: availability and latency targets for the API and
   projection freshness; alert rules with runbook links.
3. **Security hardening**: TLS everywhere in compose; secrets out of `.env`
   into compose secrets (Vault stays trigger-gated); dependency and container
   scanning in CI; JWKS/token lifetime review; rate limiting on auth
   endpoints; CIS-style host checklist.
4. **Backup/DR automation over the full recovery boundary (B-16)**: define
   the boundary explicitly — Postgres, vault **object versions + locks/legal
   holds**, Keycloak users/config (its database if local users are production
   state), FGA store identity, encryption keys — then automate: encryption is
   a property of the backup command (fail if it fails), manifest verification,
   off-host copy, scheduled restore rehearsal running audit-chain verify +
   FGA rebuild + projection rebuild against the restored copy; RPO/RTO,
   backup sequence + audit head recorded per run.
5. **Performance baseline**: load benchmarks on a defined workload manifest
   (fictional corpus generator; degree distribution, authorization filters,
   cache state, concurrency, query mix, hardware — M-23) reporting
   p50/p95/p99 warm/cold; **audit-chain append throughput under concurrent
   audited reads benchmarked with an SLO and overload policy** (H-37 — the
   ADR-015 escape hatch fires on these numbers, not anecdotes); the numbers
   that arm the trigger table get a measurement harness.
6. **Pen-test checklist + exercise**: authz matrix fuzzing, IDOR sweep across
   `/v1/*`, audit-evasion attempts, export-path leak tests — findings triaged
   as blocking/deferred with ADRs.
7. **Operational runbooks**: deploy, upgrade (incl. ontology migration),
   incident, restore, key rotation, user/role management.

## Deliverables — trigger-gated (build only when the trigger fires)

| Upgrade | Trigger (from decisions.md / plan §2) |
|---|---|
| Neo4j as primary traversal | ADR-002: CTE p95 > 2 s, traversal-dominant |
| OpenSearch | ADR-012: golden-set failure or corpus scale |
| Dagster orchestration | ≥ 3 scheduled pipelines |
| Iceberg/Trino event lake | DuckDB single-node limits |
| Kubernetes + GitOps | ADR-010: multi-host / agency cell |
| Temporal workflows | multi-day human approval chains |
| Kafka streaming | a real continuous feed exists |
| Vault + KMS | multi-user/agency deployment |
| Federation / sovereign cells (GOAL.md §33.1) | a real second agency |

Federation note: when (and only when) the second-agency trigger fires, the P7
disclosure-package *format* becomes the exchange payload; the protocol work
(originator control across organizations, signed exchange, federated queries)
is chartered then, as its own phase, against GOAL.md §27–28 and §33.

## Dependencies

- All prior phases for surface completeness, but baseline items can begin any
  time after P4 — observability and DR automation are welcome early; this
  charter gates the *exit*, not the start.

## Exit criteria

- [ ] Dashboards live; an induced fault (killed DB, stopped FGA) is visible in
      alerts within the SLO window and its runbook resolves it.
- [ ] Scheduled restore rehearsal has run ≥ twice unattended: restore →
      `aegis audit verify` → projection rebuild → snapshot compare, all green.
- [ ] Pen-test checklist executed; no unresolved blocking finding.
- [ ] Performance baseline published; every trigger row has an evidence type,
      owner, and observation cadence, and is evaluated against measured
      numbers — **a fired trigger yields a chartered work package; delivery
      is chartered separately, never implied by this gate** (H-31).
- [ ] A cold-start deploy from the runbook (fresh host → serving, restored
      data incl. Keycloak/FGA state) succeeds following only the document.

## Risks

| Risk | Mitigation |
|---|---|
| Premature scale-out ("we might need Neo4j") | Trigger table is contractual — Article XII discipline; benchmarks arm triggers, ambition doesn't |
| Observability drowns the solo operator | SLOs sized to the deployment; few alerts, each with a runbook |
| Hardening breaks dev ergonomics | compose profiles: dev stays loose, prod profile is hardened; CI runs both |
| DR rot after the drill | Restore rehearsal is scheduled and asserted in CI/cron, not remembered |

## Specs to author or update

- `specs/15-operations.md` — author at phase start (SLOs, alert catalog,
  runbook index, benchmark harness).
- `plan.md` §5 environments — prod profile details.

## Explicit non-goals

Anything in the trigger table whose trigger has not fired; multi-region;
compliance certifications (CJIS-style mappings are documented aspirations in
GOAL.md, not deliverables here).

## Task sketch (milestone level — T-file at phase start)

- **A — Observability:** OTel wiring, dashboards, SLOs, alerts.
- **B — Hardening:** TLS/secrets/scanning/rate limits, checklist.
- **C — DR:** scheduled backup + restore rehearsal automation.
- **D — Performance:** corpus generator, benchmark harness, trigger review.
- **E — Pen-test & runbooks:** exercise, triage, runbook set, cold-start
  drill.
