"""Migration 0009 lifecycle: the stored transliteration keys (ADR-035).

Two things worth proving beyond "the columns appear". The **backfill** has to
compute keys for rows that predate the columns, or search silently misses every
mention ingested before this migration — a failure that looks exactly like "no
match". And the **downgrade** has to leave the mention rows intact, because the
keys are derived data: dropping them costs a reindex, never a fact (Article V).
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from aegis.er.translit import latin_key, phonetic_key
from aegis.store import Base

pytestmark = pytest.mark.requirement("Article-V", "ADR-035", "T23c")

TRANSLIT_COLUMNS = {"latin_key", "phonetic_key"}
#: Fictional, and deliberately non-Latin: the whole point of the columns is the
#: script `norm_key` refuses to fold.
SINHALA_NAME = "නිමල් පෙරේරා"


def test_translit_columns_backfill_up_and_drop_down_without_losing_mentions(
    monkeypatch: pytest.MonkeyPatch,
    test_database_url: str,
    alembic_config: Config,
) -> None:
    monkeypatch.setenv("AEGIS_DATABASE_URL", test_database_url)
    from aegis.config import get_settings

    get_settings.cache_clear()
    engine = sa.create_engine(test_database_url)

    try:
        # Stand at the revision before the columns existed, and seed a mention
        # there — this is the row a naive "add column" migration would leave
        # permanently unsearchable.
        command.downgrade(alembic_config, "0008")
        with engine.begin() as connection:
            columns = {
                row[0]
                for row in connection.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'mention'"
                    )
                )
            }
            assert TRANSLIT_COLUMNS.isdisjoint(columns)
            _seed_legacy_mention(connection)

        command.upgrade(alembic_config, "head")

        inspector = sa.inspect(engine)
        actual = {column["name"] for column in inspector.get_columns("mention")}
        assert TRANSLIT_COLUMNS <= actual
        assert actual == set(Base.metadata.tables["mention"].c.keys())

        indexes = {index["name"] for index in inspector.get_indexes("mention")}
        assert {"ix_mention_latin_key_trgm", "ix_mention_phonetic_key"} <= indexes

        with engine.connect() as connection:
            row = connection.execute(
                sa.text(
                    "SELECT raw_text, norm_key, latin_key, phonetic_key FROM mention "
                    "WHERE mention_id = 'men_legacy_0009'"
                )
            ).one()
        raw_text, norm, latin, phonetic = row
        # Backfilled, and backfilled with the *same* functions the ER pipeline
        # uses — an approximation here would disagree with keys already in use.
        assert latin == latin_key(raw_text)
        assert phonetic == phonetic_key(raw_text)
        assert not norm.isascii(), "norm_key still preserves the script"
        assert latin.isascii(), "latin_key is the romanization search can reach"

        command.downgrade(alembic_config, "0008")
        downgraded = {
            column["name"] for column in sa.inspect(engine).get_columns("mention")
        }
        assert TRANSLIT_COLUMNS.isdisjoint(downgraded)
        with engine.connect() as connection:
            survivors = connection.execute(
                sa.text("SELECT count(*) FROM mention WHERE mention_id = 'men_legacy_0009'")
            ).scalar_one()
        assert survivors == 1, "derived columns go, the mention stays"
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            _remove_legacy_fixture(connection)
        engine.dispose()
        get_settings.cache_clear()


def _seed_legacy_mention(connection: sa.Connection) -> None:
    connection.execute(
        sa.text(
            "INSERT INTO source (source_id, source_type, name) "
            "VALUES ('src_legacy_0009', 'open_source', 'ADR-035 fixture') "
            "ON CONFLICT DO NOTHING"
        )
    )
    connection.execute(
        sa.text(
            "INSERT INTO source_record "
            "(record_id, source_id, ingest_key, content_hash, storage_uri) "
            "VALUES ('rec_legacy_0009', 'src_legacy_0009', 'key_legacy_0009', "
            ":digest, 'test://adr-035') ON CONFLICT DO NOTHING"
        ),
        {"digest": "d" * 64},
    )
    connection.execute(
        sa.text(
            "INSERT INTO mention (mention_id, record_id, raw_text, norm_key) "
            "VALUES ('men_legacy_0009', 'rec_legacy_0009', :raw, :norm) "
            "ON CONFLICT DO NOTHING"
        ),
        # norm_key as the pre-0009 pipeline would have written it: the script
        # intact, which is precisely why it cannot answer a Latin query.
        {"raw": SINHALA_NAME, "norm": SINHALA_NAME.replace(" ", "_")},
    )


def _remove_legacy_fixture(connection: sa.Connection) -> None:
    connection.execute(sa.text("DELETE FROM mention WHERE mention_id = 'men_legacy_0009'"))
    connection.execute(
        sa.text("DELETE FROM source_record WHERE record_id = 'rec_legacy_0009'")
    )
    connection.execute(sa.text("DELETE FROM source WHERE source_id = 'src_legacy_0009'"))
