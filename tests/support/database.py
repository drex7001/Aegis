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


#: Revision 0 is migration state, not test data (spec 05 §7).  ``CASCADE``
#: reaches it anyway — ``mention`` and ``er_candidate`` are referenced by
#: ``er_candidate`` → ``identity_decision`` → ``identity_revision`` — so the
#: ledger baseline is re-asserted after the wipe rather than excluded from it.
#: Restoring it is also more robust than an exclusion list, which every future
#: foreign key into the ledger would silently invalidate.
RESTORE_BASELINE_REVISION = (
    "INSERT INTO identity_revision (revision_id, decision_id) VALUES (0, NULL) "
    "ON CONFLICT DO NOTHING"
)

#: Everything except ``audit_log``, whose chain some suites verify across a
#: reset.  Callers that want the audit chain cleared name it themselves.
TRUNCATE_DOMAIN_TABLES = (
    "TRUNCATE claim_relation, review_queue, claim, entity_canonical_map, "
    "identity_negative_constraint, er_candidate, identity_decision, "
    "identity_revision, identity_membership, mention, evidence_item, "
    "custody_event, derivative, source_record, source, case_member, case_file, "
    # The investigation plane (T43). CASCADE would reach these through
    # `case_file` anyway; naming them keeps the list readable as an inventory
    # rather than as a set of roots someone has to trace.
    "case_reference, hypothesis_claim, hypothesis_revision, hypothesis, "
    "investigation_task, "
    # The geometry projection (T56). Reached through `claim` by CASCADE, and
    # named here for the same reason as the row above.
    "location_geometry_projection, "
    "entity, authz_outbox CASCADE"
)


def truncate_domain_data(engine: sa.Engine) -> None:
    """Reset mutable domain state to the migration baseline."""
    with engine.begin() as connection:
        connection.execute(sa.text("TRUNCATE audit_log CASCADE"))
        connection.execute(sa.text(TRUNCATE_DOMAIN_TABLES))
        connection.execute(sa.text(RESTORE_BASELINE_REVISION))
