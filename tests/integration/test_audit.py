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
from aegis.store import AuditLog
from tests.support.database import migrated_test_engine


pytestmark = pytest.mark.requirement("Article-X", "T6")


@pytest.fixture(scope="module")
def audit_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


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
