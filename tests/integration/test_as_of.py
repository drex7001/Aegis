"""As-of is a claim-recording snapshot, stamped with what produced it (T49, B-11).

The finding B-11 recorded was that the promise exceeded the time model: "what
did we know before X" was described as if it restored the past, and nothing in
the system could do that. Spec 09 §7 narrows it to what is actually true, and
this file is that narrowing made executable.

Three things are asserted, and the third is the one that took work:

1. `?asOf=` excludes a claim recorded after the timestamp, and restores one
   retracted after it.
2. Every response carries `{as_of, identity_revision_id, ontology_version}` —
   **including a current one**, so a caller never has to re-read its own request
   to know which identity produced an answer.
3. `?asOfRevision=` resolves entity arguments as identity was understood *then*.
   Without it, `asOf` alone answers a historical question with today's identity:
   a person merged last week absorbs claims that, at the asked-about moment,
   belonged to somebody else.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from aegis.actions import new_id
from aegis.er.canonical import canonical_entity_at, rebuild_canonical_map
from aegis.er.ledger import active_revision_id, open_membership
from aegis.er.normalize import norm_key
from aegis.store import (
    Claim,
    Entity,
    IdentityDecision,
    IdentityMembership,
    IdentityRevision,
    Mention,
    Source,
    SourceRecord,
)
from tests.integration.test_api import (  # noqa: F401
    _FakeFGA,
    api_db,
    auth,
    clean_api_database,
    client,
    fake_fga,
)

pytestmark = pytest.mark.requirement("B-11", "ADR-029", "T49")

ANALYST = "analyst-t49"
EARLY = datetime(2026, 1, 1, tzinfo=timezone.utc)
LATE = datetime(2026, 6, 1, tzinfo=timezone.utc)
BETWEEN = datetime(2026, 3, 1, tzinfo=timezone.utc)


@pytest.fixture()
def world(client: TestClient) -> dict:
    """Two people, later merged, each with a claim recorded at a known time.

    The merge is what makes the identity half testable: after it, `alias`
    resolves to `subject`, so a question about January answered with June's
    identity returns both claims — which is precisely the wrong answer.
    """
    engine = sa.create_engine(client.app.state.settings.database_url)
    ids: dict[str, str] = {}
    with Session(engine) as session, session.begin():
        session.add(Source(source_id=(sid := new_id("src")), source_type="open_source", name="T49"))
        session.add(
            SourceRecord(
                record_id=(rid := new_id("rec")),
                source_id=sid,
                ingest_key=new_id("key"),
                content_hash="9" * 64,
                storage_uri="test://t49",
            )
        )
        session.flush()
        ids["record"] = rid
        for key, label in (
            ("subject", "Fictional Primary"),
            ("alias", "Fictional Duplicate"),
            ("org", "Fictional Co"),
        ):
            entity_id, mention_id = new_id("ent"), new_id("men")
            ids[key] = entity_id
            ids[f"{key}_mention"] = mention_id
            session.add(
                Entity(
                    entity_id=entity_id,
                    entity_type="organization" if key == "org" else "person",
                    label=label,
                )
            )
            session.add(
                Mention(
                    mention_id=mention_id,
                    record_id=rid,
                    raw_text=label,
                    norm_key=f"{norm_key(label)}-{mention_id[-6:].lower()}",
                )
            )
            session.flush()
            open_membership(session, mention_id=mention_id, entity_id=entity_id)

        for key, when in (("early", EARLY), ("late", LATE)):
            claim_id = new_id("clm")
            ids[key] = claim_id
            session.add(
                Claim(
                    claim_id=claim_id,
                    subject_id=ids["subject"],
                    predicate="member_of",
                    object_id=ids["org"],
                    assertion_type="reported",
                    record_id=rid,
                    identity_revision_id=0,
                    ontology_version=client.app.state.ontology.version,
                    recorded_at=when,
                )
            )
        # One claim written against the duplicate, before anyone knew they were
        # the same person.
        ids["alias_claim"] = new_id("clm")
        session.add(
            Claim(
                claim_id=ids["alias_claim"],
                subject_id=ids["alias"],
                predicate="member_of",
                object_id=ids["org"],
                assertion_type="reported",
                record_id=rid,
                identity_revision_id=0,
                ontology_version=client.app.state.ontology.version,
                recorded_at=EARLY,
            )
        )

    # ...and the merge, as its own revision, so it has a number to pin against.
    with Session(engine) as session, session.begin():
        before = active_revision_id(session)
        decision = IdentityDecision(
            decision_id=new_id("dec"),
            kind="confirm",
            decided_by=ANALYST,
            decision_note="Same fictional person.",
            parent_revision_id=before,
            result_revision_id=before + 1,
        )
        session.add(IdentityRevision(revision_id=before + 1, decision_id=decision.decision_id))
        session.add(decision)
        session.flush()
        # The duplicate's mention moves onto the primary: closed there, opened
        # here, both at the merge revision.
        session.execute(
            sa.update(IdentityMembership)
            .where(
                IdentityMembership.mention_id == ids["alias_mention"],
                IdentityMembership.closed_revision_id.is_(None),
            )
            .values(closed_revision_id=before + 1)
        )
        # Through `open_membership`, which mints the id and refuses a mention
        # that still has an active row — the close above is what makes this a
        # move rather than a second parallel membership.
        open_membership(
            session,
            mention_id=ids["alias_mention"],
            entity_id=ids["subject"],
            revision_id=before + 1,
        )
        ids["before_merge"] = before
        ids["after_merge"] = before + 1
    with Session(engine) as session, session.begin():
        rebuild_canonical_map(session)
    engine.dispose()
    return ids


def _get(client: TestClient, entity_id: str, **params) -> dict:
    response = client.get(
        f"/v1/entities/{entity_id}", params=params, headers=auth(ANALYST, "analyst")
    )
    return {"status": response.status_code, "body": response.json()}


def _claim_ids(body: dict) -> set[str]:
    return {
        entry["claim"]["claim_id"]
        for claims in body["claims_by_predicate"].values()
        for entry in claims
    }


# ── the recording snapshot ──────────────────────────────────────────────────


def test_as_of_excludes_a_claim_recorded_after_the_timestamp(
    client: TestClient, world: dict
) -> None:
    """The charter's third exit criterion, in its smallest form."""
    now = _get(client, world["subject"])
    assert world["late"] in _claim_ids(now["body"])

    then = _get(client, world["subject"], asOf=BETWEEN.isoformat())
    assert then["status"] == 200
    assert world["early"] in _claim_ids(then["body"])
    assert world["late"] not in _claim_ids(then["body"])


