"""The scoring arithmetic, before any of it touches a database (T68).

A quality harness is a measuring instrument, and an instrument nobody
calibrates reports whatever it reports. These are the calibration checks: the
metrics behave as their definitions say, the gate can actually fail, and the
two places the arithmetic could flatter itself do not.

`quality.py` is database-free precisely so this can exist. The integration
half — seed a corpus, run the real search, score it — is
`tests/integration/test_search_quality.py`.
"""

from __future__ import annotations

import pytest

from aegis.search.quality import (
    PRECISION_AT,
    RECALL_AT,
    GoldenSet,
    QualityError,
    load_golden_set,
    measure,
    percentile,
    precision_at_k,
    recall_at_k,
)
from aegis.search.targets import RESOURCE_TARGETS, SCRIPT_TARGETS

pytestmark = pytest.mark.requirement("H-22", "ADR-012", "ADR-053", "T68")


# ── precision, and the denominator that matters ─────────────────────────────


def test_precision_divides_by_what_was_returned_not_by_k() -> None:
    """One correct hit and nothing else is a perfect answer, not a 0.2.

    Dividing by `k` would punish a search for being precise — the exact
    behaviour ADR-053's identifier rule is built to produce.
    """
    assert precision_at_k(["a"], {"a"}, PRECISION_AT) == 1.0


def test_precision_still_falls_when_wrong_hits_are_returned() -> None:
    """Non-vacuity: the lenient denominator must not make everything 1.0."""
    assert precision_at_k(["a", "b", "c", "d"], {"a"}, PRECISION_AT) == 0.25


def test_returning_nothing_when_nothing_was_expected_is_correct() -> None:
    """The identifier near-miss case. Scoring it 0.0 would punish the right answer."""
    assert precision_at_k([], set(), PRECISION_AT) == 1.0
    assert recall_at_k([], set(), RECALL_AT) == 1.0


def test_returning_nothing_when_something_was_expected_is_not() -> None:
    assert precision_at_k([], {"a"}, PRECISION_AT) == 0.0
    assert recall_at_k([], {"a"}, RECALL_AT) == 0.0


def test_precision_only_looks_at_the_first_k() -> None:
    ranked = ["wrong"] * PRECISION_AT + ["right"]
    assert precision_at_k(ranked, {"right"}, PRECISION_AT) == 0.0


def test_recall_counts_every_expected_hit() -> None:
    assert recall_at_k(["a", "b"], {"a", "b", "c"}, RECALL_AT) == pytest.approx(2 / 3)


def test_percentile_is_ordered_and_bounded() -> None:
    values = [10.0, 20.0, 30.0, 40.0]
    assert percentile(values, 0.0) == 10.0
    assert percentile(values, 1.0) == 40.0
    assert percentile([], 0.5) == 0.0


# ── the gate can fail ───────────────────────────────────────────────────────


def _golden() -> GoldenSet:
    golden, _ = load_golden_set()
    return golden


def test_a_perfect_engine_passes_every_target() -> None:
    """The control. If this failed, a failure below would prove nothing."""
    golden = _golden()
    by_query = {query.q: query.relevant for query in golden.queries}
    report = measure(
        golden, "digest", run_query=lambda q: by_query[q], normalization_version="v"
    )
    assert report.passed, report.failures


def test_an_engine_that_finds_nothing_fails_every_target() -> None:
    golden = _golden()
    report = measure(
        golden, "digest", run_query=lambda q: [], normalization_version="v"
    )
    assert not report.passed
    for name in (*SCRIPT_TARGETS, *RESOURCE_TARGETS):
        assert any(name in failure for failure in report.failures), name


def test_one_fuzzy_identifier_hit_fails_outright(monkeypatch) -> None:
    """ADR-053 is a pass/fail rule, not a threshold that can be argued down.

    The near-miss query has no correct answer. An engine returning the *real*
    identifier for it is returning a confident wrong person — the failure the
    exact-match rule exists to prevent — and it must fail the gate even though
    every other query is perfect.
    """
    golden = _golden()
    by_query = {query.q: list(query.relevant) for query in golden.queries}
    near_miss = next(
        query for query in golden.queries if query.identifier and not query.relevant
    )
    by_query[near_miss.q] = ["c_identifier_1"]

    report = measure(
        golden, "digest", run_query=lambda q: by_query[q], normalization_version="v"
    )
    assert not report.passed
    assert near_miss.q in report.identifier_violations
    assert report.identifier_precision == 0.0
    assert any("ADR-053" in failure for failure in report.failures)


