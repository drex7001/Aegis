# Testing Strategy

## Purpose and principles

Aegis handles governed claims about real people. Testing therefore prioritizes
authorization, provenance, reversibility, auditability, and the separation of
machine suggestions from canonical records. A percentage cannot substitute for
those behaviors.

Apply these principles:

1. Test the smallest boundary that proves the risk.
2. Add broader tests only for behavior that depends on wiring or real services.
3. Use deterministic fictional data by default.
4. Preserve failures as regression tests.
5. Map constitutional and phase-gate behavior to executable tests.
6. Keep tests independent, repeatable, and safe to run in any order.

## Layer selection

- **Unit:** deterministic business rules, validation, mapping, retry policy, and
  serialization with no network, process, filesystem, or database boundary.
- **Component:** FastAPI/CLI behavior in one process. Replace authentication,
  policy, clocks, and storage only at their declared boundaries.
- **Contract:** committed interfaces and governance invariants: ontology,
  SQLAlchemy metadata, OpenAPI shape, route authorization, and snapshots.
- **Integration:** real PostgreSQL schema and transactions, including API calls
  whose behavior depends on stored rows. The database must be disposable.
- **System:** real multi-service interactions such as the PostgreSQL outbox and
  OpenFGA convergence drill. Selected tests fail when services are unavailable.
- **E2E:** a small set of analyst journeys through the browser. Phase 2 begins
  with the fictional MVP ingest-to-projection loop; it is not a replacement for
  lower layers.

Manual tests are reserved for authorized real-corpus smoke checks, exploratory
testing, usability, recovery drills, or controls that cannot be automated
safely. Manual results are evidence, not a substitute for blocking automation.

## Risk-based coverage

Every feature needs its normal path, validation/failure path, and a regression
test for each fixed defect. Add these when applicable:

- role, relationship, handling-code, and field-sensitivity allow/deny cases;
- audit event and append-only behavior;
- transaction rollback and idempotent retry;
- review-queue-only behavior for machine output;
- provenance, contradiction, retraction, and reversible identity behavior;
- projection rebuild equivalence;
- boundary values, malformed input, concurrency, and stale revisions.

Constitutional and phase-gate criteria require complete behavioral coverage,
even when repository coverage already exceeds its threshold.

## Environments and CI

Pull requests run five blocking jobs: fast tests, PostgreSQL integration tests,
OpenFGA system tests, combined coverage/governance gates, and the workspace
type-check/build/hermetic-browser job. The coverage job uses the compose stack
and runs every automated Python blocking layer. Phase 2's live-stack
non-builder journey is the manual `MAN-P2-001` usability gate; its backend and
workspace behaviors remain automated at integration/system and `ui/e2e`
boundaries.

The final `test` status is a branch-protection compatibility gate. It depends
on all five jobs and passes only when every blocking stage succeeds.

Local fast tests require no service. Integration tests require
`AEGIS_TEST_DATABASE_URL`. System tests require `make up && make bootstrap`.
Credentials and `.runtime.env` are never committed.

## Defects, flakes, and failures

- Reproduce a defect with a failing test before or alongside the fix.
- Do not weaken an assertion merely to make CI pass.
- Do not use unconditional retries. A flaky test is quarantined only with an
  owner, issue, reason, expiry date, and non-blocking marker approved in review.
- Report infrastructure failures verbatim. Blocking suites do not silently
  skip missing dependencies.
- Snapshot changes require human review and an explanation of the intended
  semantic change.
