"""The workspace's screens are generated from the ontology, not written (T42).

ADR-043 makes `ui/src/api/ontology.ts` the object-view descriptor. The claim
that buys is narrow and testable: **no file a human edits under `ui/src` may
name a domain type, predicate or category.** If one does, adding a type to a
domain module stops being enough, and Article XI's "single domain artifact"
becomes a slogan.

`tests/contract/test_ontology_change_flow.py` sweeps for one predicate
(`controls`, T39's proof). This sweeps for **all** of them, which is the T42
acceptance criterion, and it grows by itself: a name added to a domain module
is a name this test starts looking for.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from aegis.ontology import load
from aegis.ontology.modules import compose
from tests.support.paths import ONTOLOGY_PATH, REPO_ROOT

pytestmark = pytest.mark.requirement("Article-XI", "Article-XIV", "ADR-043", "T42")

UI_SRC = REPO_ROOT / "ui" / "src"

#: Written by `aegis ontology generate` and by `openapi-typescript`. Exempt
#: because regenerating them is the only way to change them — which is the
#: distinction Article XI actually draws (ADR-043), not "no domain word anywhere".
GENERATED = {
    UI_SRC / "api" / "ontology.ts",
    UI_SRC / "api" / "schema.d.ts",
}


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def domain_names(ontology) -> list[str]:
    """Every name a *domain* module declares.

    Platform names are excluded on purpose: `open`, `restricted` and the
    grading vocabulary are core epistemics (Article XIV), and a workspace is
    allowed to know that a handling code exists. What it may not know is what a
    `person` is.
    """
    composed = compose(ONTOLOGY_PATH)
    domain_modules = {
        name for name, info in composed.modules.items() if name != "platform"
    }
    return sorted(
        name
        for name, owner in composed.owners.items()
        if owner in domain_modules
    )


def _sources() -> list[Path]:
    return [
        path
        for path in sorted(UI_SRC.rglob("*.ts*"))
        if path not in GENERATED
    ]


def test_the_sweep_has_something_to_look_for(domain_names: list[str]) -> None:
    """A sweep over an empty list passes for the wrong reason."""
    assert len(domain_names) > 20
    assert "person" in domain_names
    assert "member_of" in domain_names


def test_no_hand_written_source_names_a_domain_type_or_predicate(
    domain_names: list[str],
) -> None:
    # Quoted, like the T39 sweep: a bare substring also matches English prose
    # and identifiers such as `window.location`, and reporting those would teach
    # the next reader to ignore this test.
    patterns = {name: re.compile(rf"""["']{re.escape(name)}["']""") for name in domain_names}
    offenders: list[str] = []
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        for name, pattern in patterns.items():
            if pattern.search(text):
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {name!r}")
    assert offenders == [], (
        "hand-written domain vocabulary in the workspace — these names must come "
        f"from the generated descriptors (ADR-043): {offenders}"
    )


def test_the_navigation_reads_the_descriptors(domain_names: list[str]) -> None:
    """And reads them *generically* — the rail must iterate, not enumerate."""
    rail = (UI_SRC / "layout" / "OntologyNav.tsx").read_text(encoding="utf-8")
    assert "OBJECT_TYPES" in rail
    assert "INTERFACES" in rail
    assert "Object.keys(OBJECT_TYPES)" in rail
    assert "Object.keys(INTERFACES)" in rail


def test_the_object_type_screen_reads_the_descriptors() -> None:
    view = (UI_SRC / "views" / "ObjectTypeView.tsx").read_text(encoding="utf-8")
    # The four descriptor fields spec 09 §6.2 exists to supply.
    for field in ("display", "properties", "sensitivity", "conflicts"):
        assert field in view, field
    assert "PREDICATES" in view
    assert "CATEGORIES" in view


def test_the_version_banner_compares_bundle_against_server() -> None:
    """Spec 09 §6.3: the one thing a compiled-in descriptor cannot know."""
    banner = (UI_SRC / "layout" / "VersionBanner.tsx").read_text(encoding="utf-8")
    assert "ONTOLOGY_VERSION" in banner
    assert "getVocabulary" in banner


def test_the_generated_descriptors_carry_what_the_screens_need(ontology) -> None:
    """Read from disk rather than regenerated: the committed file is what ships.

    `test_ontology_generate.py` proves the generator emits these; this proves
    the file the bundle imports actually has them, which is a different failure
    (a stale commit) with the same symptom (a blank screen).
    """
    constants = (UI_SRC / "api" / "ontology.ts").read_text(encoding="utf-8")
    for name, spec in ontology.object_types.items():
        entry = next(
            (l for l in constants.splitlines() if l.strip().startswith(f'"{name}":')), None
        )
        assert entry is not None, name
        assert "display: " in entry, name
        for prop in spec.properties:
            assert f'"{prop}": {{ label: ' in entry, f"{name}.{prop}"
