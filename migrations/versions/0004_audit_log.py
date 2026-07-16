"""Append-only hash-chained audit ledger (speckit T6).

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text()),
        sa.Column("purpose", sa.Text()),
        sa.Column("case_id", sa.Text()),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.Text()),
        sa.Column("resource_id", sa.Text()),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("prev_hash", sa.Text(), nullable=False),
        sa.Column("entry_hash", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('allow', 'deny')", name="ck_audit_log_decision"
        ),
    )
    op.create_index("ix_audit_log_at", "audit_log", ["at"])
    op.create_index("ix_audit_log_actor_at", "audit_log", ["actor", "at"])

    # The migration/maintenance role owns the table.  Runtime code may append and
    # inspect the ledger, but it cannot rewrite history.  Role creation is kept
    # idempotent for developer and CI clusters; managed clusters must pre-create it
    # when the migration identity is intentionally denied CREATE ROLE.
    op.execute(
        """
        DO $role$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aegis_app') THEN
            CREATE ROLE aegis_app NOLOGIN;
          END IF;
        END
        $role$
        """
    )
    op.execute("REVOKE ALL ON TABLE audit_log FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT ON TABLE audit_log TO aegis_app")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq TO aegis_app")


def downgrade() -> None:
    op.drop_index("ix_audit_log_actor_at", table_name="audit_log")
    op.drop_index("ix_audit_log_at", table_name="audit_log")
    op.drop_table("audit_log")
    # Roles are cluster-scoped and may be shared by other databases.  Deliberately
    # leave aegis_app in place; dropping the table removes its object privileges.
