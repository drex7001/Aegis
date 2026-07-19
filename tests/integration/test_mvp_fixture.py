"""T25's deterministic offline corpus and headless MVP loop.

Every input comes from ``data/sample/mvp`` and is explicitly fictional.  The
tests use the same CLI/service path as an operator; no hosted model, network
stub, or direct canonical-table seed is involved.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
import pytest
import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from aegis.actions import ActionContext, ActionService
from aegis.audit import verify as verify_audit
from aegis.cli import app
from aegis.er.canonical import rebuild_canonical_map
from aegis.er.ledger import active_entity_for_mention
from aegis.er.settings import SPLINK_MATCH_THRESHOLD
from aegis.evidence import LocalFilesystemVault
from aegis.ingestion import IngestionError, run_semantic_pass
from aegis.ingestion.mvp_fixture import (
    MVP_FIXTURE_ROOT,
    MVP_SOURCE_SYSTEM,
    MvpFixtureError,
    load_mvp_fixture,
    reset_mvp_fixture,
)
from aegis.ontology import load
from aegis.projections import rebuild_edge_projection
from aegis.store import (
    Claim,
    ClaimRelation,
    EdgeProjection,
    ErCandidate,
    IdentityRevision,
    Mention,
    ReviewQueue,
    Source,
    SourceRecord,
)
from tests.support.database import migrated_test_engine, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement(
    "Article-VII",
    "Article-VIII",
    "Article-XIII",
    "H-09",
    "T25",
)


@pytest.fixture(scope="module")
def mvp_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


def _count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_one_cli_command_loads_an_idempotent_complete_offline_fixture(
    mvp_engine: sa.Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truncate_domain_data(mvp_engine)
    vault = LocalFilesystemVault(tmp_path / "vault")
    monkeypatch.setattr("aegis.evidence.get_vault", lambda: vault)
    runner = CliRunner()

    command = [
        "ingest",
        "mvp",
        "--fixture-dir",
        str(MVP_FIXTURE_ROOT),
        "--output",
        str(tmp_path / "projection"),
    ]
    first = runner.invoke(app, command)
    assert first.exit_code == 0, first.output
    assert "10 records (1 quarantined)" in first.output
    assert "2 new suggestions" in first.output

    second = runner.invoke(app, command)
    assert second.exit_code == 0, second.output
    assert "0 new suggestions, 0 curated claims" in second.output

    with Session(mvp_engine) as session:
        assert _count(session, SourceRecord) == 10
        assert (
            session.scalar(
                select(func.count())
                .select_from(SourceRecord)
                .where(SourceRecord.status == "quarantined")
            )
            == 1
        )
        assert {row.producer for row in session.scalars(select(ReviewQueue))} == {
            "structural_pass",
            "semantic_pass",
        }
        cached = session.scalar(
            select(ReviewQueue).where(ReviewQueue.producer == "semantic_pass")
        )
        assert cached is not None
        assert cached.producer_meta["model"] == "cached:fixture:mvp-semantic-v1"
        assert cached.producer_meta["cached"] is True
        assert cached.producer_meta["raw_response_ref"].startswith("sha256:")

        restricted = session.scalar(select(Claim).where(Claim.predicate == "has_nic"))
        assert restricted is not None
        assert restricted.object_value == "DEMO-NIC-MAYA-001"
        assert restricted.handling_code == "open", (
            "the fixture must exercise field sensitivity, not row handling"
        )
        assert _count(session, ClaimRelation) == 1
        relation = session.scalar(select(ClaimRelation))
        assert relation is not None and relation.relation == "contradicts"

        latin = session.scalar(
            select(Mention).where(Mention.raw_text == "Nimal Perera")
        )
        sinhala = session.scalar(select(Mention).where(Mention.raw_text == "නිමල් පෙරේරා"))
        assert latin is not None and sinhala is not None
        pair = tuple(sorted((latin.mention_id, sinhala.mention_id)))
        candidate = session.scalar(
            select(ErCandidate).where(
                ErCandidate.mention_a == pair[0],
                ErCandidate.mention_b == pair[1],
            )
        )
        assert candidate is not None
        assert float(candidate.score) >= SPLINK_MATCH_THRESHOLD
        assert candidate.pre_verified is False

        namesakes = session.scalars(
            select(Mention).where(Mention.raw_text == "Ruwan Silva")
        ).all()
        assert len(namesakes) == 2
        assert active_entity_for_mention(session, namesakes[0].mention_id) != (
            active_entity_for_mention(session, namesakes[1].mention_id)
        )
        assert verify_audit(session).valid is True


def test_headless_loop_accepts_one_suggestion_then_rebuilds_the_projection(
    mvp_engine: sa.Engine,
    tmp_path: Path,
) -> None:
    truncate_domain_data(mvp_engine)
    with Session(mvp_engine) as session:
        report = load_mvp_fixture(
            session,
            LocalFilesystemVault(tmp_path / "vault"),
            output_dir=tmp_path / "before",
        )
        assert report.suggestions == 2
        assert report.projection_edges == 0
        assert _count(session, Claim) == 14, "machine suggestions must not auto-accept"

        suggestion = session.scalar(
            select(ReviewQueue).where(ReviewQueue.producer == "structural_pass")
        )
        assert suggestion is not None and suggestion.status == "suggested"
        decided = ActionService(session).review_suggestion(
            ActionContext(actor="user:mvp-reviewer", purpose="headless MVP smoke"),
            suggestion_id=suggestion.suggestion_id,
            decision="accepted",
            note="Fictional remand rows and overlap verified against the fixture.",
        )
        assert decided.result_claim_id is not None
        rebuild_canonical_map(session)
        projection = rebuild_edge_projection(session, ontology=load(ONTOLOGY_PATH))
        session.commit()

        assert projection.edges == 1
        edge = session.scalar(select(EdgeProjection))
        assert edge is not None
        assert edge.predicate == "co_located_in_prison_with"
        assert decided.decided_by == "user:mvp-reviewer"
        assert _count(session, Claim) == 15


def test_reset_restores_the_empty_baseline_and_refuses_foreign_state(
    mvp_engine: sa.Engine,
    tmp_path: Path,
) -> None:
    truncate_domain_data(mvp_engine)
    with Session(mvp_engine) as session:
        load_mvp_fixture(
            session,
            LocalFilesystemVault(tmp_path / "vault"),
            output_dir=tmp_path / "loaded",
        )
        reset = reset_mvp_fixture(session, output_dir=tmp_path / "reset")
        assert reset.projection_edges == 0
        assert _count(session, SourceRecord) == 0
        assert _count(session, Claim) == 0
        assert _count(session, ReviewQueue) == 0
        assert session.get(IdentityRevision, 0) is not None

        session.add(
            Source(
                source_id="src_not_fixture",
                source_type="open_source",
                name="Foreign local source",
            )
        )
        session.commit()
        with pytest.raises(MvpFixtureError, match="non-fixture state"):
            reset_mvp_fixture(session)


def test_reset_requires_explicit_cli_confirmation(
    mvp_engine: sa.Engine,
) -> None:
    truncate_domain_data(mvp_engine)
    result = CliRunner().invoke(app, ["ingest", "mvp", "--reset"])
    assert result.exit_code == 1
    assert "repeat with --yes" in result.output


def test_cached_semantic_output_refuses_prompt_drift(
    mvp_engine: sa.Engine,
    tmp_path: Path,
) -> None:
    truncate_domain_data(mvp_engine)
    vault = LocalFilesystemVault(tmp_path / "vault")
    with Session(mvp_engine) as session:
        load_mvp_fixture(session, vault)
        record = session.scalar(
            select(SourceRecord).where(
                SourceRecord.provenance["original_filename"].astext
                == "mvp-nimal-latin.txt"
            )
        )
        assert record is not None
        before = _count(session, ReviewQueue)
        bad_cache = b'{"schema":"aegis.cached-semantic/v1","model":"fixture","prompt_sha256":"stale","result":{}}'

        with pytest.raises(IngestionError, match="prompt_sha256 does not match"):
            run_semantic_pass(
                session,
                vault,
                record=record,
                text="Nimal Perera",
                actor="user:mvp-demo-operator",
                cached_output=bad_cache,
            )
        assert _count(session, ReviewQueue) == before


def test_curated_fixture_baseline_refuses_a_machine_actor(
    mvp_engine: sa.Engine,
    tmp_path: Path,
) -> None:
    truncate_domain_data(mvp_engine)
    with Session(mvp_engine) as session:
        with pytest.raises(MvpFixtureError, match="requires a human actor"):
            load_mvp_fixture(
                session,
                LocalFilesystemVault(tmp_path / "vault"),
                actor="system:fixture-loader",
            )
        assert _count(session, Claim) == 0


def test_every_landed_record_identifies_the_fixture_source_system(
    mvp_engine: sa.Engine,
    tmp_path: Path,
) -> None:
    truncate_domain_data(mvp_engine)
    with Session(mvp_engine) as session:
        load_mvp_fixture(session, LocalFilesystemVault(tmp_path / "vault"))
        assert {
            row.provenance["source_system"]
            for row in session.scalars(select(SourceRecord))
        } == {MVP_SOURCE_SYSTEM}
