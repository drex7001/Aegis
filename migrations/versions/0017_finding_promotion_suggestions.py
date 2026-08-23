"""`ck_review_queue_kind` admits `finding_promotion` (T74, spec 12 §10).

One line, and the reason it needs a migration at all is the point: the set of
things a machine may propose is enforced by the **database**, not by the
dictionary in `aegis/actions/service.py`. Adding a kind in Python and finding
out at insert time — which is exactly how this was found — is the constraint
working.

Promotion dispatches to `record_claim`, so no new result column is needed and
`ck_review_queue_accepted_result` is untouched: an accepted promotion produces
exactly one claim, which is one typed result, which is what that check already
requires.

Nothing existing changes. Article VII is unweakened — this is the mechanism
that *keeps* a machine from turning its own reading into an assertion, and a
finding promotion is now inside it rather than beside it.

Revision ID: 0017
Revises: 0016
"""

from __future__ import annotations

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

_KINDS_BEFORE = "('claim_draft', 'identity_candidate', 'claim_relation', 'event_draft')"
_KINDS_AFTER = (
    "('claim_draft', 'identity_candidate', 'claim_relation', 'event_draft', "
    "'finding_promotion')"
)


def upgrade() -> None:
    op.drop_constraint("ck_review_queue_kind", "review_queue", type_="check")
    op.create_check_constraint(
        "ck_review_queue_kind", "review_queue", f"suggestion_kind IN {_KINDS_AFTER}"
    )


def downgrade() -> None:
    """Refuses if any promotion has been queued.

    The same rule migration `0013` set for `event_draft`: narrowing a
    vocabulary that rows already use would leave suggestions the constraint
    says cannot exist. Failing loudly is the honest outcome — the alternative
    is a database that disagrees with itself.
    """
    queued = op.get_bind().exec_driver_sql(
        "SELECT count(*) FROM review_queue WHERE suggestion_kind = 'finding_promotion'"
    ).scalar()
    if queued:
        raise RuntimeError(
            f"{queued} finding_promotion suggestion(s) exist; narrowing "
            "ck_review_queue_kind would leave rows the constraint forbids. "
            "Decide or delete them first."
        )
    op.drop_constraint("ck_review_queue_kind", "review_queue", type_="check")
    op.create_check_constraint(
        "ck_review_queue_kind", "review_queue", f"suggestion_kind IN {_KINDS_BEFORE}"
    )
