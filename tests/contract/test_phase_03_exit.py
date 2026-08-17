"""The Phase 3 release status is one consistent, executable contract (T40).

Mirrors `test_phase_02_exit.py` for the phase that just closed, and takes over
the two claims that belong to whichever phase is *current*: where work is, and
what version the repository is at. Keeping those in the P2 file meant every
later phase had to edit a test named for an earlier one.

The gate criteria themselves are proved by their own suites — this file checks
that the documents agree about what those suites established, which is the
failure mode M-01 was written about: code moves, statuses do not.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.requirement("ADR-025", "M-01", "T40")

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_every_phase_3_gate_is_checked_and_reviewed() -> None:
    charter = _read("speckit/phases/phase-03-ontology-v2.md")
    exit_criteria = charter.split("## Exit criteria", maxsplit=1)[1].split(
        "## Risks", maxsplit=1
    )[0]
    review = _read("speckit/reviews/phase-03-exit-review.md")
    reviewed = review.split("## Exit criteria", maxsplit=1)[1].split(
        "## What Phase 3 actually changed", maxsplit=1
    )[0]

    assert "Status: **COMPLETE 2026-08-17" in charter
    assert exit_criteria.count("- [x]") == 5
    assert "- [ ]" not in exit_criteria
    assert reviewed.count("- [x]") == 5
    assert "- [ ]" not in reviewed
    assert "none is deferred or weakened" in review


def test_status_surfaces_agree_on_the_current_phase() -> None:
    root_readme = _read("README.md")
    kit_readme = _read("speckit/README.md")
    roadmap = _read("speckit/roadmap.md")
    phase_3_tasks = _read("speckit/tasks/phase-03.md")

    assert "Phase 3 — ontology modules and contracts — is complete" in root_readme
    assert "Active phase: Phase 3" not in root_readme
    assert "Next phase: Phase 4" in root_readme
    assert "**DONE**, all five gate criteria checked" in kit_readme
    assert "COMPLETE 2026-08-17" in roadmap
    assert "Status: COMPLETE 2026-08-17" in phase_3_tasks


def test_the_roadmap_records_the_capability_as_implemented() -> None:
    """GOAL.md → roadmap coverage (H-35): a delivered row stops saying scheduled."""
    roadmap = _read("speckit/roadmap.md")
    assert "| Ontology modules, interfaces, typed clients | **Implemented** P3 |" in roadmap


def test_the_release_version_is_pinned_to_this_phase() -> None:
    project = tomllib.loads(_read("pyproject.toml"))
    lock = tomllib.loads(_read("uv.lock"))
    review = _read("speckit/reviews/phase-03-exit-review.md")
    locked = [package for package in lock["package"] if package["name"] == "aegis"]

    assert project["project"]["version"] == "0.3.0"
    assert len(locked) == 1
    assert locked[0]["version"] == "0.3.0"
    assert "Release: Aegis 0.3.0" in review
    assert "`phase-3-ontology-modules`" in review


def test_the_review_names_its_decisions_and_its_defects() -> None:
    """An exit review that records no discoveries is a review nobody did.

    Phase 3 appended six ADRs and fixed three defects it did not set out to
    look for; a review that omitted either would be the "speckit rots as code
    diverges" risk the roadmap names.
    """
    review = _read("speckit/reviews/phase-03-exit-review.md")
    for adr in ("ADR-037", "ADR-038", "ADR-039", "ADR-040", "ADR-041", "ADR-042"):
        assert adr in review, adr
    assert "## Defects found and fixed" in review
    assert "## Carryovers" in review


def test_every_phase_3_adr_exists_in_the_log() -> None:
    decisions = _read("speckit/decisions.md")
    for adr in ("ADR-037", "ADR-038", "ADR-039", "ADR-040", "ADR-041", "ADR-042"):
        assert f"## {adr}:" in decisions, f"{adr} is cited but not recorded"


def test_the_pilot_gate_is_still_open() -> None:
    """Phase 3 authorized no deployment, and the roadmap must not imply it did."""
    roadmap = _read("speckit/roadmap.md")
    pilot = roadmap.split("## Pilot gate", maxsplit=1)[1].split("## GOAL.md", maxsplit=1)[0]
    assert "- [x]" not in pilot
    assert "- [ ]" in pilot
    assert "may not be represented as pilot-ready" in _read(
        "speckit/reviews/phase-02-exit-review.md"
    )
