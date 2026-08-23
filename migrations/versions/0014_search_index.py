"""The searchable-document projection, and the normalization stamp (T67).

Two things, and the second is the interesting one.

**`document_text_projection`** exists because document text is not in
PostgreSQL (ADR-051). `source_record.storage_uri` and `derivative.storage_uri`
point at the object store; the database holds a hash and a URI, so there is
nothing to index and no handling code to filter by on a blob. The projection
carries the text, its `tsvector`, and the governance columns a row filter needs
— `handling_code` **copied from the record**, never defaulted, for the same
reason `location_geometry_projection` copies its own (spec 11 §2.3).

`tsv` is a **generated** column rather than one the builder writes, so it
cannot drift from the text beside it. Its configuration is `simple` on purpose:
there is no Sinhala or Tamil stemmer, and applying an English one to Sinhala
would mangle it while looking like it worked.

**`mention.normalization_version`** is the ADR-052 stamp, and this migration
does more than add the column. Every existing key was written by the pipeline
*before* it was versioned, and v1 changes behaviour: format characters (ZWJ,
ZWNJ, bidi marks) are now removed rather than turned into a separator, so a
zero-width joiner inside a Sinhala name no longer splits the token into two
keys (spec 11 §3.1 stage 6).

So the rows are **recomputed, not merely stamped**. Stamping them would assert
something untrue and leave the corpus half-normalized, with the failure mode
this whole mechanism exists to prevent: missing results that nothing reports.

Recomputation is safe because a mention key is a *blocking and lookup key,
never identity* (Article V): `identity_membership` is keyed by `mention_id`, and
no identity decision reads a key's value. This is the precise opposite of
`claim.ontology_version` (ADR-013), where the stamp is history and
recomputation is forbidden. A cache may be rebuilt; an assertion may not.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

#: Recompute in batches so a large corpus does not build one enormous
#: transaction. Correctness does not depend on the size; memory does.
_BATCH = 1_000


def upgrade() -> None:
    op.create_table(
        "document_text_projection",
        sa.Column("projection_id", sa.Text(), primary_key=True),
        sa.Column(
            "record_id",
            sa.Text(),
            sa.ForeignKey("source_record.record_id"),
            nullable=False,
        ),
        sa.Column(
            "derivative_id", sa.Text(), sa.ForeignKey("derivative.derivative_id")
        ),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("handling_code", sa.Text(), nullable=False),
        sa.Column("handling_rank", sa.Integer(), nullable=False),
        sa.Column("normalization_version", sa.Text(), nullable=False),
        sa.Column("builder_version", sa.Text(), nullable=False),
        sa.Column(
            "built_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "record_id", "derivative_id", name="uq_document_text_record_derivative"
        ),
    )
    # Generated, not written: the builder cannot forget to update it, and a
    # hand-written UPDATE cannot desynchronise it from the text.
    op.execute(
        "ALTER TABLE document_text_projection "
        "ADD COLUMN tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED"
    )
    op.create_index("ix_document_text_record", "document_text_projection", ["record_id"])
    op.create_index(
        "ix_document_text_handling", "document_text_projection", ["handling_rank"]
    )
    op.create_index(
        "ix_document_text_tsv",
        "document_text_projection",
        ["tsv"],
        postgresql_using="gin",
    )

    op.add_column("mention", sa.Column("normalization_version", sa.Text()))
    _recompute_mention_keys()


def _recompute_mention_keys() -> None:
    """Rebuild every mention key with the versioned pipeline, then stamp it.

    Imported inside the function rather than at module scope: a migration must
    not make the alembic environment depend on the search package being
    importable, and `alembic history` should not import a transliterator.
    """
    from aegis.search.pipeline import NORMALIZATION_VERSION, search_keys

    bind = op.get_bind()
    rows = bind.exec_driver_sql(
        "SELECT mention_id, raw_text FROM mention ORDER BY mention_id"
    ).fetchall()

    updates = [
        {
            "mention_id": mention_id,
            "norm_key": keys.norm,
            "latin_key": keys.latin,
            "phonetic_key": keys.phonetic,
            "script": keys.script,
            "version": keys.version,
        }
        for mention_id, raw_text in rows
        if (keys := search_keys(raw_text))
    ]

    statement = sa.text(
        "UPDATE mention SET norm_key = :norm_key, latin_key = :latin_key, "
        "phonetic_key = :phonetic_key, script = :script, "
        "normalization_version = :version WHERE mention_id = :mention_id"
    )
    for start in range(0, len(updates), _BATCH):
        bind.execute(statement, updates[start : start + _BATCH])

    stale = bind.exec_driver_sql(
        "SELECT count(*) FROM mention WHERE normalization_version IS DISTINCT FROM "
        f"'{NORMALIZATION_VERSION}'"
    ).scalar()
    if stale:
        raise RuntimeError(
            f"{stale} mention rows were not recomputed by this migration. A key "
            "at an unknown pipeline version silently stops matching every query "
            "key, and the failure mode is missing results (ADR-052) — so the "
            "upgrade stops here rather than leave the corpus half-normalized."
        )


def downgrade() -> None:
    op.drop_column("mention", "normalization_version")
    op.drop_index("ix_document_text_tsv", table_name="document_text_projection")
    op.drop_index("ix_document_text_handling", table_name="document_text_projection")
    op.drop_index("ix_document_text_record", table_name="document_text_projection")
    op.drop_table("document_text_projection")
    # The recomputed keys are deliberately left recomputed. They are derived
    # data with no prior version recorded anywhere, so "restoring" them would
    # mean recomputing with a pipeline this branch no longer has — inventing a
    # past rather than undoing a change. Nothing reads a key as identity
    # (Article V), so leaving them costs nothing.
