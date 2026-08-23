"""PostGIS, the geometry projection, and the index the time filter needs (T56).

Three things, and the first is a correction. The Phase 5 charter said "Phase 1
already enabled the PostGIS extension (migration 0001)". It did not: `0001` is
an empty baseline marker and `0002` creates only `pg_trgm`. The image has been
`postgis/postgis:16-3.4` in compose and in both CI database jobs all along, so
the extension was always one line away — it had just never been written
(spec 10 §0 D1).

**`location_geometry_projection`** is the phase's only new table, and it is a
cache (Article XIII, B-13). One row per geometry *claim*, not per place: two
claims for one location at different handling codes are two rows, so
`claim_filters` composes unchanged and each viewer sees the finest geometry they
may read (spec 10 §7.2). Every governance column the claim carries is copied,
because a filter that had to join back to `claim` would be one forgotten join
away from a leak.

There is deliberately **no** event table and **no** participation table. Those
would be a copy of `claim` rows plus a derived column; what this table buys that
`claim.object_value` JSONB cannot is a GIST index over real geometry.

The `claim(event_time_earliest, event_time_latest)` index is the other half of
that answer: it is why the shared time filter over map, timeline and graph can
read `claim` directly instead of needing a projection of its own
(spec 10 §6.1, §11.2).

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "location_geometry_projection",
        sa.Column("claim_id", sa.Text(), sa.ForeignKey("claim.claim_id"), primary_key=True),
        sa.Column("place_id", sa.Text(), sa.ForeignKey("entity.entity_id"), nullable=False),
        # Nullable: an invalid geometry is recorded with its reason and never
        # repaired. `ST_MakeValid` would change what a source said.
        sa.Column("geom", sa.Text().with_variant(sa.Text(), "postgresql"), nullable=True),
        sa.Column("geometry_kind", sa.Text(), nullable=False),
        sa.Column("admin_level", sa.Text(), nullable=False),
        sa.Column("accuracy_m", sa.Numeric(), nullable=True),
        sa.Column("derivation", sa.Text(), nullable=False),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
        sa.Column("invalid_reason", sa.Text(), nullable=True),
        sa.Column("handling_code", sa.Text(), nullable=False),
        sa.Column("handling_rank", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.Text(), sa.ForeignKey("case_file.case_id"), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ontology_version", sa.Text(), nullable=False),
        sa.Column("builder_version", sa.Text(), nullable=False),
    )
    # `geom` is created as TEXT above and retyped here, because alembic's column
    # types are SQLAlchemy's and PostGIS's `geometry` is not one of them. Doing
    # it in two statements keeps the DDL readable and the SRID explicit — and
    # the table is empty at this point, so the conversion has nothing to touch.
    op.execute(
        "ALTER TABLE location_geometry_projection "
        "ALTER COLUMN geom TYPE geometry(Geometry, 4326) USING NULL"
    )

    op.create_index(
        "ix_location_geometry_place", "location_geometry_projection", ["place_id"]
    )
    op.create_index(
        "ix_location_geometry_handling", "location_geometry_projection", ["handling_rank"]
    )
    op.create_index(
        "ix_location_geometry_geom",
        "location_geometry_projection",
        ["geom"],
        postgresql_using="gist",
    )

    op.create_index(
        "ix_claim_event_time",
        "claim",
        ["event_time_earliest", "event_time_latest"],
    )


def downgrade() -> None:
    op.drop_index("ix_claim_event_time", table_name="claim")
    op.drop_index("ix_location_geometry_geom", table_name="location_geometry_projection")
    op.drop_index("ix_location_geometry_handling", table_name="location_geometry_projection")
    op.drop_index("ix_location_geometry_place", table_name="location_geometry_projection")
    op.drop_table("location_geometry_projection")
    # The extension is deliberately left in place. Dropping it would fail on any
    # database where something else uses it, and an extension is not state this
    # migration owns — it is a capability it turned on.
