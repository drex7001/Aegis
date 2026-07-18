# Generated SDKs (Phase 3 — spec 08 §8, ADR-021)

Typed clients **generated from the ontology + API surface**; never edited by
hand. Regeneration is a `make generate` target and CI fails on drift
(generated files are committed — spec 01 §5 discipline).

| Package | Path | Consumers |
|---|---|---|
| Python SDK | `python/aegis_sdk/` | pipelines, notebooks, Phase 8 AI producers |
| TypeScript SDK | `ts/` (npm workspace) | Phase 4 investigation workspace (`ui/`) |

Contents: typed object/interface models, predicate constants, action call
wrappers (from ontology action `parameters`), query/object-set builders
(Phase 6 extends). SDK tokens are scoped to the intersection of the
application's grant and the user's own permissions (GOAL.md §7.8).

Empty until Phase 3 (T38–T39) generates the first clients.
