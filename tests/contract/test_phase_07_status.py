"""Phase 7 is open, and the documents that say so agree (T78).

Takes over the "where work is" claim from `test_phase_06_exit.py`, which is the
hand-off that file's docstring describes: a test asserting "the current phase is
N" belongs to exactly one module at a time, because two modules claiming it is
how they come to disagree. The **release version** claim stays with Phase 6
until Phase 7 ships one; this module asserts only that it has not moved yet.

The rest is T78's own acceptance criteria as executable checks: the specs it
authored exist and are final, the decisions they cite are recorded, and the
read-surface inventory covers every read route the application actually serves.
That last one is the point of the whole task — a guarantee about "every surface"
is worth exactly as much as the list of surfaces, and a list maintained by
reading the interesting ones goes stale on the next PR.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.requirement("ADR-025", "M-01", "M-20", "T78")

ROOT = Path(__file__).resolve().parents[2]

#: The decisions T78 took. Each is cited by spec 03 or spec 13.
PHASE_7_ADRS = tuple(f"ADR-{n:03d}" for n in range(61, 67))

#: Read routes that return no records and therefore need no inventory row.
#: Each is listed with the reason it is exempt, so an exemption is a decision
#: somebody made rather than a name that happened not to match.
NON_RECORD_ROUTES = {
    "/v1/ontology": "schema, not content",
}


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _route_families() -> set[str]:
    """`/v1/entities/{id}/cases` -> `/v1/entities`, over every GET operation."""
    document = json.loads(_read("ui/openapi.json"))
    families = set()
    for path, operations in document["paths"].items():
        if "get" not in operations:
            continue
        segments = [segment for segment in path.split("/") if segment]
        families.add("/" + "/".join(segments[:2]))
    return families


def test_status_surfaces_agree_that_phase_7_is_open() -> None:
    root_readme = _read("README.md")
    roadmap = _read("speckit/roadmap.md")
    charter = _read("speckit/phases/phase-07-sharing-governance.md")
    tasks = _read("speckit/tasks/phase-07.md")

    assert "Phase 7 — sharing & governance hardening — is under way" in root_readme
    assert "P7 sharing & governance [ACTIVE]" in roadmap
    assert "Status: **ACTIVE from 2026-08-24**" in charter
    assert "Status: ACTIVE from 2026-08-24." in tasks
    # The phase that closed stays closed.
    assert "P6 search, object sets & analytics [COMPLETE]" in roadmap


def test_the_release_version_has_not_moved_yet() -> None:
    """Phase 6 shipped 0.6.0; Phase 7 bumps it at T89, not before."""
    project = tomllib.loads(_read("pyproject.toml"))
    assert project["project"]["version"] == "0.6.0"


def test_the_specs_t78_owed_exist_and_are_final() -> None:
    disclosure = _read("speckit/specs/13-disclosure-packages.md")
    security = _read("speckit/specs/03-security.md")

    assert "Status: **final** (authored 2026-08-24 by T78" in disclosure
    assert "## 0. What re-validation changed" in disclosure
    # specs/03 §4 stops describing field filtering as owed work.
    assert "shipped at P2 T24a" in security
    for heading in (
        "## 6. Response modes",
        "## 7. Compartments",
        "## 8. Judicial states",
        "## 9. The precedence matrix",
        "## 10. Break-glass",
        "## 12. The read-surface inventory",
        "## 13. Governance enforcement",
    ):
        assert heading in security, heading


def test_every_phase_7_adr_exists_in_the_log() -> None:
    decisions = _read("speckit/decisions.md")
    for adr in PHASE_7_ADRS:
        assert f"## {adr}:" in decisions, f"{adr} is cited but not recorded"


def test_the_divergence_table_dispositions_every_finding_tagged_p7() -> None:
    """The charter names eight findings T78 must disposition; none may vanish."""
    disclosure = _read("speckit/specs/13-disclosure-packages.md")
    security = _read("speckit/specs/03-security.md")
    both = disclosure + security
    for finding in ("B-08", "H-25", "H-26", "H-27", "H-28", "M-14", "M-20", "M-21"):
        assert finding in both, f"{finding} is tagged P7 and is dispositioned nowhere"


def test_every_read_route_is_registered_in_the_inventory() -> None:
    """M-20's inventory is only worth its accuracy.

    T88 strengthens this into the full exclusion matrix. Here it is the weaker
    claim that already pays for itself: a read route the inventory has never
    heard of cannot be reasoned about, and adding one must not be silent.
    """
    inventory = _read("speckit/specs/03-security.md").split(
        "### 12.1 API read surfaces", maxsplit=1
    )[1].split("### 12.2", maxsplit=1)[0]

    missing = sorted(
        family
        for family in _route_families()
        if family not in NON_RECORD_ROUTES and family not in inventory
    )
    assert not missing, (
        f"read surfaces absent from specs/03 §12.1: {missing} — register them "
        "in the inventory (and in T88's matrix) rather than deleting this test"
    )


def test_the_exempt_routes_are_still_exempt_for_the_stated_reason() -> None:
    """An exemption list nobody re-checks is how the first leak gets in.

    T79 rewrote §12.1 and this assertion moved with it — which is the test
    doing its job: the exemption has to be restated in the inventory every time
    the inventory is rewritten, or it stops being a decision and becomes an
    omission.
    """
    assert NON_RECORD_ROUTES.keys() <= _route_families()
    inventory = _read("speckit/specs/03-security.md")
    # The inventory names the route, and says why it is exempt.
    assert "`GET /v1/ontology/vocabulary` is the one read route with **no**" in inventory
    assert "it returns the schema, which every caller may read" in inventory
