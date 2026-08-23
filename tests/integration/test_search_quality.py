"""The blocking search-quality gate, over the real search path (T68, H-22).

The charter's first exit criterion is "golden search-set precision/recall
targets met in CI". This is that check. It seeds the golden corpus through the
same tables the product writes, runs the **real** `search()` — same filters,
same ranking, same pipeline — and scores the answers against the numbers T66
fixed at phase start.

Two things it also proves, because a gate that only ever passes is a gate
nobody can trust:

* **it can fail** — a seeded regression drops a target below its floor;
* **the trigger is real** — a failure names the ADR-012 condition rather than
  quietly reporting a number.

What the run measures, recorded here so a future reader can see whether it
moved: cross-script retrieval sits at **0.75**, above its 0.70/0.60 floor and
comfortably below everything else. Two of eight fictional Sinhala/Tamil names
are still not reachable from their English romanization at all. That is the
honest state of the art in this system, not a rounding error.
"""

from __future__ import annotations

import json

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.orm import Session

from aegis.api.auth import UserContext
from aegis.ontology import load
from aegis.search.evaluation import evaluate, seed
from aegis.search.quality import DEFAULT_REPORT, load_golden_set
from aegis.search.targets import LATENCY_BUDGET_MS, RESOURCE_TARGETS, SCRIPT_TARGETS
from tests.support.database import migrated_test_engine, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement("H-22", "ADR-012", "charter-p6-exit-1", "T68")


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


@pytest.fixture(scope="module")
def analyst(ontology) -> UserContext:
    """A cleared analyst, never a superuser.

    Every target is computed over one authorized view (spec 11 §8), so a number
    can never be met by widening what is visible. Evaluating as something the
    product does not have would measure a system nobody uses.
    """
    return UserContext(
        sub="user:search-evaluation",
        username="search-evaluation",
        roles=frozenset({"analyst"}),
        clearance=len(ontology.handling_codes) - 1,
        claims={},
    )


@pytest.fixture(scope="module")
def report(engine: sa.Engine, ontology, analyst):
    """One evaluation, shared by every assertion below, written to disk.

    The report is written **here** rather than by the CLI, and the reason is
    the database. `aegis search evaluate` reads `AEGIS_DATABASE_URL`, while
    CI's integration job provides `AEGIS_TEST_DATABASE_URL` and migrates
    through the test harness — so a CI step calling the CLI would either point
    at nothing or depend on an earlier step having migrated for it. The CLI
    stays for operators pointing at a real database; the gate runs here.

    Written even when the gate fails, because the numbers that failed are the
    evidence (H-22).
    """
    truncate_domain_data(engine)
    with Session(engine) as session:
        result = evaluate(session, user=analyst, ontology=ontology)
        session.rollback()

    DEFAULT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_REPORT.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


# ── the gate ────────────────────────────────────────────────────────────────


def test_the_quality_gate_passes(report) -> None:
    """Charter exit criterion №1, as one assertion.

    The failure message is the report's own list, so a regression says which
    target moved rather than that something did.
    """
    assert report.passed, "\n  ".join(["search quality gate failed:", *report.failures])


@pytest.mark.parametrize("script", sorted(SCRIPT_TARGETS))
def test_each_script_meets_its_floor(report, script: str) -> None:
    target = SCRIPT_TARGETS[script]
    scores = report.by_script[script]
    assert scores["queries"] > 0, f"no query exercises {script}"
    assert scores["precision_at_5"] >= target.precision_at_5
    assert scores["recall_at_20"] >= target.recall_at_20


@pytest.mark.parametrize("resource", sorted(RESOURCE_TARGETS))
def test_each_resource_meets_its_floor(report, resource: str) -> None:
    target = RESOURCE_TARGETS[resource]
    scores = report.by_resource[resource]
    assert scores["queries"] > 0, f"no query exercises {resource}"
    assert scores["precision_at_5"] >= target.precision_at_5
    assert scores["recall_at_20"] >= target.recall_at_20


def test_latency_is_within_budget(report) -> None:
    assert report.latency_p50_ms <= LATENCY_BUDGET_MS["p50"]
    assert report.latency_p95_ms <= LATENCY_BUDGET_MS["p95"]


def test_no_identifier_query_returned_a_fuzzy_hit(report) -> None:
    """ADR-053 in the real engine, not only in the arithmetic."""
    assert report.identifier_violations == []
    assert report.identifier_precision == 1.0


# ── what the numbers actually are ───────────────────────────────────────────


def test_cross_script_is_the_weakest_surface_and_is_recorded_as_such(report) -> None:
    """The finding T68 exists to produce, asserted so it cannot drift unnoticed.

    `unidecode` romanizes an abugida by dropping inherent vowels, so a stored
    key and a typed English romanization are two different systems. Relaxing
    the floor for *differing* scripts took this from 0.375 to 0.75 with no
    measurable precision cost — but it remains the weakest bucket by a wide
    margin, and an improvement that quietly regressed it should fail here.
    """
    cross = report.by_script["cross_script"]["recall_at_20"]
    best = max(
        report.by_script[name]["recall_at_20"]
        for name in ("latin", "sinhala", "tamil")
    )
    assert cross < best, (
        "cross-script has caught up with same-script retrieval — good news, and "
        "this test and the CROSS_SCRIPT_FLOOR evidence table both need rewriting"
    )
    assert cross >= 0.6


def test_the_report_names_what_it_measured(report) -> None:
    """A number with no provenance cannot be compared to a later one."""
    _, digest = load_golden_set()
    assert report.golden_set_sha256 == digest
    assert report.normalization_version
    assert report.query_count == len(load_golden_set()[0].queries)


# ── it can fail ─────────────────────────────────────────────────────────────


def test_a_seeded_regression_fails_the_gate(engine, ontology, analyst) -> None:
    """The gate must be able to say no.

    The regression is seeded at the source: the mention rows that make
    cross-script retrieval possible are stamped with an older pipeline version,
    which the query path excludes (ADR-052). That is a real regression an
    operator could cause by changing the pipeline and forgetting to reindex —
    not a mutated report.
    """
    truncate_domain_data(engine)
    with Session(engine) as session:
        golden, _ = load_golden_set()
        ids = seed(session, golden, ontology=ontology)
        healthy = evaluate(session, user=analyst, ontology=ontology, ids=ids)
        assert healthy.passed, healthy.failures

        session.execute(
            sa.text("UPDATE mention SET normalization_version = 'search-norm-v0'")
        )
        session.flush()
        degraded = evaluate(session, user=analyst, ontology=ontology, ids=ids)
        session.rollback()

    assert not degraded.passed
    assert any("cross_script" in failure for failure in degraded.failures)
    # The same corpus, the same ids, one column changed — so the failure is
    # caused by the regression rather than by the corpus being absent. Without
    # the healthy run above, a harness that found nothing at all would pass
    # this test while proving nothing.
    assert degraded.by_script["latin"]["recall_at_20"] == 1.0, (
        "Latin retrieval should be untouched: it reads labels and claims, not "
        "the mention keys the regression invalidated"
    )
