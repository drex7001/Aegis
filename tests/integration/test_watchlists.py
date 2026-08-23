"""Watchlists: a standing question, swept explicitly (T75, spec 12 §11).

The charter risk this task carries is H-24 — that a detection quietly becomes a
fact. It does not: an alert asserts nothing about the world, it points at a
claim that already exists, and a human triages it. What the tests here have to
prove is that the pointing is honest.

**Fuzzy matching is deliberately absent and its absence is asserted, not
assumed.** Every fixture below fires a near-miss at the watchlist and requires
silence. ADR-053's reason: a near-match on an identifier is a *different* person
with a name attached, and a watchlist that fires on one teaches its readers to
believe the next one.

Fictional fixtures throughout, and no national-ID numbers even fictional ones —
`reachable_on`, because a test that reaches for a NIC teaches the wrong reflex.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.orm import Session

from aegis.api.auth import UserContext
from aegis.er.ledger import active_revision_id
from aegis.ids import new_id
from aegis.ontology import load
from aegis.sets.service import create_set
from aegis.store import AnalyticRun, AuditLog, Claim, Entity, Source, SourceRecord
from aegis.watchlists.service import (
    METHOD,
    WatchlistError,
    create_watchlist,
    evaluate_watchlist,
    last_evaluated_through,
    sweep,
    triage_alert,
)
from tests.support.database import configured_test_database, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement(
    "Article-VI", "Article-VII", "Article-X", "H-24", "ADR-056", "ADR-060",
    "spec-12-11", "T75",
)

#: The watched value, and a near-miss one digit away. Fictional.
WATCHED = "+94-70-000-0000"
NEAR_MISS = "+94-70-000-0001"


@contextmanager
def _txn(session: Session):
    """`session.begin()` in a suite that asserts between writes.

    A bare read autobegins a transaction, and `session.begin()` then refuses
    rather than joining it. Rolling back first is safe here because every block
    below is self-contained — nothing uncommitted is meant to survive one.
    """
    session.rollback()
    with session.begin():
        yield


def _user(sub: str = "user:owner", clearance: int = 2) -> UserContext:
    return UserContext(
        sub=sub,
        username=sub,
        roles=frozenset({"analyst"}),
        clearance=clearance,
        claims={},
    )


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def db(test_database_url: str, alembic_config: Config):
    with configured_test_database(test_database_url, alembic_config):
        yield test_database_url


@pytest.fixture(scope="module")
def engine(db: str) -> sa.Engine:
    return sa.create_engine(db)


@pytest.fixture()
def world(engine: sa.Engine, ontology):
    """One watched person, one stranger, and a watchlist over the watched set."""
    truncate_domain_data(engine)
    session = Session(engine)
    ids: dict = {"source": new_id("src"), "record": new_id("rec")}
    with session.begin():
        session.add(
            Source(source_id=ids["source"], source_type="open_source", name="T75")
        )
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="e" * 64,
                storage_uri="test://t75",
            )
        )
        session.flush()
        for key, label, kind in (
            ("watched", "Fictional VICTOR", "person"),
            ("stranger", "Fictional WHISKEY", "person"),
            ("other", "Fictional XRAY", "person"),
        ):
            ids[key] = new_id("ent")
            session.add(Entity(entity_id=ids[key], entity_type=kind, label=label))
        session.flush()
        # The watched person holds the number. This is the claim that makes the
        # value watched, recorded before any sweep window.
        ids["seed_claim"] = _claim(
            session, ontology, subject=ids["watched"], value=WATCHED, record=ids["record"]
        )
        # What makes VICTOR a member of the watched set, and nothing else: the
        # membership rule is "allied with XRAY", so a stranger acquiring the
        # number later cannot join the set and turn their own numbers into
        # watched ones. A set defined by the identifier itself would do exactly
        # that, and the near-miss test would pass for the wrong reason.
        session.add(
            Claim(
                claim_id=new_id("clm"),
                subject_id=ids["watched"],
                predicate="allied_with",
                object_id=ids["other"],
                assertion_type="reported",
                handling_code="open",
                record_id=ids["record"],
                identity_revision_id=active_revision_id(session),
                ontology_version=ontology.version,
                credibility_normalized="possibly_true",
                verification_status="unverified",
            )
        )
        session.flush()

    # No `rebuild_canonical_map` here, deliberately. It tombstones every entity
    # with no active identity membership, and `compile_set` excludes tombstoned
    # entities — so rebuilding it over bare fixture entities would empty the
    # watched set and every assertion below would pass by finding nothing. The
    # object-set suite makes the same choice for the same reason. Nothing here
    # needs the edge projection either: a `predicate` node compiles against
    # `claim`, and an identifier never becomes an edge.

    owner = _user()
    with session.begin():
        obj, _version = create_set(
            session,
            name="Watched people",
            # "People allied with XRAY." Stable membership, so the watched
            # values stay the ones VICTOR holds.
            # `either`, not `subject`: `allied_with` is symmetric, so the edge
            # projection normalises the endpoints and the claim's own direction
            # is not the projection's. A directional filter here would pass or
            # fail on which way the builder happened to store it.
            ast={
                "kind": "predicate",
                "predicate": "allied_with",
                "target": ids["other"],
            },
            actor=owner.sub,
            ontology=ontology,
        )
        ids["set_id"] = obj.set_id
        watchlist = create_watchlist(
            session,
            name="Harbour numbers",
            set_id=obj.set_id,
            rule="exact_identifier",
            user=owner,
        )
        ids["watchlist"] = watchlist.watchlist_id

    try:
        yield {**ids, "session": session, "owner": owner}
    finally:
        session.close()


def _claim(
    session: Session,
    ontology,
    *,
    subject: str,
    value: str,
    record: str,
    handling: str = "open",
    recorded_at: datetime | None = None,
) -> str:
    claim_id = new_id("clm")
    claim = Claim(
        claim_id=claim_id,
        subject_id=subject,
        predicate="reachable_on",
        object_value=value,
        assertion_type="reported",
        handling_code=handling,
        record_id=record,
        identity_revision_id=active_revision_id(session),
        ontology_version=ontology.version,
        credibility_normalized="possibly_true",
        verification_status="unverified",
    )
    if recorded_at is not None:
        claim.recorded_at = recorded_at
    session.add(claim)
    session.flush()
    return claim_id


def _watchlist(world):
    from aegis.store import Watchlist

    return world["session"].get(Watchlist, world["watchlist"])


# ── the headline behaviour ──────────────────────────────────────────────────


def test_an_exact_identifier_landing_in_canon_fires_on_the_next_sweep(
    world, ontology
) -> None:
    """The whole point. Not on the write path — on the **next sweep**."""
    session: Session = world["session"]
    with _txn(session):
        _claim(
            session,
            ontology,
            subject=world["stranger"],
            value=WATCHED,
            record=world["record"],
        )
    with _txn(session):
        run, alerts = evaluate_watchlist(session, _watchlist(world), ontology=ontology)

    fired = [a for a in alerts if a.entity_id == world["stranger"]]
    assert len(fired) == 1
    alert = fired[0]
    assert alert.matched_value == WATCHED
    assert alert.exactness == "exact"
    assert alert.rule_version == _watchlist(world).rule_version
    assert alert.run_id == run.run_id
    assert alert.status == "new"
    assert alert.claim_ids


def test_a_fuzzy_near_miss_does_not_fire(world, ontology) -> None:
    """Asserted, not assumed (charter risk table).

    One digit away. A watchlist that fires on this teaches its readers to
    believe the next one, which is the failure ADR-053 refuses for search and
    this refuses for detection.
    """
    session: Session = world["session"]
    with _txn(session):
        _claim(
            session,
            ontology,
            subject=world["stranger"],
            value=NEAR_MISS,
            record=world["record"],
        )
    with _txn(session):
        _, alerts = evaluate_watchlist(session, _watchlist(world), ontology=ontology)

    assert [a for a in alerts if a.matched_value == NEAR_MISS] == []


def test_the_same_identifier_landing_twice_produces_one_alert(world, ontology) -> None:
    """Dedupe is `(watchlist, rule_version, value, entity)` — schema, not memory."""
    session: Session = world["session"]
    with _txn(session):
        _claim(
            session,
            ontology,
            subject=world["stranger"],
            value=WATCHED,
            record=world["record"],
        )
    with _txn(session):
        _, first = evaluate_watchlist(session, _watchlist(world), ontology=ontology)
    assert len([a for a in first if a.entity_id == world["stranger"]]) == 1

    # The same value, recorded again, by a different claim.
    with _txn(session):
        _claim(
            session,
            ontology,
            subject=world["stranger"],
            value=WATCHED,
            record=world["record"],
        )
    with _txn(session):
        _, second = evaluate_watchlist(session, _watchlist(world), ontology=ontology)
    assert [a for a in second if a.entity_id == world["stranger"]] == []


def test_a_rerun_over_an_overlapping_window_is_idempotent(world, ontology) -> None:
    """Re-sweeping the same window twice adds nothing.

    Forced by rewinding the watermark, so this tests the **dedupe key** rather
    than the window arithmetic — a sweep whose watermark is wrong must still not
    produce a second alert.
    """
    session: Session = world["session"]
    with _txn(session):
        _claim(
            session,
            ontology,
            subject=world["stranger"],
            value=WATCHED,
            record=world["record"],
        )
    with _txn(session):
        first_run, first = evaluate_watchlist(
            session, _watchlist(world), ontology=ontology
        )
    assert first

    # Rewind: pretend the first sweep never recorded a watermark, so the second
    # scans the same claims again from the beginning of time.
    with _txn(session):
        session.get(AnalyticRun, first_run.run_id).evaluated_through = None
    with _txn(session):
        _, second = evaluate_watchlist(session, _watchlist(world), ontology=ontology)

    assert second == []


# ── the run is the record of the sweep ──────────────────────────────────────


def test_the_first_sweep_reports_where_the_watched_values_already_are(
    world, ontology
) -> None:
    """The first sweep has no watermark, so its window is all of time.

    It therefore reports the member's *own* number — which is the honest answer
    to "where does this value appear", not a false positive. Recorded here
    because it is a design choice and the alternative (start silent, report only
    what lands next) would hide everything already in the corpus.
    """
    session: Session = world["session"]
    with _txn(session):
        _, alerts = evaluate_watchlist(session, _watchlist(world), ontology=ontology)

    assert [a.entity_id for a in alerts] == [world["watched"]]
    assert alerts[0].matched_value == WATCHED


def test_a_sweep_that_found_nothing_is_still_a_run(world, ontology) -> None:
    """A sweep that found nothing and a sweep that never happened must not look
    the same, or "when was this last evaluated" has no answer."""
    session: Session = world["session"]
    with _txn(session):
        evaluate_watchlist(session, _watchlist(world), ontology=ontology)
    # Nothing has landed since, so the second sweep finds nothing — and is
    # still a run, with its own window and its own watermark.
    with _txn(session):
        run, alerts = evaluate_watchlist(session, _watchlist(world), ontology=ontology)

    assert alerts == []
    assert run.method == METHOD
    assert run.evaluated_through is not None
    assert run.finished_at is not None
    assert run.parameters["watchlist_id"] == world["watchlist"]


def test_an_unevaluated_watchlist_is_a_gap_in_the_runs(world, ontology) -> None:
    """Null is a gap, not a quiet zero: nobody has evaluated this."""
    session: Session = world["session"]
    assert last_evaluated_through(session, world["watchlist"]) is None
    session.commit()

    with _txn(session):
        evaluate_watchlist(session, _watchlist(world), ontology=ontology)
    assert last_evaluated_through(session, world["watchlist"]) is not None


def test_the_next_sweep_resumes_where_the_last_one_finished(world, ontology) -> None:
    session: Session = world["session"]
    with _txn(session):
        first, _ = evaluate_watchlist(session, _watchlist(world), ontology=ontology)
    watermark = first.evaluated_through

    with _txn(session):
        second, _ = evaluate_watchlist(session, _watchlist(world), ontology=ontology)

    assert second.parameters["window_from"] == watermark.isoformat()
    assert second.evaluated_through > watermark


def test_the_manifest_records_the_owners_authorization_not_the_callers(
    world, ontology
) -> None:
    """The one place a saved artifact runs with its owner's clearance.

    An alert nobody may read is not an alert, so the sweep uses the owner's
    eyes — and the manifest has to say so, or a detection set that differs
    between two sweeps reads as the system contradicting itself.
    """
    session: Session = world["session"]
    with _txn(session):
        run, _ = evaluate_watchlist(session, _watchlist(world), ontology=ontology)

    assert run.actor == world["owner"].sub
    assert len(run.authorization_digest) == 64


# ── authorization ───────────────────────────────────────────────────────────


def test_a_value_the_owner_cannot_read_never_becomes_a_watched_value(
    world, ontology, engine
) -> None:
    """B-17, in the place it would be easiest to miss.

    The set member holds a second number in a `sensitive` claim. An owner who
    cannot read that claim must not have a watchlist that watches its value —
    otherwise the alert it produced would disclose the number to them by
    quoting it back.
    """
    session: Session = world["session"]
    secret = "+94-70-999-9999"
    with _txn(session):
        _claim(
            session,
            ontology,
            subject=world["watched"],
            value=secret,
            record=world["record"],
            handling="sensitive",
        )
        # A stranger recorded under the same secret number.
        _claim(
            session,
            ontology,
            subject=world["stranger"],
            value=secret,
            record=world["record"],
            handling="sensitive",
        )

    # Narrowed **inside** the sweep's own transaction: `_txn` rolls back first,
    # so a change flushed before the block would be discarded and the sweep
    # would quietly run at the original clearance — passing for the wrong
    # reason, which is the failure mode this whole test exists to catch.
    with _txn(session):
        narrow = _watchlist(world)
        narrow.owner_clearance = 0
        session.flush()
        _, alerts = evaluate_watchlist(session, narrow, ontology=ontology)

    assert [a for a in alerts if a.matched_value == secret] == []


def test_an_alert_takes_the_handling_code_of_the_claims_that_fired_it(
    world, ontology
) -> None:
    """Derived, never chosen — the rule `analytic_finding` follows."""
    session: Session = world["session"]
    with _txn(session):
        _claim(
            session,
            ontology,
            subject=world["stranger"],
            value=WATCHED,
            record=world["record"],
            handling="sensitive",
        )
    with _txn(session):
        _, alerts = evaluate_watchlist(session, _watchlist(world), ontology=ontology)

    fired = [a for a in alerts if a.entity_id == world["stranger"]]
    assert len(fired) == 1
    assert fired[0].handling_code == "sensitive"
    assert fired[0].handling_rank == ontology.handling_rank("sensitive")


# ── triage ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def alert(world, ontology):
    session: Session = world["session"]
    with _txn(session):
        _claim(
            session,
            ontology,
            subject=world["stranger"],
            value=WATCHED,
            record=world["record"],
        )
    with _txn(session):
        _, alerts = evaluate_watchlist(session, _watchlist(world), ontology=ontology)
    return next(a for a in alerts if a.entity_id == world["stranger"])


def test_closing_without_a_reason_is_refused(world, alert) -> None:
    """An alert closed with no reason is indistinguishable from one nobody
    looked at."""
    session: Session = world["session"]
    with pytest.raises(WatchlistError, match="needs a reason"):
        triage_alert(
            session,
            alert_id=alert.alert_id,
            status="closed",
            actor="user:analyst",
        )
    session.rollback()


def test_the_database_refuses_a_reasonless_close_too(world, alert) -> None:
    """Not only the service. A workflow that can be routed around by writing
    the row directly is not a workflow."""
    session: Session = world["session"]
    with pytest.raises(sa.exc.IntegrityError):
        session.execute(
            sa.text(
                "UPDATE watchlist_alert SET status = 'closed' WHERE alert_id = :id"
            ),
            {"id": alert.alert_id},
        )
        session.flush()
    session.rollback()


def test_every_transition_is_audited(world, alert) -> None:
    """Including the ones that look like nothing happened. "Who looked at this
    and decided it was noise" is the question an alert queue exists to answer."""
    session: Session = world["session"]
    with _txn(session):
        triage_alert(
            session,
            alert_id=alert.alert_id,
            status="reviewing",
            actor="user:analyst",
            purpose="morning triage",
        )
    with _txn(session):
        triage_alert(
            session,
            alert_id=alert.alert_id,
            status="closed",
            actor="user:analyst",
            purpose="morning triage",
            reason="the number was reassigned by the operator in 2019",
        )

    rows = list(
        session.scalars(
            sa.select(AuditLog)
            .where(AuditLog.resource_id == alert.alert_id)
            .order_by(AuditLog.id)
        )
    )
    assert [r.action for r in rows] == ["alert.triage", "alert.triage"]
    assert [(r.detail["from"], r.detail["to"]) for r in rows] == [
        ("new", "reviewing"),
        ("reviewing", "closed"),
    ]
    assert rows[-1].detail["reason"]


