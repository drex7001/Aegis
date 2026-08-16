"""Parse and validate ontology/aegis.yaml; expose it as a typed registry.

Validation rules are spec 01 §6. Every violation is reported with the YAML path
that caused it, and all violations are collected before raising — one run tells
you everything that is wrong.

Since P3 T30 the committed artifact is a *composition* manifest (spec 08 §2), so
``load`` dispatches: a document with a ``composition:`` key is resolved by
``aegis.ontology.modules``, and anything else is validated here as a flat v1
document. The flat path is not legacy — module files, fixtures, and every
mutation test in ``tests/contract/test_ontology.py`` are flat documents, and
spec 08 §9 rule 18 keeps them valid on purpose.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal, Sequence, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from aegis.ontology.registries import (
    PAYLOAD_SCHEMAS,
    SIDE_EFFECTS,
    SUBMISSION_CRITERIA,
)

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


PropertyType = Literal[
    "text", "identifier", "date", "timestamp", "int", "decimal", "geo", "ref"
]


class SharedPropertySpec(BaseModel):
    """A property defined once and referenced by many object types (spec 08 §3).

    Carries everything that must be identical wherever it appears — type,
    cardinality, sensitivity, conflict policy. ``required`` is deliberately
    absent: whether a person must have a name is a fact about persons, not
    about names.
    """

    model_config = ConfigDict(extra="forbid")
    type: PropertyType
    many: bool = False
    sensitivity: str | None = None
    conflicts: Literal["preserve"] | None = None
    label: str | None = None


class PropertySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    #: Optional only because a `shared:` reference supplies it. After loading,
    #: every property in the registry has a resolved type — the reference form
    #: is expanded in place so consumers never learn the difference (spec 08 §3).
    type: PropertyType | None = None
    required: bool = False
    many: bool = False
    sensitivity: str | None = None
    conflicts: Literal["preserve"] | None = None
    #: The shared property this was declared from, retained after resolution so
    #: codegen and object views can render one definition rather than a copy.
    shared: str | None = None


class InterfaceSpec(BaseModel):
    """A named shape over object types (spec 08 §4).

    Membership is declared by the implementor (`object_types.*.implements`),
    not listed here — see ADR-041. An interface therefore carries only what it
    *requires*: the shared properties every implementor must present.
    """

    model_config = ConfigDict(extra="forbid")
    label: str | None = None
    properties: list[str] = Field(default_factory=list)


class ObjectTypeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    properties: dict[str, PropertySpec] = Field(default_factory=dict)
    display: DisplaySpec | None = None
    #: Interfaces this type implements. Declared here rather than as a member
    #: list on the interface so a domain module can implement a platform
    #: interface without editing the platform module (ADR-041).
    implements: list[str] = Field(default_factory=list)


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
    #: Interfaces named in the declaration, retained after `subject`/`object`
    #: are expanded to concrete implementors. The expansion is what the store
    #: sees — a claim records concrete types, never an interface — so keeping
    #: the declared form here is the only way codegen can render it (spec 08 §4).
    subject_interfaces: tuple[str, ...] = ()
    object_interfaces: tuple[str, ...] = ()

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


#: The closed parameter type list (spec 08 §6.2), sized against the real
#: Phase 2 request bodies rather than an illustration. The validator rejects
#: anything outside it, so a domain module cannot invent a value shape the
#: actions layer has no way to check.
ParameterType = Literal[
    "text",
    "identifier",
    "ref",
    "predicate",
    "object_type",
    "literal",
    "handling_code",
    "source_type",
    "grade",
    "grading_scheme",
    "assertion_type",
    "enum",
    "bool",
    "int",
    "decimal",
    "date",
    "timestamp",
    "json",
]

#: What a `ref` may point at. Platform rows only — a reference to a *domain*
#: row is an entity, and `to: entity` covers every object type at once.
REF_TARGETS = frozenset(
    {
        "entity",
        "claim",
        "case",
        "source_record",
        "evidence_item",
        "suggestion",
        "mention",
        "user",
    }
)

#: type -> the modifier key it requires. Any other type carrying a modifier is
#: a validation error, so `{type: text, values: [...]}` cannot look like it
#: constrains something.
PARAMETER_MODIFIERS: dict[str, str] = {
    "ref": "to",
    "grade": "dimension",
    "enum": "values",
    "json": "payload_schema",
}


class ParameterSpec(BaseModel):
    """One declared parameter of an action (spec 08 §6.1).

    Declares the action's **public request contract** — what an API, CLI, or
    SDK caller may send. Undeclared parameters are rejected by the generated
    request model, which is what stops a caller reaching a field the ontology
    never described.
    """

    model_config = ConfigDict(extra="forbid")

    type: ParameterType
    required: bool = False
    default: Any = None
    many: bool = False
    description: str | None = None
    #: `ref` — which table the id points at.
    to: str | None = None
    #: `grade` — which grading dimension the value is drawn from.
    dimension: str | None = None
    #: `enum` — the closed inline list.
    values: list[str] | None = None
    #: `json` — a schema id registered in `aegis.ontology.registries`.
    payload_schema: str | None = None


class SideEffectSpec(BaseModel):
    """A declared post-commit hook. Parsed and stored; never executed in P3.

    Written in YAML as a one-entry mapping — `- refresh_projection: edge_projection`
    — which reads better in a list than `{hook: ..., target: ...}` and is what
    spec 08 §6 shows. Normalized here so the registry has one shape.
    """

    model_config = ConfigDict(extra="forbid")
    hook: str
    target: str

    @model_validator(mode="before")
    @classmethod
    def _accept_single_key_mapping(cls, value: Any) -> Any:
        if isinstance(value, dict) and len(value) == 1 and "hook" not in value:
            (hook, target), = value.items()
            return {"hook": hook, "target": target}
        return value


class ActionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    roles: list[str] = Field(min_length=1)
    audit: bool
    dual_control_for: list[str] = Field(default_factory=list)
    parameters: dict[str, ParameterSpec] = Field(default_factory=dict)
    #: Named predicates the actions layer evaluates before the write; a failure
    #: is an audited denial, not a silent 403 (spec 08 §6.4).
    submission_criteria: list[str] = Field(default_factory=list)
    side_effects: list[SideEffectSpec] = Field(default_factory=list)


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


class ModuleInfo(BaseModel):
    """A resolved module, as the composed registry reports it (spec 08 §2).

    Lives beside the registry rather than with the manifest parser because it is
    part of what a caller reads off ``Ontology`` — the manifest models in
    ``aegis.ontology.modules`` are input shapes and stop existing after a load.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    namespace: str
    version: str
    label: str | None = None
    imports: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    #: Every name this module declares, sorted. Kept for disabled modules too —
    #: it is the only way to answer "does anything recorded still speak this
    #: module's vocabulary?" once the module is out of the registry (§2.6).
    declares: tuple[str, ...] = ()


