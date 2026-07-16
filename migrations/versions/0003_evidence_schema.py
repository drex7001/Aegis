"""Evidence, derivative lineage, and custody schema (speckit T5).

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_item",
        sa.Column("evidence_id", sa.Text(), primary_key=True),
        sa.Column("case_id", sa.Text(), sa.ForeignKey("case_file.case_id")),
        sa.Column("record_id", sa.Text(), sa.ForeignKey("source_record.record_id")),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text()),
        sa.Column("storage_uri", sa.Text()),
        sa.Column("acquired_at", sa.DateTime(timezone=True)),
        sa.Column("acquired_by", sa.Text()),
        sa.Column("legal_basis", sa.Text()),
        sa.Column(
            "handling_code",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'restricted'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_evidence_item_content_hash", "evidence_item", ["content_hash"])
    op.create_index("ix_evidence_item_case_id", "evidence_item", ["case_id"])

    op.create_table(
        "derivative",
        sa.Column("derivative_id", sa.Text(), primary_key=True),
        sa.Column(
            "parent_evidence",
            sa.Text(),
            sa.ForeignKey("evidence_item.evidence_id"),
        ),
        sa.Column(
            "parent_record",
            sa.Text(),
            sa.ForeignKey("source_record.record_id"),
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("tool_version", sa.Text(), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("operator", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "parent_evidence IS NOT NULL OR parent_record IS NOT NULL",
            name="ck_derivative_has_parent",
        ),
    )
    op.create_index("ix_derivative_content_hash", "derivative", ["content_hash"])

    op.create_table(
        "custody_event",
        sa.Column(
            "evidence_id",
            sa.Text(),
            sa.ForeignKey("evidence_item.evidence_id"),
            primary_key=True,
        ),
        sa.Column("seq", sa.Integer(), primary_key=True),
        sa.Column("from_actor", sa.Text()),
        sa.Column("to_actor", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column(
            "hash_checked", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("note", sa.Text()),
    )


def downgrade() -> None:
    op.drop_table("custody_event")
    op.drop_index("ix_derivative_content_hash", table_name="derivative")
    op.drop_table("derivative")
    op.drop_index("ix_evidence_item_case_id", table_name="evidence_item")
    op.drop_index("ix_evidence_item_content_hash", table_name="evidence_item")
    op.drop_table("evidence_item")
