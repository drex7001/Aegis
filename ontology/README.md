# Ontology — the single source of domain truth (Article XI)

`aegis.yaml` is **the** domain artifact: object types, properties, link
predicates, event types, grading schemes, handling codes, and actions are
declared here and nowhere else. Pydantic validators, FGA object types, API
route metadata, UI descriptors, and (from Phase 3) typed Python/TypeScript
SDKs are generated from it. Hand-written domain types that bypass the
ontology are defects (constitution, Article XI; ADR-003).

The platform core is domain-neutral (Article XIV): every analytical domain —
criminal-network analysis first; financial crime, border intelligence later —
enters Aegis as declarations in this artifact plus migrations, never as new
subsystems.

## Layout

| Path | What |
|---|---|
| `aegis.yaml` | The versioned ontology (semver — rules in `speckit/specs/01-ontology.md` §4) |
| `proposals/` | Change proposals (`NNN-short-title.md`) — motivation, YAML diff, competency questions (Phase 3, spec 08 §7) |
| `history/` | Prior versions, copied here on every **major** bump so historical claims stay interpretable (Phase 3, spec 08 §7) |

## Changing the ontology

1. Write a proposal in `proposals/` (motivation, diff, competency questions,
   migration plan if major).
2. Edit `aegis.yaml`, bump the version (minor/patch: additive only; major:
   copy the prior version to `history/` and ship the migration in the same
   change).
3. `aegis ontology validate` must pass (also the CI gate), then regenerate
   codegen targets — drift between ontology and generated code is a build
   failure.

Design principles (GOAL.md §7.9): model reality, not systems; competency
questions are requirements; curate properties intentionally; separate identity
from observation; name in the domain's language; minimal commitment, additive
evolution; rule of three.
