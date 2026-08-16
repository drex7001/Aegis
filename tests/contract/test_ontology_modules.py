"""Module composition — manifests, imports, ownership, enable/disable (T30).

Spec 08 §2 and §9 rules 8–12; ADR-037. Strategy mirrors ``test_ontology.py``:
build a small composition on disk, mutate one thing, and assert a precise error
that names both the module and the YAML path. Every fixture here is fictional
vocabulary — the real modules are exercised by the committed-artifact tests at
the top.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aegis.ontology import (
    OntologyValidationError,
    compose,
    disabled_vocabulary_in_use,
    is_composition,
    load,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY_PATH = REPO_ROOT / "ontology" / "aegis.yaml"

pytestmark = pytest.mark.requirement("Article-XI", "Article-XIV", "ADR-037", "T30")


# ── the committed composition ───────────────────────────────────────────────


def test_the_committed_artifact_is_a_composition() -> None:
    ont = load(ONTOLOGY_PATH)
    assert set(ont.modules) == {"platform", "criminal_network"}
    assert all(info.enabled for info in ont.modules.values())
    assert ont.modules["platform"].namespace == "aegis.lk/platform"
    assert ont.modules["criminal_network"].imports == {"platform": ">=1.2.0,<2.0.0"}


def test_the_platform_domain_split_holds() -> None:
    """Article XIV, made checkable: platform declares no domain vocabulary.

    If a platform module ever declares an object type or a predicate, a second
    domain can no longer replace the domain module alone — which is the whole
    claim ADR-037 makes.
    """
    ont = load(ONTOLOGY_PATH)
    owned_by_platform = {
        name for name, module in ont.owners.items() if module == "platform"
    }
    assert owned_by_platform == (
        set(ont.actions) | set(ont.interfaces) | set(ont.shared_properties)
    )
    assert not owned_by_platform & set(ont.object_types)
    assert not owned_by_platform & set(ont.predicates)

    domain = {name for name, module in ont.owners.items() if module == "criminal_network"}
    assert set(ont.object_types) <= domain
    assert set(ont.predicates) <= domain
    assert set(ont.categories) <= domain


def test_ownership_is_reported_per_name() -> None:
    ont = load(ONTOLOGY_PATH)
    assert ont.owner_module("person") == "criminal_network"
    assert ont.owner_module("record_claim") == "platform"
    assert ont.owner_module("nothing_declares_this") is None


def test_modules_report_what_they_declare() -> None:
    ont = load(ONTOLOGY_PATH)
    assert "record_claim" in ont.modules["platform"].declares
    assert "member_of" in ont.modules["criminal_network"].declares
    assert "member_of" not in ont.modules["platform"].declares


def test_a_flat_document_is_still_valid_and_reports_no_modules() -> None:
    """Spec 08 §9 rule 18 — the bump to a composition stays minor because of this."""
    composed = compose(ONTOLOGY_PATH)
    assert not is_composition(composed.document)
    from aegis.ontology import load_dict

    flat = load_dict(composed.document)
    assert flat.modules == {}
    assert flat.owners == {}


def test_the_composed_registry_matches_the_pre_split_vocabulary() -> None:
    """T30 is a reorganization: the merged sections are the whole ontology.

    Pinned as counts plus the single-owner sections, because those are what a
    silent drop during the file split would change.
    """
    ont = load(ONTOLOGY_PATH)
    assert len(ont.object_types) == 5
    assert len(ont.predicates) == 33
    assert len(ont.categories) == 5
    assert len(ont.actions) == 13
    assert ont.handling_codes == ["open", "restricted", "sensitive"]
    assert len(ont.source_types) == 8
    assert ont.normalize_grade("admiralty", "B") == {"reliability": "generally_reliable"}


# ── fixture composition helpers ─────────────────────────────────────────────

PLATFORM = {
    "module": {"name": "platform", "namespace": "test/platform", "version": "1.0.0"},
    "handling_codes": ["open", "restricted"],
    "source_types": ["open_source"],
    "grading": {
        "reliability": {"normalized": ["reliable"]},
        "credibility": {"normalized": ["confirmed"]},
        "verification": ["unverified"],
        "analytic_confidence": ["low"],
    },
    "actions": {"record_claim": {"roles": ["analyst"], "audit": True}},
}

DOMAIN = {
    "module": {
        "name": "harbour",
        "namespace": "test/harbour",
        "version": "1.0.0",
        "imports": [{"module": "platform", "version": ">=1.0.0,<2.0.0"}],
    },
    "categories": {"logistics": {"label": "Logistics"}},
    "object_types": {
        "berth": {"label": "Berth", "properties": {"code": {"type": "text", "required": True}}}
    },
    "predicates": {"moored_at": {"subject": ["berth"], "object": "literal"}},
}


def _write(root: Path, modules: dict[str, dict], entries: list[dict]) -> Path:
    (root / "modules").mkdir(parents=True, exist_ok=True)
    for filename, body in modules.items():
        (root / "modules" / filename).write_text(yaml.safe_dump(body), encoding="utf-8")
    manifest = {"version": "1.0.0", "namespace": "test", "composition": entries}
    path = root / "aegis.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return path


def _default(root: Path, **overrides) -> Path:
    platform = overrides.get("platform", PLATFORM)
    domain = overrides.get("domain", DOMAIN)
    entries = overrides.get(
        "entries",
        [
            {"module": "platform", "path": "modules/platform.yaml", "version": "1.0.0"},
            {"module": "harbour", "path": "modules/harbour.yaml", "version": "1.0.0"},
        ],
    )
    return _write(
        root,
        {"platform.yaml": platform, "harbour.yaml": domain},
        entries,
    )


def errors_of(path: Path) -> list[str]:
    with pytest.raises(OntologyValidationError) as excinfo:
        load(path)
    return excinfo.value.errors


def test_the_fixture_composition_is_valid(tmp_path: Path) -> None:
    ont = load(_default(tmp_path))
    assert set(ont.modules) == {"platform", "harbour"}
    assert ont.owner_module("berth") == "harbour"
    assert ont.owner_module("record_claim") == "platform"


# ── rule 10: cross-module reference without an import ───────────────────────


def test_reference_without_a_declared_import_fails_precisely(tmp_path: Path) -> None:
    """The charter's third exit criterion."""
    domain = {**DOMAIN, "module": {**DOMAIN["module"], "imports": []}}
    domain["object_types"] = {
        "berth": {
            "label": "Berth",
            "properties": {"code": {"type": "text", "sensitivity": "restricted"}},
        }
    }
    errors = errors_of(_default(tmp_path, domain=domain))
    assert any(
        "harbour.object_types.berth.properties.code.sensitivity: handling codes "
        "are owned by module 'platform', which 'harbour' does not import" in e
        for e in errors
    )


