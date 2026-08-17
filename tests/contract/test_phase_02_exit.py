"""The Phase 2 release status is one consistent, executable contract (T28)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest


pytestmark = pytest.mark.requirement("ADR-025", "M-01", "T28", "T29")

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_every_phase_2_gate_is_checked_and_reviewed() -> None:
    charter = _read("speckit/phases/phase-02-mvp-identity-provenance.md")
    exit_criteria = charter.split("## Exit criteria", maxsplit=1)[1].split(
        "## Risks", maxsplit=1
    )[0]
    review = _read("speckit/reviews/phase-02-exit-review.md")
    reviewed_gates = review.split(
        "## MVP gate — non-deferrable criteria", maxsplit=1
    )[1].split("## Constitution conformance", maxsplit=1)[0]

    assert "Status: **COMPLETE 2026-07-20 — ★ MVP GATE PASSED**" in charter
    assert exit_criteria.count("- [x]") == 5
    assert "- [ ]" not in exit_criteria
    assert reviewed_gates.count("- [x]") == 5
    assert "- [ ]" not in reviewed_gates
    assert "none is deferred or weakened" in review


def test_phase_2_status_surfaces_still_agree() -> None:
    """Phase 2's own boundary, which never moves again.

    Scoped to P2's immutable facts. The *current* phase's status and release
    version live in that phase's own exit test — this one used to assert both,
    which meant every later phase had to edit a file named for an earlier one.
    """
    root_readme = _read("README.md")
    kit_readme = _read("speckit/README.md")
    roadmap = _read("speckit/roadmap.md")
    phase_2_tasks = _read("speckit/tasks/phase-02.md")

    assert "Milestones I and II (Phases 0–2) are complete" in root_readme
    assert "Active phase: Phase 2" not in root_readme
    assert "DONE, ★ MVP gate passed" in kit_readme
    assert "Milestone II — MVP *(complete 2026-07-20)*" in roadmap
    assert "Status: COMPLETE 2026-07-20 — ★ MVP GATE PASSED" in phase_2_tasks


def test_phase_2_release_tag_is_pinned() -> None:
    """0.2.0 was P2's release; the repository has moved on, the review has not."""
    review = _read("speckit/reviews/phase-02-exit-review.md")
    assert "Release: Aegis 0.2.0" in review
    assert "`phase-2-mvp`" in review
