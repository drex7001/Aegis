"""Ingestion rewire tests (speckit T9, spec 04).

The acceptance criterion: running an extraction pass creates **zero** rows in
``claim`` and N rows in ``review_queue``.  Landing is idempotent by ingest key;
a same-name/different-bytes artifact quarantines as a version conflict.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, new_id
from aegis.evidence import LocalFilesystemVault
from aegis.ingestion import (
    MANUAL_SOURCE_ID,
    land_bytes,
    run_semantic_pass,
    run_structural_pass,
)
from aegis.er.ledger import active_entity_for_mention, open_membership
from aegis.store import Claim, Entity, Mention, ReviewQueue
from tests.support.database import migrated_test_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
ARREST_LIST = REPO_ROOT / "data/sample" / "pcoi_arrest_list.txt"
B_REPORT = REPO_ROOT / "data/sample" / "b_report_excerpt.txt"

pytestmark = pytest.mark.requirement("Article-VII", "T9")


@pytest.fixture(scope="module")
def ingest_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


@pytest.fixture()
def vault(tmp_path: Path) -> LocalFilesystemVault:
    return LocalFilesystemVault(tmp_path / "vault")


@pytest.fixture()
def session(ingest_engine: sa.Engine):
    with Session(ingest_engine) as session:
        yield session
        session.rollback()


def _claim_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Claim))


@pytest.mark.integration
def test_landing_is_idempotent_by_ingest_key(session: Session, vault) -> None:
    name = f"note-{new_id('t')}.txt"
    first = land_bytes(
        session, vault, data=b"same bytes", original_filename=name, operator="user:test"
    )
    again = land_bytes(
        session, vault, data=b"same bytes", original_filename=name, operator="user:test"
    )
    assert first.created and not again.created
    assert again.record.record_id == first.record.record_id
    assert first.record.status == "landed"
    assert first.record.source_id == MANUAL_SOURCE_ID
    assert first.record.provenance["operator"] == "user:test"


@pytest.mark.integration
def test_same_name_different_bytes_quarantines(session: Session, vault) -> None:
    name = f"versioned-{new_id('t')}.txt"
    land_bytes(session, vault, data=b"v1", original_filename=name, operator="user:test")
    conflict = land_bytes(
        session, vault, data=b"v2", original_filename=name, operator="user:test"
    )
    assert conflict.created and conflict.quarantined
    assert conflict.record.status == "quarantined"
    assert "version conflict" in conflict.record.quarantine_reason


@pytest.mark.integration
def test_structural_pass_lands_in_review_queue_only(session: Session, vault) -> None:
    landing = land_bytes(
        session,
        vault,
        data=ARREST_LIST.read_bytes(),
        original_filename=f"arrests-{new_id('t')}.txt",
        operator="user:test",
        media_type="text/plain",
    )
    claims_before = _claim_count(session)
    text = ARREST_LIST.read_text(encoding="utf-8")
    suggestions = run_structural_pass(
        session, record=landing.record, text=text, actor="user:test"
    )
    assert suggestions, "the sample arrest list must produce suggestions"
    assert _claim_count(session) == claims_before  # AC: zero claims
    # Every producer emits one closed kind (ADR-031 §1); there is no
    # entity_draft, so overlapping remand windows propose claims and nothing else.
    assert {s.suggestion_kind for s in suggestions} == {"claim_draft"}
    assert {s.target_action for s in suggestions} == {"record_claim"}
    for suggestion in suggestions:
        assert suggestion.producer == "structural_pass"
        assert suggestion.producer_version == "v1"
        assert suggestion.producer_meta["rule"] == "remand-overlap"
        # the adapter maps the pass verb onto the ontology predicate
        assert suggestion.payload["predicate"] == "co_located_in_prison_with"
        assert suggestion.payload["collection_method"] == "structural"
        # nothing silently dropped: unmatched refs are flagged for the reviewer
        assert suggestion.producer_meta["needs_entity"]


@pytest.mark.integration
def test_semantic_pass_creates_zero_claims_n_suggestions(session: Session, vault) -> None:
    landing = land_bytes(
        session,
        vault,
        data=B_REPORT.read_bytes(),
        original_filename=f"b-report-{new_id('t')}.txt",
        operator="user:test",
        media_type="text/plain",
    )
    claims_before = _claim_count(session)
    queue_before = session.scalar(select(func.count()).select_from(ReviewQueue))
    text = B_REPORT.read_text(encoding="utf-8")
    suggestions = run_semantic_pass(
        session, vault, record=landing.record, text=text, actor="user:test", mock=True
    )
    # Mock extraction finds 4 nodes and 4 edges, and proposes 4 suggestions:
    # an unseen name is not a separate draft, it rides in the claim's
    # subject_ref/object_ref as an unresolved mention (ADR-031 §1, spec 02 §3.2).
    assert len(suggestions) == 4
    assert _claim_count(session) == claims_before  # AC: zero rows in claim
    assert (
        session.scalar(select(func.count()).select_from(ReviewQueue))
        == queue_before + 4
    )
    for suggestion in suggestions:
        meta = suggestion.producer_meta
        assert suggestion.producer == "semantic_pass"
        assert suggestion.suggestion_kind == "claim_draft"
        # a changed prompt is a different producer, even behind the same model
        assert suggestion.producer_version.startswith("mock+")
        assert suggestion.record_id == landing.record.record_id
        assert meta["model"] == "mock"
        assert len(meta["prompt_sha256"]) == 64
        assert meta["raw_response_ref"].startswith("sha256:")
    # the parsed model output is itself vaulted for debuggability
    ref = suggestions[0].producer_meta["raw_response_ref"].removeprefix("sha256:")
    assert vault.exists(ref)
    # verbs outside the ontology are carried raw with predicate unset
    met_in_prison = [
        s for s in suggestions if s.producer_meta.get("raw_relation") == "met_in_prison"
    ]
    assert met_in_prison and met_in_prison[0].payload["predicate"] is None

    # replay safety: an identical re-run submits nothing new
    again = run_semantic_pass(
        session, vault, record=landing.record, text=text, actor="user:test", mock=True
    )
    assert again == []


@pytest.mark.integration
def test_reviewer_edits_resolve_and_accept_a_suggestion(session: Session, vault) -> None:
    landing = land_bytes(
        session,
        vault,
        data=B_REPORT.read_bytes(),
        original_filename=f"b-report-accept-{new_id('t')}.txt",
        operator="user:test",
        media_type="text/plain",
    )
    text = B_REPORT.read_text(encoding="utf-8")
    suggestions = run_semantic_pass(
        session, vault, record=landing.record, text=text, actor="user:test", mock=True
    )
    target = next(
        s for s in suggestions if s.producer_meta.get("raw_relation") == "met_in_prison"
    )
    assert target.producer_meta["needs_entity"] == ["kasun_wijeratne", "rizvi_farook"]

    # the reviewer adjudicates the two people, then accepts with edits
    kasun = Entity(entity_id=new_id("ent"), entity_type="person", label="Kasun Wijeratne")
    rizvi = Entity(entity_id=new_id("ent"), entity_type="person", label="Rizvi Farook")
    session.add_all([kasun, rizvi])
    session.flush()
    service = ActionService(session)
    context = ActionContext(actor="user:reviewer", purpose="T9 review test")
    decided = service.review_suggestion(
        context,
        suggestion_id=target.suggestion_id,
        decision="accepted",
        edits={
            "subject_id": kasun.entity_id,
            "object_id": rizvi.entity_id,
            "predicate": "co_located_in_prison_with",
        },
        note="resolved entities; met_in_prison → co_located_in_prison_with",
    )
    assert decided.status == "accepted"
    claim = session.get(Claim, decided.result_claim_id)
    assert claim is not None
    assert claim.predicate == "co_located_in_prison_with"
    assert claim.record_id == landing.record.record_id
    assert claim.credibility_scheme == "legacy-confidence-tag"
    assert claim.location_text == "Welikada Prison"
    assert claim.valid_from is not None and claim.valid_to is not None
    # The draft carried mention anchors from extraction, so the accepted claim
    # can point at the text each argument was read from (ADR-029), and the
    # anchored mentions are now attached to the entities the reviewer chose.
    assert claim.subject_mention_id is not None
    assert claim.object_mention_id is not None
    for mention_id, entity_id in (
        (claim.subject_mention_id, claim.subject_id),
        (claim.object_mention_id, claim.object_id),
    ):
        assert session.get(Mention, mention_id).record_id == landing.record.record_id
        assert active_entity_for_mention(session, mention_id) == entity_id


@pytest.mark.integration
def test_known_entities_resolve_instead_of_drafting(session: Session, vault) -> None:
    """A mention already adjudicated to an entity is reused, not re-proposed."""
    landing = land_bytes(
        session,
        vault,
        data=B_REPORT.read_bytes(),
        original_filename=f"b-report-known-{new_id('t')}.txt",
        operator="user:test",
        media_type="text/plain",
    )
    entity = Entity(entity_id=new_id("ent"), entity_type="person", label="Kasun Wijeratne")
    mention = Mention(
        mention_id=new_id("men"),
        record_id=landing.record.record_id,
        raw_text="Kasun Wijeratne",
        norm_key="kasun_wijeratne",
    )
    session.add_all([entity, mention])
    session.flush()
    open_membership(
        session, mention_id=mention.mention_id, entity_id=entity.entity_id
    )
    text = B_REPORT.read_text(encoding="utf-8")
    suggestions = run_semantic_pass(
        session, vault, record=landing.record, text=text, actor="user:test", mock=True
    )
    claim_drafts = [
        s
        for s in suggestions
        if s.producer_meta.get("raw_relation") == "met_in_prison"
    ]
    # the adjudicated mention resolves to its entity; the other side stays
    # unresolved and is flagged rather than dropped (Article VIII)
    assert claim_drafts[0].payload["subject_id"] == entity.entity_id
    assert claim_drafts[0].producer_meta["needs_entity"] == ["rizvi_farook"]
