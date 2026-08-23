"""The review queue learns to hold an occurrence (T58, proposal 008).

Three changes, one idea: a producer may now propose a whole event, and the queue
has to be able to say what accepting it created.

* `ck_review_queue_kind` admits `event_draft`.
* `result_entity_id` records the occurrence an acceptance produced — the entity
  rather than one of its claims, because the claims are reachable from it and
  picking one of them as *the* result would be arbitrary.
* `ck_review_queue_accepted_result` still requires **exactly one** typed result,
  now across four columns instead of three. The invariant is unchanged; only its
  arity moved. That check is what makes "acceptance wrote one kind of thing"
  answerable by the database rather than by reading the dispatch branch.

Nothing existing changes. Every suggestion already in a queue keeps its kind, its
target action and its meaning (Article VII is unweakened — this is the mechanism
that *keeps* a machine from writing an event directly).

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_KINDS_BEFORE = "('claim_draft', 'identity_candidate', 'claim_relation')"
_KINDS_AFTER = "('claim_draft', 'identity_candidate', 'claim_relation', 'event_draft')"


def upgrade() -> None:
    op.add_column(
        "review_queue",
        sa.Column("result_entity_id", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_review_queue_result_entity",
        "review_queue",
        "entity",
        ["result_entity_id"],
        ["entity_id"],
    )

    op.drop_constraint("ck_review_queue_kind", "review_queue", type_="check")
    op.create_check_constraint(
        "ck_review_queue_kind", "review_queue", f"suggestion_kind IN {_KINDS_AFTER}"
    )

    op.drop_constraint("ck_review_queue_accepted_result", "review_queue", type_="check")
    op.create_check_constraint(
        "ck_review_queue_accepted_result",
        "review_queue",
        "status <> 'accepted' OR num_nonnulls(result_claim_id, result_decision_id, "
        "result_relation, result_entity_id) = 1",
    )


def downgrade() -> None:
    # Refuses rather than discards: an accepted event_draft's result lives in the
    # column this would drop, and losing which occurrence a reviewer admitted is
    # not something a schema rollback may do quietly (Article X).
    accepted = (
        op.get_bind()
        .exec_driver_sql(
            "SELECT count(*) FROM review_queue WHERE suggestion_kind = 'event_draft'"
        )
        .scalar_one()
    )
    if accepted:
        raise RuntimeError(
            f"{accepted} event_draft suggestion(s) exist; downgrading would drop "
            "the record of which occurrence each acceptance created. Decide or "
            "delete them first."
        )

    op.drop_constraint("ck_review_queue_accepted_result", "review_queue", type_="check")
    op.create_check_constraint(
        "ck_review_queue_accepted_result",
        "review_queue",
        "status <> 'accepted' OR num_nonnulls(result_claim_id, result_decision_id, "
        "result_relation) = 1",
    )
    op.drop_constraint("ck_review_queue_kind", "review_queue", type_="check")
    op.create_check_constraint(
        "ck_review_queue_kind", "review_queue", f"suggestion_kind IN {_KINDS_BEFORE}"
    )
    op.drop_constraint("fk_review_queue_result_entity", "review_queue", type_="foreignkey")
    op.drop_column("review_queue", "result_entity_id")
