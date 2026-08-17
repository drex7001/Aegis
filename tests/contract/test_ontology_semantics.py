"""Shared properties and interfaces — the semantic layer v2 (T32).

Spec 08 §3–4 and §9 rules 13–14; ADR-041. Two ideas are under test:

* a **shared property** is a definition, not a default — a reference cannot
  restate its type or sensitivity, and after loading it *is* the property, so
  no consumer learns the syntax exists;
* an **interface** is implemented by the object type, not listed on the
  interface, so a domain module can implement a platform interface without
  editing the platform module.
"""

from __future__ import annotations

import copy

import pytest

from aegis.ontology import OntologyError, OntologyValidationError, compose, load, load_dict
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement("Article-XI", "Article-XIV", "ADR-041", "T32")


@pytest.fixture(scope="module")
def composed() -> dict:
    return compose(ONTOLOGY_PATH).document


@pytest.fixture()
def data(composed: dict) -> dict:
    return copy.deepcopy(composed)


def errors_of(data: dict) -> list[str]:
    with pytest.raises(OntologyValidationError) as excinfo:
        load_dict(data)
    return excinfo.value.errors


# ── the committed artifact ──────────────────────────────────────────────────


def test_the_starter_set_is_declared() -> None:
    ont = load(ONTOLOGY_PATH)
    assert set(ont.shared_properties) == {"alias", "registered_identifier", "notes"}
    assert set(ont.interfaces) == {"party", "identifiable"}
    assert ont.implementors("party") == ["person", "organization"]
    assert ont.implementors("identifiable") == ["person", "phone_number"]


def test_a_shared_reference_resolves_in_place() -> None:
    """The whole design goal: `authz.filters` reads this and sees no reference."""
    ont = load(ONTOLOGY_PATH)
    nic = ont.object_type("person").properties["nic"]
    assert nic.type == "identifier"
    assert nic.sensitivity == "restricted"      # from the shared definition
    assert nic.shared == "registered_identifier"  # ...and where it came from

    aliases = ont.object_type("person").properties["aliases"]
    assert aliases.type == "text"
    assert aliases.many is True


def test_required_belongs_to_the_reference_not_the_definition() -> None:
    """Whether a phone number must have a number is a fact about phone numbers."""
    ont = load(ONTOLOGY_PATH)
    number = ont.object_type("phone_number").properties["number"]
    assert number.required is True
    assert number.sensitivity == "restricted"
    assert ont.object_type("person").properties["nic"].required is False


def test_the_sensitivity_boundary_did_not_move() -> None:
    """T32 is additive: every property keeps the clearance it already had.

    Pinned because adopting a shared property is exactly the change that could
    silently raise or lower a handling floor on rows already recorded.
    """
    ont = load(ONTOLOGY_PATH)
    restricted = {
        f"{tname}.{pname}"
        for tname, otype in ont.object_types.items()
        for pname, prop in otype.properties.items()
        if prop.sensitivity == "restricted"
    }
    assert restricted == {"person.nic", "phone_number.number"}
    # `vehicle.registration` is a registry identifier that is deliberately not
    # `registered_identifier`: adopting it would raise its clearance, which is
    # a policy change and needs a proposal (see the module file's comment).
    assert ont.object_type("vehicle").properties["registration"].sensitivity is None
    assert "identifiable" not in ont.object_type("vehicle").implements


def test_interfaces_are_owned_by_platform_and_implemented_by_the_domain() -> None:
    """ADR-041's reason for existing, asserted on the real composition."""
    ont = load(ONTOLOGY_PATH)
    assert ont.owner_module("party") == "platform"
    assert ont.owner_module("alias") == "platform"
    assert ont.owner_module("person") == "criminal_network"


# ── rule 13: shared properties ──────────────────────────────────────────────


def test_unknown_shared_reference_fails(data: dict) -> None:
    data["object_types"]["person"]["properties"]["notes"] = {"shared": "ghost"}
    errors = errors_of(data)
    assert any(
        "object_types.person.properties.notes.shared: unknown shared property 'ghost'" in e
        for e in errors
    )


def test_a_reference_may_not_override_type(data: dict) -> None:
    data["object_types"]["person"]["properties"]["nic"] = {
        "shared": "registered_identifier",
        "type": "text",
    }
    errors = errors_of(data)
    assert any(
        "object_types.person.properties.nic.type: a `shared:` reference may not "
        "override 'type'" in e
        for e in errors
    )


def test_a_reference_may_not_override_sensitivity(data: dict) -> None:
    """The governance case: a domain must not quietly declassify a shared field."""
    data["object_types"]["person"]["properties"]["nic"] = {
        "shared": "registered_identifier",
        "sensitivity": "open",
    }
    errors = errors_of(data)
    assert any(
        "object_types.person.properties.nic.sensitivity: a `shared:` reference "
        "may not override 'sensitivity'" in e
        for e in errors
    )


def test_a_reference_may_not_override_cardinality(data: dict) -> None:
    data["object_types"]["person"]["properties"]["nic"] = {
        "shared": "registered_identifier",
        "many": True,
    }
    errors = errors_of(data)
    assert any(
        "object_types.person.properties.nic.many: cardinality comes from "
        "shared_properties.registered_identifier" in e
        for e in errors
    )


def test_a_property_with_neither_type_nor_shared_fails(data: dict) -> None:
    data["object_types"]["person"]["properties"]["mystery"] = {"required": True}
    errors = errors_of(data)
    assert any(
        "object_types.person.properties.mystery: declare either a `type` or a "
        "`shared` reference" in e
        for e in errors
    )


