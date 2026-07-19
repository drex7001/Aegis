# Phase 2 MVP fixture

Every person, organisation, identifier, date, facility, and event in this
directory is invented. The corpus is deterministic, contains no captured model
response, and must never be represented as real intelligence.

`harbor-note.semantic.json` is a hand-authored cached response in the same
validated envelope used for offline semantic extraction. Its `model` value
identifies a fixture, not a hosted provider call, and its prompt digest makes
prompt/cache drift fail explicitly.

Load the corpus with `aegis ingest mvp`. On a database containing only this
fixture, `aegis ingest mvp --reset --yes` restores the migrated empty baseline
and rebuilds empty projections. Reset deliberately refuses any non-fixture
record, source, or case.