def test_a_slow_engine_fails_on_latency(monkeypatch) -> None:
    """The budget is a gate too, not a note in the report."""
    import aegis.search.quality as quality

    ticks = iter(range(0, 10_000))
    monkeypatch.setattr(quality, "perf_counter", lambda: next(ticks))
    golden = _golden()
    by_query = {query.q: query.relevant for query in golden.queries}
    report = measure(
        golden, "digest", run_query=lambda q: by_query[q], normalization_version="v"
    )
    assert not report.passed
    assert any("latency" in failure for failure in report.failures)


# ── the golden set itself ───────────────────────────────────────────────────


def test_the_committed_golden_set_loads() -> None:
    golden, digest = load_golden_set()
    assert len(digest) == 64
    assert golden.queries


def test_every_target_has_a_query_measuring_it() -> None:
    """A number nothing measures is not a gate.

    Enforced by the loader, so a target added to `targets.py` without a query
    fails at load rather than passing silently on an empty bucket.
    """
    golden = _golden()
    for name in SCRIPT_TARGETS:
        assert any(query.script == name for query in golden.queries), name
    for name in RESOURCE_TARGETS:
        assert any(query.resource == name for query in golden.queries), name


def test_a_golden_set_missing_a_target_is_refused(tmp_path) -> None:
    """Non-vacuity for the rule above."""
    path = tmp_path / "partial.json"
    path.write_text(
        """
        {"schema": "aegis.search-golden/v1", "description": "partial",
         "entities": [{"id": "e_1", "type": "person", "label": "Fictional One"}],
         "queries": [{"q": "Fictional One", "script": "latin",
                      "resource": "entity", "relevant": ["e_1"]}]}
        """,
        encoding="utf-8",
    )
    with pytest.raises(QualityError) as excinfo:
        load_golden_set(path)
    assert "sinhala" in str(excinfo.value) or "tamil" in str(excinfo.value)


def test_the_corpus_has_names_that_should_not_match() -> None:
    """Precision needs something to lose.

    A golden set containing only the answers scores 1.0 on everything by
    having nowhere else to go, and measures nothing at all.
    """
    golden = _golden()
    answers = {item for query in golden.queries for item in query.relevant}
    distractors = [
        entity for entity in golden.entities if entity.id not in answers
    ]
    assert len(distractors) >= 10, (
        f"only {len(distractors)} entities are not somebody's answer"
    )


def test_the_golden_set_is_actually_committed() -> None:
    """A gate whose input is not in the repository is not a gate.

    `.gitignore` ignores `*.json` wholesale, so every committed JSON fixture
    needs an explicit negation. Without one this file passes locally — the
    file is right there — and CI fails with "cannot read golden set" on a
    checkout that never had it. The ER golden set needed the same line, which
    is why this test exists for both shapes of the same mistake.
    """
    import subprocess

    from aegis.search.quality import DEFAULT_GOLDEN_SET

    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(DEFAULT_GOLDEN_SET)],
        cwd=DEFAULT_GOLDEN_SET.parents[3],
        capture_output=True,
        text=True,
    )
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", str(DEFAULT_GOLDEN_SET)],
        cwd=DEFAULT_GOLDEN_SET.parents[3],
        capture_output=True,
    )
    assert tracked.returncode == 0 or ignored.returncode != 0, (
        f"{DEFAULT_GOLDEN_SET} is neither tracked nor exempt from .gitignore — "
        "add a `!` negation beside the T26 one, or CI will fail on a checkout "
        "that never received it"
    )


def test_no_fixture_identifier_could_be_a_real_one() -> None:
    """Data ethics, enforced rather than reviewed (`data/real/README.md`)."""
    golden = _golden()
    for claim in golden.claims:
        if claim.predicate == "has_nic":
            assert claim.value and claim.value.startswith("FIXTURE-ID-"), claim.value
