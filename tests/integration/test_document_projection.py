"""The document projection is a cache, and it never writes history (T67, ADR-051).

Two properties, and the second is the one that would be easy to lose.

**It rebuilds.** `TRUNCATE`, rebuild, and the table comes back the same —
Article XIII, and the reason the ids are derived rather than generated: a random
primary key makes every rebuild a different table that merely happens to say the
same thing.

**It never extracts.** Extraction produces a `derivative`, which is a provenance
row — tool, version, parameters, operator, output hash. A cache that could mint
one would write history every time it was rebuilt. So a PDF nobody has extracted
is *absent from the index*, and the test asserts the absence rather than
trusting the docstring.

The handling code is copied from the record, and copied means copied: the test
changes a record's handling code without rebuilding and asserts the projection
still says the old value, because that staleness is exactly why the builder is
the only writer.

Fictional fixtures throughout.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.orm import Session

from aegis.actions import new_id
from aegis.evidence.vault import LocalFilesystemVault, ProvenanceEnvelope
from aegis.ingestion.derivatives import TEXT_KIND
from aegis.ontology import load
from aegis.projections.documents import (
    BUILDER_VERSION,
    rebuild_document_text_projection,
)
from aegis.search.pipeline import NORMALIZATION_VERSION
from aegis.store import Derivative, DocumentTextProjection, Source, SourceRecord
from tests.support.database import migrated_test_engine, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement("Article-XIII", "ADR-051", "T67")

REPORT = "A fictional report about the harbour meeting."
ANNEX = "A fictional annex extracted from a PDF."


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


@pytest.fixture()
def vault(tmp_path):
    return LocalFilesystemVault(tmp_path / "vault")


def _land(vault, text: str, *, media_type: str) -> tuple[str, str]:
    stored = vault.put(
        text.encode("utf-8"),
        ProvenanceEnvelope(
            source_system="test",
            original_filename="fictional.txt",
            connector="tests",
            connector_version="1",
            operator="user:test",
        ),
        media_type=media_type,
    )
    return stored.content_hash, stored.storage_uri


@pytest.fixture()
def world(engine: sa.Engine, vault):
    """Four records: text, an extracted PDF, an un-extracted PDF, a quarantined one."""
    truncate_domain_data(engine)
    session = Session(engine)
    ids = {"source": new_id("src")}
    with session.begin():
        session.add(Source(source_id=ids["source"], source_type="open_source", name="T67"))
        session.flush()

        content_hash, uri = _land(vault, REPORT, media_type="text/plain")
        ids["text_record"] = new_id("rec")
        session.add(
            SourceRecord(
                record_id=ids["text_record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash=content_hash,
                storage_uri=uri,
                media_type="text/plain",
                handling_code="restricted",
            )
        )

        pdf_hash, pdf_uri = _land(vault, "%PDF-fictional", media_type="application/pdf")
        ids["pdf_record"] = new_id("rec")
        session.add(
            SourceRecord(
                record_id=ids["pdf_record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash=pdf_hash,
                storage_uri=pdf_uri,
                media_type="application/pdf",
            )
        )
        session.flush()

        annex_hash, annex_uri = _land(vault, ANNEX, media_type="text/plain")
        ids["derivative"] = new_id("der")
        session.add(
            Derivative(
                derivative_id=ids["derivative"],
                parent_record=ids["pdf_record"],
                kind=TEXT_KIND,
                tool="pdftotext",
                tool_version="fictional",
                operator="user:test",
                content_hash=annex_hash,
                storage_uri=annex_uri,
            )
        )

        # A PDF nobody extracted: no derivative, so nothing to index.
        raw_hash, raw_uri = _land(vault, "%PDF-unread", media_type="application/pdf")
        ids["unextracted"] = new_id("rec")
        session.add(
            SourceRecord(
                record_id=ids["unextracted"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash=raw_hash,
                storage_uri=raw_uri,
                media_type="application/pdf",
            )
        )

        held_hash, held_uri = _land(vault, REPORT, media_type="text/plain")
        ids["quarantined"] = new_id("rec")
        session.add(
            SourceRecord(
                record_id=ids["quarantined"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash=held_hash,
                storage_uri=held_uri,
                media_type="text/plain",
                status="quarantined",
                quarantine_reason="fictional",
            )
        )
    try:
        yield {**ids, "session": session}
    finally:
        session.close()


def _rebuild(session, vault, ontology):
    report = rebuild_document_text_projection(session, vault=vault, ontology=ontology)
    session.commit()
    return report


def _rows(session) -> dict[str, DocumentTextProjection]:
    return {
        row.record_id: row
        for row in session.scalars(sa.select(DocumentTextProjection))
    }


# ── what gets indexed ───────────────────────────────────────────────────────


def test_a_text_record_is_indexed_from_its_own_bytes(world, vault, ontology) -> None:
    session: Session = world["session"]
    _rebuild(session, vault, ontology)
    row = _rows(session)[world["text_record"]]
    assert row.text_body == REPORT
    assert row.derivative_id is None, "a text record needs no transformation"


def test_an_extracted_pdf_is_indexed_through_its_derivative(world, vault, ontology) -> None:
    session: Session = world["session"]
    _rebuild(session, vault, ontology)
    row = _rows(session)[world["pdf_record"]]
    assert row.text_body == ANNEX
    assert row.derivative_id == world["derivative"]


def test_an_unextracted_pdf_is_absent_and_the_builder_does_not_extract_it(
    world, vault, ontology
) -> None:
    """The rule, asserted twice: no row, and no derivative invented to make one.

    A cache that could mint a provenance row would write history on every
    rebuild, and Article XIII's "rebuild reproduces it" would stop being true
    the first time the tool version changed.
    """
    session: Session = world["session"]
    before = session.scalar(sa.select(sa.func.count()).select_from(Derivative))
    report = _rebuild(session, vault, ontology)
    after = session.scalar(sa.select(sa.func.count()).select_from(Derivative))

    assert world["unextracted"] not in _rows(session)
    assert report.skipped_no_text == 1
    assert after == before, "the builder created a derivative — it must never write one"


def test_a_quarantined_record_is_not_indexed(world, vault, ontology) -> None:
    """Surfacing its contents through search would route around the refusal."""
    session: Session = world["session"]
    report = _rebuild(session, vault, ontology)
    assert world["quarantined"] not in _rows(session)
    assert report.skipped_quarantined == 1


# ── it is a cache ───────────────────────────────────────────────────────────


def test_truncate_and_rebuild_reproduces_the_table(world, vault, ontology) -> None:
    session: Session = world["session"]
    _rebuild(session, vault, ontology)

    def snapshot():
        return sorted(
            (
                row.projection_id,
                row.record_id,
                row.derivative_id,
                row.content_hash,
                row.text_body,
                row.handling_code,
                row.handling_rank,
                row.normalization_version,
                row.builder_version,
            )
            for row in session.scalars(sa.select(DocumentTextProjection))
        )

    before = snapshot()
    session.execute(sa.text("TRUNCATE document_text_projection"))
    session.commit()
    assert session.scalar(sa.select(sa.func.count()).select_from(DocumentTextProjection)) == 0

    _rebuild(session, vault, ontology)
    assert snapshot() == before


def test_the_tsvector_is_generated_by_the_database(world, vault, ontology) -> None:
    """Not written by the builder, so it cannot drift from the text beside it."""
    session: Session = world["session"]
    _rebuild(session, vault, ontology)
    matched = session.scalar(
        sa.select(sa.func.count())
        .select_from(DocumentTextProjection)
        .where(
            DocumentTextProjection.tsv.op("@@")(
                sa.func.plainto_tsquery(sa.literal_column("'simple'::regconfig"), "harbour")
            )
        )
    )
    assert matched == 1


# ── the governance columns ──────────────────────────────────────────────────


def test_the_handling_code_is_copied_from_the_record(world, vault, ontology) -> None:
    session: Session = world["session"]
    _rebuild(session, vault, ontology)
    row = _rows(session)[world["text_record"]]
    assert row.handling_code == "restricted"
    assert row.handling_rank == ontology.handling_rank("restricted")


def test_a_changed_handling_code_is_stale_until_a_rebuild(world, vault, ontology) -> None:
    """Copied means copied, and that is why the builder is the only writer.

    The staleness is real and is stated rather than hidden: a record reclassified
    upward is under-protected in the index until the projection is rebuilt. The
    alternative — a filter that joins back to `source_record` at query time — is
    one forgotten join away from a leak, every time.
    """
    session: Session = world["session"]
    _rebuild(session, vault, ontology)
    session.execute(
        sa.update(SourceRecord)
        .where(SourceRecord.record_id == world["text_record"])
        .values(handling_code="sensitive")
    )
    session.commit()

    assert _rows(session)[world["text_record"]].handling_code == "restricted"
    _rebuild(session, vault, ontology)
    assert _rows(session)[world["text_record"]].handling_code == "sensitive"


def test_every_row_is_stamped(world, vault, ontology) -> None:
    session: Session = world["session"]
    _rebuild(session, vault, ontology)
    for row in _rows(session).values():
        assert row.builder_version == BUILDER_VERSION
        assert row.normalization_version == NORMALIZATION_VERSION
        assert row.built_at is not None


def test_the_projection_carries_no_case_scope(world, vault, ontology) -> None:
    """`source_record` has none, and a column that is always NULL is a lie.

    Asserted structurally rather than by value: a future `case_id` column would
    have to arrive with a rule for what to put in it for a record cited by two
    cases, and this is where that conversation starts.
    """
    assert "case_id" not in DocumentTextProjection.__table__.columns
