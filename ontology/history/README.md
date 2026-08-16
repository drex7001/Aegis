# Ontology version history (spec 08 §7.2)

Claims are immutable and stamp the `ontology_version` current at `recorded_at`
(ADR-013), so every released version must stay interpretable forever. This
directory is where that guarantee lives.

| File shape | Written on | Landed by |
|---|---|---|
| `aegis-<version>.yaml` | a **major** bump, before the breaking change lands | Phase 1 rule (spec 01 §4). `aegis-0.4.0.yaml` is the pre-1.0.0 copy archived when `merged_into` was removed (ADR-028 §5). |
| `composed-<composition-version>.json` | **every** bump | P3 T35 (spec 08 §7.2) |

The composed artifact is the normalized, module-resolved registry in canonical
JSON. It exists for two reasons: a minor bump changes what a stamped version
means just as a major one does, and the compatibility diff in CI compares
against a **committed artifact** rather than reading git history (H-16).

CI enforces the copy on major bumps and the composed artifact on every bump;
`ontology/release.json` names the previous version and its content hash, which
is how the chain is followed.
