"""Deterministic ER rules (T18; spec 05 §3.1, ADR-027).

The load-bearing assertion in every test below is the same one: **no membership
moved**.  A rule that quietly merged would be indistinguishable from a rule that
proposed well, right up until the first wrong merge nobody could explain.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic.config import Config
from datetime import date
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, new_id
from aegis.er.ledger import active_entity_for_mention, open_membership
from aegis.er.rules import run_rules
from aegis.er.settings import RULES_VERSION, SAME_KEY_IN_DOCUMENT_RULE
from aegis.ontology import load
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
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement("Article-V", "Article-VII", "ADR-027", "H-07", "T18")

NIC_A = "923456789V"


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def rules_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


@pytest.fixture()
def world(rules_engine: sa.Engine):
    """Two records, two person entities, one mention of each per record.

    Every test starts from an empty store: the rules read the *whole* table, so
    residue from a neighbouring test would change what they propose.
    """
    truncate_domain_data(rules_engine)
    session = Session(rules_engine)
    ids = {
        "source": new_id("src"),
        "record_1": new_id("rec"),
        "record_2": new_id("rec"),
        "entity_a": new_id("ent"),
        "entity_b": new_id("ent"),
    }
    with session.begin():
        session.add(
            Source(source_id=ids["source"], source_type="open_source", name="T18 source")
        )
        for key in ("record_1", "record_2"):
            session.add(
                SourceRecord(
                    record_id=ids[key],
                    source_id=ids["source"],
                    ingest_key=new_id("key"),
                    content_hash="f" * 64,
                    storage_uri=f"test://{key}",
                )
            )
        session.add_all(
            [
                Entity(entity_id=ids["entity_a"], entity_type="person", label="Nimal P"),
                Entity(entity_id=ids["entity_b"], entity_type="person", label="N. Perera"),
            ]
        )
    try:
        yield {**ids, "session": session}
    finally:
        session.close()


def _mention(session: Session, record_id: str, raw: str, key: str) -> Mention:
    row = Mention(
        mention_id=new_id("men"), record_id=record_id, raw_text=raw, norm_key=key
    )
    session.add(row)
    session.flush()
    return row


def _nic_claim(
    world,
    *,
    entity_id: str,
    mention_id: str,
    record_id: str,
    value: str = NIC_A,
    jurisdiction: str | None = None,
    valid_from: date | None = None,
    valid_to: date | None = None,
):
    service = ActionService(world["session"])
    return service.record_claim(
        ActionContext(actor="user:analyst", purpose="T18 test"),
        subject_id=entity_id,
        predicate="has_nic",
        object_value=value,
        assertion_type="reported",
        collection_method="curated",
        record_id=record_id,
        subject_mention_id=mention_id,
        jurisdiction=jurisdiction,
        valid_from=valid_from,
        valid_to=valid_to,
    )


def _memberships(session: Session) -> set[tuple[str, str]]:
    return {
        (mention_id, entity_id)
        for mention_id, entity_id in session.execute(
            select(IdentityMembership.mention_id, IdentityMembership.entity_id).where(
                IdentityMembership.closed_revision_id.is_(None)
            )
        )
    }


# ── the acceptance criterion ─────────────────────────────────────────────────


@pytest.mark.integration
def test_matching_nic_produces_a_candidate_and_moves_nothing(world, ontology) -> None:
    session: Session = world["session"]
    left = _mention(session, world["record_1"], "Nimal Perera", "nimal_perera")
    right = _mention(session, world["record_2"], "N. Perera", "n_perera")
    open_membership(session, mention_id=left.mention_id, entity_id=world["entity_a"])
    open_membership(session, mention_id=right.mention_id, entity_id=world["entity_b"])
    _nic_claim(
        world, entity_id=world["entity_a"], mention_id=left.mention_id,
        record_id=world["record_1"],
    )
    _nic_claim(
        world, entity_id=world["entity_b"], mention_id=right.mention_id,
        record_id=world["record_2"],
    )
    session.commit()
    before = _memberships(session)

    report = run_rules(session, ontology=ontology)
    session.commit()

    candidate = session.scalar(
        select(ErCandidate).where(ErCandidate.producer == "rule:has_nic")
    )
    assert candidate is not None
    assert candidate.pre_verified is True
    assert candidate.producer_version == RULES_VERSION
    # A rule computes no probability; a fabricated 1.0 would be
    # indistinguishable from a model that was certain.
    assert candidate.score is None
    assert candidate.features["rule"] == "identifier_match"
    assert candidate.disposition == "open"
    assert report.pre_verified == 1

    # THE assertion: nothing merged, nothing decided.
    assert _memberships(session) == before
    assert session.scalar(select(func.count()).select_from(IdentityDecision)) == 0
    assert active_entity_for_mention(session, left.mention_id) == world["entity_a"]
    assert active_entity_for_mention(session, right.mention_id) == world["entity_b"]


@pytest.mark.integration
def test_cross_document_same_slug_never_reaches_the_pre_verified_band(
    world, ontology
) -> None:
    """The band exists so a reviewer can confirm in bulk *without* reading each.

    A shared common name across two documents is exactly the evidence that must
    not be confirmable that way — it is Splink's job to score it (T19).
    """
    session: Session = world["session"]
    left = _mention(session, world["record_1"], "Nimal Perera", "nimal_perera")
    right = _mention(session, world["record_2"], "Nimal Perera", "nimal_perera")
    open_membership(session, mention_id=left.mention_id, entity_id=world["entity_a"])
    open_membership(session, mention_id=right.mention_id, entity_id=world["entity_b"])
    session.commit()

    run_rules(session, ontology=ontology)
    session.commit()

    assert session.scalars(
        select(ErCandidate).where(ErCandidate.pre_verified.is_(True))
    ).all() == []


@pytest.mark.integration
def test_same_norm_key_in_one_document_is_a_candidate_but_not_pre_verified(
    world, ontology
) -> None:
    session: Session = world["session"]
    left = _mention(session, world["record_1"], "Nimal Perera", "nimal_perera")
    right = _mention(session, world["record_1"], "NIMAL PERERA", "nimal_perera")
    open_membership(session, mention_id=left.mention_id, entity_id=world["entity_a"])
    open_membership(session, mention_id=right.mention_id, entity_id=world["entity_b"])
    session.commit()

    run_rules(session, ontology=ontology)
    session.commit()

    candidate = session.scalar(
        select(ErCandidate).where(ErCandidate.producer == SAME_KEY_IN_DOCUMENT_RULE)
    )
    assert candidate is not None
    assert candidate.pre_verified is False
    assert candidate.features["norm_key"] == "nimal_perera"


# ── H-07: an exact string match is not by itself evidence ────────────────────


@pytest.mark.integration
def test_conflicting_issuer_suppresses_the_identifier_candidate(world, ontology) -> None:
    """Two registries that never agreed to share a number space (H-07)."""
    session: Session = world["session"]
    left = _mention(session, world["record_1"], "Nimal Perera", "nimal_perera")
    right = _mention(session, world["record_2"], "N. Perera", "n_perera")
    open_membership(session, mention_id=left.mention_id, entity_id=world["entity_a"])
    open_membership(session, mention_id=right.mention_id, entity_id=world["entity_b"])
    _nic_claim(
        world, entity_id=world["entity_a"], mention_id=left.mention_id,
        record_id=world["record_1"], jurisdiction="LK",
    )
    _nic_claim(
        world, entity_id=world["entity_b"], mention_id=right.mention_id,
        record_id=world["record_2"], jurisdiction="IN",
    )
    session.commit()

    report = run_rules(session, ontology=ontology)
    session.commit()

    assert report.suppressed_conflict == 1
    assert session.scalars(
        select(ErCandidate).where(ErCandidate.producer == "rule:has_nic")
    ).all() == []


@pytest.mark.integration
def test_disjoint_validity_windows_suppress_the_identifier_candidate(
    world, ontology
) -> None:
    """A reissued identifier names two different people (H-07)."""
    session: Session = world["session"]
    left = _mention(session, world["record_1"], "Nimal Perera", "nimal_perera")
    right = _mention(session, world["record_2"], "N. Perera", "n_perera")
    open_membership(session, mention_id=left.mention_id, entity_id=world["entity_a"])
    open_membership(session, mention_id=right.mention_id, entity_id=world["entity_b"])
    _nic_claim(
        world, entity_id=world["entity_a"], mention_id=left.mention_id,
        record_id=world["record_1"],
        valid_from=date(1990, 1, 1), valid_to=date(1999, 12, 31),
    )
    _nic_claim(
        world, entity_id=world["entity_b"], mention_id=right.mention_id,
        record_id=world["record_2"], valid_from=date(2005, 1, 1),
    )
    session.commit()

    report = run_rules(session, ontology=ontology)
    session.commit()

    assert report.suppressed_conflict == 1
    assert session.scalars(
        select(ErCandidate).where(ErCandidate.producer == "rule:has_nic")
    ).all() == []


# ── lifecycle ────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_a_rejected_pair_is_never_re_proposed(world, ontology) -> None:
    """Spec 05 §3.3: a reject is durable, and constraints gate *emission*.

    Re-proposing a pair a human already ruled on wastes the scarcest resource
    in the system and trains reviewers to click through the queue.
    """
    session: Session = world["session"]
    left = _mention(session, world["record_1"], "Nimal Perera", "nimal_perera")
    right = _mention(session, world["record_2"], "N. Perera", "n_perera")
    open_membership(session, mention_id=left.mention_id, entity_id=world["entity_a"])
    open_membership(session, mention_id=right.mention_id, entity_id=world["entity_b"])
    _nic_claim(
        world, entity_id=world["entity_a"], mention_id=left.mention_id,
        record_id=world["record_1"],
    )
    _nic_claim(
        world, entity_id=world["entity_b"], mention_id=right.mention_id,
        record_id=world["record_2"],
    )
    pair = tuple(sorted((left.mention_id, right.mention_id)))
    decision = IdentityDecision(
        decision_id=new_id("dec"),
        kind="reject",
        decided_by="user:analyst",
        decision_note="different people; DOB conflict in the file",
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
            evidence_basis="matching NIC, conflicting date of birth",
        )
    )
    session.commit()

    report = run_rules(session, ontology=ontology)
    session.commit()

    assert report.suppressed_constraint >= 1
    assert session.scalars(
        select(ErCandidate).where(ErCandidate.mention_a == pair[0])
    ).all() == []


@pytest.mark.integration
def test_re_running_the_rules_proposes_nothing_new(world, ontology) -> None:
    session: Session = world["session"]
    left = _mention(session, world["record_1"], "Nimal Perera", "nimal_perera")
    right = _mention(session, world["record_1"], "NIMAL PERERA", "nimal_perera")
    open_membership(session, mention_id=left.mention_id, entity_id=world["entity_a"])
    open_membership(session, mention_id=right.mention_id, entity_id=world["entity_b"])
    session.commit()

    first = run_rules(session, ontology=ontology)
    session.commit()
    assert first.emitted == 1

    second = run_rules(session, ontology=ontology)
    session.commit()
    assert second.emitted == 0
    assert second.already_open == 1
    assert session.scalar(select(func.count()).select_from(ErCandidate)) == 1


@pytest.mark.integration
def test_mentions_already_in_one_entity_are_not_proposed(world, ontology) -> None:
    """Nothing to adjudicate: they are already the same entity."""
    session: Session = world["session"]
    left = _mention(session, world["record_1"], "Nimal Perera", "nimal_perera")
    right = _mention(session, world["record_1"], "NIMAL PERERA", "nimal_perera")
    open_membership(session, mention_id=left.mention_id, entity_id=world["entity_a"])
    open_membership(session, mention_id=right.mention_id, entity_id=world["entity_a"])
    session.commit()

    report = run_rules(session, ontology=ontology)
    session.commit()

    assert report.emitted == 0
    assert report.same_entity == 1
