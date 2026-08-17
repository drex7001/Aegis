"""Phase 4 is open, and its opening artifact says what T41 promised (T41).

The mirror image of `test_phase_03_exit.py`: that file pins a phase that has
closed and never moves again, this one pins a phase that is *running*. It
therefore asserts two different kinds of thing —

* the **re-validation deliverable** (spec 09 exists and covers the surfaces the
  charter names, every finding tagged P4 is dispositioned, every ADR cited is
  recorded), which is T41's acceptance criterion; and
* the **gate is still open** — no exit criterion may be checked before T53's
  review. ADR-025 makes gate criteria non-deferrable; the failure mode it does
  *not* catch on its own is a checkbox ticked optimistically mid-phase, which
  is what the last test here exists for.

T53 flips the second half and takes over the current-phase status claims, the
way T40 did for Phase 3.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.requirement("ADR-025", "M-01", "H-17", "H-18", "T41")

ROOT = Path(__file__).resolve().parents[2]

#: The 2026-07 external-review findings the charter tags P4. T41 dispositions
#: them; each must be named in spec 09, not merely inherited.
P4_FINDINGS = ("H-17", "H-18", "H-19", "B-11")

#: Divergences T41 found between the pre-authored plan and the P3-as-built
#: system. Each is a decision, so each is an ADR.
T41_ADRS = ("ADR-043", "ADR-044", "ADR-045")


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_spec_09_covers_the_investigation_model_before_any_screen() -> None:
    """H-17's actual complaint: the operational model had no spec at all."""
    spec = _read("speckit/specs/09-investigation-domain.md")

    # The operational half — storage, actions, authorization.
    for heading in (
        "## 2. Cases",
        "## 3. Hypotheses",
        "## 4. Tasks and leads",
        "## 5. Authorization",
    ):
        assert heading in spec, heading
    for table in ("hypothesis_revision", "hypothesis_claim", "investigation_task"):
        assert table in spec, table

    # Model before UI is the point of H-17, so the spec must say so where a
    # reader lands, not only imply it by ordering.
    assert "before** any screen" in spec


def test_spec_09_covers_every_surface_the_generic_object_view_renders() -> None:
    """T41's AC names the surfaces; a spec missing one is a screen nobody specced."""
    spec = _read("speckit/specs/09-investigation-domain.md")
    contract = spec.split("## 6. The object-view contract", maxsplit=1)[1].split(
        "## 7.", maxsplit=1
    )[0]
    for surface in (
        "Title / subtitle",
        "Properties",
        "Links",
        "Sources",
        "Timeline strip",
        "Cases",
    ):
        assert surface in contract, surface
    # Grading and conflict metadata are what make the properties row honest.
    assert "grading dimensions" in contract
    assert "side by side" in contract


def test_every_p4_finding_is_dispositioned_in_spec_09() -> None:
    spec = _read("speckit/specs/09-investigation-domain.md")
    for finding in P4_FINDINGS:
        assert finding in spec, f"{finding} is tagged P4 and spec 09 never mentions it"


def test_the_case_list_is_leak_free_by_construction() -> None:
    """H-18 is the one finding a spec can get *almost* right and still fail.

    Filtering an answer computed from everything leaves a timing and ordering
    signal. Deriving the answer only from readable rows does not. Spec 09 has to
    say the second thing.
    """
    spec = _read("speckit/specs/09-investigation-domain.md")
    section = spec.split("### 6.5", maxsplit=1)[1].split("### 6.6", maxsplit=1)[0]
    assert "derived only from rows the caller can already read" in section
    assert "no total" in section
    assert "ordering by relevance" in section


def test_the_as_of_promise_is_stated_as_narrowed() -> None:
    """B-11 was a promise wider than the time model. It must read narrower now."""
    spec = _read("speckit/specs/09-investigation-domain.md")
    section = spec.split("## 7. Time and as-of", maxsplit=1)[1].split(
        "## 8.", maxsplit=1
    )[0]
    assert "claim-recording snapshot" in section
    assert "does **not** restore" in section
    for stamp in ("as_of", "identity_revision_id", "ontology_version"):
        assert stamp in section, stamp


def test_every_t41_adr_exists_in_the_log() -> None:
    decisions = _read("speckit/decisions.md")
    for adr in T41_ADRS:
        assert f"## {adr}:" in decisions, f"{adr} is cited but not recorded"


def test_t41_divergences_are_cited_where_they_bind() -> None:
    """An ADR nobody references from the spec it corrects is an ADR that rots."""
    spec_09 = _read("speckit/specs/09-investigation-domain.md")
    spec_07 = _read("speckit/specs/07-ui.md")
    tasks = _read("speckit/tasks/phase-04.md")
    for adr in T41_ADRS:
        assert adr in spec_09, adr
        assert adr in tasks, adr
    # ADR-043 and ADR-045 both correct spec 07 specifically.
    assert "ADR-043" in spec_07
    assert "ADR-045" in spec_07


def test_status_surfaces_agree_that_phase_4_is_active() -> None:
    root_readme = _read("README.md")
    kit_readme = _read("speckit/README.md")
    roadmap = _read("speckit/roadmap.md")
    charter = _read("speckit/phases/phase-04-workspace-object-views.md")
    tasks = _read("speckit/tasks/phase-04.md")

    assert "Active phase: Phase 4" in root_readme
    assert "Next phase: Phase 4" not in root_readme
    assert "**ACTIVE**, re-validated by T41" in kit_readme
    assert "P4 workspace v2 & object views [ACTIVE]" in roadmap
    assert "Status: **ACTIVE — opened 2026-08-17**" in charter
    assert "Status: ACTIVE — opened 2026-08-17" in tasks


def test_no_phase_4_gate_criterion_is_checked_before_the_exit_review() -> None:
    """The gate closes at T53 or not at all (ADR-025)."""
    charter = _read("speckit/phases/phase-04-workspace-object-views.md")
    criteria = charter.split("## Exit criteria", maxsplit=1)[1].split(
        "## Risks", maxsplit=1
    )[0]
    assert criteria.count("- [ ]") == 5
    assert "- [x]" not in criteria
    assert not (ROOT / "speckit/reviews/phase-04-exit-review.md").exists()
