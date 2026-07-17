"""edge_projection materialized view + projection functions (T10, spec 02 §7).

The weight map is committed code (spec 02 §6 — "tune only with an ADR"), not an
ontology constraint: the functions only *derive* display/traversal values and
default unknown vocabulary safely (weight floor, maximum handling rank), so
ADR-013 is untouched — nothing here rejects a write.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

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

HANDLING_RANK_SQL = """
CREATE FUNCTION handling_code_rank(code text) RETURNS integer
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE code
    WHEN 'open'       THEN 0
    WHEN 'restricted' THEN 1
    WHEN 'sensitive'  THEN 2
    ELSE 999  -- unknown handling never leaks: treat as maximally restricted
  END
$$
"""

EDGE_PROJECTION_SQL = """
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
    op.execute(PROJECTION_WEIGHT_SQL)
    op.execute(HANDLING_RANK_SQL)
    op.execute(EDGE_PROJECTION_SQL)
    # unique index enables REFRESH MATERIALIZED VIEW CONCURRENTLY
    op.execute(
        "CREATE UNIQUE INDEX ux_edge_projection "
        "ON edge_projection (subject_id, object_id, predicate)"
    )
    op.execute("CREATE INDEX ix_edge_projection_object ON edge_projection (object_id)")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW edge_projection")
    op.execute("DROP FUNCTION handling_code_rank(text)")
    op.execute("DROP FUNCTION projection_weight(text)")
