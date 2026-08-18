"""The investigation operational plane: references, hypotheses, tasks (T43).

Five tables, three ideas (spec 09 §2.3, §3, §4).

**`case_reference`** exists because "link a claim to a case" had two readings
and only one of them is safe. ``claim.case_id`` is an *access predicate* —
``aegis/authz/filters.py`` admits a claim when it is null or the reader is a
member of that case — so re-assigning it would widen or narrow who can read a
recorded row, performed by an ordinary analyst, on an append-only table. A
reference is the other reading: *this investigation refers to that*, granting
nothing (ADR-044).

**`hypothesis` + `hypothesis_revision`** split the way the identity ledger does
(ADR-028). A version counter plus an audit row would leave the earlier statement
recoverable only by parsing audit payloads, which is the history-you-cannot-query
failure that design was written against. The immutable row holds identity; the
latest revision is current state.

**`investigation_task`** carries tasks and leads together, with a status column
and no transition graph. Plan §2's workflow-engine trigger stays untouched.

Nothing here is projected, and nothing here is a claim: hypotheses are
assertions about our own reasoning, never about the world (Article IX).

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_reference",
        sa.Column("case_id", sa.Text(), sa.ForeignKey("case_file.case_id"), nullable=False),
        # No foreign key: the target is one of three tables and a polymorphic
        # reference cannot carry one. The actions layer checks existence against
        # the table `target_type` names.
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("linked_by", sa.Text(), nullable=False),
        sa.Column(
            "linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        # Unlinking is a tombstone. Deleting the row would take with it the fact
        # that somebody once thought the two were connected.
        sa.Column("detached_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("case_id", "target_type", "target_id"),
        sa.CheckConstraint(
            "target_type IN ('claim', 'entity', 'evidence_item')",
            name="ck_case_reference_target_type",
        ),
    )
    op.create_index("ix_case_reference_target", "case_reference", ["target_type", "target_id"])

    op.create_table(
        "hypothesis",
        sa.Column("hypothesis_id", sa.Text(), primary_key=True),
        # Always case-scoped: there is no global hypothesis, and the case is the
        # resource its authorization derives from (spec 09 §5).
        sa.Column("case_id", sa.Text(), sa.ForeignKey("case_file.case_id"), nullable=False),
        sa.Column("opened_by", sa.Text(), nullable=False),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("handling_code", sa.Text(), nullable=False, server_default=sa.text("'open'")),
    )
    op.create_index("ix_hypothesis_case_id", "hypothesis", ["case_id"])

    op.create_table(
        "hypothesis_revision",
        sa.Column(
            "hypothesis_id", sa.Text(), sa.ForeignKey("hypothesis.hypothesis_id"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("missing_info", sa.Text(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("authored_by", sa.Text(), nullable=False),
        sa.Column(
            "authored_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("hypothesis_id", "version"),
        sa.CheckConstraint(
            "status IN ('open', 'supported', 'refuted', 'withdrawn')",
            name="ck_hypothesis_revision_status",
        ),
        # GOAL.md §18: a hypothesis states what would change it. NOT NULL does
        # not reject "   ", and a blank note is not a note — the
        # `required_text_is_substantive` submission criterion refuses it at the
        # action, and this refuses it at the table.
        sa.CheckConstraint(
            "length(btrim(missing_info)) > 0", name="ck_hypothesis_revision_missing_info"
        ),
    )

    op.create_table(
        "hypothesis_claim",
        sa.Column(
            "hypothesis_id", sa.Text(), sa.ForeignKey("hypothesis.hypothesis_id"), nullable=False
        ),
        sa.Column("claim_id", sa.Text(), sa.ForeignKey("claim.claim_id"), nullable=False),
        # `supports`/`contradicts`, not `claim_relation`'s
        # `corroborates`/`contradicts`: a claim corroborating a claim is about
        # the world, a claim supporting a hypothesis is about our reasoning, and
        # only one of them may reach a projection.
        sa.Column("stance", sa.Text(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("linked_by", sa.Text(), nullable=False),
        sa.Column(
            "linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("detached_at", sa.DateTime(timezone=True)),
        # `stance` is part of the key: the same claim may be linked under both,
        # by two analysts or by one who thinks it cuts both ways (Article VIII).
        sa.PrimaryKeyConstraint("hypothesis_id", "claim_id", "stance"),
        sa.CheckConstraint(
            "stance IN ('supports', 'contradicts')", name="ck_hypothesis_claim_stance"
        ),
    )
    op.create_index("ix_hypothesis_claim_claim_id", "hypothesis_claim", ["claim_id"])

    op.create_table(
        "investigation_task",
        sa.Column("task_id", sa.Text(), primary_key=True),
        sa.Column("case_id", sa.Text(), sa.ForeignKey("case_file.case_id"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False, server_default=sa.text("'task'")),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'open'")),
        # Unassigned is a real state; inventing an owner to avoid a null would
        # make the queue look attended when it is not.
        sa.Column("owner", sa.Text()),
        sa.Column("due_date", sa.Date()),
        sa.Column("hypothesis_id", sa.Text(), sa.ForeignKey("hypothesis.hypothesis_id")),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("kind IN ('task', 'lead')", name="ck_investigation_task_kind"),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'blocked', 'done', 'dropped')",
            name="ck_investigation_task_status",
        ),
    )
    op.create_index("ix_investigation_task_case_id", "investigation_task", ["case_id"])


def downgrade() -> None:
    # Reverse dependency order: tasks reference hypotheses, revisions and links
    # reference hypotheses, and every one of them references a case.
    op.drop_index("ix_investigation_task_case_id", table_name="investigation_task")
    op.drop_table("investigation_task")
    op.drop_index("ix_hypothesis_claim_claim_id", table_name="hypothesis_claim")
    op.drop_table("hypothesis_claim")
    op.drop_table("hypothesis_revision")
    op.drop_index("ix_hypothesis_case_id", table_name="hypothesis")
    op.drop_table("hypothesis")
    op.drop_index("ix_case_reference_target", table_name="case_reference")
    op.drop_table("case_reference")