def test_reference_to_a_type_in_an_unimported_module_fails(tmp_path: Path) -> None:
    platform = {**PLATFORM, "object_types": {"vessel": {"label": "Vessel", "properties": {}}}}
    domain = {**DOMAIN, "module": {**DOMAIN["module"], "imports": []}}
    domain["predicates"] = {"moored_at": {"subject": ["vessel"], "object": "literal"}}
    domain["object_types"] = {"berth": {"label": "Berth", "properties": {}}}
    errors = errors_of(_default(tmp_path, platform=platform, domain=domain))
    assert any(
        "harbour.predicates.moored_at.subject: 'vessel' is owned by module "
        "'platform', which 'harbour' does not import" in e
        for e in errors
    )


def test_an_imported_reference_is_accepted(tmp_path: Path) -> None:
    platform = {**PLATFORM, "object_types": {"vessel": {"label": "Vessel", "properties": {}}}}
    domain = dict(DOMAIN)
    domain["predicates"] = {"moored_at": {"subject": ["vessel"], "object": "literal"}}
    domain["object_types"] = {"berth": {"label": "Berth", "properties": {}}}
    ont = load(_default(tmp_path, platform=platform, domain=domain))
    assert ont.predicate("moored_at").subject == ["vessel"]


# ── rule 11: collisions ─────────────────────────────────────────────────────


