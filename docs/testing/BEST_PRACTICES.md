# Testing Best Practices

## Naming and structure

- Name files `test_<subject>.py` and cases
  `test_<condition>_<expected_outcome>`.
- Keep one observable behavior per case. Use a short docstring when the risk or
  requirement is not obvious from the name.
- Organize the body as Arrange, Act, Assert. Comments are useful only where the
  boundary is not self-evident.
- Use `@pytest.mark.requirement("Article-VI", "T24b")` for governance,
  specification, ADR, and phase-gate traceability.

## Fixtures and test data

- Use the narrowest fixture scope that is practical. Session/module fixtures
  may provision immutable infrastructure; mutable scenario data belongs to a
  function-scoped fixture.
- Put shared paths and generic builders in `tests/support/`. Keep domain seeds
  beside the suite that owns them until at least two suites need them.
- Factories return valid minimal objects and accept explicit overrides. Avoid
  large implicit object graphs.
- Freeze or inject clocks and identifiers when their values affect assertions.
- Use fictional deterministic fixtures. Never copy real identifiers or
  sensitive API responses into tests, snapshots, logs, or failure messages.

## Boundaries and mocking

- Mock at an owned interface, not inside the behavior being tested.
- Unit/component tests may fake OpenFGA, OIDC keys, MinIO clients, and clocks.
  Integration/system tests use the real dependency named by their layer.
- Assert outcomes and durable side effects, not private call sequences, unless
  the sequence is the contract (for example append-only custody events).

## Database tests

- Use only `AEGIS_TEST_DATABASE_URL`; never fall back to the development URL.
- Assume the database is disposable. Migrations and cleanup must leave the
  schema at `head`, including after assertion failures.
- Seed through public actions/services unless the test explicitly verifies a
  lower storage contract.
- Test commit, rollback, idempotency, and concurrent/stale operations where the
  feature owns those risks.
- Do not enable parallel database execution until each worker has an isolated
  database or schema.

## Parametrization, errors, and snapshots

- Parametrize rule tables and boundary values when setup and expected behavior
  are genuinely identical. Give parameters readable IDs.
- Assert the error type, status code, safe message, and field/path information;
  avoid matching unstable full strings.
- Keep snapshots small and semantic. Normalize nondeterministic ordering,
  timestamps, and generated IDs before comparison.
- Never regenerate snapshots blindly. Review the diff against the governing
  spec and ontology version.

## Review checklist

- Does the case fail without the production change?
- Is this the lowest layer that proves the behavior?
- Are positive, negative, and applicable governance paths covered?
- Is state isolated and cleanup guaranteed?
- Are assertions precise enough to prevent regression without coupling to
  implementation details?
- Is the requirement marker and traceability entry present when required?
