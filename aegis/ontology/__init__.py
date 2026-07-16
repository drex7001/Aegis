"""Ontology loader, validator, and registry (speckit spec 01, Article XI)."""

from aegis.ontology.loader import (
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
