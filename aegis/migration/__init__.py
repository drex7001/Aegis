"""One-time legacy adapters (T8, ADR-016) — the only place legacy vocabulary lives.

:mod:`aegis.migration.legacy` holds the verb-remap table and the
ConfidenceTag→grading map (specs/02 §6), both validated against the ontology
registry at run time.
"""

from aegis.migration.legacy import (
    CONFIDENCE_TAG_GRADING,
    EXPECTED_CATEGORY_CORRECTIONS,
    VERB_REMAP,
    LegacyMigrationError,
    MigrationReport,
    RemapTarget,
    migrate,
    remap_edge,
    validate_legacy_maps,
)

__all__ = [
    "CONFIDENCE_TAG_GRADING",
    "EXPECTED_CATEGORY_CORRECTIONS",
    "VERB_REMAP",
    "LegacyMigrationError",
    "MigrationReport",
    "RemapTarget",
    "migrate",
    "remap_edge",
    "validate_legacy_maps",
]
