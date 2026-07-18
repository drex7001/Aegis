"""Probabilistic ER with Splink (T19; spec 05 §3.2, H-07).

The seeded pair is a Sinhala/English transliteration of one fictional name —
the case the whole feature exists for, and the one an exact-match pipeline
cannot see at all.  As with the deterministic rules, every test also asserts
that **nothing merged**: a score is a reason to ask, never a reason to act.

All fixture data here is fictional (`data/real/README.md`).
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, new_id
from aegis.er.features import build_feature_frame, graph_snapshot_id
from aegis.er.ledger import active_entity_for_mention, open_membership
from aegis.er.settings import SPLINK_MATCH_THRESHOLD, SPLINK_VERSION
from aegis.er.splink_job import run_splink
from aegis.er.translit import phonetic_key
from aegis.store import (
    Entity,
    ErCandidate,
    IdentityDecision,
    IdentityMembership,
    IdentityNegativeConstraint,
    Mention,
    Source,
    SourceRecord,
)
from tests.support.database import migrated_test_engine, truncate_domain_data

pytestmark = pytest.mark.requirement("Article-V", "Article-VII", "H-07", "H-08", "T19")

#: One fictional person written two ways — the seeded transliteration pair.
LATIN_NAME = "Nimal Perera"
SINHALA_NAME = "නිමල් පෙරේරා"
#: A different fictional person who shares neither name nor network.
UNRELATED_NAME = "Anura Silva"


@pytest.fixture(scope="module")
def splink_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


@pytest.fixture()
def seeded(splink_engine: sa.Engine):
    """Two entities naming the same person in two scripts, plus a distractor.

    Both carry the same alias and the same affiliation, which is what a real
    corpus gives you when two documents describe one person differently.
    """
    truncate_domain_data(splink_engine)
    session = Session(splink_engine)
    ids: dict[str, str] = {"source": new_id("src")}
    with session.begin():
        session.add(
            Source(source_id=ids["source"], source_type="open_source", name="T19 source")
        )
        session.flush()
        org_id = new_id("ent")
        ids["org"] = org_id
        session.add(
            Entity(entity_id=org_id, entity_type="organization", label="Coast Traders")
        )
        for slot, name in (
            ("latin", LATIN_NAME),
            ("sinhala", SINHALA_NAME),
            ("other", UNRELATED_NAME),
        ):
            record_id, entity_id, mention_id = new_id("rec"), new_id("ent"), new_id("men")
            ids[f"record_{slot}"] = record_id
            ids[f"entity_{slot}"] = entity_id
            ids[f"mention_{slot}"] = mention_id
            session.add(
                SourceRecord(
                    record_id=record_id,
                    source_id=ids["source"],
                    ingest_key=new_id("key"),
                    content_hash="b" * 64,
                    storage_uri=f"test://{slot}",
                )
            )
            session.add(Entity(entity_id=entity_id, entity_type="person", label=name))
            session.flush()
            session.add(
                Mention(
                    mention_id=mention_id,
                    record_id=record_id,
                    raw_text=name,
                    norm_key=f"seed_{slot}",
                )
            )
            session.flush()
            open_membership(session, mention_id=mention_id, entity_id=entity_id)

    service = ActionService(session)
    context = ActionContext(actor="user:analyst", purpose="T19 test")
    for slot in ("latin", "sinhala"):
        # a shared alias and a shared affiliation — the corroborating evidence
        service.record_claim(
            context,
            subject_id=ids[f"entity_{slot}"],
            predicate="known_as",
            object_value="Podda",
            assertion_type="reported",
            collection_method="curated",
            record_id=ids[f"record_{slot}"],
        )
        service.record_claim(
            context,
            subject_id=ids[f"entity_{slot}"],
            predicate="affiliated_with",
            object_id=ids["org"],
            assertion_type="reported",
            collection_method="curated",
            record_id=ids[f"record_{slot}"],
        )
    session.commit()
    try:
        yield {**ids, "session": session, "service": service, "context": context}
    finally:
        session.close()


def _pair(seeded) -> tuple[str, str]:
    left, right = seeded["mention_latin"], seeded["mention_sinhala"]
    return (left, right) if left < right else (right, left)


def _memberships(session: Session) -> set[tuple[str, str]]:
    return {
        row
        for row in session.execute(
            select(IdentityMembership.mention_id, IdentityMembership.entity_id).where(
                IdentityMembership.closed_revision_id.is_(None)
            )
        )
    }


# ── the acceptance criterion ─────────────────────────────────────────────────


@pytest.mark.integration
def test_the_transliteration_pair_scores_above_threshold_with_a_waterfall(seeded) -> None:
    session: Session = seeded["session"]
    before = _memberships(session)

    report = run_splink(session)
    session.commit()

    pair = _pair(seeded)
    candidate = session.scalar(
        select(ErCandidate).where(
            ErCandidate.mention_a == pair[0], ErCandidate.mention_b == pair[1]
        )
    )
    assert candidate is not None, "the seeded transliteration pair must be proposed"
    assert float(candidate.score) >= SPLINK_MATCH_THRESHOLD
    assert candidate.producer == "splink"
    assert candidate.producer_version == SPLINK_VERSION

    # The per-feature waterfall is persisted verbatim: a score that exists only
    # in a log cannot be audited, evaluated, or defended (GOAL.md §10.4).
    waterfall = candidate.features
    assert waterfall["rule"] == "splink"
    assert any(key.startswith("gamma_") for key in waterfall), waterfall
    assert any(key.startswith("bf_") for key in waterfall), waterfall

    # A probabilistic score is exactly the thing a human has to read, so it
    # never enters the band that means "confirmable in bulk without reading".
    assert candidate.pre_verified is False

    # THE assertion: nothing merged.
    assert _memberships(session) == before
    assert session.scalar(select(func.count()).select_from(IdentityDecision)) == 0
    assert (
        active_entity_for_mention(session, seeded["mention_latin"])
        == seeded["entity_latin"]
    )
    assert report.emitted >= 1


@pytest.mark.integration
def test_the_run_records_its_settings_version_and_graph_snapshot(seeded) -> None:
    """Without the snapshot id, a stored score is not reproducible (H-07)."""
    session: Session = seeded["session"]
    report = run_splink(session)
    session.commit()

    assert report.settings_version == SPLINK_VERSION
    assert report.graph_snapshot_id is not None
    assert report.graph_snapshot_id.startswith("sha256:")
    for candidate in session.scalars(select(ErCandidate)):
        assert candidate.graph_snapshot_id == report.graph_snapshot_id

    # The snapshot id is a digest of the association graph, so it moves when
    # the graph does — and stays put when it does not.
    assert graph_snapshot_id(session) == report.graph_snapshot_id
    seeded["service"].record_claim(
        seeded["context"],
        subject_id=seeded["entity_other"],
        predicate="affiliated_with",
        object_id=seeded["org"],
        assertion_type="reported",
        collection_method="curated",
        record_id=seeded["record_other"],
    )
    session.commit()
    assert graph_snapshot_id(session) != report.graph_snapshot_id


@pytest.mark.integration
def test_a_rejected_pair_is_never_re_emitted(seeded) -> None:
    """Spec 05 §3.3: constraints gate emission, so a human is not asked twice."""
    session: Session = seeded["session"]
    pair = _pair(seeded)
    decision = IdentityDecision(
        decision_id=new_id("dec"),
        kind="reject",
        decided_by="user:analyst",
        decision_note="namesakes; different districts and employers",
        parent_revision_id=0,
        result_revision_id=0,
    )
    session.add(decision)
    session.flush()
    session.add(
        IdentityNegativeConstraint(
            constraint_id=new_id("neg"),
            mention_a=pair[0],
            mention_b=pair[1],
            decision_id=decision.decision_id,
            evidence_basis="transliteration match only; no corroborating identifier",
        )
    )
    session.commit()

    report = run_splink(session)
    session.commit()

    assert report.suppressed_constraint >= 1
    assert (
        session.scalar(
            select(func.count())
            .select_from(ErCandidate)
            .where(ErCandidate.mention_a == pair[0], ErCandidate.mention_b == pair[1])
        )
        == 0
    )


@pytest.mark.integration
def test_re_running_splink_does_not_duplicate_candidates(seeded) -> None:
    session: Session = seeded["session"]
    first = run_splink(session)
    session.commit()
    assert first.emitted >= 1

    second = run_splink(session)
    session.commit()
    assert second.emitted == 0
    assert second.already_open >= 1


@pytest.mark.integration
def test_mentions_already_in_one_entity_are_not_proposed(seeded) -> None:
    session: Session = seeded["session"]
    frame = build_feature_frame(session)
    # Force both seeded mentions onto one entity, as a confirmed merge would.
    membership = session.scalar(
        select(IdentityMembership).where(
            IdentityMembership.mention_id == seeded["mention_sinhala"],
            IdentityMembership.closed_revision_id.is_(None),
        )
    )
    membership.entity_id = seeded["entity_latin"]
    session.commit()

    report = run_splink(session)
    session.commit()
    assert report.same_entity >= 1
    assert (
        session.scalar(
            select(func.count())
            .select_from(ErCandidate)
            .where(ErCandidate.mention_a == _pair(seeded)[0])
        )
        == 0
    )


# ── the features that make the pair findable ─────────────────────────────────


@pytest.mark.integration
def test_the_feature_frame_carries_both_transliteration_keys(seeded) -> None:
    session: Session = seeded["session"]
    frame = build_feature_frame(session)
    rows = {row["unique_id"]: row for row in frame.rows}

    latin = rows[seeded["mention_latin"]]
    sinhala = rows[seeded["mention_sinhala"]]

    # The phonetic key is what puts them in the same block at all: their Latin
    # keys differ too much for a prefix block to catch them.
    assert latin["phonetic_key"] == sinhala["phonetic_key"] == phonetic_key(LATIN_NAME)
    assert latin["latin_key"] != sinhala["latin_key"]
    # The raw-script key keeps them distinguishable as *written*, so a lossy
    # romanization cannot manufacture agreement invisibly.
    assert latin["script_key"] != sinhala["script_key"]
    assert latin["script"] == "Latn" and sinhala["script"] == "Sinh"
    assert "podda" in latin["alias_keys"]
    assert seeded["org"] in latin["associates"]


@pytest.mark.integration
def test_unresolved_mentions_are_excluded_from_the_frame(seeded) -> None:
    """Every feature but the name is reached through the entity.

    An unattached mention would be compared on its name alone and score
    misleadingly high against anything similar.
    """
    session: Session = seeded["session"]
    orphan = Mention(
        mention_id=new_id("men"),
        record_id=seeded["record_latin"],
        raw_text=LATIN_NAME,
        norm_key="seed_orphan",
    )
    session.add(orphan)
    session.commit()

    frame = build_feature_frame(session)
    assert orphan.mention_id not in {row["unique_id"] for row in frame.rows}


@pytest.mark.integration
def test_an_unrelated_person_is_not_proposed(seeded) -> None:
    """The hard negative.

    Recall on the transliteration pair is worthless without this: a model that
    proposes everything would pass the test above and be useless, because
    review capacity is what the threshold is really protecting (spec 05 §6).
    """
    session: Session = seeded["session"]
    run_splink(session)
    session.commit()

    proposed = {
        (row.mention_a, row.mention_b) for row in session.scalars(select(ErCandidate))
    }
    other = seeded["mention_other"]
    assert all(other not in pair for pair in proposed), (
        f"{UNRELATED_NAME} shares an affiliation with the seeded pair but neither "
        "a name nor an alias, and must not be proposed"
    )
    assert proposed == {_pair(seeded)}
