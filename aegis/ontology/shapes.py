"""Structural questions about a composed registry (spec 10 §3.2, ADR-046).

"Which entities are occurrences?" and "which claims say who was there?" have to
be answerable without the core learning that `arrest` or `has_arrestee` exist —
that is Article XIV, and it is what makes the second-domain fixture more than a
gesture.

Four rules, all read off the *shape* of a declaration rather than its name:

===========================  =============================================
The core needs               The rule
===========================  =============================================
event entities               `entity_type` implements ``event``
participation claims         every subject type implements ``event`` **and**
                             every object type implements ``party``
event-place claims           every subject type implements ``event`` **and**
                             every object type implements ``place``
geometry claims              the predicate declares a property of type ``geo``
===========================  =============================================

The names this module *does* use — ``event``, ``place``, ``party`` — are
**platform interfaces**, declared in `ontology/modules/platform.yaml`, which is
the core's own vocabulary. The distinction that matters is not "no strings" but
"no *domain* strings": a second domain implements the same interfaces under its
own type names and every rule here keeps working.

Rules are evaluated on **expanded** type lists, so a declaration may name either
an interface or concrete types. `took_place_at` names three concrete event types
because travel has no single place, and it is still recognised as an event-place
predicate.
"""

from __future__ import annotations

from aegis.ontology.loader import Ontology, PredicateSpec

#: Platform interfaces the structural rules are written against.
EVENT_INTERFACE = "event"
PLACE_INTERFACE = "place"
PARTY_INTERFACE = "party"

#: The property type a geometry claim carries. The `geo` slot P3 added to the
#: DSL; ADR-047's `property:` declaration is what connects a predicate to it.
GEO_PROPERTY_TYPE = "geo"


def event_object_types(ontology: Ontology) -> list[str]:
    """Object types that are occurrences, in declaration order.

    Empty when no module declares one — which is the correct answer for a
    composition without an event domain, not an error.
    """
    if EVENT_INTERFACE not in ontology.interfaces:
        return []
    return ontology.implementors(EVENT_INTERFACE)


def place_object_types(ontology: Ontology) -> list[str]:
    """Object types that can carry geometry, in declaration order."""
    if PLACE_INTERFACE not in ontology.interfaces:
        return []
    return ontology.implementors(PLACE_INTERFACE)


def is_event_type(ontology: Ontology, entity_type: str) -> bool:
    return entity_type in set(event_object_types(ontology))


def participation_predicates(ontology: Ontology) -> dict[str, PredicateSpec]:
    """Predicates that say who was at an occurrence, and as what.

    The **role is the predicate**, so this returns the role vocabulary itself
    (ADR-046). A caller that wants a display name reads ``spec.label``.
    """
    return _predicates_between(ontology, EVENT_INTERFACE, PARTY_INTERFACE)


def event_place_predicates(ontology: Ontology) -> dict[str, PredicateSpec]:
    """Predicates that say where an occurrence happened.

    Plural on purpose: travel has an origin *and* a destination, so an event may
    relate to more than one place and the map draws a feature per claim.
    """
    return _predicates_between(ontology, EVENT_INTERFACE, PLACE_INTERFACE)


def geometry_predicates(ontology: Ontology) -> dict[str, PredicateSpec]:
    """Predicates whose declared property is a geometry (ADR-047)."""
    return ontology.predicates_carrying(GEO_PROPERTY_TYPE)


def _predicates_between(
    ontology: Ontology, subject_interface: str, object_interface: str
) -> dict[str, PredicateSpec]:
    subjects = _implementors(ontology, subject_interface)
    objects = _implementors(ontology, object_interface)
    if not subjects or not objects:
        return {}
    return {
        name: spec
        for name, spec in ontology.predicates.items()
        # `is_literal` short-circuits before `entity_object_types`, which is
        # empty for a literal predicate and would otherwise make `<=` vacuously
        # true — `summarized_as` is subjected to events and must not be read as
        # a participation claim.
        if not spec.is_literal
        and set(spec.subject) <= subjects
        and set(spec.entity_object_types) <= objects
        and spec.entity_object_types
    }


def _implementors(ontology: Ontology, interface: str) -> set[str]:
    if interface not in ontology.interfaces:
        return set()
    return set(ontology.implementors(interface))


__all__ = [
    "EVENT_INTERFACE",
    "GEO_PROPERTY_TYPE",
    "PARTY_INTERFACE",
    "PLACE_INTERFACE",
    "event_object_types",
    "event_place_predicates",
    "geometry_predicates",
    "is_event_type",
    "participation_predicates",
    "place_object_types",
]