def test_a_current_read_carries_the_stamp_too(client: TestClient, world: dict) -> None:
    """Not only as-of responses. A caller must never have to re-read its own
    request to know which identity produced an answer."""
    stamp = _get(client, world["subject"])["body"]["stamp"]
    assert stamp["as_of"] is None
    assert stamp["identity_revision_id"] == world["after_merge"]
    assert stamp["ontology_version"] == client.app.state.ontology.version


def test_an_as_of_read_stamps_all_three_fields(client: TestClient, world: dict) -> None:
    body = _get(
        client,
        world["subject"],
        asOf=BETWEEN.isoformat(),
        asOfRevision=world["before_merge"],
    )["body"]
    assert body["stamp"]["as_of"].startswith("2026-03-01")
    assert body["stamp"]["identity_revision_id"] == world["before_merge"]
    assert body["stamp"]["ontology_version"] == client.app.state.ontology.version


# ── the identity half (the part `asOf` alone gets wrong) ────────────────────


def test_without_a_pin_a_historical_question_gets_todays_identity(
    client: TestClient, world: dict
) -> None:
    """Stated as a test rather than a caveat, because it is the trap.

    In January these were two people. Asking about January with today's identity
    answers about the merged person — which is why spec 06 §3 requires the
    revision to be echoed, and why the workspace's banner names it.
    """
    unpinned = _get(client, world["subject"], asOf=BETWEEN.isoformat())["body"]
    assert world["alias_claim"] in _claim_ids(unpinned)
    assert unpinned["stamp"]["identity_revision_id"] == world["after_merge"]


def test_pinning_the_revision_answers_with_the_identity_of_the_time(
    client: TestClient, world: dict
) -> None:
    pinned = _get(
        client,
        world["subject"],
        asOf=BETWEEN.isoformat(),
        asOfRevision=world["before_merge"],
    )["body"]
    # Before the merge, the duplicate's claim was not this person's.
    assert world["alias_claim"] not in _claim_ids(pinned)
    assert world["early"] in _claim_ids(pinned)


def test_the_pinned_resolution_is_computed_not_read_from_the_cache(
    client: TestClient, world: dict
) -> None:
    """`entity_canonical_map` holds one answer — the active one.

    So the pinned lineage has to be replayed from the ledger, and this asserts
    the replay disagrees with the cache exactly where it should.
    """
    engine = sa.create_engine(client.app.state.settings.database_url)
    with Session(engine) as session:
        assert (
            canonical_entity_at(session, world["alias"], world["after_merge"])
            == world["subject"]
        )
        assert (
            canonical_entity_at(session, world["alias"], world["before_merge"])
            == world["alias"]
        )
    engine.dispose()


def test_a_revision_that_has_not_happened_is_refused(
    client: TestClient, world: dict
) -> None:
    """422, not a clamp to the head.

    Answering about *now* under a heading that says otherwise is the failure
    this parameter exists against.
    """
    refused = _get(client, world["subject"], asOfRevision=world["after_merge"] + 500)
    assert refused["status"] == 422


def test_as_of_restores_a_claim_retracted_afterwards(
    client: TestClient, world: dict
) -> None:
    """"Recorded and not retracted at that instant" — both halves."""
    engine = sa.create_engine(client.app.state.settings.database_url)
    with Session(engine) as session, session.begin():
        session.execute(
            sa.update(Claim)
            .where(Claim.claim_id == world["early"])
            .values(retracted_at=LATE, retraction_reason="withdrawn by the source")
        )
    engine.dispose()

    assert world["early"] not in _claim_ids(_get(client, world["subject"])["body"])
    earlier = _get(client, world["subject"], asOf=BETWEEN.isoformat())["body"]
    assert world["early"] in _claim_ids(earlier)


def test_as_of_does_not_restore_the_ontology_version(
    client: TestClient, world: dict
) -> None:
    """The narrowing, asserted as an absence.

    A claim stamped an older composition version still reports the version the
    *server* is running, because as-of restores no vocabulary — which is exactly
    what the promise now says and did not before.
    """
    body = _get(client, world["subject"], asOf=BETWEEN.isoformat())["body"]
    assert body["stamp"]["ontology_version"] == client.app.state.ontology.version


def test_a_future_timestamp_is_the_same_as_now(client: TestClient, world: dict) -> None:
    later = datetime.now(timezone.utc) + timedelta(days=365)
    assert _claim_ids(_get(client, world["subject"], asOf=later.isoformat())["body"]) == (
        _claim_ids(_get(client, world["subject"])["body"])
    )
