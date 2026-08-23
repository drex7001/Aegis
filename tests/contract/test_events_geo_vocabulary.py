"""Events and geometry in the ontology (T55) — spec 10, ADR-046…048.

Three things are under test, and only the first is about geography:

* an **occurrence is an object type** implementing the platform `event`
  interface, so the core recognises one without learning a single domain name;
* a literal-object predicate may **declare the property it carries**
  (ADR-047), which is what turns field-level sensitivity from a name
  coincidence into a statement — and what lets the core find geometry claims
  without naming `has_geometry`;
* the composition's **major** class is honest: `location.precision` is gone,
  and declaring the bump as anything weaker fails the release gate.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from aegis.authz.filters import forbidden_field_predicates, property_sensitivity
from aegis.ontology import OntologyValidationError, compose, load, load_dict
from aegis.ontology.generate import content_hash, typescript_constants
from aegis.ontology.registries import (
    GEO_ADMIN_LEVELS,
    GEO_DERIVATIONS,
    GEO_DERIVATIONS_REQUIRING_ACCURACY,
    GEO_NOT_ADMINISTRATIVE,
)
from aegis.ontology.release import COMPATIBILITY_ORDER, check, compare
from tests.support.paths import ONTOLOGY_PATH, REPO_ROOT

pytestmark = pytest.mark.requirement(
    "Article-I", "Article-XI", "Article-XIV", "ADR-046", "ADR-047", "ADR-048", "T55"
)

EVENT_TYPES = ("meeting", "arrest", "travel", "observation")
ROLE_PREDICATES = (
    "has_participant",
    "has_attendee",
    "has_arrestee",
    "has_arresting_officer",
    "has_traveller",
    "has_observer",
)


@pytest.fixture(scope="module")
def ont():
    return load(ONTOLOGY_PATH)


@pytest.fixture()
def data() -> dict:
    return copy.deepcopy(compose(ONTOLOGY_PATH).document)


# ── occurrences are object types (ADR-046, spec 10 §3.1) ────────────────────


def test_the_four_event_types_are_object_types_implementing_the_interface(ont) -> None:
    """Not a parallel registry: an occurrence gets everything an object type has.

    The `event_types:` section spec 01 reserved from P0 is gone with this bump,
    and this is what replaced it. If these were their own section they would
    each need identity, display, claims, provenance and an object view
    re-invented; as object types they have all five already.
    """
    for name in EVENT_TYPES:
        spec = ont.object_type(name)
        assert "event" in spec.implements, name
        assert "summary" in spec.properties, name
        assert spec.display is not None and spec.display.title == "summary", name
    assert ont.implementors("event") == list(EVENT_TYPES)


def test_the_dsl_no_longer_has_an_event_types_section(ont, data: dict) -> None:
    """Removed rather than left reserved — a placeholder nothing fills is rot."""
    assert not hasattr(ont, "event_types")
    assert "event_types" not in data
    data["event_types"] = {"riot": {}}
    with pytest.raises(OntologyValidationError):
        load_dict(data)


def test_the_role_is_the_predicate(ont) -> None:
    """So an undeclared role is an undeclared predicate — no new validation.

    And a role that only fits one kind of occurrence says so in its subject
    list: an arrestee at a meeting is a validation error, not a convention.
    """
    for name in ROLE_PREDICATES:
        spec = ont.predicate(name)
        assert not spec.is_literal, name
        assert set(spec.subject) <= set(EVENT_TYPES), name

    assert ont.predicate("has_arrestee").subject == ["arrest"]
    assert ont.predicate("has_arrestee").entity_object_types == ["person"]
    # `has_participant` targets the `event` and `party` interfaces, so it
    # expands to every implementor of each without naming one.
    participant = ont.predicate("has_participant")
    assert participant.subject_interfaces == ("event",)
    assert set(participant.subject) == set(EVENT_TYPES)
    assert set(participant.entity_object_types) == {"person", "organization"}


def test_travel_has_no_single_place_and_says_so(ont) -> None:
    """`took_place_at` names three concrete types, not the interface.

    A journey has an origin and a destination; "the place the journey happened"
    is not a thing, and expanding the interface would have invented one.
    """
    assert "travel" not in ont.predicate("took_place_at").subject
    assert ont.predicate("travelled_from").subject == ["travel"]
    assert ont.predicate("travelled_to").subject == ["travel"]


def test_no_new_time_column_or_time_predicate_exists(ont) -> None:
    """Time rides the claim envelope, which has carried intervals since P1.

    Asserted as an absence because that is the decision: a predicate whose
    object is a time would have been a second, contradictable time model beside
    `event_time_earliest`/`event_time_latest` (spec 10 §3.3).
    """
    for name, spec in ont.predicates.items():
        for prop in ont.property_specs_for(name):
            assert prop.type != "timestamp", f"{name} carries an asserted time"
    assert not any("time" in name for name in ont.predicates)


# ── the declared property (ADR-047, spec 10 §5) ─────────────────────────────


def test_geometry_is_discovered_by_type_never_by_name(ont) -> None:
    """The Article XIV half of ADR-047: the core asks for `geo`, not for a name."""
    assert set(ont.predicates_carrying("geo")) == {"has_geometry"}
    assert ont.predicate("has_geometry").property_name == "geometry"
    assert [prop.type for prop in ont.property_specs_for("has_geometry")] == ["geo"]
    # `location` is the only implementor today, so exactly one property resolves.
    assert ont.implementors("place") == ["location"]


def test_the_three_identifier_predicates_now_declare_their_property(ont) -> None:
    """They already worked by name coincidence; now they say so.

    Declaring it on the predicates that *did* work is the point — it proves the
    mechanism agrees with the heuristic before anything depends on it alone.
    """
    assert ont.predicate("has_nic").property_name == "nic"
    assert ont.predicate("registered_as").property_name == "registration"
    assert ont.predicate("reachable_on").property_name == "number"
    assert property_sensitivity(ont, "has_nic") == "restricted"
    assert property_sensitivity(ont, "reachable_on") == "restricted"
    assert property_sensitivity(ont, "registered_as") is None  # open, deliberately


def test_the_declaration_beats_the_heuristic(ont) -> None:
    """A predicate whose name matches nothing still gets its clearance.

    This is the case that would have failed silently: under the heuristic alone
    `has_geometry` matches no property called `has_geometry` and carries no
    `identifier` flag, so a restricted geometry would have been readable by
    anyone. Constructed rather than shipped, because geometry is deliberately
    *not* restricted by default — the claim's handling code is what governs it
    (spec 10 §7.2).
    """
    restricted = load_dict(_with_restricted_geometry(compose(ONTOLOGY_PATH).document))
    assert property_sensitivity(restricted, "has_geometry") == "restricted"
    assert "has_geometry" in forbidden_field_predicates(restricted, clearance=0)
    assert "has_geometry" not in forbidden_field_predicates(restricted, clearance=1)

    # ...and as shipped it is governed per claim, not per field.
    ont_shipped = load(ONTOLOGY_PATH)
    assert property_sensitivity(ont_shipped, "has_geometry") is None
    assert "has_geometry" not in forbidden_field_predicates(ont_shipped, clearance=0)


def _with_restricted_geometry(document: dict) -> dict:
    changed = copy.deepcopy(document)
    changed["shared_properties"]["geometry"]["sensitivity"] = "restricted"
    return changed


def test_a_property_missing_from_one_subject_type_fails(data: dict) -> None:
    """Rule 15's first half. Sensitivity that depends on which subject happened
    to be recorded is not sensitivity."""
    data["object_types"]["observation"]["properties"].pop("summary")
    # `observation` still implements `event`, so the interface check fires too;
    # what this asserts is that rule 15 names the predicate and the type.
    errors = _errors_of(data)
    assert any(
        "predicates.summarized_as.property: object type 'observation' declares no "
        "property 'summary'" in e
        for e in errors
    )


def test_a_property_on_an_entity_only_predicate_fails(data: dict) -> None:
    """Rule 15's second half: only a literal value can carry a property."""
    data["predicates"]["member_of"]["property"] = "name"
    errors = _errors_of(data)
    assert any(
        "predicates.member_of.property: 'name' is declared on a predicate whose "
        "object is always an entity" in e
        for e in errors
    )