def test_reopening_clears_the_reason_it_was_closed_with(world, alert) -> None:
    """Deciding you were wrong is a thing that happens, and a reopened alert
    must not carry a closure reason as though it were still closed."""
    session: Session = world["session"]
    with _txn(session):
        triage_alert(
            session,
            alert_id=alert.alert_id,
            status="closed",
            actor="user:analyst",
            reason="noise",
        )
    with _txn(session):
        reopened = triage_alert(
            session,
            alert_id=alert.alert_id,
            status="reviewing",
            actor="user:second",
        )
    assert reopened.status == "reviewing"
    assert reopened.closed_reason is None


def test_an_unknown_status_is_refused(world, alert) -> None:
    session: Session = world["session"]
    with pytest.raises(WatchlistError, match="not a triage status"):
        triage_alert(
            session, alert_id=alert.alert_id, status="dismissed", actor="user:analyst"
        )
    session.rollback()


# ── creation ────────────────────────────────────────────────────────────────


def test_the_set_version_is_pinned_at_creation(world, ontology) -> None:
    """A membership rule that widens later must not silently widen a watchlist
    (ADR-054)."""
    watchlist = _watchlist(world)
    assert watchlist.set_version == 1
    assert watchlist.rule_version


def test_a_watchlist_cannot_be_created_above_its_creators_clearance(
    world, ontology
) -> None:
    """`owner_clearance` comes from the creator's own token, so there is no way
    to ask for one you do not have."""
    session: Session = world["session"]
    with _txn(session):
        watchlist = create_watchlist(
            session,
            name="Narrow",
            set_id=world["set_id"],
            rule="exact_identifier",
            user=_user("user:junior", clearance=0),
        )
    assert watchlist.owner_clearance == 0
    assert watchlist.owner == "user:junior"


def test_an_unknown_rule_is_refused(world) -> None:
    session: Session = world["session"]
    with pytest.raises(WatchlistError, match="is not a rule"):
        create_watchlist(
            session,
            name="Fuzzy",
            set_id=world["set_id"],
            rule="similar_name",
            user=_user(),
        )
    session.rollback()


def test_sweeping_a_watchlist_that_does_not_exist_is_refused(world, ontology) -> None:
    session: Session = world["session"]
    with pytest.raises(WatchlistError, match="not active or does not exist"):
        sweep(session, ontology=ontology, watchlist_id="wl_nothing")
    session.rollback()
