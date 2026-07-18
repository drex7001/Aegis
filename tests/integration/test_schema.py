"""Core claim-store schema tests (speckit T4)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from aegis.store import Base
from tests.support.paths import REPO_ROOT
from tests.support.schema import EXPECTED_CHECKS, ONTOLOGY_COLUMNS, T4_TABLES


pytestmark = pytest.mark.requirement("Article-XI", "Article-XIV", "T4")


@pytest.mark.integration
def test_postgres_migration_up_inspect_down_clean(
    monkeypatch: pytest.MonkeyPatch,
    test_database_url: str,
    alembic_config: Config,
) -> None:
    """Exercise real PostgreSQL DDL when CI (or a developer) provides a test DB."""
    database_url = test_database_url

    monkeypatch.setenv("AEGIS_DATABASE_URL", database_url)
    from aegis.config import get_settings

    get_settings.cache_clear()
    engine = sa.create_engine(database_url)

    command.upgrade(alembic_config, "head")
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

        command.downgrade(alembic_config, "0001")
        assert T4_TABLES.isdisjoint(sa.inspect(engine).get_table_names())
    finally:
        # Leave a developer/CI test database at head even if an assertion fails.
        command.upgrade(alembic_config, "head")
        engine.dispose()
        get_settings.cache_clear()
