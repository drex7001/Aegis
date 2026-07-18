"""Parse and validate ontology/aegis.yaml; expose it as a typed registry.

Validation rules are spec 01 §6. Every violation is reported with the YAML path
that caused it, and all violations are collected before raising — one run tells
you everything that is wrong.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# Roles the platform defines (speckit spec 03 §2). Actions may only reference these.
KNOWN_ROLES = frozenset(
    {"admin", "supervisor", "analyst", "investigator", "evidence_officer", "auditor"}
)

GRADING_DIMENSIONS = ("reliability", "credibility", "verification", "analytic_confidence")

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class OntologyError(Exception):
    """Base error for ontology handling."""


class OntologyValidationError(OntologyError):
    def __init__(self, errors: list[str], source: str = "<dict>") -> None:
        self.errors = errors
        self.source = source
        super().__init__(
            f"ontology validation failed for {source}:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )


# ── section models (structural validation) ─────────────────────────────────


class DisplaySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    subtitle: str | None = None


class PropertySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["text", "identifier", "date", "timestamp", "int", "decimal", "geo", "ref"]
    required: bool = False
    many: bool = False
    sensitivity: str | None = None
    conflicts: Literal["preserve"] | None = None


class ObjectTypeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    properties: dict[str, PropertySpec] = Field(default_factory=dict)
    display: DisplaySpec | None = None


class PredicateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: list[str] = Field(min_length=1)
    # Either the string 'literal' (literal-only), a list of object types, or a
    # list of object types that also contains 'literal' — meaning the object may
    # be an entity of those types *or* a literal value (spec 02 §6).
    object: Union[list[str], Literal["literal"]]
    category: str | None = None
    symmetric: bool = False
    computed: bool = False
    system: bool = False
    #: The object value is a registry identifier, so two subjects carrying the
    #: same value are a reason to *propose* they are the same (spec 05 §3.1).
    #: Declared here rather than hardcoded in the ER rules, so the core stays
    #: domain-neutral (Article XIV) — a new domain adds identifiers by
    #: declaring them, not by editing the rule engine.
    identifier: bool = False

    @property
    def is_literal(self) -> bool:
        """The object must be a literal value (never an entity)."""
        return self.object == "literal"

    @property
    def allows_literal(self) -> bool:
        """A literal object value is acceptable."""
        return self.is_literal or "literal" in self.object

    @property
    def entity_object_types(self) -> list[str]:
        """Object types an entity object may have ([] for literal-only)."""
        if self.is_literal:
            return []
        return [name for name in self.object if name != "literal"]

    @property
    def allows_entity(self) -> bool:
        """An entity object is acceptable."""
        return bool(self.entity_object_types)


class CategorySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str | None = None
    color: str | None = None


class ActionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    roles: list[str] = Field(min_length=1)
    audit: bool
    dual_control_for: list[str] = Field(default_factory=list)


class GradedScale(BaseModel):
    model_config = ConfigDict(extra="forbid")
    normalized: list[str] = Field(min_length=1)


class GradingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reliability: GradedScale
    credibility: GradedScale
    verification: list[str] = Field(min_length=1)
    analytic_confidence: list[str] = Field(min_length=1)
    # scheme name -> original grade -> {dimension: normalized value}
    schemes: dict[str, dict[str, dict[str, str]]] = Field(default_factory=dict)

    def values_for(self, dimension: str) -> list[str]:
        value = getattr(self, dimension)
        return value.normalized if isinstance(value, GradedScale) else value


# ── the registry ────────────────────────────────────────────────────────────


class Ontology(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    namespace: str
    handling_codes: list[str] = Field(min_length=1)
    source_types: list[str] = Field(min_length=1)
    grading: GradingSpec
    categories: dict[str, CategorySpec]
    object_types: dict[str, ObjectTypeSpec]
    predicates: dict[str, PredicateSpec]
    event_types: dict[str, Any] = Field(default_factory=dict)  # Phase 4 (spec 01 §2)
    actions: dict[str, ActionSpec]

    def handling_rank(self, code: str) -> int:
        """Clearance level required for a handling code (index in the ordered list)."""
        try:
            return self.handling_codes.index(code)
        except ValueError:
            raise OntologyError(
                f"unknown handling code {code!r} (declared: {self.handling_codes})"
            ) from None

    def object_type(self, name: str) -> ObjectTypeSpec:
        try:
            return self.object_types[name]
        except KeyError:
            raise OntologyError(
                f"unknown object type {name!r} (declared: {sorted(self.object_types)})"
            ) from None

    def predicate(self, name: str) -> PredicateSpec:
        try:
            return self.predicates[name]
        except KeyError:
            raise OntologyError(
                f"unknown predicate {name!r} (declared: {sorted(self.predicates)})"
            ) from None

    def identifier_predicates(self) -> dict[str, PredicateSpec]:
        """Predicates whose object value is a registry identifier (spec 05 §3.1).

        The deterministic ER rules iterate this instead of naming NIC or
        vehicle registrations, so the rule engine carries no domain vocabulary
        (Article XIV).
        """
        return {
            name: spec for name, spec in self.predicates.items() if spec.identifier
        }

    def action(self, name: str) -> ActionSpec:
        try:
            return self.actions[name]
        except KeyError:
            raise OntologyError(
                f"unknown action {name!r} (declared: {sorted(self.actions)})"
            ) from None

    def normalize_grade(self, scheme: str, original: str) -> dict[str, str]:
        """Map an external grade to internal normalized dimensions (spec 01 §3.2)."""
        schemes = self.grading.schemes
        if scheme not in schemes:
            raise OntologyError(f"unknown grading scheme {scheme!r} (declared: {sorted(schemes)})")
        if original not in schemes[scheme]:
            raise OntologyError(
                f"grade {original!r} not defined in scheme {scheme!r} "
                f"(declared: {sorted(schemes[scheme])})"
            )
        return dict(schemes[scheme][original])


# ── semantic validation (spec 01 §6) ────────────────────────────────────────


def _semantic_errors(ont: Ontology) -> list[str]:
    errors: list[str] = []

    # rule 7: version format (the ≥-previous comparison is CI's job)
    if not _SEMVER_RE.match(ont.version):
        errors.append(f"version: {ont.version!r} is not MAJOR.MINOR.PATCH semver")

    # rule 4: handling codes unique (order = the list order)
    if len(set(ont.handling_codes)) != len(ont.handling_codes):
        errors.append(f"handling_codes: duplicates in {ont.handling_codes}")

    if len(set(ont.source_types)) != len(ont.source_types):
        errors.append(f"source_types: duplicates in {ont.source_types}")

    # naming hygiene for referenceable names
    for section, names in (
        ("object_types", ont.object_types),
        ("predicates", ont.predicates),
        ("actions", ont.actions),
        ("categories", ont.categories),
    ):
        for name in names:
            if not _NAME_RE.match(name):
                errors.append(f"{section}.{name}: name must be snake_case ([a-z][a-z0-9_]*)")

    # rule 1: unique names ACROSS sections (they share the claim/DDL namespace)
    seen: dict[str, str] = {}
    for section, names in (
        ("object_types", ont.object_types),
        ("predicates", ont.predicates),
        ("actions", ont.actions),
    ):
        for name in names:
            if name in seen:
                errors.append(
                    f"{section}.{name}: duplicate name — already declared in {seen[name]}"
                )
            else:
                seen[name] = section

    # rule 2: predicate endpoint types exist (object may be the string 'literal',
    # or a list of object types optionally including 'literal' for mixed objects)
    declared = set(ont.object_types)
    for pname, pred in ont.predicates.items():
        for stype in pred.subject:
            if stype not in declared:
                errors.append(
                    f"predicates.{pname}.subject: unknown object type {stype!r} "
                    f"(declared object_types: {sorted(declared)})"
                )
        if not pred.is_literal:
            if not pred.allows_entity:
                errors.append(
                    f"predicates.{pname}.object: ['literal'] is redundant — "
                    "use the string form object: literal"
                )
            for otype in pred.entity_object_types:
                if otype not in declared:
                    errors.append(
                        f"predicates.{pname}.object: unknown object type {otype!r} "
                        f"(declared object_types: {sorted(declared)})"
                    )
        # rule 3: category exists
        if pred.category is not None and pred.category not in ont.categories:
            errors.append(
                f"predicates.{pname}.category: unknown category {pred.category!r} "
                f"(declared: {sorted(ont.categories)})"
            )

    # rule 3: property sensitivity is a declared handling code
    for tname, otype_spec in ont.object_types.items():
        for prop_name, prop in otype_spec.properties.items():
            if prop.sensitivity is not None and prop.sensitivity not in ont.handling_codes:
                errors.append(
                    f"object_types.{tname}.properties.{prop_name}.sensitivity: "
                    f"unknown handling code {prop.sensitivity!r} "
                    f"(declared: {ont.handling_codes})"
                )
        if otype_spec.display is not None:
            for field_name in filter(None, (otype_spec.display.title, otype_spec.display.subtitle)):
                if field_name not in otype_spec.properties:
                    errors.append(
                        f"object_types.{tname}.display: references undeclared property "
                        f"{field_name!r}"
                    )

    # rule 5: every action audited, roles known
    for aname, action in ont.actions.items():
        if action.audit is not True:
            errors.append(f"actions.{aname}.audit: must be true (Article X — all actions audited)")
        for role in action.roles:
            if role not in KNOWN_ROLES:
                errors.append(
                    f"actions.{aname}.roles: unknown role {role!r} "
                    f"(known roles: {sorted(KNOWN_ROLES)})"
                )

    # rule 6: scheme maps target only declared dimensions/values
    for scheme, grades in ont.grading.schemes.items():
        for grade, mapping in grades.items():
            for dimension, value in mapping.items():
                if dimension not in GRADING_DIMENSIONS:
                    errors.append(
                        f"grading.schemes.{scheme}.{grade}: unknown dimension {dimension!r} "
                        f"(declared: {list(GRADING_DIMENSIONS)})"
                    )
                    continue
                allowed = ont.grading.values_for(dimension)
                if value not in allowed:
                    errors.append(
                        f"grading.schemes.{scheme}.{grade}.{dimension}: "
                        f"{value!r} is not a declared {dimension} value ({allowed})"
                    )

    return errors


def _format_pydantic_errors(exc: ValidationError) -> list[str]:
    formatted = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "<root>"
        formatted.append(f"{loc}: {err['msg']}")
    return formatted


# ── entry points ─────────────────────────────────────────────────────────────


def load_dict(data: dict[str, Any], source: str = "<dict>") -> Ontology:
    """Validate a parsed ontology mapping; raise OntologyValidationError with every
    violation, or return the frozen registry."""
    if not isinstance(data, dict):
        raise OntologyValidationError([f"top level must be a mapping, got {type(data).__name__}"], source)
    try:
        ont = Ontology.model_validate(data)
    except ValidationError as exc:
        raise OntologyValidationError(_format_pydantic_errors(exc), source) from exc

    errors = _semantic_errors(ont)
    if errors:
        raise OntologyValidationError(errors, source)
    return ont


def load(path: str | Path) -> Ontology:
    """Load and validate an ontology YAML file."""
    path = Path(path)
    if not path.exists():
        raise OntologyError(f"ontology file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return load_dict(data, source=str(path))
