"""Watchlists, alerts, and the sweep watermark (T75, spec 12 §11, ADR-060).

Two tables and one column, and the reason the tables are new rather than a
widened `review_queue` is ADR-060: an alert dispatches to no action, produces no
typed result on acceptance, uses a different status vocabulary, and takes its
sensitivity from the **claims** that triggered it rather than from a source
record. Reusing the queue would have given alerts a visibility rule keyed on the
wrong thing, quietly, in the direction that discloses.

`analytic_run.evaluated_through` is the sweep watermark. It lives on the run
rather than on the watchlist so that "a window that was never evaluated is a
visible gap in the runs" is literally true — you read the runs, and a
denormalized field on the watchlist cannot disagree with them because there
isn't one.

Revision ID: 0018
Revises: 0017
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analytic_run",
        sa.Column("evaluated_through", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "watchlist",
        sa.Column("watchlist_id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "set_id", sa.Text(), sa.ForeignKey("object_set.set_id"), nullable=False
        ),
        sa.Column("set_version", sa.Integer(), nullable=False),
        sa.Column("rule", sa.Text(), nullable=False),
        sa.Column("rule_version", sa.Text(), nullable=False),
        # Sweeps run as the owner, not as the caller (spec 12 §11.3).
        sa.Column("owner", sa.Text(), nullable=False),
        # The owner's clearance, snapshotted at creation. There is no user
        # table to look one up from — Keycloak holds it — so a sweep running
        # offline has to carry the number with the watchlist. Captured from
        # the creator's own token, so it can never exceed what they had.
        sa.Column("owner_clearance", sa.Integer(), nullable=False),
        sa.Column(
            "active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("rule IN ('exact_identifier')", name="ck_watchlist_rule"),
    )
    op.create_index("ix_watchlist_active", "watchlist", ["active"])

    op.create_table(
        "watchlist_alert",
        sa.Column("alert_id", sa.Text(), primary_key=True),
        sa.Column(
            "watchlist_id",
            sa.Text(),
            sa.ForeignKey("watchlist.watchlist_id"),
            nullable=False,
        ),
        sa.Column(
            "run_id", sa.Text(), sa.ForeignKey("analytic_run.run_id"), nullable=False
        ),
        sa.Column("rule", sa.Text(), nullable=False),
        sa.Column("rule_version", sa.Text(), nullable=False),
        sa.Column("matched_value", sa.Text(), nullable=False),
        sa.Column(
            "entity_id", sa.Text(), sa.ForeignKey("entity.entity_id"), nullable=False
        ),
        sa.Column("claim_ids", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=False),
        sa.Column("exactness", sa.Text(), nullable=False),
        # B-08 seam: nullable now, enforced P7.
        sa.Column("authority_ref", sa.Text(), nullable=True),
        sa.Column("handling_code", sa.Text(), nullable=False),
        sa.Column("handling_rank", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'new'")
        ),
        sa.Column("closed_reason", sa.Text(), nullable=True),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('new', 'reviewing', 'closed')",
            name="ck_watchlist_alert_status",
        ),
        sa.CheckConstraint(
            "exactness IN ('exact')", name="ck_watchlist_alert_exactness"
        ),
        sa.CheckConstraint(
            "status <> 'closed' OR (closed_reason IS NOT NULL "
            "AND length(btrim(closed_reason)) > 0)",
            name="ck_watchlist_alert_closed_reason",
        ),
        sa.UniqueConstraint("dedupe_key", name="uq_watchlist_alert_dedupe"),
    )
    op.create_index(
        "ix_watchlist_alert_watchlist_status",
        "watchlist_alert",
        ["watchlist_id", "status"],
    )
    op.create_index(
        "ix_watchlist_alert_handling", "watchlist_alert", ["handling_rank"]
    )


def downgrade() -> None:
    """Refuses while any alert exists.

    The rule migrations `0013` and `0017` set. Dropping a table that holds
    triaged detections would discard the record of decisions people made — and
    unlike a widened enum, there is no narrower state to fall back to.
    """
    alerts = op.get_bind().exec_driver_sql(
        "SELECT count(*) FROM watchlist_alert"
    ).scalar()
    if alerts:
        raise RuntimeError(
            f"{alerts} watchlist alert(s) exist; dropping the table would "
            "discard triage decisions. Close and export them first."
        )
    op.drop_index("ix_watchlist_alert_handling", table_name="watchlist_alert")
    op.drop_index("ix_watchlist_alert_watchlist_status", table_name="watchlist_alert")
    op.drop_table("watchlist_alert")
    op.drop_index("ix_watchlist_active", table_name="watchlist")
    op.drop_table("watchlist")
    op.drop_column("analytic_run", "evaluated_through")