def test_name_collision_across_modules_fails(tmp_path: Path) -> None:
    platform = {**PLATFORM, "object_types": {"berth": {"label": "Pier", "properties": {}}}}
    errors = errors_of(_default(tmp_path, platform=platform))
    assert any(
        "harbour.object_types.berth: name collision — module 'platform' already "
        "declares 'berth'" in e
        for e in errors
    )


def test_two_modules_declaring_handling_codes_fails(tmp_path: Path) -> None:
    domain = {**DOMAIN, "handling_codes": ["open"]}
    errors = errors_of(_default(tmp_path, domain=domain))
    assert any(
        "harbour.handling_codes: already declared by module 'platform'" in e
        for e in errors
    )


# ── rules 8–9: manifest shape, versions, imports ────────────────────────────


def test_pinned_version_must_match_the_module_file(tmp_path: Path) -> None:
    entries = [
        {"module": "platform", "path": "modules/platform.yaml", "version": "1.0.0"},
        {"module": "harbour", "path": "modules/harbour.yaml", "version": "2.0.0"},
    ]
    errors = errors_of(_default(tmp_path, entries=entries))
    assert any(
        "composition.harbour.version: manifest pins '2.0.0'" in e and "'1.0.0'" in e
        for e in errors
    )


def test_pinned_version_must_satisfy_the_import_specifier(tmp_path: Path) -> None:
    platform = {**PLATFORM, "module": {**PLATFORM["module"], "version": "2.0.0"}}
    entries = [
        {"module": "platform", "path": "modules/platform.yaml", "version": "2.0.0"},
        {"module": "harbour", "path": "modules/harbour.yaml", "version": "1.0.0"},
    ]
    errors = errors_of(_default(tmp_path, platform=platform, entries=entries))
    assert any(
        "harbour.imports.platform.version: composition pins platform '2.0.0', "
        "which does not satisfy '>=1.0.0,<2.0.0'" in e
        for e in errors
    )


def test_import_of_an_unlisted_module_fails(tmp_path: Path) -> None:
    domain = {
        **DOMAIN,
        "module": {
            **DOMAIN["module"],
            "imports": [{"module": "ghost", "version": ">=1.0.0"}],
        },
    }
    errors = errors_of(_default(tmp_path, domain=domain))
    assert any("harbour.imports.ghost: no module named 'ghost'" in e for e in errors)


def test_invalid_specifier_fails(tmp_path: Path) -> None:
    domain = {
        **DOMAIN,
        "module": {
            **DOMAIN["module"],
            "imports": [{"module": "platform", "version": "roughly 1"}],
        },
    }
    errors = errors_of(_default(tmp_path, domain=domain))
    assert any(
        "harbour.imports.platform.version: 'roughly 1' is not a PEP 440 specifier" in e
        for e in errors
    )


def test_import_cycle_fails(tmp_path: Path) -> None:
    platform = {
        **PLATFORM,
        "module": {
            **PLATFORM["module"],
            "imports": [{"module": "harbour", "version": ">=1.0.0"}],
        },
    }
    errors = errors_of(_default(tmp_path, platform=platform))
    assert any(e.startswith("imports: cycle detected") for e in errors)


def test_module_name_must_match_the_manifest(tmp_path: Path) -> None:
    domain = {**DOMAIN, "module": {**DOMAIN["module"], "name": "docks"}}
    errors = errors_of(_default(tmp_path, domain=domain))
    assert any(
        "composition.harbour.module.name: file declares 'docks' but the manifest "
        "lists it as 'harbour'" in e
        for e in errors
    )


