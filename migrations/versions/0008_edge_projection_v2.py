"""edge_projection v2: time-segmented, identity-resolved, honestly aggregated.

Replaces the Phase-1 materialized view (migration ``0006``) that ADR-030
condemns.  That view did three things this one refuses to do:

* collapsed disjoint validity intervals with ``min``/``max``, inventing an
  unbroken edge across years nobody claimed anything about;
* reduced every contradiction to ``max(projection_weight(...))``, so the
  loudest claim silently won and the disagreement disappeared (Article VIII);
* counted distinct records and called them ``independent_records``, which is a
  claim about source derivation Aegis cannot substantiate (ADR-030 §3).

A **table**, not a matview: one row per maximal interval over which the same
supporting claim set holds is not expressible as a single ``GROUP BY``
(specs/02 §7).  ``aegis.projections.edges`` owns the build; losing the whole
table loses nothing (Article XIII).

``projection_weight()`` is dropped with the view.  A display score is still
computed — but in the emitter, from the visible claims, where it is inspectable
(specs/02 §7).  ``handling_code_rank()`` survives: it is the single definition
of the row-filter ordering and the v2 builder selects it.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

# Kept verbatim from 0006 so the downgrade restores the Phase-1 view exactly.
PROJECTION_WEIGHT_SQL = """
CREATE FUNCTION projection_weight(credibility text) RETURNS double precision
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE credibility
    WHEN 'confirmed'     THEN 1.0
    WHEN 'probably_true' THEN 0.7
    WHEN 'possibly_true' THEN 0.55
    WHEN 'doubtful'      THEN 0.4
    WHEN 'improbable'    THEN 0.2
    WHEN 'cannot_judge'  THEN 0.4
    ELSE 0.4
  END
$$
"""

LEGACY_EDGE_PROJECTION_SQL = """
CREATE MATERIALIZED VIEW edge_projection AS
SELECT subject_id,
       object_id,
       predicate,
       min(valid_from)                          AS valid_from,
       CASE WHEN bool_or(valid_to IS NULL) THEN NULL ELSE max(valid_to) END AS valid_to,
       count(*)                                 AS claim_count,
       count(DISTINCT record_id)                AS independent_records,
       max(projection_weight(credibility_normalized)) AS weight,
       array_agg(claim_id ORDER BY claim_id)    AS claim_ids,
       max(handling_code_rank(handling_code))   AS handling_rank
FROM claim
WHERE object_id IS NOT NULL
  AND retracted_at IS NULL
GROUP BY subject_id, object_id, predicate
"""


def upgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW edge_projection")
    op.execute("DROP FUNCTION projection_weight(text)")

    op.create_table(
        "edge_projection",
        # Content-derived (see aegis.projections.edges): the same segment keeps
        # the same id across rebuilds, so a rebuild is idempotent in identity
        # as well as in content and two builds are diffable.
        sa.Column("edge_id", sa.Text(), primary_key=True),
        # Canonical at build time — the merge/split collapse and restore happen
        # here, with zero claim rows rewritten (ADR-029 §3).
        sa.Column(
            "subject_id", sa.Text(), sa.ForeignKey("entity.entity_id"), nullable=False
        ),
        sa.Column(
            "object_id", sa.Text(), sa.ForeignKey("entity.entity_id"), nullable=False
        ),
        sa.Column("predicate", sa.Text(), nullable=False),
        # NULL bounds are genuinely open, not unknown: NULL segment_from means
        # the supporting claims state no start, and the segment is unbounded.
        sa.Column("segment_from", sa.Date()),
        sa.Column("segment_to", sa.Date()),
        sa.Column(
            "claim_ids", postgresql.ARRAY(sa.Text()), nullable=False
        ),
        # DISTINCT source records. Never "independent" — see the module note.
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("support", postgresql.JSONB(), nullable=False),
        sa.Column("handling_rank", sa.Integer(), nullable=False),
        # Stamps: what identity, vocabulary and code produced this row, so a
        # stale projection is detectable rather than quietly wrong.
        sa.Column(
            "built_at_revision_id",
            sa.BigInteger(),
            sa.ForeignKey("identity_revision.revision_id"),
            nullable=False,
        ),
        sa.Column("ontology_version", sa.Text(), nullable=False),
        sa.Column("builder_version", sa.Text(), nullable=False),
    )

    # "One row per maximal interval" as a database invariant, not a convention.
    # NULLS NOT DISTINCT (PostgreSQL 15+) is what makes it hold for open
    # starts: without it every unbounded segment would be trivially unique.
    op.execute(
        "CREATE UNIQUE INDEX ux_edge_projection_segment "
        "ON edge_projection (subject_id, object_id, predicate, segment_from) "
        "NULLS NOT DISTINCT"
    )
    op.create_index("ix_edge_projection_subject", "edge_projection", ["subject_id"])
    op.create_index("ix_edge_projection_object", "edge_projection", ["object_id"])
    op.create_index("ix_edge_projection_predicate", "edge_projection", ["predicate"])
    # Traversal filters on handling before it filters on anything else.
    op.create_index("ix_edge_projection_handling", "edge_projection", ["handling_rank"])


def downgrade() -> None:
    """Lossy: the support summaries and segment boundaries are not recoverable.

    The Phase-1 view is recreated with its original fabrications intact — that
    is what downgrading to Phase 1 *means*.  Rebuild forward with
    ``aegis projections rebuild`` rather than relying on this path for data.
    """
    op.drop_table("edge_projection")
    op.execute(PROJECTION_WEIGHT_SQL)
    op.execute(LEGACY_EDGE_PROJECTION_SQL)
    op.execute(
        "CREATE UNIQUE INDEX ux_edge_projection "
        "ON edge_projection (subject_id, object_id, predicate)"
    )
    op.execute("CREATE INDEX ix_edge_projection_object ON edge_projection (object_id)")
