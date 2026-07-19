"""Store the transliteration keys search has to reach (ADR-035).

``norm_key`` preserves non-Latin script deliberately — in Sinhala and Tamil the
combining marks are vowel signs, and folding them merges names that are not the
same name.  The consequence is that no key derivable from a Latin query is ever
Sinhala, so ``GET /v1/search/entities`` cannot find a Sinhala mention by its
romanization while ``norm_key`` is the only thing indexed.

``latin_key`` and ``phonetic_key`` already existed in ``aegis/er/translit.py``;
they were computed per run inside ``aegis/er/features.py`` and never stored, so
no query could reach them.  Storing them puts cross-script matching inside one
SQL statement, which is what lets authorization stay in candidate generation
rather than in hydration (spec 06 §2.1, ADR-012, B-17).

Nullable, and derived: losing them costs a backfill, never a fact (Article V).
The backfill runs in Python because the keys are Python — ``unidecode`` and
metaphone have no faithful SQL equivalent, and an approximation here would
silently disagree with the ER pipeline that produced the ones already in use.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_BATCH = 1000


def upgrade() -> None:
    op.add_column("mention", sa.Column("latin_key", sa.Text(), nullable=True))
    op.add_column("mention", sa.Column("phonetic_key", sa.Text(), nullable=True))

    _backfill()

    # Created after the backfill: building an index once over finished data is
    # cheaper than maintaining it across every batched UPDATE above.
    op.create_index(
        "ix_mention_latin_key_trgm",
        "mention",
        ["latin_key"],
        postgresql_using="gin",
        postgresql_ops={"latin_key": "gin_trgm_ops"},
    )
    op.create_index("ix_mention_phonetic_key", "mention", ["phonetic_key"])


def _backfill() -> None:
    """Compute the keys for rows that predate the columns.

    Imported here rather than at module scope so that a migration run in an
    environment without the ER extras still imports; if the helpers are
    genuinely unavailable the columns stay null and `aegis identity
    backfill-keys` can fill them later, which is a degraded search rather than
    a failed upgrade.
    """
    try:
        from aegis.er.translit import latin_key, phonetic_key
    except ImportError:  # pragma: no cover - transliteration extras absent
        return

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT mention_id, raw_text FROM mention")
    ).fetchall()
    updates = [
        {
            "id": mention_id,
            "latin": latin_key(raw_text),
            "phonetic": phonetic_key(raw_text),
        }
        for mention_id, raw_text in rows
    ]
    statement = sa.text(
        "UPDATE mention SET latin_key = :latin, phonetic_key = :phonetic "
        "WHERE mention_id = :id"
    )
    for start in range(0, len(updates), _BATCH):
        connection.execute(statement, updates[start : start + _BATCH])


def downgrade() -> None:
    op.drop_index("ix_mention_phonetic_key", table_name="mention")
    op.drop_index("ix_mention_latin_key_trgm", table_name="mention")
    op.drop_column("mention", "phonetic_key")
    op.drop_column("mention", "latin_key")