def test_missing_module_file_fails(tmp_path: Path) -> None:
    entries = [
        {"module": "platform", "path": "modules/platform.yaml", "version": "1.0.0"},
        {"module": "harbour", "path": "modules/nope.yaml", "version": "1.0.0"},
    ]
    errors = errors_of(_default(tmp_path, entries=entries))
    assert any("composition.harbour.path: module file not found" in e for e in errors)


def test_module_declaring_a_composition_field_fails(tmp_path: Path) -> None:
    """Version and namespace have exactly one home (spec 08 §2.5)."""
    domain = {**DOMAIN, "version": "9.9.9"}
    errors = errors_of(_default(tmp_path, domain=domain))
    assert any(
        "composition.harbour.version: modules do not declare 'version'" in e
        for e in errors
    )


def test_unknown_section_in_a_module_fails(tmp_path: Path) -> None:
    domain = {**DOMAIN, "spells": {}}
    errors = errors_of(_default(tmp_path, domain=domain))
    assert any("composition.harbour.spells: not an ontology section" in e for e in errors)


def test_loader_owned_fields_cannot_be_declared() -> None:
    from aegis.ontology import load_dict

    with pytest.raises(OntologyValidationError) as excinfo:
        load_dict({"owners": {"person": "someone"}})
    assert any("owners: populated by the composition loader" in e for e in excinfo.value.errors)


# ── rule 12: enable/disable (spec 08 §2.6) ──────────────────────────────────


def test_disabling_a_module_removes_its_vocabulary(tmp_path: Path) -> None:
    entries = [
        {"module": "platform", "path": "modules/platform.yaml", "version": "1.0.0"},
        {
            "module": "harbour",
            "path": "modules/harbour.yaml",
            "version": "1.0.0",
            "enabled": False,
        },
    ]
    ont = load(_default(tmp_path, entries=entries))
    assert "berth" not in ont.object_types
    assert "moored_at" not in ont.predicates
    assert ont.owner_module("berth") is None
    # ...but the module is still reported, with what it declared, so the
    # startup check can ask whether anything recorded still speaks it.
    assert ont.modules["harbour"].enabled is False
    assert "berth" in ont.modules["harbour"].declares


def test_an_enabled_module_may_not_import_a_disabled_one(tmp_path: Path) -> None:
    entries = [
        {
            "module": "platform",
            "path": "modules/platform.yaml",
            "version": "1.0.0",
            "enabled": False,
        },
        {"module": "harbour", "path": "modules/harbour.yaml", "version": "1.0.0"},
    ]
    errors = errors_of(_default(tmp_path, entries=entries))
    assert any(
        "harbour.imports.platform: module 'platform' is disabled but imported by "
        "an enabled module" in e
        for e in errors
    )


def test_disabled_vocabulary_in_use_is_detected(tmp_path: Path) -> None:
    entries = [
        {"module": "platform", "path": "modules/platform.yaml", "version": "1.0.0"},
        {
            "module": "harbour",
            "path": "modules/harbour.yaml",
            "version": "1.0.0",
            "enabled": False,
        },
    ]
    ont = load(_default(tmp_path, entries=entries))
    assert disabled_vocabulary_in_use(ont, predicates=["moored_at"]) == {
        "harbour": ["moored_at"]
    }
    assert disabled_vocabulary_in_use(ont, entity_types=["berth"]) == {"harbour": ["berth"]}
    # Nothing recorded, nothing to refuse — the common path costs no complaint.
    assert disabled_vocabulary_in_use(ont) == {}
    assert disabled_vocabulary_in_use(ont, predicates=["member_of"]) == {}


def test_disabled_vocabulary_check_ignores_enabled_modules() -> None:
    """A live module's vocabulary is never a reason to refuse startup."""
    ont = load(ONTOLOGY_PATH)
    assert disabled_vocabulary_in_use(ont, predicates=["member_of"], entity_types=["person"]) == {}
