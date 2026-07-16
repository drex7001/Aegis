"""Core claim-store schema tests (speckit T4)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint

from aegis.store import Base

REPO_ROOT = Path(__file__).resolve().parents[1]

T4_TABLES = {
    "source",
    "source_record",
    "entity",
    "claim",
    "claim_relation",
    "review_queue",
    "case_file",
    "case_member",
    "authz_outbox",
}

EXPECTED_CHECKS = {
    "ck_source_record_status",
    "ck_case_file_status",
    "ck_claim_object_exactly_one",
    "ck_claim_no_self_reference",
    "ck_claim_event_time_order",
    "ck_claim_valid_date_order",
    "ck_claim_relation_relation",
    "ck_review_queue_status",
    "ck_authz_outbox_op",
}

# These columns hold ontology-owned vocabulary and must never occur in DDL CHECKs
# (ADR-013).  Defaults are fine; membership constraints are not.
ONTOLOGY_COLUMNS = {
    "source_type",
    "reliability_normalized",
    "entity_type",
    "predicate",
    "credibility_normalized",
    "verification_status",
    "analytic_confidence",
    "handling_code",
    "role",
}


def _metadata_checks(table_names: set[str]) -> dict[str, str]:
    return {
        constraint.name: str(constraint.sqltext).lower()
        for table_name, table in Base.metadata.tables.items()
        if table_name in table_names
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def test_core_metadata_declares_t4_tables() -> None:
    assert T4_TABLES <= set(Base.metadata.tables)


def test_checks_cover_only_code_owned_invariants() -> None:
    checks = _metadata_checks(T4_TABLES)
    assert set(checks) == EXPECTED_CHECKS
    for sqltext in checks.values():
        assert all(column not in sqltext for column in ONTOLOGY_COLUMNS)


def test_ontology_vocabulary_columns_are_plain_text() -> None:
    locations = {
        "source.source_type",
        "source.reliability_normalized",
        "source_record.handling_code",
        "entity.entity_type",
        "case_file.handling_code",
        "case_member.role",
        "claim.predicate",
        "claim.credibility_normalized",
        "claim.verification_status",
        "claim.analytic_confidence",
        "claim.handling_code",
    }
    for location in locations:
        table_name, column_name = location.split(".")
        assert type(Base.metadata.tables[table_name].c[column_name].type) is sa.Text


@pytest.mark.integration
def test_postgres_migration_up_inspect_down_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise real PostgreSQL DDL when CI (or a developer) provides a test DB."""
    database_url = os.getenv("AEGIS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("set AEGIS_TEST_DATABASE_URL to run PostgreSQL migration test")

    monkeypatch.setenv("AEGIS_DATABASE_URL", database_url)
    from aegis.config import get_settings

    get_settings.cache_clear()
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    engine = sa.create_engine(database_url)

    command.upgrade(config, "head")
    try:
        inspector = sa.inspect(engine)
        assert T4_TABLES <= set(inspector.get_table_names())

        checks = {
            check["name"]: check["sqltext"].lower()
            for table_name in T4_TABLES
            for check in inspector.get_check_constraints(table_name)
        }
        assert set(checks) == EXPECTED_CHECKS
        for sqltext in checks.values():
            assert all(column not in sqltext for column in ONTOLOGY_COLUMNS)

        # The migration and ORM mappings must not drift apart.
        for table_name in T4_TABLES:
            actual = {column["name"] for column in inspector.get_columns(table_name)}
            mapped = set(Base.metadata.tables[table_name].c.keys())
            assert actual == mapped

        command.downgrade(config, "0001")
        assert T4_TABLES.isdisjoint(sa.inspect(engine).get_table_names())
    finally:
        # Leave a developer/CI test database at head even if an assertion fails.
        command.upgrade(config, "head")
        engine.dispose()
        get_settings.cache_clear()
