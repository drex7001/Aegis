# Ontology version history (spec 08 §7.2)

Claims are immutable and stamp the `ontology_version` current at `recorded_at`
(ADR-013), so every released version must stay interpretable forever. This
directory is where that guarantee lives.

| File shape | Written on | Landed by |
|---|---|---|
| `aegis-<version>.yaml` | a **major** bump, before the breaking change lands | Phase 1 rule (spec 01 §4). `aegis-0.4.0.yaml` is the pre-1.0.0 copy archived when `merged_into` was removed (ADR-028 §5). |
| `composed-<composition-version>.json` | **every** bump, by `aegis ontology generate` | P3 T33 (spec 08 §7.2); T35 adds the compatibility gate that reads it |

The composed artifact is the normalized, module-resolved registry in canonical
JSON. It exists for two reasons: a minor bump changes what a stamped version
means just as a major one does, and the compatibility diff in CI compares
against a **committed artifact** rather than reading git history (H-16).

CI enforces the copy on major bumps and the composed artifact on every bump
(`aegis ontology generate --check`); `ontology/release.json` names the previous
version and its content hash, which is how the chain is followed.

The chain starts at **1.4.0** — the first version generated after the tooling
existed. Versions 1.0.0–1.3.0 predate it and have no composed artifact; their
`aegis.yaml` is recoverable from git, and the compatibility diff only ever
compares against the previous *generated* artifact.
