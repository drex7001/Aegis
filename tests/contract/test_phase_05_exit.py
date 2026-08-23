"""The Phase 5 release status is one consistent, executable contract (T65).

Mirrors `test_phase_04_exit.py` for the phase that just closed.

**The two current-phase claims moved on at T77** — where work is, and what
version the repository is at — and now live in `test_phase_06_exit.py`. That
hand-off is the pattern: T40 gave them to T53, T53 to this file, this file to
T77. It exists because a test asserting "the current phase is N" belongs to
exactly one file at a time, and two files claiming it is how they come to
disagree. What stays here is what stays true about Phase 5 forever.

The gate criteria themselves are proved by their own suites; this checks that
the documents agree about what those suites established (M-01: code moves,
statuses do not).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from packaging.version import Version

pytestmark = pytest.mark.requirement("ADR-025", "M-01", "T65")

ROOT = Path(__file__).resolve().parents[2]

#: T54's divergences. Cited by the review, so each must exist in the log.
T54_ADRS = ("ADR-046", "ADR-047", "ADR-048", "ADR-049")


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_every_phase_5_gate_is_checked_and_reviewed() -> None:
    charter = _read("speckit/phases/phase-05-events-geo-time.md")
    exit_criteria = charter.split("## Exit criteria", maxsplit=1)[1].split(
        "## Risks", maxsplit=1
    )[0]
    review = _read("speckit/reviews/phase-05-exit-review.md")
    reviewed = review.split("## Exit criteria", maxsplit=1)[1].split(
        "## What Phase 5 actually changed", maxsplit=1
    )[0]

    assert "Status: **COMPLETE 2026-08-23**" in charter
    assert exit_criteria.count("- [x]") == 5
    assert "- [ ]" not in exit_criteria
    assert reviewed.count("- [x]") == 5
    assert "- [ ]" not in reviewed
    assert "none is deferred or weakened" in review


def test_phase_5_stays_closed() -> None:
    """What remains here after the hand-off: Phase 5's own status, forever.

    The *current*-phase half of this claim went to `test_phase_06_exit.py`;
    "Phase 5 is complete" is not a claim about the present and does not move.
    """
    roadmap = _read("speckit/roadmap.md")
    phase_5_tasks = _read("speckit/tasks/phase-05.md")

    assert "COMPLETE 2026-08-23" in roadmap
    assert "Status: COMPLETE 2026-08-23" in phase_5_tasks


def test_the_roadmap_records_the_capability_as_implemented() -> None:
    """GOAL.md → roadmap coverage (H-35): a delivered row stops saying scheduled."""
    roadmap = _read("speckit/roadmap.md")
    assert (
        "| Events, geospatial, timeline, map privacy | **Implemented** P5 |" in roadmap
    )


def test_the_version_phase_5_shipped_is_still_recorded() -> None:
    """The *repository's* version moved to `test_phase_06_exit.py` at T77.

    What does not move is what Phase 5 released, which its own review states —
    and the monotonicity the hand-off is supposed to preserve.
    """
    project = tomllib.loads(_read("pyproject.toml"))
    review = _read("speckit/reviews/phase-05-exit-review.md")

    assert "Release: Aegis 0.5.0" in review
    assert "`phase-5-events-geo`" in review
    # Never backwards. The next phase's exit test owns the exact value.
    assert Version(project["project"]["version"]) >= Version("0.5.0")


def test_the_review_names_its_decisions_and_its_defects() -> None:
    """An exit review that records no discoveries is a review nobody did."""
    review = _read("speckit/reviews/phase-05-exit-review.md")
    for adr in T54_ADRS:
        assert adr in review, adr
    assert "## Defects and gaps found" in review
    assert "## Carryovers" in review
    # The two worth naming: an extension the charter believed already existed,
    # and a staleness check that cannot see the staleness this phase creates.
    assert "CREATE EXTENSION postgis" in review
    assert "is_stale" in review


def test_every_phase_5_adr_exists_in_the_log() -> None:
    decisions = _read("speckit/decisions.md")
    for adr in T54_ADRS:
        assert f"## {adr}:" in decisions, f"{adr} is cited but not recorded"


def test_the_migration_list_is_dispositioned_in_writing() -> None:
    """T63's actual deliverable: a decision, not a script.

    §2.4 enumerated every predicate; a phase that ran the migration without
    recording why the others were kept would leave the next reader re-deriving
    a judgement that was already made.
    """
    dispositions = _read("speckit/reviews/phase-05-migration-dispositions.md")
    assert "## The one migration" in dispositions
    assert "co_arrested_with" in dispositions
    # The five that meet the rule and wait for their event type. Recorded so a
    # future phase inherits a decision rather than re-deriving one.
    for flagged in (
        "masterminded_attack_with",
        "co_attacker_with",
        "ordered_killing_of",
        "killed_family_of",
        "tipped_off_police_on",
    ):
        assert flagged in dispositions, flagged
    # ...and the standing decision that outlives the phase.
    assert "No automatic pairwise derivation" in dispositions


def test_the_claims_first_boundary_is_stated_as_binding() -> None:
    """B-13, in the documents as well as in the schema.

    The schema sweep (`test_geometry_lives_only_in_the_projection`) proves it
    holds today. This proves the *rule* survived the phase — that nobody quietly
    softened "no canonical event table" into "no canonical event table yet".
    """
    spec = _read("speckit/specs/10-events-geospatial.md")
    review = _read("speckit/reviews/phase-05-exit-review.md")
    assert "**The storage rule (B-13, binding).**" in spec
    assert "requires an Article I amendment first" in spec
    assert "no canonical event table" in review


def test_the_pilot_gate_is_still_open() -> None:
    """Phase 5 authorized no deployment, and no document may imply it did."""
    roadmap = _read("speckit/roadmap.md")
    pilot = roadmap.split("## Pilot gate", maxsplit=1)[1].split("## GOAL.md", maxsplit=1)[0]
    assert "- [x]" not in pilot
    assert "- [ ]" in pilot

    review = _read("speckit/reviews/phase-05-exit-review.md")
    assert "## Deployment boundary" in review
    assert "may be represented as pilot-ready" in review
    # The map is the one thing in this phase that could have widened the
    # boundary, and it narrows it instead (M-19).
    assert "contacts no external service" in review