def test_an_unknown_property_fails(data: dict) -> None:
    data["predicates"]["known_as"]["property"] = "ghost"
    errors = _errors_of(data)
    assert any(
        "predicates.known_as.property: object type 'person' declares no property "
        "'ghost'" in e
        for e in errors
    )


def _errors_of(data: dict) -> list[str]:
    with pytest.raises(OntologyValidationError) as excinfo:
        load_dict(data)
    return excinfo.value.errors


# ── the geo vocabularies are code-owned and exported ────────────────────────


def test_the_geo_vocabularies_are_closed_and_coherent() -> None:
    """Code-owned for the H-13 reason: a declarable value nothing implements
    would be a promise nothing keeps."""
    assert GEO_ADMIN_LEVELS == ("country", "subdivision", "locality", "site")
    assert GEO_NOT_ADMINISTRATIVE not in GEO_ADMIN_LEVELS
    assert GEO_DERIVATIONS_REQUIRING_ACCURACY < GEO_DERIVATIONS
    assert GEO_DERIVATIONS_REQUIRING_ACCURACY == {"admin_unit_centroid", "coverage_area"}


def test_the_workspace_gets_the_vocabularies_without_typing_them(ont) -> None:
    """No geospatial vocabulary is hand-written into React either (Article XI)."""
    generated = typescript_constants(ont)
    assert "GEO_ADMIN_LEVELS" in generated
    assert "GEO_DERIVATIONS" in generated
    assert '"admin_unit_centroid"' in generated
    committed = (REPO_ROOT / "ui" / "src" / "api" / "ontology.ts").read_text("utf-8")
    assert "GEO_ADMIN_LEVELS" in committed
    for name in EVENT_TYPES:
        assert f'"{name}"' in committed
    assert '"has_arrestee"' in committed
    # The declared property travels with the predicate, so a screen can resolve
    # a value to the property it describes without a second lookup.
    assert 'property: "geometry"' in committed


