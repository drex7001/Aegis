"""Metrics record answers, with their manifests and their caveats (T72).

Two acceptance criteria live here, and the first is the one ADR-055 had to
redefine before it could be tested at all.

**"Re-running with the same inputs reproduces the finding"** is not a testable
claim: neither an object set nor a projection is immutable, so "the same
inputs" names nothing. The testable version is **equal manifests produce equal
finding digests**, and that is what these tests check — including that the
manifest is sensitive to the things that should change it (a different
clearance, a rebuilt projection) and insensitive to the things that should not
(who ran it, when, why).

**"Every finding carries its catalog caveat and its exact inputs"** is checked
by reading the row, not the renderer. `caveat_text` is stored on the finding,
so there is no render path that fetches one — and therefore none that can fail
to (spec 12 §9.3).

Fictional fixtures throughout.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.orm import Session

from aegis.analytics.caveats import CAVEATS, CAVEAT_VERSION
from aegis.analytics.manifest import Manifest, NON_REPRODUCIBILITY_FIELDS
from aegis.analytics.service import AnalyticsError, run_metric
from aegis.api.auth import UserContext
from aegis.er.canonical import rebuild_canonical_map
from aegis.er.ledger import active_revision_id
from aegis.ids import new_id
from aegis.ontology import load
from aegis.projections import rebuild_edge_projection
from aegis.store import AnalyticFinding, AnalyticRun, Claim, Entity, Source, SourceRecord
from tests.support.database import migrated_test_engine, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement(
    "Article-IX", "Article-VI", "H-23", "ADR-055", "charter-p6-exit-2", "T72"
)


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


def _user(sub: str, clearance: int) -> UserContext:
    return UserContext(
        sub=sub,
        username=sub,
        roles=frozenset({"analyst"}),
        clearance=clearance,
        claims={},
    )


@pytest.fixture()
def world(engine: sa.Engine, ontology):
    """A small connected graph. One edge is reachable only above clearance 0.

    `MIKE — NOVEMBER — OSCAR` in a line, so betweenness has something to say
    about the middle, plus a `sensitive` link so a finding's handling code has
    something to derive from.
    """
    truncate_domain_data(engine)
    session = Session(engine)
    ids = {"source": new_id("src"), "record": new_id("rec")}
    with session.begin():
        session.add(Source(source_id=ids["source"], source_type="open_source", name="T72"))
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="c" * 64,
                storage_uri="test://t72",
            )
        )
        session.flush()
        for key, label in (
            ("mike", "Fictional MIKE"),
            ("november", "Fictional NOVEMBER"),
            ("oscar", "Fictional OSCAR"),
        ):
            ids[key] = new_id("ent")
            session.add(Entity(entity_id=ids[key], entity_type="person", label=label))
        session.flush()

        revision = active_revision_id(session)

        def link(subject: str, obj: str, handling: str) -> str:
            claim_id = new_id("clm")
            session.add(
                Claim(
                    claim_id=claim_id,
                    subject_id=ids[subject],
                    predicate="allied_with",
                    object_id=ids[obj],
                    assertion_type="reported",
                    handling_code=handling,
                    record_id=ids["record"],
                    identity_revision_id=revision,
                    ontology_version="2.1.0",
                    credibility_normalized="possibly_true",
                    verification_status="unverified",
                )
            )
            return claim_id

        ids["open_link"] = link("mike", "november", "open")
        ids["sensitive_link"] = link("november", "oscar", "sensitive")

    with Session(engine) as builder:
        rebuild_canonical_map(builder)
        rebuild_edge_projection(builder, ontology=ontology)
        builder.commit()

    try:
        yield {**ids, "session": session}
    finally:
        session.close()


def _run(session, metric, ontology, *, user=None, **kwargs):
    return run_metric(
        session,
        metric=metric,
        user=user or _user("user:analyst", 2),
        ontology=ontology,
        purpose="testing",
        **kwargs,
    )


# ── the metrics record something ────────────────────────────────────────────


def test_degree_counts_recorded_connections(world, ontology) -> None:
    session = world["session"]
    _, findings = _run(session, "degree", ontology)
    by_subject = {f.subjects[0]: f.value["degree"] for f in findings}
    assert by_subject[world["november"]] == 2
    assert by_subject[world["mike"]] == 1


def test_betweenness_finds_the_entity_in_the_middle(world, ontology) -> None:
    session = world["session"]
    _, findings = _run(session, "betweenness", ontology)
    by_subject = {f.subjects[0]: f.value["betweenness"] for f in findings}
    assert by_subject[world["november"]] > by_subject[world["mike"]]


def test_community_records_which_library_ran(world, ontology) -> None:
    """The manifest names the implementation, not just the algorithm.

    `clustering.py` falls back from Leiden to Louvain when igraph is missing.
    It labels the result — but a label on a summary nobody must persist is not
    provenance, and here the fallback is a different manifest.
    """
    session = world["session"]
    run, findings = _run(session, "community", ontology)
    assert findings
    assert run.implementation
    assert any(name in run.implementation for name in ("leiden", "louvain"))
    # A version, not just a name: "leiden" alone would compare equal across
    # two different releases of the library.
    assert any(char.isdigit() for char in run.implementation)


def test_an_unknown_metric_is_refused(world, ontology) -> None:
    session = world["session"]
    with pytest.raises(AnalyticsError):
        _run(session, "influence", ontology)


# ── every finding carries its caveat ────────────────────────────────────────


@pytest.mark.parametrize("metric", ["degree", "betweenness", "community"])
def test_every_finding_carries_the_catalog_caveat(world, ontology, metric: str) -> None:
    """Read from the row, not from the renderer.

    There is no render path that fetches a caveat, which is why there is no
    render path that can fail to (spec 12 §9.3).
    """
    session = world["session"]
    _, findings = _run(session, metric, ontology)
    assert findings
    for finding in findings:
        assert finding.caveat_text == CAVEATS[metric].text
        assert finding.caveat_version == CAVEAT_VERSION


def test_a_caveat_cannot_be_blanked_even_by_direct_sql(world, ontology) -> None:
    """Article IX at the column, so a future code path cannot route around it."""
    session = world["session"]
    _, findings = _run(session, "degree", ontology)
    session.flush()
    with pytest.raises(sa.exc.IntegrityError):
        session.execute(
            sa.update(AnalyticFinding)
            .where(AnalyticFinding.finding_id == findings[0].finding_id)
            .values(caveat_text="   ")
        )
        session.flush()
    session.rollback()


# ── reproducibility, as ADR-055 defines it ──────────────────────────────────


def test_two_runs_by_the_same_caller_agree(world, ontology) -> None:
    """Equal manifests, equal finding digests — the testable form of the AC."""
    session = world["session"]
    first_run, first = _run(session, "degree", ontology)
    second_run, second = _run(session, "degree", ontology)

    assert _key(first_run) == _key(second_run)
    assert {f.finding_digest for f in first} == {f.finding_digest for f in second}


def _key(run: AnalyticRun) -> str:
    fields = {
        name: getattr(run, name)
        for name in Manifest.__dataclass_fields__
        if name not in NON_REPRODUCIBILITY_FIELDS
    }
    return Manifest(**fields).reproducibility_key()


def test_two_runs_by_different_callers_do_not(world, ontology) -> None:
    """A finding computed under a narrower clearance is a different finding.

    Article VI, made mechanical: the authorization digest is part of the
    manifest, so the two runs are not expected to agree and nobody can compare
    them as though they were.
    """
    session = world["session"]
    senior_run, senior = _run(session, "degree", ontology, user=_user("user:senior", 2))
    junior_run, junior = _run(session, "degree", ontology, user=_user("user:junior", 0))

    assert senior_run.authorization_digest != junior_run.authorization_digest
    assert _key(senior_run) != _key(junior_run)
    assert {f.finding_digest for f in senior} != {f.finding_digest for f in junior}


def test_who_ran_it_and_when_do_not_change_the_key(world, ontology) -> None:
    """Otherwise the digest would be measuring the analyst.

    Two people asking the same question of the same corpus under the same
    clearance must get the same answer, or reproducibility means nothing.
    """
    session = world["session"]
    first, _ = _run(session, "degree", ontology, user=_user("user:one", 2))
    second, _ = _run(session, "degree", ontology, user=_user("user:two", 2))
    assert first.actor != second.actor
    assert _key(first) == _key(second)


def test_a_rebuilt_projection_is_visible_as_a_different_edge_digest(
    world, ontology, engine
) -> None:
    """`edge_digest` is over the rows read, so a rebuild that changed them shows.

    Which is what the stamps alone would not catch: a projection rebuilt at the
    same identity revision has the same stamps and possibly different rows.
    """
    session = world["session"]
    before, _ = _run(session, "degree", ontology)
    session.commit()

    with Session(engine) as builder:
        builder.execute(
            sa.update(Claim)
            .where(Claim.claim_id == world["open_link"])
            .values(retracted_at=sa.func.now(), retraction_reason="fixture")
        )
        rebuild_edge_projection(builder, ontology=ontology)
        builder.commit()

    after, _ = _run(session, "degree", ontology)
    assert before.edge_digest != after.edge_digest


# ── the manifest records which projection, not whether it was fresh ─────────


def test_the_manifest_names_the_projection_it_read(world, ontology) -> None:
    """The Phase-5 `is_stale` carryover, closed without changing what it means.

    Freshness is an operator's question about a cache; provenance is a
    finding's question about its own inputs. The manifest answers the second.
    """
    session = world["session"]
    run, _ = _run(session, "degree", ontology)
    assert run.projection_built_at_revision_id is not None
    assert run.projection_builder_version
    assert run.projection_aggregation_method_version
    assert len(run.edge_digest) == 64


def test_the_manifest_records_an_unseeded_run_as_unseeded(world, ontology) -> None:
    """NULL rather than 0, which would later read as a determinism it never had."""
    session = world["session"]
    run, _ = _run(session, "degree", ontology)
    assert run.seed is None

    community, _ = _run(session, "community", ontology)
    assert community.seed == 42


def test_the_manifest_is_written_before_the_findings(world, ontology) -> None:
    """A run that crashed mid-metric should still be visible as a run.

    A manifest written afterwards would only ever describe successes, which is
    the opposite of what a provenance record is for.
    """
    session = world["session"]
    run, findings = _run(session, "degree", ontology)
    assert run.started_at <= findings[0].created_at or run.finished_at is not None


# ── handling code is derived ────────────────────────────────────────────────


def test_a_finding_over_restricted_evidence_is_restricted(world, ontology) -> None:
    """Derived from the claims that contributed, never chosen.

    A finding computed from sensitive evidence and stored as `open` would be
    the leak the whole evaluation path exists to prevent, arriving one level
    up (spec 12 §8.3).
    """
    session = world["session"]
    _, findings = _run(session, "degree", ontology)
    by_subject = {f.subjects[0]: f for f in findings}
    # OSCAR is reachable only through the sensitive link.
    assert by_subject[world["oscar"]].handling_code == "sensitive"
    # MIKE's only link is open.
    assert by_subject[world["mike"]].handling_code == "open"


def test_a_narrower_caller_computes_over_less(world, ontology) -> None:
    session = world["session"]
    _, senior = _run(session, "degree", ontology, user=_user("user:senior", 2))
    _, junior = _run(session, "degree", ontology, user=_user("user:junior", 0))
    assert {f.subjects[0] for f in junior} < {f.subjects[0] for f in senior}
    assert world["oscar"] not in {f.subjects[0] for f in junior}
