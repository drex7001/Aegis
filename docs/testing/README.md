# Testing in Aegis

Testing is a release control, not a cleanup task. Every behavior change must
arrive with evidence at the lowest useful layer and with the governance checks
that apply to it.

## Documentation

- [Testing strategy](TESTING_STRATEGY.md) — layers, environments, ownership,
  and CI execution.
- [Testing criteria](TESTING_CRITERIA.md) — Definition of Done, quality gates,
  coverage policy, and requirement traceability.
- [Best practices](BEST_PRACTICES.md) — how to design, name, isolate, and review
  tests.

## Test layers

| Path | Boundary | Default dependencies |
|---|---|---|
| `tests/unit/` | One function or class | None |
| `tests/component/` | In-process API or CLI | Fakes/mocks only |
| `tests/contract/` | Schema, ontology, OpenAPI, governance | Committed artifacts |
| `tests/integration/` | Aegis with PostgreSQL | Disposable test database |
| `tests/system/` | Multiple real services | Compose stack and bootstrap |
| `tests/e2e/` | Browser-to-database journey | Full application stack |

Layer markers are applied from these directories by `tests/conftest.py`.
Cross-cutting markers do not replace correct placement.

## Commands

```bash
make test-fast          # unit + component + contract
make test-integration   # requires AEGIS_TEST_DATABASE_URL
make up && make bootstrap
make test-system        # real PostgreSQL/OpenFGA behavior
make test               # all currently automated blocking layers
make test-coverage      # line + branch coverage and coverage.xml
uv run pytest --collect-only -q
```

Use a disposable PostgreSQL database. Integration and system tests may migrate,
truncate, or downgrade it. Missing blocking infrastructure is a failure, not a
skip.

## Ownership

The author of a behavior change owns its tests and requirement mapping. The
reviewer verifies layer choice, failure-path coverage, and test evidence. The
phase owner maintains the traceability matrix and resolves planned gaps before
a phase exit review.
