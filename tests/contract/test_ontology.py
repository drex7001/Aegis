"""Ontology loader/validator tests (speckit T3).

Strategy: the committed ontology/aegis.yaml must load cleanly; every validation
rule from spec 01 §6 is exercised by mutating a deep copy of it and asserting a
precise, path-bearing error message.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from aegis.ontology import Ontology, OntologyError, OntologyValidationError, load, load_dict

REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.requirement("Article-XI", "T3")
ONTOLOGY_PATH = REPO_ROOT / "ontology" / "aegis.yaml"


@pytest.fixture(scope="module")
def ontology_data() -> dict:
    with ONTOLOGY_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture()
def data(ontology_data: dict) -> dict:
    return copy.deepcopy(ontology_data)


def errors_of(data: dict) -> list[str]:
    with pytest.raises(OntologyValidationError) as excinfo:
        load_dict(data)
    return excinfo.value.errors


# ── the committed artifact is valid ─────────────────────────────────────────


def test_committed_ontology_loads() -> None:
    ont = load(ONTOLOGY_PATH)
    assert isinstance(ont, Ontology)
    assert ont.version == "1.1.0"
    assert "person" in ont.object_types
    assert "member_of" in ont.predicates
    assert "record_claim" in ont.actions
    assert "remove_case_member" in ont.actions


def test_registry_accessors(data: dict) -> None:
    ont = load_dict(data)
    assert ont.handling_rank("open") == 0
    assert ont.handling_rank("sensitive") == 2
    assert ont.predicate("sibling_of").symmetric is True
    assert ont.predicate("known_as").is_literal is True
    assert ont.object_type("person").properties["nic"].sensitivity == "restricted"
    assert ont.action("record_claim").audit is True
    # external scheme values map onto the internal grading model (ADR-011)
    assert ont.normalize_grade("admiralty", "B") == {"reliability": "generally_reliable"}


def test_registry_unknown_lookups_raise(data: dict) -> None:
    ont = load_dict(data)
    with pytest.raises(OntologyError, match="unknown handling code 'top_secret'"):
        ont.handling_rank("top_secret")
    with pytest.raises(OntologyError, match="unknown predicate 'owns_yacht'"):
        ont.predicate("owns_yacht")
    with pytest.raises(OntologyError, match="unknown grading scheme 'nato'"):
        ont.normalize_grade("nato", "A")


# ── rule 2: predicate endpoint types (the T3 acceptance criterion) ──────────


def test_unknown_predicate_object_type_fails_precisely(data: dict) -> None:
    data["predicates"]["member_of"]["object"] = ["organizatoin"]  # typo on purpose
    errors = errors_of(data)
    assert any(
        "predicates.member_of.object: unknown object type 'organizatoin'" in e for e in errors
    )


def test_unknown_predicate_subject_type_fails(data: dict) -> None:
    data["predicates"]["founded"]["subject"] = ["ghost"]
    errors = errors_of(data)
    assert any("predicates.founded.subject: unknown object type 'ghost'" in e for e in errors)


def test_literal_object_is_allowed(data: dict) -> None:
    assert load_dict(data).predicate("known_as").is_literal


def test_mixed_entity_or_literal_object(data: dict) -> None:
    """spec 02 §6: affiliated_with resolves to an org entity when one exists, else literal."""
    pred = load_dict(data).predicate("affiliated_with")
    assert not pred.is_literal
    assert pred.allows_literal
    assert pred.allows_entity
    assert pred.entity_object_types == ["organization"]


def test_literal_only_list_form_is_rejected(data: dict) -> None:
    data["predicates"]["member_of"]["object"] = ["literal"]
    errors = errors_of(data)
    assert any(
        "predicates.member_of.object: ['literal'] is redundant" in e for e in errors
    )


def test_mixed_object_unknown_type_still_fails(data: dict) -> None:
    data["predicates"]["member_of"]["object"] = ["ghost", "literal"]
    errors = errors_of(data)
    assert any("predicates.member_of.object: unknown object type 'ghost'" in e for e in errors)


# ── rule 3: referenced categories / sensitivities exist ─────────────────────


def test_unknown_category_fails(data: dict) -> None:
    data["predicates"]["allied_with"]["category"] = "astral"
    errors = errors_of(data)
    assert any("predicates.allied_with.category: unknown category 'astral'" in e for e in errors)


def test_unknown_sensitivity_fails(data: dict) -> None:
    data["object_types"]["person"]["properties"]["nic"]["sensitivity"] = "cosmic"
    errors = errors_of(data)
    assert any(
        "object_types.person.properties.nic.sensitivity: unknown handling code 'cosmic'" in e
        for e in errors
    )


# ── rule 1: unique names across sections ────────────────────────────────────


def test_cross_section_duplicate_name_fails(data: dict) -> None:
    data["predicates"]["person"] = {"subject": ["person"], "object": ["person"]}
    errors = errors_of(data)
    assert any("predicates.person: duplicate name" in e for e in errors)


# ── rule 4: handling codes ordered & unique ─────────────────────────────────


def test_duplicate_handling_codes_fail(data: dict) -> None:
    data["handling_codes"] = ["open", "restricted", "open"]
    errors = errors_of(data)
    assert any(e.startswith("handling_codes: duplicates") for e in errors)


# ── rule 5: actions must declare roles and audit ────────────────────────────


def test_action_missing_audit_fails(data: dict) -> None:
    del data["actions"]["record_claim"]["audit"]
    errors = errors_of(data)
    assert any("actions.record_claim.audit" in e for e in errors)


def test_action_audit_false_fails(data: dict) -> None:
    data["actions"]["record_claim"]["audit"] = False
    errors = errors_of(data)
    assert any("actions.record_claim.audit: must be true" in e for e in errors)


def test_action_unknown_role_fails(data: dict) -> None:
    data["actions"]["record_claim"]["roles"] = ["analyst", "wizard"]
    errors = errors_of(data)
    assert any("actions.record_claim.roles: unknown role 'wizard'" in e for e in errors)


def test_action_empty_roles_fails(data: dict) -> None:
    data["actions"]["record_claim"]["roles"] = []
    errors = errors_of(data)
    assert any("actions.record_claim.roles" in e for e in errors)


# ── rule 6: grading scheme maps target declared values ──────────────────────


def test_scheme_unknown_dimension_fails(data: dict) -> None:
    data["grading"]["schemes"]["admiralty"]["A"] = {"vibes": "reliable"}
    errors = errors_of(data)
    assert any(
        "grading.schemes.admiralty.A: unknown dimension 'vibes'" in e
        for e in errors
    )


def test_scheme_unknown_value_fails(data: dict) -> None:
    data["grading"]["schemes"]["admiralty"]["A"] = {"reliability": "immaculate"}
    errors = errors_of(data)
    assert any(
        "grading.schemes.admiralty.A.reliability: 'immaculate' is not a declared" in e
        for e in errors
    )


# ── rule 7: version format ──────────────────────────────────────────────────


def test_bad_version_fails(data: dict) -> None:
    data["version"] = "v1-beta"
    errors = errors_of(data)
    assert any("version: 'v1-beta' is not MAJOR.MINOR.PATCH semver" in e for e in errors)


# ── structural hygiene ──────────────────────────────────────────────────────


def test_unknown_top_level_key_fails(data: dict) -> None:
    data["magic"] = {}
    errors = errors_of(data)
    assert any(e.startswith("magic:") for e in errors)


def test_non_snake_case_name_fails(data: dict) -> None:
    data["predicates"]["AlliedWith"] = {"subject": ["person"], "object": ["person"]}
    errors = errors_of(data)
    assert any("predicates.AlliedWith: name must be snake_case" in e for e in errors)


def test_display_referencing_undeclared_property_fails(data: dict) -> None:
    data["object_types"]["person"]["display"]["title"] = "nickname"
    errors = errors_of(data)
    assert any("object_types.person.display: references undeclared property 'nickname'" in e for e in errors)


def test_all_errors_collected_in_one_pass(data: dict) -> None:
    data["version"] = "nope"
    data["predicates"]["member_of"]["object"] = ["ghost"]
    data["actions"]["record_claim"]["audit"] = False
    errors = errors_of(data)
    assert len(errors) >= 3


def test_missing_file_raises_ontology_error(tmp_path: Path) -> None:
    with pytest.raises(OntologyError, match="not found"):
        load(tmp_path / "nope.yaml")


@pytest.mark.requirement("Article-XIV", "ADR-027", "T18")
def test_identifier_predicates_are_declared_not_hardcoded() -> None:
    """The ER rules key off this flag rather than naming NIC or registrations.

    A domain-neutral core (Article XIV) means a new domain adds an identifier
    by declaring one here — never by editing `aegis/er/rules.py`.
    """
    ont = load(ONTOLOGY_PATH)
    identifiers = ont.identifier_predicates()
    assert set(identifiers) == {"has_nic", "registered_as", "reachable_on"}
    for name, spec in identifiers.items():
        # An identifier is a value the source states, not a link between two
        # entities: a shared *entity* object would already be the same node.
        assert spec.is_literal, f"{name} must take a literal object"
    # every other predicate must opt out, so the flag stays meaningful
    assert not any(
        spec.identifier for name, spec in ont.predicates.items() if name not in identifiers
    )
