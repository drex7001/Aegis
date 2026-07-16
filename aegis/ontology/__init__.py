"""Ontology loader, validator, and registry (speckit spec 01, Article XI)."""

from aegis.ontology.loader import (
    KNOWN_ROLES,
    ActionSpec,
    CategorySpec,
    GradingSpec,
    ObjectTypeSpec,
    Ontology,
    OntologyError,
    OntologyValidationError,
    PredicateSpec,
    PropertySpec,
    load,
    load_dict,
)

__all__ = [
    "KNOWN_ROLES",
    "ActionSpec",
    "CategorySpec",
    "GradingSpec",
    "ObjectTypeSpec",
    "Ontology",
    "OntologyError",
    "OntologyValidationError",
    "PredicateSpec",
    "PropertySpec",
    "load",
    "load_dict",
]
