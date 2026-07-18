"""PostgreSQL migration lifecycle for the evidence schema."""

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from aegis.store import Base
from tests.support.schema import T4_TABLES


EVIDENCE_TABLES = {"evidence_item", "derivative", "custody_event"}
pytestmark = pytest.mark.requirement("Article-IV", "T5")


def test_evidence_migration_up_inspect_down_clean(
    monkeypatch: pytest.MonkeyPatch,
    test_database_url: str,
    alembic_config: Config,
) -> None:
    monkeypatch.setenv("AEGIS_DATABASE_URL", test_database_url)
    from aegis.config import get_settings

    get_settings.cache_clear()
    engine = sa.create_engine(test_database_url)

    command.upgrade(alembic_config, "head")
    try:
        inspector = sa.inspect(engine)
        table_names = set(inspector.get_table_names())
        assert EVIDENCE_TABLES <= table_names
        assert T4_TABLES <= table_names
        assert {check["name"] for check in inspector.get_check_constraints("derivative")} == {
            "ck_derivative_has_parent"
        }

        for table_name in EVIDENCE_TABLES:
            actual = {column["name"] for column in inspector.get_columns(table_name)}
            mapped = set(Base.metadata.tables[table_name].c.keys())
            assert actual == mapped

        command.downgrade(alembic_config, "0002")
        downgraded_tables = set(sa.inspect(engine).get_table_names())
        assert EVIDENCE_TABLES.isdisjoint(downgraded_tables)
        assert T4_TABLES <= downgraded_tables
    finally:
        command.upgrade(alembic_config, "head")
        engine.dispose()
        get_settings.cache_clear()