def test_shared_property_sensitivity_must_be_a_declared_handling_code(data: dict) -> None:
    data["shared_properties"]["registered_identifier"]["sensitivity"] = "cosmic"
    errors = errors_of(data)
    assert any(
        "shared_properties.registered_identifier.sensitivity: unknown handling "
        "code 'cosmic'" in e
        for e in errors
    )


# ── rule 14: interfaces ─────────────────────────────────────────────────────


def test_implementing_an_unknown_interface_fails(data: dict) -> None:
    data["object_types"]["vehicle"]["implements"] = ["conveyance"]
    errors = errors_of(data)
    assert any(
        "object_types.vehicle.implements: unknown interface 'conveyance'" in e
        for e in errors
    )


def test_an_implementor_missing_a_required_property_fails(data: dict) -> None:
    """An interface is a promise about every implementor, or it is nothing."""
    data["object_types"]["location"]["implements"] = ["party"]
    errors = errors_of(data)
    assert any(
        "object_types.location.implements: 'party' requires shared property "
        "'alias', which 'location' does not declare" in e
        for e in errors
    )


def test_an_interface_requiring_an_unknown_shared_property_fails(data: dict) -> None:
    data["interfaces"]["party"]["properties"] = ["nickname"]
    errors = errors_of(data)
    assert any(
        "interfaces.party.properties: unknown shared property 'nickname'" in e
        for e in errors
    )


def test_an_interface_may_not_share_a_name_with_an_object_type(data: dict) -> None:
    data["interfaces"]["person"] = {"label": "Person-ish"}
    errors = errors_of(data)
    assert any("interfaces.person: duplicate name" in e for e in errors)


# ── interface-targeting predicates ──────────────────────────────────────────


def test_a_predicate_targeting_an_interface_expands_to_its_implementors(
    data: dict,
) -> None:
    """The charter's criterion: `subject: [party]` validates for members."""
    data["predicates"]["negotiated_with"] = {
        "subject": ["party"],
        "object": ["party"],
        "category": "financial",
    }
    ont = load_dict(data)
    predicate = ont.predicate("negotiated_with")
    # Expanded in place, so `actions.service` needs no interface awareness.
    assert predicate.subject == ["person", "organization"]
    assert predicate.entity_object_types == ["person", "organization"]
    # ...and the declaration survives for codegen.
    assert predicate.subject_interfaces == ("party",)
    assert predicate.object_interfaces == ("party",)
    # A non-member is rejected exactly as it would be for a concrete list.
    assert "location" not in predicate.subject


def test_expansion_preserves_a_mixed_entity_or_literal_object(data: dict) -> None:
    data["predicates"]["represented_by"] = {
        "subject": ["person"],
        "object": ["party", "literal"],
    }
    predicate = load_dict(data).predicate("represented_by")
    assert predicate.allows_literal
    assert predicate.entity_object_types == ["person", "organization"]


def test_expansion_does_not_duplicate_a_type_named_twice(data: dict) -> None:
    data["predicates"]["knows_of"] = {"subject": ["party", "person"], "object": "literal"}
    assert load_dict(data).predicate("knows_of").subject == ["person", "organization"]


def test_a_predicate_targeting_an_unimplemented_interface_fails(data: dict) -> None:
    """A predicate no entity can satisfy is a modelling mistake, not an empty set."""
    data["interfaces"]["vessel"] = {"label": "Vessel"}
    data["predicates"]["docked_at"] = {"subject": ["vessel"], "object": "literal"}
    errors = errors_of(data)
    assert any(
        "predicates.docked_at.subject: interface 'vessel' has no implementing "
        "object type" in e
        for e in errors
    )


def test_an_unreferenced_interface_is_allowed(data: dict) -> None:
    """A platform interface no enabled domain implements is a normal state."""
    data["interfaces"]["vessel"] = {"label": "Vessel"}
    assert "vessel" in load_dict(data).interfaces


def test_expand_types_and_implementors_reject_unknown_names() -> None:
    ont = load(ONTOLOGY_PATH)
    assert ont.expand_types(["party", "vehicle"]) == ["person", "organization", "vehicle"]
    with pytest.raises(OntologyError, match="unknown interface 'ghost'"):
        ont.implementors("ghost")


# ── the v1 shape still loads (spec 08 §9 rule 18) ───────────────────────────


def test_a_document_with_no_v2_sections_still_validates(data: dict) -> None:
    """Inline properties keep working; v2 is additive, not a migration.

    The transformation below is a faithful downgrade: remove the v2 sections
    *and* every reference to them — shared properties become inline, and a
    predicate targeting an interface names its members instead. Dropping the
    sections while leaving `subject: [party]` behind would be testing a
    document nobody could have written before v2.
    """
    interfaces = data.pop("interfaces")
    data.pop("shared_properties")
    for otype in data["object_types"].values():
        otype.pop("implements", None)
        for name, prop in list(otype["properties"].items()):
            if "shared" in prop:
                otype["properties"][name] = {"type": "text"}
    for predicate in data["predicates"].values():
        for endpoint in ("subject", "object"):
            names = predicate.get(endpoint)
            if not isinstance(names, list):
                continue
            predicate[endpoint] = [
                name for name in names if name not in interfaces
            ] or ["person"]

    ont = load_dict(data)
    assert ont.shared_properties == {}
    assert ont.interfaces == {}
    assert ont.object_type("person").properties["nic"].type == "text"
    assert ont.predicate("controls").subject_interfaces == ()
