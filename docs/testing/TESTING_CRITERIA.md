# Testing Criteria and Quality Gates

## Definition of Done

A feature or fix is complete only when:

- acceptance criteria are mapped to automated tests at the appropriate layers;
- success, invalid input/failure, and regression paths pass;
- authorization, audit, provenance, review-queue, rollback, and idempotency
  paths are covered wherever applicable;
- test data is fictional and deterministic;
- fast, affected integration/system, coverage, and ontology commands are green;
- no unexplained skip, warning, flaky retry, or weakened assertion is added;
- documentation, manual procedure, and traceability status are updated when the
  user-visible workflow or phase gate changes.

The PR description records commands and results. A test gap is acceptable only
when it is non-blocking, explicitly justified, owned, and scheduled. A
constitutional or phase-exit gate cannot be deferred without a superseding ADR.

## Coverage policy

Coverage is measured over `aegis/` with line and branch tracking. The first
green reorganized full-suite run on Linux CI measured 80.88% combined coverage,
so CI enforces the rounded-down initial 80% repository floor. It must never
decrease; raise the floor when sustained coverage improves.

Long-term expectations are at least 90% line coverage and 80% branch coverage.
New and materially changed behavior should meet those levels in its owning
modules. Constitutional invariants and phase-gate acceptance criteria require
complete behavioral coverage regardless of aggregate percentages.

Excluded code requires a narrow `# pragma: no cover` plus review justification;
generated code, unreachable defensive branches, and platform guards are the
only normal candidates.

## Gate criteria

| Gate | Required evidence |
|---|---|
| Pull request | Fast suite, affected integration/system suites, requirement mapping, coverage non-regression |
| Ontology/schema change | Contract tests, migration up/down test, `aegis ontology validate`, required semver/proposal/history changes |
| Security/governance change | Allow and deny matrix, no-existence-leak checks, audit outcome, real policy-engine system test when wiring changes |
| Phase exit | Every charter criterion executable or authorized manual evidence recorded; no planned blocking row below |
| Release/pilot | Full CI, migrations, backup/restore and authorized smoke evidence required by the active gate |

## Traceability matrix

Status means **implemented**, **planned in the active phase**, or **later
phase/not yet applicable**. A path identifies the owning executable suite, not
a duplicated catalog of individual test steps.

| Requirement | Current evidence | Status |
|---|---|---|
| Article IV — immutable evidence/provenance | `tests/unit/test_evidence_vault.py`, `tests/contract/test_evidence_schema.py`, `tests/integration/test_evidence_migration.py` | Implemented |
| Article VI — authorization at query time | `tests/component/test_auth.py`, `tests/integration/test_api.py`, `tests/integration/test_authz.py`, `tests/system/test_authz_openfga.py` | Implemented for Phase 1 routes; Phase 2 field matrix planned in T24a/T24b |
| Article VII — machines suggest, humans decide | `tests/integration/test_ingestion.py`, `tests/integration/test_actions.py` | Implemented for Phase 1 extraction; typed Phase 2 envelope planned in T17c |
| Article VIII — disagreement/retraction preserved | `tests/integration/test_actions.py`, `tests/integration/test_api.py` | Implemented for claim retraction; contradiction UI planned in T23 |
| Article X — append-only audit | `tests/contract/test_audit_schema.py`, `tests/integration/test_audit.py`, `tests/integration/test_actions.py` | Implemented |
| Article XI — ontology is domain truth | `tests/contract/test_ontology.py`, `tests/contract/test_schema.py`, ontology CI gate | Implemented for ontology v1; module/codegen drift planned in Phase 3 |
| Article XIII — rebuildable projections | `tests/unit/test_projection_weights.py`, `tests/integration/test_projections.py` | Implemented for Phase 1 projection; v2 semantics (identity resolution, time segmentation, support summary, stamps) designed in T17b with seven blocking cases in `speckit/specs/02-data-model.md` §7.1 — implementation planned T21 |
| Phase 2 reversible identity/stale revision | Future identity ledger suites: `tests/integration/` (ledger behavior, one-active-membership index, scoped concurrency) + `tests/unit/` (revision arithmetic, canonical-map cycle detection); the seven cases are enumerated in `speckit/specs/05-entity-resolution.md` §8 | Design recorded in T17a; implementation planned T17/T20–T21 |
| Phase 2 provenance panel/contradictions | Future component + browser E2E suites | Planned: T23 |
| Phase 2 transliteration quality thresholds | Future ER evaluation contract/system suite; numeric floors recorded in `speckit/specs/05-entity-resolution.md` §6 | Thresholds recorded in T17a; harness planned T26 |
| Phase 2 field sensitivity and route matrix | Future contract + integration matrix suite | Planned: T24a/T24b |
| Phase 2 fictional ingest-to-projection UI loop | Future `tests/e2e/` MVP journey using `data/sample/mvp/` | Planned: T25/T27 |

## Manual test case format

Use IDs such as `MAN-P2-001`. Record requirement, owner, environment,
preconditions, fictional or authorized dataset, steps, expected results,
evidence location, cleanup, result, and execution date. Manual real-corpus
smokes must follow `data/real/README.md`, capture no sensitive output, and
remain non-blocking unless the phase charter explicitly says otherwise.
