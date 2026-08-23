"""The Phase 6 release status is one consistent, executable contract (T77).

Mirrors `test_phase_05_exit.py` for the phase that just closed, and **takes over
the two claims that belong to whichever phase is current**: where work is, and
what version the repository is at. That hand-off is the pattern — T40 gave them
to T53, T53 to T65, T65 to this file — and it exists because a test asserting
"the current phase is N" belongs to exactly one file at a time. Two files
claiming it is how they come to disagree.

The gate criteria themselves are proved by their own suites; this checks that
the documents agree about what those suites established (M-01: code moves,
statuses do not).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from packaging.version import Version

pytestmark = pytest.mark.requirement("ADR-025", "M-01", "T77")

ROOT = Path(__file__).resolve().parents[2]

#: The phase's decisions. Cited by the review, so each must exist in the log.
PHASE_6_ADRS = tuple(f"ADR-{n:03d}" for n in range(50, 61))

#: The three corrections that came from *building* what a spec described. They
#: are the phase's most valuable output and the easiest thing for a later
#: summary to quietly drop, so the review is required to name each one.
CORRECTIONS = ("ADR-058", "ADR-059", "ADR-060")


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_every_phase_6_gate_is_checked_and_reviewed() -> None:
    charter = _read("speckit/phases/phase-06-search-object-sets-analytics.md")
    exit_criteria = charter.split("## Exit criteria", maxsplit=1)[1].split(
        "## Risks", maxsplit=1
    )[0]
    review = _read("speckit/reviews/phase-06-exit-review.md")

    # Non-deferrable (ADR-025): every box ticked, none left open.
    assert "- [ ]" not in exit_criteria
    assert exit_criteria.count("- [x]") == 4
    assert "**PASS — Phase 6 is complete.**" in review


def test_status_surfaces_agree_on_the_current_phase() -> None:
    """The claim this file takes over from `test_phase_05_exit.py`."""
    root_readme = _read("README.md")
    kit_readme = _read("speckit/README.md")
    roadmap = _read("speckit/roadmap.md")
    phase_6_tasks = _read("speckit/tasks/phase-06.md")

    assert "Phase 6 — search, object sets & governed analytics — is complete" in root_readme
    assert "Next phase: Phase 7" in root_readme
    assert "**DONE**, all four gate criteria checked" in kit_readme
    assert "COMPLETE 2026-08-24" in roadmap
    assert "Status: COMPLETE, closed 2026-08-24" in phase_6_tasks


def test_the_roadmap_records_the_capability_as_implemented() -> None:
    """GOAL.md → roadmap coverage (H-35): a delivered row stops saying scheduled."""
    roadmap = _read("speckit/roadmap.md")
    assert (
        "| Search, object sets, analytics, watchlists/alert triage | "
        "**Implemented** P6 |" in roadmap
    )


def test_the_release_version_is_the_one_this_phase_shipped() -> None:
    """The second claim taken over from `test_phase_05_exit.py`."""
    project = tomllib.loads(_read("pyproject.toml"))
    lock = tomllib.loads(_read("uv.lock"))
    review = _read("speckit/reviews/phase-06-exit-review.md")
    locked = [package for package in lock["package"] if package["name"] == "aegis"]

    assert project["project"]["version"] == "0.6.0"
    assert len(locked) == 1
    assert locked[0]["version"] == "0.6.0"
    assert "Release: Aegis 0.6.0" in review
    assert "`phase-6-search-analytics`" in review
    # The version only ever goes up, which the next phase's exit test inherits
    # when this one hands the claim over.
    assert Version(project["project"]["version"]) > Version("0.5.0")


def test_every_phase_6_adr_exists_in_the_log() -> None:
    decisions = _read("speckit/decisions.md")
    for adr in PHASE_6_ADRS:
        assert f"## {adr}:" in decisions, f"{adr} is cited but not recorded"


def test_the_review_names_its_decisions_and_its_defects() -> None:
    """An exit review that records no discoveries is a review nobody did."""
    review = _read("speckit/reviews/phase-06-exit-review.md")
    for adr in CORRECTIONS:
        assert adr in review, adr
    assert "## Defects and gaps found" in review
    # The three that would be most tempting to leave out, because each is an
    # admission rather than an achievement.
    assert "third" in review  # the authorization hole's third appearance
    assert "no test of any kind" in review  # shared_identifier had none
    assert "no python linter" in review.lower()


def test_the_opensearch_trigger_is_recorded_with_its_numbers() -> None:
    """The AC says the measured numbers are recorded *whether or not it fired*.

    "We measured and Postgres held" is a result worth keeping, and a review that
    only recorded triggers when they fired would make every quiet phase
    indistinguishable from an unmeasured one.
    """
    review = _read("speckit/reviews/phase-06-exit-review.md")
    spec = _read("speckit/specs/11-search.md")

    assert "did not fire" in review
    # The number it failed at first, and the number the tuning attempt reached.
    # Both, because the second alone would read as though it always passed.
    assert "0.375" in review and "0.750" in review
    assert "documented tuning attempt" in spec
    # And the honest limits on the fix.
    assert "eight pairs" in review
    assert "OpenSearch would not have helped" in review


def test_the_authorization_rule_is_stated_as_binding() -> None:
    """B-17, in the documents as well as in the queries.

    The suites prove it holds today. This proves the *rule* survived the phase —
    that nobody softened "absent from the scan" into "filtered from the answer"
    while writing three modules that had to obey it.
    """
    spec = _read("speckit/specs/11-search.md")
    review = _read("speckit/reviews/phase-06-exit-review.md")
    assert "absent from the scan" in spec
    assert "absent from the scan" in review


def test_the_pilot_gate_is_still_open() -> None:
    """Phase 6 authorized no deployment, and no document may imply it did."""
    roadmap = _read("speckit/roadmap.md")
    pilot = roadmap.split("## Pilot gate", maxsplit=1)[1].split("## GOAL.md", maxsplit=1)[0]
    assert "- [x]" not in pilot
    assert "- [ ]" in pilot

    review = _read("speckit/reviews/phase-06-exit-review.md")
    assert "## Deployment boundary" in review
    # Search and watchlists both make the gate matter *more*, and the review is
    # required to say so rather than to note the boundary and move on.
    assert "the fastest way to learn what a corpus contains" in review
