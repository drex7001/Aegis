"""Promotion: a human decides, and the finding survives (T74, spec 12 §10).

Charter exit criterion №3. The line being crossed is Article IX's: a **finding**
is a machine's reading of what was written down, a **claim** is somebody's
assertion about the world. Promotion turns the first into the second, so it
crosses the way every other machine output reaches canon — as a typed
suggestion a human decides on.

Four properties, each of which a plausible implementation gets wrong:

* between proposal and acceptance there is **no claim** — Article VII is not
  relaxed because the producer is deterministic;
* the claim is `assessed`, and the **reviewer** is its actor, not the promoter;
* the finding is **not consumed** — it stays, immutable, pointing at the claim
  it became the basis of;
* promoting twice is refused, because two assessed claims from one computation
  read as two independent assessments.

Fictional fixtures throughout.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService
from aegis.analytics.promotion import PromotionError, promote_finding
from aegis.analytics.service import run_metric
from aegis.api.auth import UserContext
from aegis.er.canonical import rebuild_canonical_map
from aegis.er.ledger import active_revision_id
from aegis.ids import new_id
from aegis.ontology import load
from aegis.projections import rebuild_edge_projection
from aegis.store import (
    AnalyticFinding,
    AuditLog,
    Claim,
    Entity,
    ReviewQueue,
    Source,
    SourceRecord,
)
from tests.support.database import migrated_test_engine, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement(
    "Article-VII", "Article-IX", "H-23", "charter-p6-exit-3", "T74"
)

ANALYST = frozenset({"analyst"})


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


def _user(sub: str, clearance: int = 2) -> UserContext:
    return UserContext(
        sub=sub, username=sub, roles=ANALYST, clearance=clearance, claims={}
    )


@pytest.fixture()
def world(engine: sa.Engine, ontology):
    """Two connected people, one open link, and a degree finding over them."""
    truncate_domain_data(engine)
    session = Session(engine)
    ids = {"source": new_id("src"), "record": new_id("rec")}
    with session.begin():
        session.add(Source(source_id=ids["source"], source_type="open_source", name="T74"))
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="c" * 64,
                storage_uri="test://t74",
            )
        )
        session.flush()
        for key, label in (("a", "Fictional ROMEO"), ("b", "Fictional SIERRA")):
            ids[key] = new_id("ent")
            session.add(Entity(entity_id=ids[key], entity_type="person", label=label))
        session.flush()
        session.add(
            Claim(
                claim_id=new_id("clm"),
                subject_id=ids["a"],
                predicate="allied_with",
                object_id=ids["b"],
                assertion_type="reported",
                handling_code="open",
                record_id=ids["record"],
                identity_revision_id=active_revision_id(session),
                ontology_version="2.1.0",
                credibility_normalized="possibly_true",
                verification_status="unverified",
            )
        )

    with Session(engine) as builder:
        rebuild_canonical_map(builder)
        rebuild_edge_projection(builder, ontology=ontology)
        builder.commit()

    _, findings = run_metric(
        session,
        metric="degree",
        user=_user("user:analyst"),
        ontology=ontology,
        purpose="fixture",
    )
    session.commit()
    # The finding about ROMEO specifically, so the promoted claim can name
    # SIERRA as its object — an assessment a degree finding actually supports
    # ("these two are closely associated"), rather than an invented literal.
    about_a = next(f for f in findings if f.subjects[0] == ids["a"])
    ids["finding"] = about_a.finding_id
    ids["subject"] = ids["a"]

    try:
        yield {**ids, "session": session, "findings": findings}
    finally:
        session.close()


def _propose(world, ontology, **overrides) -> ReviewQueue:
    return promote_finding(
        world["session"],
        finding_id=overrides.pop("finding_id", world["finding"]),
        subject_id=overrides.pop("subject_id", world["subject"]),
        predicate="close_associate_of",
        record_id=world["record"],
        rationale=overrides.pop("rationale", "central to the harbour movements"),
        actor=overrides.pop("actor", "user:promoter"),
        roles=ANALYST,
        ontology=ontology,
        object_id=overrides.pop("object_id", world["b"]),
        **overrides,
    )


# ── nothing canonical until a human accepts ─────────────────────────────────


def test_proposing_writes_a_suggestion_and_no_claim(world, ontology) -> None:
    """Article VII, unchanged by the producer being deterministic."""
    session: Session = world["session"]
    before = session.scalar(sa.select(sa.func.count()).select_from(Claim))

    suggestion = _propose(world, ontology)
    session.commit()

    assert suggestion.suggestion_kind == "finding_promotion"
    assert suggestion.status == "suggested"
    assert suggestion.target_action == "record_claim"
    assert session.scalar(sa.select(sa.func.count()).select_from(Claim)) == before
    assert suggestion.result_claim_id is None


def test_the_suggestion_carries_the_caveat_the_finding_was_issued_with(
    world, ontology
) -> None:
    """The reviewer decides with the caveat in front of them, not beside them.

    Copied into `producer_meta` rather than looked up, for the same reason the
    finding row copies it: a caveat fetched at render time is a caveat that can
    fail to arrive at the moment it matters most.
    """
    session: Session = world["session"]
    suggestion = _propose(world, ontology)
    session.commit()

    finding = session.get(AnalyticFinding, world["finding"])
    assert suggestion.producer_meta["caveat_text"] == finding.caveat_text
    assert suggestion.producer_meta["rationale"] == "central to the harbour movements"
    assert suggestion.producer_meta["finding_id"] == world["finding"]


def test_a_promotion_without_a_rationale_is_refused(world, ontology) -> None:
    """The finding says what was computed; the promoter says why it is worth asserting."""
    with pytest.raises(PromotionError) as excinfo:
        _propose(world, ontology, rationale="   ")
    assert "rationale" in str(excinfo.value)


def test_promoting_a_finding_that_does_not_exist_is_refused(world, ontology) -> None:
    with pytest.raises(PromotionError):
        _propose(world, ontology, finding_id="find_nonexistent")


# ── acceptance: the reviewer is the actor ───────────────────────────────────


def _accept(world, ontology, suggestion, reviewer="user:reviewer") -> ReviewQueue:
    service = ActionService(world["session"], ontology)
    return service.review_suggestion(
        ActionContext(actor=reviewer, roles=ANALYST),
        suggestion_id=suggestion.suggestion_id,
        decision="accepted",
    )


def test_acceptance_produces_an_assessed_claim_actored_by_the_reviewer(
    world, ontology
) -> None:
    """ADR-031 §2. The promoter proposed; the reviewer decided; both are recorded."""
    session: Session = world["session"]
    suggestion = _propose(world, ontology, actor="user:promoter")
    session.commit()

    decided = _accept(world, ontology, suggestion, reviewer="user:reviewer")
    session.commit()

    claim = session.get(Claim, decided.result_claim_id)
    assert claim.assertion_type == "assessed"
    assert decided.decided_by == "user:reviewer"
    assert suggestion.producer == "finding-promotion"

    audits = list(
        session.scalars(
            sa.select(AuditLog).where(AuditLog.resource_id == suggestion.suggestion_id)
        )
    )
    assert any(row.actor == "user:reviewer" for row in audits)


def test_the_claim_is_attributed_to_a_real_source_record(world, ontology) -> None:
    """H-23: never an invented record.

    A finding computed over several records promotes against the one the
    promoter names, and attributing an assertion to a record that did not make
    it is the specific failure H-23 warned about.
    """
    session: Session = world["session"]
    suggestion = _propose(world, ontology)
    session.commit()
    decided = _accept(world, ontology, suggestion)
    session.commit()

    claim = session.get(Claim, decided.result_claim_id)
    assert claim.record_id == world["record"]
    assert session.get(SourceRecord, claim.record_id) is not None


def test_the_finding_is_linked_and_not_consumed(world, ontology) -> None:
    """Spec 12 §10 rule 5. It remains, immutable, as the basis of the claim."""
    session: Session = world["session"]
    suggestion = _propose(world, ontology)
    session.commit()
    decided = _accept(world, ontology, suggestion)
    session.commit()

    finding = session.get(AnalyticFinding, world["finding"])
    assert finding is not None, "the finding was consumed"
    assert finding.promoted_claim_id == decided.result_claim_id
    # Still a finding, still carrying its caveat, still readable.
    assert finding.caveat_text
    assert finding.finding_digest


def test_the_promoted_claim_is_an_ordinary_claim_from_then_on(world, ontology) -> None:
    """Article VIII: retractable, contradictable, graded like any other."""
    session: Session = world["session"]
    suggestion = _propose(world, ontology)
    session.commit()
    decided = _accept(world, ontology, suggestion)
    session.commit()

    claim = session.get(Claim, decided.result_claim_id)
    assert claim.retracted_at is None
    assert claim.credibility_normalized
    assert claim.verification_status
    assert claim.handling_code == "open"


# ── one finding, one assessed claim ─────────────────────────────────────────


def test_promoting_twice_is_refused(world, ontology) -> None:
    """Two assessed claims from one computation read as two independent assessments."""
    session: Session = world["session"]
    suggestion = _propose(world, ontology)
    session.commit()
    _accept(world, ontology, suggestion)
    session.commit()

    with pytest.raises(PromotionError) as excinfo:
        _propose(world, ontology)
    assert "already been promoted" in str(excinfo.value)


def test_a_second_proposal_while_one_is_pending_is_refused(world, ontology) -> None:
    """Otherwise two reviewers could each accept, and the second would fail late."""
    session: Session = world["session"]
    _propose(world, ontology)
    session.commit()

    with pytest.raises(PromotionError) as excinfo:
        _propose(world, ontology)
    assert "awaiting review" in str(excinfo.value)


def test_the_finding_survives_a_rejection_unmarked(world, ontology) -> None:
    """A rejected promotion leaves the finding exactly as it was.

    Not "promoted and then unpromoted" — never promoted. The queue row records
    the decision; the finding records nothing, because nothing happened to it.
    """
    session: Session = world["session"]
    suggestion = _propose(world, ontology)
    session.commit()

    service = ActionService(session, ontology)
    decided = service.review_suggestion(
        ActionContext(actor="user:reviewer", roles=ANALYST),
        suggestion_id=suggestion.suggestion_id,
        decision="rejected",
        note="not enough on its own",
    )
    session.commit()

    assert decided.status == "rejected"
    finding = session.get(AnalyticFinding, world["finding"])
    assert finding.promoted_claim_id is None


def test_the_same_argument_cannot_be_resubmitted_after_a_rejection(
    world, ontology
) -> None:
    """…but a different one can. The rationale is part of the idempotency key.

    The default key digests the payload, so two promotions of one finding with
    the same subject and predicate would collide however differently they were
    argued — and a promotion rejected once could never be re-proposed on better
    reasoning. Including the rationale makes the rule the one worth having: a
    reviewer who said no to *this* argument is not saying no to every future
    case anybody might make from the same finding.
    """
    session: Session = world["session"]
    first = _propose(world, ontology, rationale="central to the harbour movements")
    session.commit()

    service = ActionService(session, ontology)
    service.review_suggestion(
        ActionContext(actor="user:reviewer", roles=ANALYST),
        suggestion_id=first.suggestion_id,
        decision="rejected",
        note="not enough on its own",
    )
    session.commit()

    with pytest.raises(Exception):
        _propose(world, ontology, rationale="central to the harbour movements")
        session.flush()
    session.rollback()

    again = _propose(
        world,
        ontology,
        rationale="the shipping manifests corroborate it independently",
    )
    session.commit()
    assert again.status == "suggested"
    assert again.suggestion_id != first.suggestion_id


# ── the assertion type cannot be talked out of ──────────────────────────────


def test_an_edit_cannot_downgrade_the_assertion_type(world, ontology) -> None:
    """A promoted finding is an assessment, whatever a reviewer edits it to.

    `edits` exists so a reviewer can correct a draft (spec 04 §4) — not so they
    can relabel a machine's reading as a first-hand observation.
    """
    session: Session = world["session"]
    suggestion = _propose(world, ontology)
    session.commit()

    service = ActionService(session, ontology)
    from aegis.actions import ActionValidationError

    with pytest.raises(ActionValidationError) as excinfo:
        service.review_suggestion(
            ActionContext(actor="user:reviewer", roles=ANALYST),
            suggestion_id=suggestion.suggestion_id,
            decision="accepted",
            edits={"assertion_type": "observed"},
        )
    assert "assessed" in excinfo.value.message
    session.rollback()