# ── the registry ────────────────────────────────────────────────────────────


class Ontology(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    namespace: str
    handling_codes: list[str] = Field(min_length=1)
    source_types: list[str] = Field(min_length=1)
    grading: GradingSpec
    categories: dict[str, CategorySpec]
    shared_properties: dict[str, SharedPropertySpec] = Field(default_factory=dict)
    interfaces: dict[str, InterfaceSpec] = Field(default_factory=dict)
    object_types: dict[str, ObjectTypeSpec]
    predicates: dict[str, PredicateSpec]
    event_types: dict[str, Any] = Field(default_factory=dict)  # Phase 4 (spec 01 §2)
    actions: dict[str, ActionSpec]

    #: Resolved modules, populated by the composition loader and empty for a
    #: flat document — which is exactly right: a flat file is one implicit
    #: module, and nothing may pretend otherwise.
    modules: dict[str, ModuleInfo] = Field(default_factory=dict)
    #: Declared name -> owning module. Derived from where a name is declared
    #: (ADR-037), never from a hand-written list.
    owners: dict[str, str] = Field(default_factory=dict)

    def owner_module(self, name: str) -> str | None:
        """The module that declares ``name``, or None for a flat document."""
        return self.owners.get(name)

    def implementors(self, interface: str) -> list[str]:
        """Object types implementing ``interface``, in declaration order.

        Derived from ``object_types.*.implements`` rather than stored on the
        interface, which is what lets a domain module implement a platform
        interface without editing it (ADR-041).
        """
        if interface not in self.interfaces:
            raise OntologyError(
                f"unknown interface {interface!r} (declared: {sorted(self.interfaces)})"
            )
        return [
            name for name, spec in self.object_types.items() if interface in spec.implements
        ]

    def expand_types(self, names: Sequence[str]) -> list[str]:
        """Replace any interface name with its implementors, preserving order."""
        expanded: list[str] = []
        for name in names:
            for value in self.implementors(name) if name in self.interfaces else [name]:
                if value not in expanded:
                    expanded.append(value)
        return expanded

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


# ── semantic validation (spec 01 §6, spec 08 §9) ────────────────────────────


def _shared_property_errors(ont: Ontology) -> list[str]:
    """Spec 08 §9 rule 13 — `shared:` references resolve and override nothing."""
    errors: list[str] = []
    for tname, otype in ont.object_types.items():
        for pname, prop in otype.properties.items():
            where = f"object_types.{tname}.properties.{pname}"
            if prop.shared is None:
                if prop.type is None:
                    errors.append(
                        f"{where}: declare either a `type` or a `shared` reference"
                    )
                continue
            if prop.shared not in ont.shared_properties:
                errors.append(
                    f"{where}.shared: unknown shared property {prop.shared!r} "
                    f"(declared: {sorted(ont.shared_properties)})"
                )
                continue
            # A shared property exists so that one answer is given everywhere.
            # Letting a reference restate `type` or `sensitivity` would make it
            # a default rather than a definition — and a *quieter* one than an
            # inline property, because the reader would have to check both.
            for field in ("type", "sensitivity"):
                if getattr(prop, field) is not None:
                    errors.append(
                        f"{where}.{field}: a `shared:` reference may not override "
                        f"{field!r} — change shared_properties.{prop.shared} or "
                        "declare an inline property instead"
                    )
            if prop.many:
                errors.append(
                    f"{where}.many: cardinality comes from "
                    f"shared_properties.{prop.shared}"
                )
    return errors


def _interface_errors(ont: Ontology) -> list[str]:
    """Spec 08 §9 rule 14 — interfaces, their requirements, and their implementors."""
    errors: list[str] = []
    for iname, interface in ont.interfaces.items():
        for required in interface.properties:
            if required not in ont.shared_properties:
                errors.append(
                    f"interfaces.{iname}.properties: unknown shared property "
                    f"{required!r} (declared: {sorted(ont.shared_properties)})"
                )

    for tname, otype in ont.object_types.items():
        for iname in otype.implements:
            if iname not in ont.interfaces:
                errors.append(
                    f"object_types.{tname}.implements: unknown interface {iname!r} "
                    f"(declared: {sorted(ont.interfaces)})"
                )
                continue
            # The point of an interface is that a reader of `subject: [party]`
            # knows what every match carries. A member missing a required
            # property makes that false for one type and silently wrong for the
            # caller who trusted it.
            carried = {
                prop.shared for prop in otype.properties.values() if prop.shared is not None
            }
            for required in ont.interfaces[iname].properties:
                if required in ont.shared_properties and required not in carried:
                    errors.append(
                        f"object_types.{tname}.implements: {iname!r} requires shared "
                        f"property {required!r}, which {tname!r} does not declare"
                    )

    # A predicate targeting an interface nothing implements matches no entity
    # and can never be recorded. That is a modelling mistake, not a valid
    # empty state — unlike an interface nobody references, which is fine.
    for pname, pred in ont.predicates.items():
        endpoints = [("subject", pred.subject)]
        if not pred.is_literal:
            endpoints.append(("object", pred.object))
        for role, names in endpoints:
            for name in names:
                if name in ont.interfaces and not ont.implementors(name):
                    errors.append(
                        f"predicates.{pname}.{role}: interface {name!r} has no "
                        "implementing object type, so the predicate can never "
                        "be satisfied"
                    )
    return errors


def _action_errors(ont: Ontology) -> list[str]:
    """Spec 08 §9 rules 15–17 — parameters, criteria, and side effects."""
    errors: list[str] = []
    for aname, action in ont.actions.items():
        for pname, parameter in action.parameters.items():
            where = f"actions.{aname}.parameters.{pname}"
            if not _NAME_RE.match(pname):
                errors.append(f"{where}: name must be snake_case ([a-z][a-z0-9_]*)")

            required_modifier = PARAMETER_MODIFIERS.get(parameter.type)
            for modifier in set(PARAMETER_MODIFIERS.values()):
                value = getattr(parameter, modifier)
                if value is None:
                    continue
                if modifier != required_modifier:
                    errors.append(
                        f"{where}.{modifier}: only valid on a "
                        f"{[t for t, m in PARAMETER_MODIFIERS.items() if m == modifier][0]!r} "
                        f"parameter, not {parameter.type!r}"
                    )
            if required_modifier is not None and getattr(parameter, required_modifier) is None:
                errors.append(
                    f"{where}.{required_modifier}: required for a "
                    f"{parameter.type!r} parameter"
                )

            if parameter.type == "ref" and parameter.to is not None:
                if parameter.to not in REF_TARGETS:
                    errors.append(
                        f"{where}.to: unknown reference target {parameter.to!r} "
                        f"(known: {sorted(REF_TARGETS)})"
                    )
            if parameter.type == "grade" and parameter.dimension is not None:
                if parameter.dimension not in GRADING_DIMENSIONS:
                    errors.append(
                        f"{where}.dimension: unknown grading dimension "
                        f"{parameter.dimension!r} (declared: {list(GRADING_DIMENSIONS)})"
                    )
            if parameter.type == "enum" and not parameter.values:
                errors.append(f"{where}.values: an enum needs at least one value")
            if parameter.type == "json" and parameter.payload_schema is not None:
                # Without this, `json` would be a hole straight through the
                # closed suggestion-kind list (ADR-031 §1).
                if parameter.payload_schema not in PAYLOAD_SCHEMAS:
                    errors.append(
                        f"{where}.payload_schema: unregistered schema "
                        f"{parameter.payload_schema!r} (registered: {sorted(PAYLOAD_SCHEMAS)})"
                    )
            if parameter.required and parameter.default is not None:
                errors.append(
                    f"{where}.default: a required parameter has no default — "
                    "the caller must supply it"
                )

        for criterion in action.submission_criteria:
            if criterion not in SUBMISSION_CRITERIA:
                errors.append(
                    f"actions.{aname}.submission_criteria: {criterion!r} is not "
                    f"implemented (registered: {sorted(SUBMISSION_CRITERIA)}). A "
                    "criterion must be enforceable before it can be declared."
                )
        if len(set(action.submission_criteria)) != len(action.submission_criteria):
            errors.append(
                f"actions.{aname}.submission_criteria: duplicate criterion"
            )

        for effect in action.side_effects:
            if effect.hook not in SIDE_EFFECTS:
                errors.append(
                    f"actions.{aname}.side_effects.{effect.hook}: unknown hook "
                    f"(registered: {sorted(SIDE_EFFECTS)})"
                )
    return errors


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
        ("interfaces", ont.interfaces),
        ("shared_properties", ont.shared_properties),
    ):
        for name in names:
            if not _NAME_RE.match(name):
                errors.append(f"{section}.{name}: name must be snake_case ([a-z][a-z0-9_]*)")

    # rule 1: unique names ACROSS sections (they share the claim/DDL namespace).
    # Interfaces join the same namespace: a predicate's `subject:` cannot tell
    # an interface from an object type by shape, so one name must mean one thing.
    seen: dict[str, str] = {}
    for section, names in (
        ("object_types", ont.object_types),
        ("predicates", ont.predicates),
        ("actions", ont.actions),
        ("interfaces", ont.interfaces),
    ):
        for name in names:
            if name in seen:
                errors.append(
                    f"{section}.{name}: duplicate name — already declared in {seen[name]}"
                )
            else:
                seen[name] = section

    errors += _shared_property_errors(ont)
    errors += _interface_errors(ont)
    errors += _action_errors(ont)

    # rule 2: predicate endpoint types exist (object may be the string 'literal',
    # or a list of object types optionally including 'literal' for mixed objects).
    # An interface name is accepted here and expanded to its implementors after
    # validation, so a predicate may target `party` (spec 08 §4).
    declared = set(ont.object_types) | set(ont.interfaces)
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
    for shared_name, shared in ont.shared_properties.items():
        if shared.sensitivity is not None and shared.sensitivity not in ont.handling_codes:
            errors.append(
                f"shared_properties.{shared_name}.sensitivity: unknown handling code "
                f"{shared.sensitivity!r} (declared: {ont.handling_codes})"
            )
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


