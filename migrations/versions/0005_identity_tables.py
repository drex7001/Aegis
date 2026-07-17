"""Mention + identity_membership — versioned, reversible identity (spec 02 §2).

Deferred from T4 (the core tables did not need them); required by the T8 legacy
migration, which creates one mention and one membership per legacy node.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mention",
        sa.Column("mention_id", sa.Text(), primary_key=True),
        sa.Column(
            "record_id",
            sa.Text(),
            sa.ForeignKey("source_record.record_id"),
            nullable=False,
        ),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("norm_key", sa.Text(), nullable=False),
        sa.Column("context", sa.Text()),
    )
    op.create_index("ix_mention_norm_key", "mention", ["norm_key"])

    op.create_table(
        "identity_membership",
        sa.Column("membership_id", sa.Text(), primary_key=True),
        sa.Column(
            "mention_id", sa.Text(), sa.ForeignKey("mention.mention_id"), nullable=False
        ),
        sa.Column(
            "entity_id", sa.Text(), sa.ForeignKey("entity.entity_id"), nullable=False
        ),
        sa.Column("decided_by", sa.Text(), nullable=False),
        sa.Column("decision_note", sa.Text()),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_identity_membership_mention",
        "identity_membership",
        ["mention_id", "valid_to"],
    )
    op.create_index(
        "ix_identity_membership_entity", "identity_membership", ["entity_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_identity_membership_entity", table_name="identity_membership")
    op.drop_index("ix_identity_membership_mention", table_name="identity_membership")
    op.drop_table("identity_membership")
    op.drop_index("ix_mention_norm_key", table_name="mention")
    op.drop_table("mention")
