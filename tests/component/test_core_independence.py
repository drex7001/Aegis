"""The core does not import the quarantine (T21, H-36; ADR-023, ADR-024).

"Quarantined" has to mean *the core does not import it*, not merely that the
directory carries a warning README — otherwise a packaged wheel, which ships
``aegis`` and not ``legacy``, is missing code a documented command needs.

ADR-023 exempts exactly two things: one-time migration adapters, and code
already scheduled for deletion.  Both exemptions are enumerated below with the
module that holds them, so an exemption is a line in this file rather than a
habit — a new ``legacy`` import anywhere else fails here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.support.paths import REPO_ROOT

pytestmark = pytest.mark.requirement("Article-XIV", "ADR-023", "H-36", "T21")

AEGIS_ROOT = REPO_ROOT / "aegis"

#: The only modules permitted to import ``legacy.*``, and why.  Both are
#: ADR-023 exemptions; both disappear when their entry in ``legacy/README.md``
#: completes.  Adding to this set is a decision, not a fix.
EXEMPT: dict[str, str] = {
    "aegis/migration/legacy.py": (
        "one-time migration adapter (ADR-023, ADR-016) — reads the curated "
        "prototype corpus once; deleted with the adapters"
    ),
    "aegis/ingestion/service.py": (
        "governed wrapper around the prototype extraction passes — replaced by "
        "extraction v2 (legacy/README.md), not by T21"
    ),
}


def _module_paths() -> list[Path]:
    return sorted(AEGIS_ROOT.rglob("*.py"))


def _legacy_imports(path: Path) -> list[str]:
    """Every ``legacy...`` import in a module, including function-local ones."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split(".")[0] == "legacy"]
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == "legacy":
                found.append(node.module)
    return found


def test_the_core_imports_the_quarantine_only_where_adr_023_exempts_it() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _module_paths():
        relative = path.relative_to(REPO_ROOT).as_posix()
        imports = _legacy_imports(path)
        if imports and relative not in EXEMPT:
            offenders[relative] = imports

    assert not offenders, (
        "aegis must not import legacy.* outside the ADR-023 exemptions; "
        f"found {offenders}. Move the code into the core (H-36) rather than "
        "adding an exemption."
    )


def test_every_exemption_is_still_load_bearing() -> None:
    """An exemption that no longer imports legacy is a stale licence — drop it."""
    stale = [
        module
        for module in EXEMPT
        if not _legacy_imports(REPO_ROOT / module)
    ]
    assert not stale, (
        f"these modules no longer import legacy.*: {stale}. Remove them from "
        "EXEMPT so the next one cannot hide behind the entry."
    )


def test_the_projection_path_is_free_of_the_quarantine() -> None:
    """The specific H-36 finding: `aegis projections rebuild` must stand alone.

    Named separately from the sweep above because this is the command the
    finding was written about, and a future exemption must never quietly
    re-cover it.
    """
    for module in ("projections", "analytics"):
        for path in sorted((AEGIS_ROOT / module).rglob("*.py")):
            assert not _legacy_imports(path), (
                f"{path.relative_to(REPO_ROOT)} imports legacy — the projection "
                "rebuild must not depend on quarantined code (H-36)"
            )


def test_clustering_and_cypher_export_live_in_the_core() -> None:
    """The two algorithms T21 vendored are importable without `legacy` present."""
    from aegis.analytics.clustering import detect_cells
    from aegis.projections.cypher import generate_cypher

    assert detect_cells.__module__ == "aegis.analytics.clustering"
    assert generate_cypher.__module__ == "aegis.projections.cypher"
