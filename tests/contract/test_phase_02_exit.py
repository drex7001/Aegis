"""The Phase 2 release status is one consistent, executable contract (T28)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest


pytestmark = pytest.mark.requirement("ADR-025", "M-01", "T28")

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


def test_status_surfaces_agree_on_the_phase_boundary() -> None:
    root_readme = _read("README.md")
    kit_readme = _read("speckit/README.md")
    roadmap = _read("speckit/roadmap.md")
    phase_2_tasks = _read("speckit/tasks/phase-02.md")
    phase_3_tasks = _read("speckit/tasks/phase-03.md")

    assert "Milestones I and II (Phases 0–2) are complete" in root_readme
    assert "Active phase: Phase 2" not in root_readme
    assert "DONE, ★ MVP gate passed" in kit_readme
    assert "Milestone II — MVP *(complete 2026-07-20)*" in roadmap
    assert "Status: COMPLETE 2026-07-20 — ★ MVP GATE PASSED" in phase_2_tasks
    assert "READY FOR T29 RE-VALIDATION, NOT ACTIVE" in phase_3_tasks


def test_phase_2_release_version_and_tag_are_pinned() -> None:
    project = tomllib.loads(_read("pyproject.toml"))
    lock = tomllib.loads(_read("uv.lock"))
    review = _read("speckit/reviews/phase-02-exit-review.md")
    locked_aegis = [
        package for package in lock["package"] if package["name"] == "aegis"
    ]

    assert project["project"]["version"] == "0.2.0"
    assert len(locked_aegis) == 1
    assert locked_aegis[0]["version"] == "0.2.0"
    assert "`phase-2-mvp`" in review
