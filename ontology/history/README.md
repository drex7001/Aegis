# Ontology version history (Phase 3 — spec 08 §7)

Every **major** version bump copies the prior `aegis.yaml` here (as
`aegis-<version>.yaml`) before the breaking change lands, so claims stamped
with an earlier `ontology_version` remain interpretable forever (claims are
immutable; ADR-013). CI enforces the copy on major bumps.

Directory is seeded in Phase 3; empty until the first major bump.
