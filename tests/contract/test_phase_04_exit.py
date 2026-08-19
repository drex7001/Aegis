"""The Phase 4 release status is one consistent, executable contract (T53).

Mirrors `test_phase_03_exit.py` for the phase that just closed, and takes over
the two claims that belong to whichever phase is *current*: where work is, and
what version the repository is at. `test_phase_04_status.py` — which asserted
the phase was **open** and its gate unchecked — is replaced by this file, the
same way T40 replaced its own opening test.

The gate criteria themselves are proved by their own suites. What this checks is
that the documents agree about what those suites established, which is the
failure mode M-01 was written about: code moves, statuses do not.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.requirement("ADR-025", "M-01", "T53")

ROOT = Path(__file__).resolve().parents[2]

#: T41's divergences. Cited by the review, so each must exist in the log.
T41_ADRS = ("ADR-043", "ADR-044", "ADR-045")


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_every_phase_4_gate_is_checked_and_reviewed() -> None:
    charter = _read("speckit/phases/phase-04-workspace-object-views.md")
    exit_criteria = charter.split("## Exit criteria", maxsplit=1)[1].split(
        "## Risks", maxsplit=1
    )[0]
    review = _read("speckit/reviews/phase-04-exit-review.md")
    reviewed = review.split("## Exit criteria", maxsplit=1)[1].split(
        "## What Phase 4 actually changed", maxsplit=1
    )[0]

    assert "Status: **COMPLETE 2026-08-19" in charter
    assert exit_criteria.count("- [x]") == 5
    assert "- [ ]" not in exit_criteria
    assert reviewed.count("- [x]") == 5
    assert "- [ ]" not in reviewed
    assert "none is deferred or weakened" in review


def test_status_surfaces_agree_on_the_current_phase() -> None:
    root_readme = _read("README.md")
    kit_readme = _read("speckit/README.md")
    roadmap = _read("speckit/roadmap.md")
    phase_4_tasks = _read("speckit/tasks/phase-04.md")

    assert "Phase 4 — investigation workspace v2 & object views — is complete" in root_readme
    assert "Active phase: Phase 4" not in root_readme
    assert "Next phase: Phase 5" in root_readme
    assert "**DONE**, all five gate criteria checked" in kit_readme
    assert "COMPLETE 2026-08-19" in roadmap
    assert "Status: COMPLETE 2026-08-19" in phase_4_tasks


def test_the_roadmap_records_the_capability_as_implemented() -> None:
    """GOAL.md → roadmap coverage (H-35): a delivered row stops saying scheduled."""
    roadmap = _read("speckit/roadmap.md")
    assert (
        "| Investigation workspace, object views, hypotheses, as-of (narrowed) "
        "| **Implemented** P4 |" in roadmap
    )


def test_the_release_version_is_pinned_to_this_phase() -> None:
    project = tomllib.loads(_read("pyproject.toml"))
    lock = tomllib.loads(_read("uv.lock"))
    review = _read("speckit/reviews/phase-04-exit-review.md")
    locked = [package for package in lock["package"] if package["name"] == "aegis"]

    assert project["project"]["version"] == "0.4.0"
    assert len(locked) == 1
    assert locked[0]["version"] == "0.4.0"
    assert "Release: Aegis 0.4.0" in review
    assert "`phase-4-workspace`" in review


def test_the_review_names_its_decisions_and_its_defects() -> None:
    """An exit review that records no discoveries is a review nobody did."""
    review = _read("speckit/reviews/phase-04-exit-review.md")
    for adr in T41_ADRS:
        assert adr in review, adr
    assert "## Defects found and fixed" in review
    assert "## Carryovers" in review
    # The one worth naming: a 401 that had been losing its header since T36.
    assert "WWW-Authenticate" in review


def test_every_phase_4_adr_exists_in_the_log() -> None:
    decisions = _read("speckit/decisions.md")
    for adr in T41_ADRS:
        assert f"## {adr}:" in decisions, f"{adr} is cited but not recorded"


def test_the_analyst_needs_checklist_records_what_was_dropped() -> None:
    """The charter's parity-trap mitigation.

    A checklist that only lists what was built is a wish-list. "We decided not
    to" and "we forgot" look identical a year later, which is why the dropped
    table has to be there.
    """
    checklist = _read("speckit/reviews/phase-04-analyst-needs.md")
    assert "## What was dropped, deliberately" in checklist
    for dropped in ("Cell colouring", "Temporal slider", "Audit console"):
        assert dropped in checklist, dropped
    assert "## Sign-off" in checklist


def test_the_pilot_gate_is_still_open() -> None:
    """Phase 4 authorized no deployment, and no document may imply it did."""
    roadmap = _read("speckit/roadmap.md")
    pilot = roadmap.split("## Pilot gate", maxsplit=1)[1].split("## GOAL.md", maxsplit=1)[0]
    assert "- [x]" not in pilot
    assert "- [ ]" in pilot

    review = _read("speckit/reviews/phase-04-exit-review.md")
    assert "## Deployment boundary" in review
    assert "may be represented as pilot-ready" in review


def test_the_opening_status_test_was_replaced_not_kept() -> None:
    """`test_phase_04_status.py` asserted the gate was **unchecked**.

    Keeping it would mean two files disagreeing about the same phase — exactly
    the rot this suite exists to prevent — so T53 replaces it, as T40 did.
    """
    assert not (ROOT / "tests/contract/test_phase_04_status.py").exists()
