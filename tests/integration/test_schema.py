"""Core claim-store schema tests (speckit T4)."""

from __future__ import annotations


import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from aegis.store import Base
from tests.support.schema import (
    EXPECTED_CHECKS,
    LEDGER_TABLES,
    ONTOLOGY_COLUMNS,
    T4_TABLES,
)


pytestmark = pytest.mark.requirement("Article-XI", "Article-XIV", "ADR-028", "T4", "T17")


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
        for table_name in T4_TABLES | LEDGER_TABLES:
            actual = {column["name"] for column in inspector.get_columns(table_name)}
            mapped = set(Base.metadata.tables[table_name].c.keys())
            assert actual == mapped

        # The T17 ledger comes up with its baseline and its invariant in place.
        assert LEDGER_TABLES <= set(inspector.get_table_names())
        with engine.connect() as connection:
            assert connection.execute(
                sa.text("SELECT count(*) FROM identity_revision WHERE revision_id = 0")
            ).scalar_one() == 1
        assert "ux_membership_one_active" in {
            index["name"] for index in inspector.get_indexes("identity_membership")
        }

        # Down through 0007 and back is clean: the ledger drops without
        # stranding the Phase-1 shape it was layered onto.
        command.downgrade(alembic_config, "0001")
        remaining = set(sa.inspect(engine).get_table_names())
        assert T4_TABLES.isdisjoint(remaining)
        assert LEDGER_TABLES.isdisjoint(remaining)
    finally:
        # Leave a developer/CI test database at head even if an assertion fails.
        command.upgrade(alembic_config, "head")
        engine.dispose()
        get_settings.cache_clear()
