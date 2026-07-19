"""Ingestion: raw landing via the vault + extraction passes → review queue (T9).

The derivative stage between the two (spec 04 §1 stage 3) landed at T23a in
:mod:`aegis.ingestion.derivatives`.
"""

from aegis.ingestion.derivatives import (
    PDF_MEDIA_TYPE,
    TEXT_KIND,
    EmptyDerivative,
    TextExtraction,
    UnsupportedMediaType,
    ensure_text,
    resolve_media_type,
)
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
from aegis.ingestion.mvp_fixture import (
    MVP_FIXTURE_ROOT,
    MvpFixtureError,
    MvpFixtureReport,
    MvpResetReport,
    load_mvp_fixture,
    reset_mvp_fixture,
)

__all__ = [
    "DEFAULT_SOURCE_SYSTEM",
    "MANUAL_SOURCE_ID",
    "PDF_MEDIA_TYPE",
    "STRUCTURAL_PREDICATES",
    "TEXT_KIND",
    "EmptyDerivative",
    "IngestionError",
    "LandingResult",
    "TextExtraction",
    "UnsupportedMediaType",
    "ensure_manual_source",
    "ensure_text",
    "land_bytes",
    "land_file",
    "make_ingest_key",
    "resolve_media_type",
    "run_semantic_pass",
    "run_structural_pass",
    "MVP_FIXTURE_ROOT",
    "MvpFixtureError",
    "MvpFixtureReport",
    "MvpResetReport",
    "load_mvp_fixture",
    "reset_mvp_fixture",
]
