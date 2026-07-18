"""Global search: Postgres FTS + pg_trgm + transliteration keys behind SearchPort (Phase 6, ADR-012).

Results return ids only; authorization is re-checked before hydration
(GOAL.md §11.6). Quality tracked by the golden Sinhala/Tamil/English test set.
OpenSearch replaces the backend only if the ADR-012 trigger fires.
"""