# ── resolution (spec 08 §3–4) ───────────────────────────────────────────────


def _resolved(ont: Ontology) -> Ontology:
    """Expand `shared:` references and interface endpoints, in place.

    Both expansions happen once, at load, so that **no consumer has to know
    the v2 syntax exists**. ``authz.filters`` still reads
    ``object_type.properties['nic'].sensitivity`` and gets the shared value;
    ``actions.service`` still checks ``entity_type in predicate.subject`` and
    gets concrete types. The declared form survives on ``PropertySpec.shared``
    and ``PredicateSpec.*_interfaces`` for codegen, which is the one consumer
    that does need to know.

    Runs only after validation passes, so every reference here resolves.
    """
    if not ont.shared_properties and not ont.interfaces:
        return ont

    object_types = {
        name: spec.model_copy(
            update={
                "properties": {
                    prop_name: _resolve_property(prop, ont)
                    for prop_name, prop in spec.properties.items()
                }
            }
        )
        for name, spec in ont.object_types.items()
    }
    predicates = {
        name: _resolve_predicate(spec, ont) for name, spec in ont.predicates.items()
    }
    return ont.model_copy(update={"object_types": object_types, "predicates": predicates})


def _resolve_property(prop: PropertySpec, ont: Ontology) -> PropertySpec:
    if prop.shared is None:
        return prop
    shared = ont.shared_properties[prop.shared]
    return prop.model_copy(
        update={
            "type": shared.type,
            "many": shared.many,
            "sensitivity": shared.sensitivity,
            # `conflicts` is part of the shared definition, but an inline
            # `conflicts` on the reference is not an override of a stated value
            # — the shared property may simply not have declared one.
            "conflicts": prop.conflicts if shared.conflicts is None else shared.conflicts,
        }
    )


