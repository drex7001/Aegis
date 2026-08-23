"""The structural rules the core uses instead of domain names (T56, spec 10 §3.2).

Article XIV in four functions. "Which entities are occurrences?" and "which
claims say who was there?" are answered from the *shape* of a declaration — the
interfaces its endpoints implement — so a second domain gets all of it by
implementing the same interfaces under its own type names.

The names these rules do use, `event`/`place`/`party`, are **platform**
interfaces. The distinction that matters is not "no strings" but "no *domain*
strings", and `test_second_domain.py` is what keeps the two apart.
"""

from __future__ import annotations

import pytest

from aegis.ontology import compose, load, load_dict
from aegis.ontology.modules import registry
from aegis.ontology.shapes import (
    event_object_types,
    event_place_predicates,
    geometry_predicates,
    is_event_type,
    participation_predicates,
    place_object_types,
)
from tests.support.paths import ONTOLOGY_PATH, REPO_ROOT

pytestmark = pytest.mark.requirement("Article-XIV", "ADR-046", "ADR-047", "T56")

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "ontology" / "border-cargo-composition.yaml"


@pytest.fixture(scope="module")
def ont():
    return load(ONTOLOGY_PATH)


def test_occurrences_are_found_through_the_interface(ont) -> None:
    assert event_object_types(ont) == ["meeting", "arrest", "travel", "observation"]
    assert place_object_types(ont) == ["location"]
    assert is_event_type(ont, "arrest")
    assert not is_event_type(ont, "person")
    assert not is_event_type(ont, "location")


def test_participation_predicates_are_the_role_vocabulary(ont) -> None:
    roles = participation_predicates(ont)
    assert set(roles) == {
        "has_participant",
        "has_attendee",
        "has_arrestee",
        "has_arresting_officer",
        "has_traveller",
        "has_observer",
    }
    # The role *is* the predicate, so its label is the role's name on a screen.
    assert roles["has_arrestee"].label == "Arrestee"


def test_the_summary_claim_is_not_read_as_participation(ont) -> None:
    """`summarized_as` is subjected to events and carries a literal.

    Worth its own case because the natural implementation gets it wrong: an
    empty object-type list is a subset of every set, so a literal predicate
    passes a naive `<=` check and the event's own description would be counted
    as a person who was there.
    """
    assert "summarized_as" not in participation_predicates(ont)
    assert "summarized_as" not in event_place_predicates(ont)
    assert "has_geometry" not in participation_predicates(ont)


def test_place_predicates_include_both_ends_of_a_journey(ont) -> None:
    """Plural on purpose: travel has an origin *and* a destination."""
    assert set(event_place_predicates(ont)) == {
        "took_place_at",
        "travelled_from",
        "travelled_to",
    }


def test_a_predicate_naming_concrete_types_is_still_recognised(ont) -> None:
    """`took_place_at` names three event types rather than the interface.

    The rule is evaluated on expanded types, so a declaration may name either —
    which is what let travel be excluded without losing the recognition.
    """
    assert ont.predicate("took_place_at").subject_interfaces == ()
    assert "took_place_at" in event_place_predicates(ont)


def test_geometry_is_found_by_property_type(ont) -> None:
    assert set(geometry_predicates(ont)) == {"has_geometry"}


def test_a_composition_without_places_answers_emptily_rather_than_failing() -> None:
    """The correct answer for a domain with no geography, not an error."""
    border_cargo = registry(compose(FIXTURE))
    assert place_object_types(border_cargo) == []
    assert geometry_predicates(border_cargo) == {}
    assert event_object_types(border_cargo) == []
    assert participation_predicates(border_cargo) == {}


def test_a_second_domain_gets_the_rules_by_implementing_the_interfaces(ont) -> None:
    """The acceptance criterion, in one construction.

    A fictional `port` type implementing `place`, with its own geometry
    predicate, is recognised by every rule here without one line of code
    knowing the word `port`.
    """
    document = compose(ONTOLOGY_PATH).document
    document = {
        **document,
        "object_types": {
            **document["object_types"],
            "port": {
                "label": "Port",
                "implements": ["place"],
                "properties": {"name": {"type": "text"}, "geometry": {"shared": "geometry"}},
                "display": {"title": "name"},
            },
        },
        "predicates": {
            **document["predicates"],
            "berthed_at": {
                "subject": ["port"],
                "object": "literal",
                "property": "geometry",
            },
        },
    }
    extended = load_dict(document)
    assert set(place_object_types(extended)) == {"location", "port"}
    assert set(geometry_predicates(extended)) == {"has_geometry", "berthed_at"}
    # `took_place_at` now reaches ports too, because `place` gained an
    # implementor — the endpoint was declared as an interface for exactly this.
    assert "port" in extended.predicate("took_place_at").object
