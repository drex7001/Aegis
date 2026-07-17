"""Ingestion: raw landing via the vault + extraction passes → review queue (T9)."""

from aegis.ingestion.service import (
    DEFAULT_SOURCE_SYSTEM,
    MANUAL_SOURCE_ID,
    STRUCTURAL_PREDICATES,
    IngestionError,
    LandingResult,
    ensure_manual_source,
    land_bytes,
    land_file,
    make_ingest_key,
    run_semantic_pass,
    run_structural_pass,
)

__all__ = [
    "DEFAULT_SOURCE_SYSTEM",
    "MANUAL_SOURCE_ID",
    "STRUCTURAL_PREDICATES",
    "IngestionError",
    "LandingResult",
    "ensure_manual_source",
    "land_bytes",
    "land_file",
    "make_ingest_key",
    "run_semantic_pass",
    "run_structural_pass",
]