def _resolve_predicate(pred: PredicateSpec, ont: Ontology) -> PredicateSpec:
    update: dict[str, Any] = {}
    subject_interfaces = tuple(name for name in pred.subject if name in ont.interfaces)
    if subject_interfaces:
        update["subject"] = ont.expand_types(pred.subject)
        update["subject_interfaces"] = subject_interfaces
    if not pred.is_literal:
        object_interfaces = tuple(name for name in pred.object if name in ont.interfaces)
        if object_interfaces:
            # 'literal' passes through expand_types untouched: it is not an
            # object type and not an interface, so a mixed entity-or-literal
            # object keeps its literal branch.
            update["object"] = ont.expand_types(pred.object)
            update["object_interfaces"] = object_interfaces
    return pred.model_copy(update=update) if update else pred


def _format_pydantic_errors(exc: ValidationError) -> list[str]:
    formatted = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "<root>"
        formatted.append(f"{loc}: {err['msg']}")
    return formatted


# ── entry points ─────────────────────────────────────────────────────────────


#: Fields the composition loader fills in. A document that declares them is
#: asserting an ownership it cannot know, so they are rejected on input rather
#: than silently overwritten.
_LOADER_OWNED_FIELDS = ("modules", "owners")


def load_dict(data: dict[str, Any], source: str = "<dict>") -> Ontology:
    """Validate a parsed *flat* ontology mapping; raise OntologyValidationError with
    every violation, or return the frozen registry."""
    if not isinstance(data, dict):
        raise OntologyValidationError([f"top level must be a mapping, got {type(data).__name__}"], source)
    reserved = [field for field in _LOADER_OWNED_FIELDS if field in data]
    if reserved:
        raise OntologyValidationError(
            [f"{field}: populated by the composition loader, not declared" for field in reserved],
            source,
        )
    try:
        ont = Ontology.model_validate(data)
    except ValidationError as exc:
        raise OntologyValidationError(_format_pydantic_errors(exc), source) from exc

    errors = _semantic_errors(ont)
    if errors:
        raise OntologyValidationError(errors, source)
    return _resolved(ont)


def load(path: str | Path) -> Ontology:
    """Load and validate an ontology artifact — a composition manifest or a flat file."""
    path = Path(path)
    if not path.exists():
        raise OntologyError(f"ontology file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    # Imported here rather than at module scope: `modules` imports this file for
    # the registry model and the shared error type.
    from aegis.ontology.modules import is_composition, load_composition

    if is_composition(data):
        return load_composition(path, data)
    return load_dict(data, source=str(path))
