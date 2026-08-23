"""`shared_identifier` must scan only what the caller may read (T75, B-17).

Spec 11's governing sentence is about search, but it states the rule the whole
phase runs on: **a result you may not see must be absent from the scan, not
removed from the answer.** Every other metric obeys it structurally, because
`load_graph` filters the projection by clearance before anything is computed.

This one queries `claim` directly. The test exists because "the finding is
stored with the maximum handling code of its evidence, so a narrower reader
cannot list it later" is a *different* guarantee from "a narrower caller never
computed it" — and the first one is not the one Article VI asks for.

Fictional fixtures throughout. `reachable_on` rather than `has_nic`: the data
ethics rule in AGENTS.md is about real people, and a test that reaches for a
national-ID number even fictionally is a test that teaches the wrong reflex.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.orm import Session

from aegis.analytics.service import run_metric
from aegis.api.auth import UserContext
from aegis.er.canonical import rebuild_canonical_map
from aegis.er.ledger import active_revision_id
from aegis.ids import new_id
from aegis.ontology import load
from aegis.projections import rebuild_edge_projection
from aegis.store import Claim, Entity, Source, SourceRecord
from tests.support.database import configured_test_database, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement("Article-VI", "B-17", "spec-12-9.1", "T75")

#: The shared value. Fictional, and deliberately not an identifier shaped like
#: anything a real registry issues.
SHARED = "+94-70-000-0000"


def _user(sub: str, clearance: int) -> UserContext:
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
    """Two people recorded under one phone number, in **sensitive** claims."""
    truncate_domain_data(engine)
    session = Session(engine)
    ids = {"source": new_id("src"), "record": new_id("rec")}
    with session.begin():
        session.add(Source(source_id=ids["source"], source_type="open_source", name="T75"))
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="d" * 64,
                storage_uri="test://t75",
            )
        )
        session.flush()
        for key, label in (("a", "Fictional TANGO"), ("b", "Fictional UNIFORM")):
            ids[key] = new_id("ent")
            session.add(Entity(entity_id=ids[key], entity_type="person", label=label))
        session.flush()
        for key in ("a", "b"):
            session.add(
                Claim(
                    claim_id=new_id("clm"),
                    subject_id=ids[key],
                    predicate="reachable_on",
                    object_value=SHARED,
                    assertion_type="reported",
                    handling_code="sensitive",
                    record_id=ids["record"],
                    identity_revision_id=active_revision_id(session),
                    ontology_version=ontology.version,
                    credibility_normalized="possibly_true",
                    verification_status="unverified",
                )
            )

        # A relationship claim as well, so the graph metrics have something to
        # find. Without it the sweep below passes for four metrics by computing
        # nothing at all, which is the shape of a test that proves nothing.
        session.add(
            Claim(
                claim_id=new_id("clm"),
                subject_id=ids["a"],
                predicate="allied_with",
                object_id=ids["b"],
                assertion_type="reported",
                handling_code="sensitive",
                record_id=ids["record"],
                identity_revision_id=active_revision_id(session),
                ontology_version=ontology.version,
                credibility_normalized="possibly_true",
                verification_status="unverified",
            )
        )

    with Session(engine) as builder:
        rebuild_canonical_map(builder)
        rebuild_edge_projection(builder, ontology=ontology)
        builder.commit()

    try:
        yield {**ids, "session": session}
    finally:
        session.close()


def test_the_metric_finds_the_shared_identifier_for_a_cleared_caller(
    world, ontology
) -> None:
    """The control. Without this, the test below passes for the wrong reason."""
    session: Session = world["session"]
    _, findings = run_metric(
        session,
        metric="shared_identifier",
        user=_user("user:analyst", clearance=2),
        ontology=ontology,
        purpose="checking the number",
    )
    assert len(findings) == 1
    assert sorted(findings[0].subjects) == sorted([world["a"], world["b"]])
    assert findings[0].handling_code == "sensitive"


def test_a_narrower_caller_does_not_compute_the_finding_at_all(world, ontology) -> None:
    """Absent from the scan, not removed from the answer.

    A clearance-0 caller may not read either contributing claim. Storing the
    finding at `sensitive` and filtering it out of a later list is not the same
    guarantee: the run response returns findings directly, so a finding that
    was *computed* is a finding that was disclosed — it says two named people
    share a number, which is the whole content of the restricted claims.
    """
    session: Session = world["session"]
    _, findings = run_metric(
        session,
        metric="shared_identifier",
        user=_user("user:junior", clearance=0),
        ontology=ontology,
        purpose="checking the number",
    )
    assert findings == []


def test_an_object_set_scopes_the_metric(world, ontology) -> None:
    """`entity_ids` is the caller's evaluation of a set; ignoring it runs a
    different question from the one that was asked."""
    session: Session = world["session"]
    _, findings = run_metric(
        session,
        metric="shared_identifier",
        user=_user("user:analyst", clearance=2),
        ontology=ontology,
        purpose="checking the number",
        entity_ids=[world["a"]],
    )
    # Only one of the two subjects is in scope, so nothing is *shared* within it.
    assert findings == []

# ── the invariant, across every metric ──────────────────────────────────────

#: The metrics that record findings today. `k_hop` and `shortest_path` are
#: served by `/v1/graph` and raise rather than record (spec 12 §9.1), so they
#: cannot be swept here — and the sweep asserts that too, below, rather than
#: letting a metric quietly leave the list.
RECORDING = ("degree", "betweenness", "community", "shared_identifier")


@pytest.mark.parametrize("metric", RECORDING)
def test_a_cleared_caller_gets_findings_from_every_metric(
    world, ontology, metric
) -> None:
    """The control for the sweep below.

    Without it, "a narrower caller gets nothing" passes for any metric that
    computes nothing for anybody — which is exactly how a filter that is
    missing looks identical to a filter that works.
    """
    session: Session = world["session"]
    _, findings = run_metric(
        session,
        metric=metric,
        user=_user("user:analyst", clearance=2),
        ontology=ontology,
        purpose="control",
    )
    assert findings, f"{metric} computed nothing for a cleared caller"


@pytest.mark.parametrize("metric", RECORDING)
def test_no_metric_computes_a_finding_over_evidence_the_caller_cannot_read(
    world, ontology, metric
) -> None:
    """Every claim in this world is `sensitive`; the caller has clearance 0.

    Parameterised over every recording metric on purpose. This hole has now
    appeared three times, each time in a module that selected entities without
    going through the shared filter, and each time it was found by someone
    writing a test for that one module. A per-metric assertion is what makes
    the *next* metric arrive with the question already asked of it.
    """
    session: Session = world["session"]
    _, findings = run_metric(
        session,
        metric=metric,
        user=_user("user:junior", clearance=0),
        ontology=ontology,
        purpose="checking",
    )
    assert findings == [], f"{metric} disclosed a finding over unreadable evidence"


def test_the_recording_list_matches_what_the_service_will_run(ontology) -> None:
    """A metric added to `METRICS` without a caveat, or without joining the
    sweep above, should not be able to slip past both."""
    from aegis.analytics.service import METRICS

    non_recording = {"k_hop", "shortest_path"}
    assert set(METRICS) - non_recording == set(RECORDING)
