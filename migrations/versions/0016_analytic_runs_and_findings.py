"""Analytic runs and findings — two tables, and a claim is neither (T72).

The charter's second exit criterion is that "findings and claims are different
tables with different lifecycles". This migration is where that stops being a
sentence.

What is deliberately absent: any foreign key from `claim` to
`analytic_finding`. `analytic_finding.promoted_claim_id` points *at* a claim,
so a finding can say which claim it became the basis of — but nothing points
back, because a claim reachable *as* a finding would be one lifecycle wearing
two names. Promotion (spec 12 §10) writes a new claim and leaves the finding
standing.

`analytic_run` is the manifest H-23 asks for, written before the algorithm runs
and never updated. Its `projection_*` columns record **which** projection was
read rather than whether it was fresh — which is what closes the Phase-5
`is_stale` carryover without changing what `is_stale` means.

`seed` is nullable on purpose: NULL records an **unseeded** run as unseeded,
rather than storing a zero that would later read as determinism the run never
had.

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytic_run",
        sa.Column("run_id", sa.Text(), primary_key=True),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("method_version", sa.Text(), nullable=False),
        sa.Column("implementation", sa.Text(), nullable=False),
        sa.Column(
            "parameters", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("seed", sa.Integer()),
        sa.Column("input_kind", sa.Text(), nullable=False),
        sa.Column("object_set_id", sa.Text(), sa.ForeignKey("object_set.set_id")),
        sa.Column("object_set_version", sa.Integer()),
        sa.Column("evaluation_digest", sa.Text()),
        sa.Column("edge_digest", sa.Text(), nullable=False),
        sa.Column("projection_built_at_revision_id", sa.BigInteger()),
        sa.Column("projection_builder_version", sa.Text()),
        sa.Column("projection_aggregation_method_version", sa.Text()),
        sa.Column("ontology_version", sa.Text(), nullable=False),
        sa.Column("identity_revision_id", sa.BigInteger(), nullable=False),
        sa.Column("code_version", sa.Text(), nullable=False),
        sa.Column("settings_digest", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text()),
        sa.Column("authorization_digest", sa.Text(), nullable=False),
        sa.Column("caveat_version", sa.Text(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "input_kind IN ('object_set', 'projection')",
            name="ck_analytic_run_input_kind",
        ),
        # An object-set run has to say which set *and* which version: a finding
        # naming a set without a version names something that can move under
        # it (spec 12 §3).
        sa.CheckConstraint(
            "input_kind <> 'object_set' OR "
            "(object_set_id IS NOT NULL AND object_set_version IS NOT NULL "
            "AND evaluation_digest IS NOT NULL)",
            name="ck_analytic_run_object_set_complete",
        ),
    )
    op.create_index("ix_analytic_run_method", "analytic_run", ["method"])
    op.create_index("ix_analytic_run_set", "analytic_run", ["object_set_id"])

    op.create_table(
        "analytic_finding",
        sa.Column("finding_id", sa.Text(), primary_key=True),
        sa.Column(
            "run_id", sa.Text(), sa.ForeignKey("analytic_run.run_id"), nullable=False
        ),
        sa.Column("finding_type", sa.Text(), nullable=False),
        sa.Column("subjects", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column("caveat_text", sa.Text(), nullable=False),
        sa.Column("caveat_version", sa.Text(), nullable=False),
        sa.Column("finding_digest", sa.Text(), nullable=False),
        sa.Column("promoted_claim_id", sa.Text(), sa.ForeignKey("claim.claim_id")),
        sa.Column("handling_code", sa.Text(), nullable=False),
        sa.Column("handling_rank", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # A caveat is not optional and not blank. Article IX is enforced at the
        # column, so a finding cannot exist without the sentence that says how
        # to read it — not even one written by a future code path that forgot.
        sa.CheckConstraint("length(btrim(caveat_text)) > 0", name="ck_finding_has_caveat"),
        sa.UniqueConstraint("run_id", "finding_digest", name="uq_analytic_finding_digest"),
    )
    op.create_index("ix_analytic_finding_run", "analytic_finding", ["run_id"])
    op.create_index("ix_analytic_finding_type", "analytic_finding", ["finding_type"])
    op.create_index(
        "ix_analytic_finding_handling", "analytic_finding", ["handling_rank"]
    )


def downgrade() -> None:
    op.drop_index("ix_analytic_finding_handling", table_name="analytic_finding")
    op.drop_index("ix_analytic_finding_type", table_name="analytic_finding")
    op.drop_index("ix_analytic_finding_run", table_name="analytic_finding")
    op.drop_table("analytic_finding")
    op.drop_index("ix_analytic_run_set", table_name="analytic_run")
    op.drop_index("ix_analytic_run_method", table_name="analytic_run")
    op.drop_table("analytic_run")
