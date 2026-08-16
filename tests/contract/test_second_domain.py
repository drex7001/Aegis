"""Article XIV, made executable: a second domain needs zero core-code change (T31).

The claim "domains are ontology modules" is only worth making if something
fails when it stops being true. That is this file: `border-cargo` is a
fictional module the core has never seen, and the assertions below break the
moment a file under `aegis/` needs to know what a consignment is.

The graph/claim round-trip against the same module lives in
`tests/integration/test_second_domain.py`, where a database is available.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from aegis.ontology import load
from tests.support.paths import REPO_ROOT

pytestmark = pytest.mark.requirement("Article-XIV", "ADR-037", "B-07", "T31")

AEGIS_ROOT = REPO_ROOT / "aegis"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "ontology"
COMPOSITION = FIXTURE_ROOT / "border-cargo-composition.yaml"

#: Every name the fixture domain declares. The core may not contain any of
#: them — not in a branch, not in a lookup table, not in a comment that hints a
#: future one is coming.
FIXTURE_VOCABULARY = frozenset(
    {
        "consignment",
        "port_of_entry",
        "declared_as",
        "cleared_at",
        "manifested_under",
        "border_cargo",
    }
)


@pytest.fixture(scope="module")
def border_cargo():
    return load(COMPOSITION)


def test_the_second_domain_composes_against_the_real_platform_module(border_cargo) -> None:
    assert set(border_cargo.modules) == {"platform", "border_cargo"}
    assert set(border_cargo.object_types) == {"consignment", "port_of_entry"}
    assert set(border_cargo.predicates) == {
        "declared_as",
        "cleared_at",
        "manifested_under",
    }
    # The platform module arrives whole: the same clearance ladder, grading
    # model and actions the criminal-network composition uses.
    assert border_cargo.handling_codes == ["open", "restricted", "sensitive"]
    assert "record_claim" in border_cargo.actions
    assert border_cargo.owner_module("record_claim") == "platform"


def test_the_criminal_network_vocabulary_is_absent(border_cargo) -> None:
    """Not disabled — absent. The core is running a domain it has never met."""
    assert "person" not in border_cargo.object_types
    assert "member_of" not in border_cargo.predicates
    assert "criminal_network" not in border_cargo.modules


def test_no_core_module_names_the_fixture_vocabulary() -> None:
    """The acceptance criterion: the test fails if `aegis/` needs a domain edit."""
    offenders: dict[str, list[str]] = {}
    for path in sorted(AEGIS_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        hits = sorted(word for word in FIXTURE_VOCABULARY if word in text)
        if hits:
            offenders[path.relative_to(REPO_ROOT).as_posix()] = hits

    assert not offenders, (
        "the core names border-cargo vocabulary — a domain module must not "
        f"require code: {offenders}. Declare the behaviour in the ontology "
        "(Article XIV) rather than branching on a type name."
    )


def test_the_identifier_flag_reaches_the_second_domain(border_cargo) -> None:
    """The ER rules pick this domain up without knowing what it is (spec 05 §3.1)."""
    identifiers = border_cargo.identifier_predicates()
    assert set(identifiers) == {"manifested_under"}
    assert identifiers["manifested_under"].is_literal


def test_the_er_rule_engine_carries_no_domain_vocabulary() -> None:
    """`aegis/er/rules.py` iterates the declared flag, never a predicate name.

    Checked as a string sweep over the whole core above; asserted here against
    the module the criterion was written about, so a regression names the file
    that caused it.
    """
    source = (AEGIS_ROOT / "er" / "rules.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    domain = load(REPO_ROOT / "ontology" / "aegis.yaml")
    named = literals & (set(domain.predicates) | set(domain.object_types))
    assert not named, (
        f"aegis/er/rules.py names domain vocabulary {sorted(named)}; it must key "
        "off the ontology's `identifier` flag instead (Article XIV)"
    )


def test_disabling_the_second_domain_removes_its_vocabulary(tmp_path: Path) -> None:
    """Enable/disable is real, not a manifest comment (spec 08 §2.6)."""
    import yaml

    manifest = yaml.safe_load(COMPOSITION.read_text(encoding="utf-8"))
    for entry in manifest["composition"]:
        # Module paths resolve against the manifest's own directory, so a copy
        # written elsewhere has to name the originals absolutely.
        entry["path"] = str((FIXTURE_ROOT / entry["path"]).resolve())
        if entry["module"] == "border_cargo":
            entry["enabled"] = False
    manifest_path = tmp_path / "disabled.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    disabled = load(manifest_path)
    assert disabled.object_types == {}
    assert disabled.predicates == {}
    assert disabled.modules["border_cargo"].enabled is False
    # Platform survives: disabling a domain is not disabling the platform.
    assert "record_claim" in disabled.actions
