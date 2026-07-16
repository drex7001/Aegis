"""Audit ledger acceptance tests (speckit T6)."""

from __future__ import annotations

from datetime import datetime, timezone
import os

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from aegis.audit import append, verify
from aegis.store import AuditLog, Base


def test_audit_mapping_and_code_owned_constraint() -> None:
    table = Base.metadata.tables["audit_log"]
    assert {
        "id",
        "at",
        "actor",
        "session_id",
        "purpose",
        "case_id",
        "action",
        "resource_type",
        "resource_id",
        "decision",
        "detail",
        "prev_hash",
        "entry_hash",
    } == set(table.c.keys())
    assert {constraint.name for constraint in table.constraints} >= {
        "ck_audit_log_decision"
    }


@pytest.fixture(scope="module")
def audit_engine() -> sa.Engine:
    database_url = os.getenv("AEGIS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("set AEGIS_TEST_DATABASE_URL to run PostgreSQL audit tests")
    config = Config("alembic.ini")
    config.set_main_option("script_location", "migrations")
    previous = os.environ.get("AEGIS_DATABASE_URL")
    os.environ["AEGIS_DATABASE_URL"] = database_url
    from aegis.config import get_settings

    get_settings.cache_clear()
    command.upgrade(config, "head")
    engine = sa.create_engine(database_url)
    yield engine
    engine.dispose()
    if previous is None:
        os.environ.pop("AEGIS_DATABASE_URL", None)
    else:
        os.environ["AEGIS_DATABASE_URL"] = previous
    get_settings.cache_clear()


@pytest.mark.integration
def test_append_builds_chain_and_verify_passes(audit_engine: sa.Engine) -> None:
    with Session(audit_engine) as session, session.begin():
        first = append(
            session,
            actor="test:auditor",
            action="test:first",
            decision="allow",
            detail={"unicode": "ශ්‍රී ලංකා"},
            at=datetime.now(timezone.utc),
        )
        second = append(
            session,
            actor="test:auditor",
            action="test:second",
            decision="deny",
            detail={"reason": "acceptance test"},
        )
        assert second.prev_hash == first.entry_hash
        assert len(first.entry_hash) == 64

    with Session(audit_engine) as session:
        assert verify(session).valid


@pytest.mark.integration
def test_tampering_fails_at_edited_row_without_persisting_tamper(
    audit_engine: sa.Engine,
) -> None:
    with Session(audit_engine) as session, session.begin():
        row = append(
            session,
            actor="test:tamper",
            action="test:tamper-target",
            decision="allow",
            detail={"original": True},
        )
        row_id = row.id

    # The database owner represents the dedicated maintenance/superuser role. Keep
    # the edit inside a transaction and roll it back after proving detection.
    with audit_engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(
            sa.text(
                "UPDATE audit_log SET detail = detail || "
                "'{\"tampered\": true}'::jsonb WHERE id = :id"
            ),
            {"id": row_id},
        )
        with Session(bind=connection) as session:
            report = verify(session)
            assert not report.valid
            assert report.failed_id == row_id
            assert report.reason == "entry hash does not match canonical event data"
        transaction.rollback()

    with Session(audit_engine) as session:
        assert verify(session).valid


@pytest.mark.integration
def test_app_role_has_no_audit_update_or_delete_grant(audit_engine: sa.Engine) -> None:
    with audit_engine.connect() as connection:
        grants = set(
            connection.execute(
                sa.text(
                    """
                    SELECT privilege_type
                    FROM information_schema.role_table_grants
                    WHERE grantee = 'aegis_app' AND table_name = 'audit_log'
                    """
                )
            ).scalars()
        )
    assert {"SELECT", "INSERT"} <= grants
    assert {"UPDATE", "DELETE", "TRUNCATE"}.isdisjoint(grants)