# ── the major bump is honest (ADR-048) ──────────────────────────────────────


def test_precision_is_gone(ont) -> None:
    assert "precision" not in ont.object_type("location").properties
    assert "geometry" in ont.object_type("location").properties
    assert ont.object_type("location").properties["geometry"].type == "geo"
    assert "place" in ont.object_type("location").implements


#: The bump that removed `location.precision`, and the one before it. Named
#: rather than read from `release.json`, because what these cases are about is
#: **that** bump — reading "the current release" made them fail for every later
#: release they had no opinion about (T58 was the first).
PRECISION_REMOVED_IN = "2.0.0"
PRECISION_REMOVED_FROM = "1.7.0"


def _history(version: str) -> dict:
    return json.loads(
        (REPO_ROOT / "ontology" / "history" / f"composed-{version}.json").read_text("utf-8")
    )


def test_the_removal_is_what_makes_the_bump_major() -> None:
    """Diffed between the two committed artifacts, not against today's head."""
    report = compare(_history(PRECISION_REMOVED_FROM), _history(PRECISION_REMOVED_IN))
    assert report.computed == "major"
    assert report.breaking == ["object_types.location.properties.precision: removed"]
    # Everything else in the bump is additive, and the list is worth reading.
    assert "object_types.arrest: added" in report.additive
    assert "interfaces.event: added" in report.additive
    assert "actions.record_event: added" in report.additive


def test_declaring_that_bump_as_minor_would_have_failed_the_gate(tmp_path: Path) -> None:
    """The gate is only worth what it refuses."""
    previous = _history(PRECISION_REMOVED_FROM)
    understated = {
        "version": PRECISION_REMOVED_IN,
        "compatibility": "minor",
        "proposal": "007-events-and-geometry",
        "previous_version": PRECISION_REMOVED_FROM,
        "previous_content_hash": content_hash(previous),
        "modules": {m["name"]: m["version"] for m in previous["modules"]},
    }
    errors = check(REPO_ROOT, release=understated, artifact=_history(PRECISION_REMOVED_IN))
    assert any("declared 'minor' but the diff" in e for e in errors)
    assert any("breaking change without a major bump" in e for e in errors)


def test_the_committed_release_still_declares_its_own_class_honestly() -> None:
    """Whatever the head release is, its declaration matches its diff."""
    release = json.loads((REPO_ROOT / "ontology" / "release.json").read_text("utf-8"))
    assert release["compatibility"] in COMPATIBILITY_ORDER
    composition = compose(ONTOLOGY_PATH)
    from aegis.ontology.generate import composed_artifact
    from aegis.ontology.modules import registry

    current = composed_artifact(composition, registry(composition))
    assert check(REPO_ROOT, release=release, artifact=current) == []


def test_the_prior_module_sources_are_archived() -> None:
    """A major bump keeps what it broke (spec 01 §4), named for the version that
    broke it."""
    archive = REPO_ROOT / "ontology" / "history" / "2.0.0"
    names = {path.name for path in archive.glob("*.yaml")}
    assert names == {"aegis.yaml", "platform.yaml", "criminal-network.yaml"}
    assert "precision:" in (archive / "criminal-network.yaml").read_text("utf-8")
