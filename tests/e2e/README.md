# End-to-end tests

This directory is the home for future **automated live-stack** browser
journeys. Phase 2 deliberately closes with three complementary boundaries,
not a duplicated browser harness:

- `tests/integration/test_mvp_fixture.py` automates the real PostgreSQL
  ingest/review/projection loop over `data/sample/mvp/` (T25);
- `ui/e2e/` automates the workspace behavior with Keycloak/API boundaries
  stubbed (T22–T27); and
- `docs/MVP_DEMO.md` / `MAN-P2-001` is the chartered non-builder usability
  journey against the real local stack (T27).

The last item is manual because the gate asks whether a new operator can
complete the runbook in one sitting. That human-usability observation cannot
be manufactured by running the same Playwright assertions again. Backend and
authorization behavior remain blocking automation at integration/system
layers; the manual record is not used as their substitute.

The workspace's browser tests are **not** here — they live beside the code
they exercise, in [`ui/e2e/`](../../ui/e2e), and run in the Node-only CI job
(`make ui-test`). They are hermetic by design: Keycloak and the API are stubbed
at the network boundary so a UI change gets its answer in seconds, which means
they prove the workspace and prove nothing about the stack behind it. A future
journey belongs here only when it adds a wiring risk not already covered by the
Phase 2 integration/system matrix and `MAN-P2-001`.
