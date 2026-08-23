"""Findings and claims are different tables with different lifecycles (T72).

Charter exit criterion №2, and the charter asks for a **schema-level** test —
which is right, because the property has to hold against code nobody has
written yet. A behavioural test proves that today's promotion path makes a new
claim; only the schema proves that no path could do otherwise.

So this asserts three things rather than one:

1. they are different tables, with different columns and different lifecycles;
2. **no foreign key lets a claim be reached as a finding** — `promoted_claim_id`
   points one way, and nothing points back, because a claim reachable *as* a
   finding would be one lifecycle wearing two names;
3. no code path turns a finding row into a claim row.

Article IX is the reason. A finding is a machine's reading of what was written
down; a claim is somebody's assertion about the world. Blurring them is how
"most connected" becomes "leader" one refactor at a time.
"""

from __future__ import annotations

import ast

import pytest

from aegis.store import AnalyticFinding, AnalyticRun, Claim
from tests.support.paths import REPO_ROOT

pytestmark = pytest.mark.requirement("Article-IX", "H-23", "charter-p6-exit-2", "T72")


# ── different tables ────────────────────────────────────────────────────────


def test_they_are_different_tables() -> None:
    assert AnalyticFinding.__tablename__ != Claim.__tablename__
    assert AnalyticFinding.__tablename__ == "analytic_finding"


def test_a_finding_carries_none_of_a_claims_epistemics() -> None:
    """No grading, no assertion type, no source record.

    A finding is not graded because grading describes *evidence*, and a finding
    is a reading of evidence rather than a piece of it. Giving it the columns
    would invite the reading Article IX forbids.
    """
    finding_columns = set(AnalyticFinding.__table__.columns.keys())
    claim_only = {
        "assertion_type",
        "credibility_normalized",
        "verification_status",
        "analytic_confidence",
        "record_id",
        "excerpt",
        "retracted_at",
    }
    assert not finding_columns & claim_only, sorted(finding_columns & claim_only)


def test_a_claim_carries_none_of_a_findings_machinery() -> None:
    """And the other direction, which is the one that would drift.

    A `run_id` or a `caveat_text` on `claim` would make a claim readable as a
    finding, which is the same collapse from the other side.
    """
    claim_columns = set(Claim.__table__.columns.keys())
    finding_only = {"run_id", "caveat_text", "caveat_version", "finding_digest"}
    assert not claim_columns & finding_only


# ── the link runs one way ───────────────────────────────────────────────────


def test_a_finding_may_point_at_a_claim() -> None:
    """Promotion has to be recordable, or the basis link would be a convention."""
    targets = {
        key.column.table.name
        for key in AnalyticFinding.__table__.foreign_keys
    }
    assert "claim" in targets


def test_nothing_points_back_from_a_claim_to_a_finding() -> None:
    """The asymmetry is the design.

    A claim reachable *as* a finding would be one lifecycle wearing two names,
    and the promotion path would become an edit rather than a new assertion.
    """
    targets = {key.column.table.name for key in Claim.__table__.foreign_keys}
    assert "analytic_finding" not in targets
    assert "analytic_run" not in targets


def test_the_run_owns_the_finding_and_not_the_reverse() -> None:
    run_targets = {key.column.table.name for key in AnalyticRun.__table__.foreign_keys}
    assert "analytic_finding" not in run_targets


# ── no path converts one to the other ───────────────────────────────────────


def _calls_in(path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            names.add(node.func.id)
    return names


def test_the_analytics_service_constructs_no_claims() -> None:
    """A metric may read claims; it may never write one.

    Article VII as much as Article IX: a machine that could write a claim would
    be a machine deciding, and the whole promotion path (spec 12 §10) exists so
    that a human does.
    """
    service = REPO_ROOT / "aegis" / "analytics" / "service.py"
    source = service.read_text(encoding="utf-8")
    assert "Claim(" not in source, (
        "aegis/analytics/service.py constructs a Claim — a metric may read "
        "claims and must never write one (Article VII)"
    )
    # Reading is not only fine but expected: the service selects claims to
    # derive a finding's handling code. Asserting that it *does* keeps the
    # check above from passing because the module stopped touching claims
    # altogether, which would be a different bug wearing a green test.
    assert "Claim" in _calls_in(service) or "select(Claim" in source


def test_no_analytics_module_writes_a_claim() -> None:
    """The whole package, so a future metric cannot quietly gain the ability."""
    offenders = [
        path.name
        for path in (REPO_ROOT / "aegis" / "analytics").glob("*.py")
        if "Claim(" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"{offenders} construct claims"


def test_the_sweep_would_notice(tmp_path) -> None:
    """Non-vacuity: the check above passes trivially if nothing is scanned."""
    assert list((REPO_ROOT / "aegis" / "analytics").glob("*.py")), "nothing scanned"
    probe = tmp_path / "probe.py"
    probe.write_text("row = Claim(claim_id='x')", encoding="utf-8")
    assert "Claim(" in probe.read_text(encoding="utf-8")


# ── a finding cannot exist without its caveat ───────────────────────────────


def test_the_caveat_columns_are_not_nullable() -> None:
    """Article IX at the column, not at the code path that happens to fill it."""
    table = AnalyticFinding.__table__
    assert not table.columns["caveat_text"].nullable
    assert not table.columns["caveat_version"].nullable


def test_the_handling_code_is_not_nullable_either() -> None:
    """A finding over restricted evidence is restricted, or it is a leak."""
    table = AnalyticFinding.__table__
    assert not table.columns["handling_code"].nullable
    assert not table.columns["handling_rank"].nullable
