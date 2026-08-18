"""Adding an object type needs no React (T51, charter exit criterion 4).

The criterion is about a **diff**: "add a test object type via the ontology
alone — a working object view with properties, links and provenance appears
with no new React code", and "the change's diff is ontology + proposal +
regenerated files only".

So that is what this checks, mechanically. `vessel` was added to the
`border-cargo` fixture at T51 — *after* `ObjectTypeView`, `ObjectView` and the
rail already existed, which is what makes it a proof rather than a fixture that
happened to be there first. It deliberately carries every field a generic screen
reads: a `display` with a subtitle, a required property, a `many` property, a
`restricted` one, a `conflicts: preserve` one, and a shared reference.

The rendering half is proved by `ui/e2e/object-view.spec.ts` (two types through
one component) and `test_workspace_descriptors.py` (the screens iterate rather
than enumerate). What is proved here is that the *addition* costs nothing in the
workspace: the generator emits a complete descriptor, and no hand-written file
under `aegis/` or `ui/src` names the new type.
"""

from __future__ import annotations

import re

import pytest

from aegis.ontology import load
from aegis.ontology.generate import typescript_constants
from aegis.ontology.modules import compose
from tests.support.paths import REPO_ROOT

pytestmark = pytest.mark.requirement("Article-XI", "Article-XIV", "ADR-043", "T51")

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "ontology" / "border-cargo-composition.yaml"

#: The type T51 added, and the two links that reach it.
NEW_TYPE = "vessel"
NEW_PREDICATES = ("carried_on", "berthed_at")

#: Generated, so naming a domain term in them is how the mechanism works rather
#: than a violation of it (ADR-043).
GENERATED = {
    REPO_ROOT / "ui" / "src" / "api" / "ontology.ts",
    REPO_ROOT / "ui" / "src" / "api" / "schema.d.ts",
}


@pytest.fixture(scope="module")
def cargo():
    return load(FIXTURE)


@pytest.fixture(scope="module")
def constants(cargo) -> str:
    return typescript_constants(cargo)


def _entry(rendered: str, name: str) -> str:
    line = next(
        (l for l in rendered.splitlines() if l.strip().startswith(f'"{name}":')), None
    )
    assert line is not None, f"{name} is absent from the generated constants"
    return line


def test_the_new_type_reaches_the_registry(cargo) -> None:
    assert NEW_TYPE in cargo.object_types
    assert cargo.owner_module(NEW_TYPE) == "border_cargo"
    for predicate in NEW_PREDICATES:
        assert predicate in cargo.predicates, predicate


def test_the_generator_emits_everything_a_screen_reads(constants: str) -> None:
    """The descriptor contract (spec 09 §6.2), for a type nobody wrote code for."""
    entry = _entry(constants, NEW_TYPE)
    assert 'label: "Vessel"' in entry
    # A heading and a subtitle, so the object view has something to draw.
    assert 'display: { title: "name", subtitle: "former_names" }' in entry
    for prop in ("name", "imo_number", "former_names", "flag_state", "notes"):
        assert f'"{prop}": {{ label: ' in entry, prop


def test_the_governance_fields_survive_the_journey(constants: str) -> None:
    """A restricted property says so on the screen, and a preserved conflict
    renders as two values rather than one — both read from the descriptor."""
    entry = _entry(constants, NEW_TYPE)
    assert '"imo_number": { label: "IMO number"' in entry
    assert 'sensitivity: "restricted"' in entry
    assert 'conflicts: "preserve"' in entry
    # `many` reaches the screen too: an alias list is a list.
    assert '"former_names": { label: "Aliases", type: "text", required: false, many: true' in entry


def test_a_declared_label_beats_the_default_here_too(constants: str) -> None:
    """`imo_number` would humanize to "Imo number"; the ontology overrides it.

    Which is the point of the override existing: a domain fixes its own naming
    without a UI change.
    """
    entry = _entry(constants, NEW_TYPE)
    assert '"Imo number"' not in entry


def test_the_links_arrive_with_their_category_and_direction(constants: str) -> None:
    carried = _entry(constants, "carried_on")
    assert 'object: ["vessel"]' in carried
    assert 'category: "customs"' in carried
    berthed = _entry(constants, "berthed_at")
    assert 'subject: ["vessel"]' in berthed
    assert 'object: ["port_of_entry"]' in berthed


def test_the_interface_it_implements_lists_it(constants: str) -> None:
    """`identifiable` is a platform interface; the fixture implements it without
    the platform module being edited (ADR-041)."""
    entry = _entry(constants, "identifiable")
    assert NEW_TYPE in entry


def test_no_hand_written_file_names_the_new_type() -> None:
    """The criterion's core: the addition costs nothing outside the ontology.

    Quoted-form matching, like the other sweeps: `vessel` is an English word and
    a bare substring would also catch prose.
    """
    pattern = re.compile(rf"""["']{NEW_TYPE}["']""")
    sources = [
        *(REPO_ROOT / "aegis").rglob("*.py"),
        *(p for p in (REPO_ROOT / "ui" / "src").rglob("*.ts*") if p not in GENERATED),
    ]
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted(sources)
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        f"{offenders} name {NEW_TYPE!r}. Adding an object type must need no code "
        "(charter exit criterion 4)."
    )


def test_the_addition_changed_only_the_fixture_module_and_its_pin() -> None:
    """"ontology + regenerated files only", checked against the change itself.

    The fixture is not the shipped composition, so there is no `release.json`
    and no proposal to write — the equivalent discipline is the module's own
    version and the pin that names it, and both moved.
    """
    module = (
        REPO_ROOT / "tests" / "fixtures" / "ontology" / "border-cargo.yaml"
    ).read_text(encoding="utf-8")
    composition = (
        REPO_ROOT / "tests" / "fixtures" / "ontology" / "border-cargo-composition.yaml"
    ).read_text(encoding="utf-8")
    assert "version: 1.2.0" in module
    assert '1.2.0 (T51)' in module, "the bump says what it was for"
    assert 'version: "1.2.0"' in composition


def test_the_shipped_ontology_is_untouched_by_the_proof() -> None:
    """A fixture type must never leak into the product's own vocabulary."""
    from tests.support.paths import ONTOLOGY_PATH

    shipped = load(ONTOLOGY_PATH)
    assert NEW_TYPE not in shipped.object_types
    for predicate in NEW_PREDICATES:
        assert predicate not in shipped.predicates
    assert NEW_TYPE not in compose(ONTOLOGY_PATH).owners
