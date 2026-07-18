"""Shared lifecycle helpers for disposable PostgreSQL tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os

from alembic import command
from alembic.config import Config
import sqlalchemy as sa


@contextmanager
def configured_test_database(database_url: str, config: Config) -> Iterator[None]:
    """Point Aegis at the test DB, migrate it, then restore process settings."""
    previous = os.environ.get("AEGIS_DATABASE_URL")
    os.environ["AEGIS_DATABASE_URL"] = database_url
    from aegis.config import get_settings

    get_settings.cache_clear()
    command.upgrade(config, "head")
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("AEGIS_DATABASE_URL", None)
        else:
            os.environ["AEGIS_DATABASE_URL"] = previous
        get_settings.cache_clear()


@contextmanager
def migrated_test_engine(database_url: str, config: Config) -> Iterator[sa.Engine]:
    """Yield a migrated engine and always dispose it."""
    with configured_test_database(database_url, config):
        engine = sa.create_engine(database_url)
        try:
            yield engine
        finally:
            engine.dispose()


def truncate_domain_data(engine: sa.Engine) -> None:
    """Clear mutable Phase 1 state for cross-session API isolation."""
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE audit_log, claim_relation, review_queue, claim, "
                "identity_membership, mention, evidence_item, custody_event, "
                "derivative, source_record, source, case_member, case_file, "
                "entity, authz_outbox CASCADE"
            )
        )
