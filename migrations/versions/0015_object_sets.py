"""Object sets: a definition, its immutable versions, and its notices (T69).

Three tables, and the interesting thing about them is a column that is **not**
here.

There is no results column and no results table. Spec 12 §3 and T69's
acceptance criterion say a stored definition contains no result rows "because
the schema makes it impossible", and this migration is where that becomes true.
A nullable `results` column with a comment saying not to use it would be a
results column; the only durable version of that rule is nowhere to put them.

`object_set_version` is append-only by convention and by shape: `(set_id,
version)` is the primary key and an edit writes a new row. Nothing updates one,
because a finding names `(set_id, version)` and has to name something that
cannot change under it (spec 12 §8.2).

`ast` holds the definition **after** interface expansion and `ast_as_written`
holds it before. Both, because they answer different questions: the first is
what the set means, and the second is what its author meant — which is what
tells §4.3 whose sets to notify when an interface gains a member (ADR-054).

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "object_set",
        sa.Column("set_id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("case_id", sa.Text(), sa.ForeignKey("case_file.case_id")),
        sa.Column("owner", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_object_set_case", "object_set", ["case_id"])

    op.create_table(
        "object_set_version",
        sa.Column(
            "set_id", sa.Text(), sa.ForeignKey("object_set.set_id"), primary_key=True
        ),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("ast", JSONB(), nullable=False),
        sa.Column("ast_as_written", JSONB(), nullable=False),
        sa.Column("ontology_version", sa.Text(), nullable=False),
        sa.Column(
            "track_interface_members",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("as_of", sa.DateTime(timezone=True)),
        sa.Column("as_of_revision", sa.BigInteger()),
        sa.Column("note", sa.Text()),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("version >= 1", name="ck_object_set_version_positive"),
    )
    op.create_index("ix_object_set_version_set", "object_set_version", ["set_id"])

    op.create_table(
        "object_set_notice",
        sa.Column("notice_id", sa.Text(), primary_key=True),
        sa.Column(
            "set_id", sa.Text(), sa.ForeignKey("object_set.set_id"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("interface", sa.Text(), nullable=False),
        sa.Column("member", sa.Text(), nullable=False),
        sa.Column("ontology_version", sa.Text(), nullable=False),
        sa.Column("tracking", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # One notice per (set version, interface, member, composition). A
        # rerun of the notice sweep must not multiply what an owner sees.
        sa.UniqueConstraint(
            "set_id",
            "version",
            "interface",
            "member",
            "ontology_version",
            name="uq_object_set_notice_event",
        ),
    )


def downgrade() -> None:
    op.drop_table("object_set_notice")
    op.drop_index("ix_object_set_version_set", table_name="object_set_version")
    op.drop_table("object_set_version")
    op.drop_index("ix_object_set_case", table_name="object_set")
    op.drop_table("object_set")
