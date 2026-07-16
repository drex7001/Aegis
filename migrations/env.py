"""Alembic environment — URL from aegis.config, metadata from aegis.store."""

from __future__ import annotations

from alembic import context
from sqlalchemy import Connection, create_engine, text

from aegis.config import get_settings
from aegis.store import Base  # imports mappings so autogenerate sees canonical tables

target_metadata = Base.metadata


def _extension_relation_names(connection: Connection) -> frozenset[str]:
    """Relations installed by PostGIS et al. are not part of Aegis metadata.

    The PostGIS image exposes some extension schemas through its search path, so
    Alembic otherwise proposes dropping their tables during autogeneration.
    PostgreSQL records extension ownership in ``pg_depend``; using that catalog
    avoids a brittle hard-coded list of PostGIS/TIGER relation names.
    """
    rows = connection.execute(
        text(
            """
            SELECT DISTINCT class.relname
            FROM pg_depend AS dependency
            JOIN pg_extension AS extension
              ON extension.oid = dependency.refobjid
            JOIN pg_class AS class
              ON class.oid = dependency.objid
            WHERE dependency.classid = 'pg_class'::regclass
              AND dependency.refclassid = 'pg_extension'::regclass
              AND dependency.deptype = 'e'
            """
        )
    )
    return frozenset(row[0] for row in rows)


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_settings().database_url)
    with connectable.connect() as connection:
        extension_relations = _extension_relation_names(connection)
        # SQLAlchemy autobegins a transaction for the catalog SELECT above.  End
        # that read transaction so Alembic owns (and commits) the migration one.
        connection.commit()

        def include_object(object_, name, type_, reflected, compare_to):
            del object_, compare_to
            return not (reflected and type_ == "table" and name in extension_relations)

        def include_name(name, type_, parent_names):
            del parent_names
            return not (type_ == "table" and name in extension_relations)

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_name=include_name,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
