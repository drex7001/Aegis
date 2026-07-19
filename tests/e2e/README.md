# End-to-end tests

Reserved for the **live-stack** MVP journey: `data/sample/mvp/` loaded through
the real API, Keycloak and database, driven from the browser (T25/T27). Nothing
lives here yet.

The workspace's own browser tests are **not** here — they live beside the code
they exercise, in [`ui/e2e/`](../../ui/e2e), and run in the Node-only CI job
(`make ui-test`). They are hermetic by design: Keycloak and the API are stubbed
at the network boundary so a UI change gets its answer in seconds, which means
they prove the workspace and prove nothing about the stack behind it. Proving
the stack is this directory's job.
