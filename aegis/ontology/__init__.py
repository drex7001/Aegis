"""Ontology loader, validator, and registry (speckit spec 01, Article XI)."""

from aegis.ontology.loader import (
    KNOWN_ROLES,
    ActionSpec,
    CategorySpec,
    GradingSpec,
    ModuleInfo,
    ObjectTypeSpec,
    Ontology,
    OntologyError,
    OntologyValidationError,
    PredicateSpec,
    PropertySpec,
    load,
    load_dict,
)
from aegis.ontology.modules import (
    Composition,
    compose,
    disabled_vocabulary_in_use,
    is_composition,
    load_composition,
)

__all__ = [
    "KNOWN_ROLES",
    "ActionSpec",
    "CategorySpec",
    "Composition",
    "GradingSpec",
    "ModuleInfo",
    "ObjectTypeSpec",
    "Ontology",
    "OntologyError",
    "OntologyValidationError",
    "PredicateSpec",
    "PropertySpec",
    "compose",
    "disabled_vocabulary_in_use",
    "is_composition",
    "load",
    "load_composition",
    "load_dict",
]
