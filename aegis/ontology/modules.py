"""Resolve an ontology composition — platform module + domain modules — into one registry.

Spec 08 §2, ADR-037. ``ontology/aegis.yaml`` stays the single artifact Article XI
names; its content became a manifest over module files. This module reads that
manifest, resolves each module, checks what one module is allowed to say about
another, and hands the merged document to the ordinary spec 01 validator.

Two design points are load-bearing and easy to get wrong later:

* **Names are not prefixed.** ``claim.predicate`` is an immutable TEXT column
  (ADR-013), so a lexical namespace would mean rewriting recorded rows or
  translating on every read. Names stay globally unique instead, and a
  collision across modules is an error rather than a shadowing rule.
* **Ownership is derived, never declared.** The module that declares a name owns
  it. A hand-written ``owns:`` list in the manifest would be a second source of
  truth sitting next to the sections it describes, free to drift from them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal

import yaml
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from aegis.ontology.loader import (
    ModuleInfo,
    Ontology,
    OntologyError,
    OntologyValidationError,
    _format_pydantic_errors,
    load_dict,
)

_MODULE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_NAMESPACE_RE = re.compile(r"^[a-z][a-z0-9._/-]*$")

#: Sections a single module owns outright. Two modules declaring one is a
#: collision, the same as two modules declaring the same predicate: there is no
#: meaningful merge of two clearance ladders or two grading models.
SINGLE_OWNER_SECTIONS = ("handling_codes", "source_types", "grading")

#: Sections merged by name, with every key attributed to its declaring module.
NAME_KEYED_SECTIONS = (
    "categories",
    "shared_properties",
    "interfaces",
    "object_types",
    "predicates",
    "actions",
)


class ModuleHeader(BaseModel):
    """The ``module:`` block at the top of a module file."""

    model_config = ConfigDict(extra="forbid")

    name: str
    namespace: str
    version: str
    label: str | None = None
    imports: list["ModuleImport"] = Field(default_factory=list)


class ModuleImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module: str
    #: PEP 440 specifier (Article XII — `packaging` is already a dependency and
    #: semver strings are valid PEP 440 versions, so no constraint grammar is
    #: invented for one repository).
    version: str


class CompositionEntry(BaseModel):
    """One row of the manifest's ``composition:`` list."""

    model_config = ConfigDict(extra="forbid")

    module: str
    path: str
    #: The exact version this composition pins. The module file's own
    #: ``module.version`` must agree, so a module cannot be swapped underneath a
    #: composition without the manifest saying so.
    version: str
    enabled: bool = True


class ReleaseDeclaration(BaseModel):
    """The authored half of the release metadata (spec 08 §7.2).

    Neither field can be derived: which proposal justified a bump and what
    compatibility class it claims are statements a person makes. The generator
    records them; T35's CI gate is what makes them mandatory.
    """

    model_config = ConfigDict(extra="forbid")

    proposal: str | None = None
    compatibility: Literal["major", "minor", "patch"] | None = None


class CompositionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    namespace: str
    release: ReleaseDeclaration = Field(default_factory=ReleaseDeclaration)
    composition: list[CompositionEntry] = Field(min_length=1)


ModuleHeader.model_rebuild()


def is_composition(data: Any) -> bool:
    """True when a parsed document is a manifest rather than a flat ontology."""
    return isinstance(data, dict) and "composition" in data


@dataclass(frozen=True, slots=True)
class Composition:
    """A resolved composition, before spec 01 §6 semantic validation runs.

    Exposed rather than kept internal because two callers legitimately need the
    merged document without a registry: the T33 generator, which serializes it
    as the release artifact, and the loader tests, which mutate it to prove each
    validation rule still fires on composed input.
    """

    document: dict[str, Any]
    modules: dict[str, ModuleInfo]
    owners: dict[str, str]
    source: str
    #: The manifest's authored ``release:`` block, carried through so the
    #: generator can record what a person claimed about this bump without
    #: re-reading the manifest (spec 08 §7.2).
    release: dict[str, Any] = field(default_factory=dict)


def compose(path: str | Path, data: dict[str, Any] | None = None) -> Composition:
    """Resolve a composition manifest into one merged document.

    Errors are collected across the whole composition before raising, the same
    discipline spec 01 §6 applies within a file: one run tells you everything
    that is wrong, with the module name and YAML path on every line.
    """
    path = Path(path)
    source = str(path)
    if data is None:
        data = _read_yaml(path, source)

    try:
        manifest = CompositionManifest.model_validate(data)
    except ValidationError as exc:
        raise OntologyValidationError(_format_pydantic_errors(exc), source) from exc

    errors: list[str] = []
    _check_manifest_shape(manifest, errors)

    parsed: dict[str, _ParsedModule] = {}
    for entry in manifest.composition:
        module = _parse_module(path.parent / entry.path, entry, errors)
        if module is not None:
            parsed[entry.module] = module

    # Structural failures stop here: attribution and import checks would report
    # cascading nonsense about modules that did not parse.
    if errors:
        raise OntologyValidationError(errors, source)

    _check_versions(manifest, parsed, errors)
    owners, section_owners = _attribute_names(manifest, parsed, errors)
    _check_imports(manifest, parsed, owners, section_owners, errors)

    if errors:
        raise OntologyValidationError(errors, source)

    return Composition(
        document=_merge(manifest, parsed),
        modules=_module_infos(manifest, parsed),
        owners=owners,
        source=source,
        release=manifest.release.model_dump(),
    )


def registry(composed: Composition) -> Ontology:
    """Validate a composed document and stamp its module metadata onto it."""
    ontology = load_dict(composed.document, source=composed.source)
    return ontology.model_copy(
        update={"modules": composed.modules, "owners": composed.owners}
    )


def load_composition(path: str | Path, data: dict[str, Any] | None = None) -> Ontology:
    """Resolve a composition manifest into one validated registry."""
    return registry(compose(path, data))


class _ParsedModule:
    """A module file split into its header and its ordinary v1 sections."""

    __slots__ = ("header", "sections", "source")

    def __init__(self, header: ModuleHeader, sections: dict[str, Any], source: str) -> None:
        self.header = header
        self.sections = sections
        self.source = source

    def declared_names(self) -> list[str]:
        names: list[str] = []
        for section in NAME_KEYED_SECTIONS:
            names.extend(self.sections.get(section) or {})
        return sorted(names)


def _read_yaml(path: Path, source: str) -> dict[str, Any]:
    if not path.exists():
        raise OntologyError(f"ontology file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise OntologyValidationError(
            [f"top level must be a mapping, got {type(data).__name__}"], source
        )
    return data


def _check_manifest_shape(manifest: CompositionManifest, errors: list[str]) -> None:
    seen: set[str] = set()
    for index, entry in enumerate(manifest.composition):
        where = f"composition[{index}]"
        if not _MODULE_NAME_RE.match(entry.module):
            errors.append(f"{where}.module: {entry.module!r} must be snake_case")
        if entry.module in seen:
            errors.append(f"{where}.module: {entry.module!r} is listed twice")
        seen.add(entry.module)
        _check_version_string(entry.version, f"{where}.version", errors)


def _check_version_string(value: str, where: str, errors: list[str]) -> None:
    try:
        Version(value)
    except InvalidVersion:
        errors.append(f"{where}: {value!r} is not a valid version")


def _parse_module(
    path: Path, entry: CompositionEntry, errors: list[str]
) -> _ParsedModule | None:
    where = f"composition.{entry.module}"
    if not path.exists():
        errors.append(f"{where}.path: module file not found: {path}")
        return None
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        errors.append(f"{where}: module file must be a mapping, got {type(data).__name__}")
        return None

    raw_header = data.pop("module", None)
    if raw_header is None:
        errors.append(f"{where}: module file is missing its `module:` header")
        return None
    try:
        header = ModuleHeader.model_validate(raw_header)
    except ValidationError as exc:
        errors.extend(f"{where}.module.{line}" for line in _format_pydantic_errors(exc))
        return None

    if header.name != entry.module:
        errors.append(
            f"{where}.module.name: file declares {header.name!r} but the manifest "
            f"lists it as {entry.module!r}"
        )
    if not _NAMESPACE_RE.match(header.namespace):
        errors.append(f"{where}.module.namespace: {header.namespace!r} is not a valid namespace")
    _check_version_string(header.version, f"{where}.module.version", errors)

    # The composition owns identity and version for the whole artifact; a module
    # restating them would create a second answer to "what version is this?".
    for reserved in ("version", "namespace"):
        if reserved in data:
            errors.append(
                f"{where}.{reserved}: modules do not declare {reserved!r} — the "
                "composition manifest does (spec 08 §2.5)"
            )
            data.pop(reserved)

    unknown = set(data) - set(SINGLE_OWNER_SECTIONS) - set(NAME_KEYED_SECTIONS)
    for key in sorted(unknown):
        errors.append(f"{where}.{key}: not an ontology section")

    return _ParsedModule(header, data, str(path))


def _check_versions(
    manifest: CompositionManifest, parsed: dict[str, _ParsedModule], errors: list[str]
) -> None:
    for entry in manifest.composition:
        module = parsed.get(entry.module)
        if module is None:
            continue
        if module.header.version != entry.version:
            errors.append(
                f"composition.{entry.module}.version: manifest pins "
                f"{entry.version!r} but {module.source} declares "
                f"{module.header.version!r}"
            )


def _attribute_names(
    manifest: CompositionManifest,
    parsed: dict[str, _ParsedModule],
    errors: list[str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Map every declared name and single-owner section to its module."""
    owners: dict[str, str] = {}
    section_owners: dict[str, str] = {}
    for entry in manifest.composition:
        if not entry.enabled:
            continue
        module = parsed.get(entry.module)
        if module is None:
            continue
        for section in SINGLE_OWNER_SECTIONS:
            if section not in module.sections:
                continue
            previous = section_owners.get(section)
            if previous is not None:
                errors.append(
                    f"{entry.module}.{section}: already declared by module "
                    f"{previous!r} — one module owns it (spec 08 §2.2)"
                )
                continue
            section_owners[section] = entry.module
        for section in NAME_KEYED_SECTIONS:
            for name in module.sections.get(section) or {}:
                previous = owners.get(name)
                if previous is not None:
                    errors.append(
                        f"{entry.module}.{section}.{name}: name collision — module "
                        f"{previous!r} already declares {name!r}. Names are global "
                        "and unprefixed (ADR-037); resolve it with a proposal"
                    )
                    continue
                owners[name] = entry.module
    return owners, section_owners


def _references(module: _ParsedModule) -> list[tuple[str, str]]:
    """(referenced name, YAML path) for every cross-module-visible reference."""
    found: list[tuple[str, str]] = []
    for name, predicate in (module.sections.get("predicates") or {}).items():
        if not isinstance(predicate, dict):
            continue
        for subject in predicate.get("subject") or ():
            if isinstance(subject, str):
                found.append((subject, f"predicates.{name}.subject"))
        objects = predicate.get("object")
        if isinstance(objects, list):
            for value in objects:
                if isinstance(value, str) and value != "literal":
                    found.append((value, f"predicates.{name}.object"))
        category = predicate.get("category")
        if isinstance(category, str):
            found.append((category, f"predicates.{name}.category"))

    for name, spec in (module.sections.get("object_types") or {}).items():
        if not isinstance(spec, dict):
            continue
        for interface in spec.get("implements") or ():
            if isinstance(interface, str):
                found.append((interface, f"object_types.{name}.implements"))
        for prop_name, prop in (spec.get("properties") or {}).items():
            if isinstance(prop, dict) and isinstance(prop.get("shared"), str):
                found.append(
                    (prop["shared"], f"object_types.{name}.properties.{prop_name}.shared")
                )

    for name, spec in (module.sections.get("interfaces") or {}).items():
        if not isinstance(spec, dict):
            continue
        for required in spec.get("properties") or ():
            if isinstance(required, str):
                found.append((required, f"interfaces.{name}.properties"))
    return found


def _sensitivity_paths(module: _ParsedModule) -> list[str]:
    """YAML paths where this module names a handling code."""
    paths: list[str] = []
    for type_name, spec in (module.sections.get("object_types") or {}).items():
        if not isinstance(spec, dict):
            continue
        for prop_name, prop in (spec.get("properties") or {}).items():
            if isinstance(prop, dict) and prop.get("sensitivity") is not None:
                paths.append(f"object_types.{type_name}.properties.{prop_name}.sensitivity")
    return paths


def _check_imports(
    manifest: CompositionManifest,
    parsed: dict[str, _ParsedModule],
    owners: dict[str, str],
    section_owners: dict[str, str],
    errors: list[str],
) -> None:
    pinned = {entry.module: entry.version for entry in manifest.composition}
    enabled = {entry.module for entry in manifest.composition if entry.enabled}

    for entry in manifest.composition:
        module = parsed.get(entry.module)
        if module is None:
            continue
        imports = {imp.module: imp.version for imp in module.header.imports}

        for target, specifier in imports.items():
            where = f"{entry.module}.imports.{target}"
            if target == entry.module:
                errors.append(f"{where}: a module cannot import itself")
                continue
            if target not in pinned:
                errors.append(
                    f"{where}: no module named {target!r} in the composition "
                    f"(listed: {sorted(pinned)})"
                )
                continue
            if entry.enabled and target not in enabled:
                errors.append(
                    f"{where}: module {target!r} is disabled but imported by an "
                    "enabled module (spec 08 §2.6)"
                )
            try:
                allowed = SpecifierSet(specifier)
            except InvalidSpecifier:
                errors.append(f"{where}.version: {specifier!r} is not a PEP 440 specifier")
                continue
            if not allowed.contains(pinned[target]):
                errors.append(
                    f"{where}.version: composition pins {target} "
                    f"{pinned[target]!r}, which does not satisfy {specifier!r}"
                )

        if not entry.enabled:
            continue

        for name, where in _references(module):
            owner = owners.get(name)
            if owner is None or owner == entry.module or owner in imports:
                continue
            errors.append(
                f"{entry.module}.{where}: {name!r} is owned by module {owner!r}, "
                f"which {entry.module!r} does not import (spec 08 §2.3)"
            )

        handling_owner = section_owners.get("handling_codes")
        if handling_owner is not None and handling_owner != entry.module:
            if handling_owner not in imports:
                for where in _sensitivity_paths(module):
                    errors.append(
                        f"{entry.module}.{where}: handling codes are owned by module "
                        f"{handling_owner!r}, which {entry.module!r} does not import "
                        "(spec 08 §2.3)"
                    )

    _check_import_cycles(parsed, errors)


def _check_import_cycles(parsed: dict[str, _ParsedModule], errors: list[str]) -> None:
    graph = {
        name: [imp.module for imp in module.header.imports if imp.module in parsed]
        for name, module in parsed.items()
    }
    state: dict[str, int] = {}

    def visit(node: str, trail: list[str]) -> None:
        if state.get(node) == 2:
            return
        if state.get(node) == 1:
            cycle = " -> ".join(trail[trail.index(node) :] + [node])
            errors.append(f"imports: cycle detected ({cycle})")
            return
        state[node] = 1
        for target in graph.get(node, ()):
            visit(target, trail + [node])
        state[node] = 2

    for name in sorted(graph):
        visit(name, [])


def _merge(manifest: CompositionManifest, parsed: dict[str, _ParsedModule]) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": manifest.version,
        "namespace": manifest.namespace,
    }
    # Seeded empty rather than left absent: a composition with every domain
    # module disabled is a legitimate state (it is what you have before enabling
    # one), and it should compose to an empty vocabulary rather than to "this
    # document is missing a required section". A hand-written flat file that
    # forgets `predicates:` still gets that error, which is the case the
    # requirement was written for.
    document.update({section: {} for section in NAME_KEYED_SECTIONS})
    for entry in manifest.composition:
        if not entry.enabled:
            continue
        module = parsed.get(entry.module)
        if module is None:
            continue
        for section, value in module.sections.items():
            if section in SINGLE_OWNER_SECTIONS:
                document.setdefault(section, value)
            else:
                document[section].update(value or {})
    return document


def _module_infos(
    manifest: CompositionManifest, parsed: dict[str, _ParsedModule]
) -> dict[str, ModuleInfo]:
    infos: dict[str, ModuleInfo] = {}
    for entry in manifest.composition:
        module = parsed[entry.module]
        infos[entry.module] = ModuleInfo(
            name=module.header.name,
            namespace=module.header.namespace,
            version=module.header.version,
            label=module.header.label,
            imports={imp.module: imp.version for imp in module.header.imports},
            enabled=entry.enabled,
            declares=tuple(module.declared_names()),
        )
    return infos


def disabled_vocabulary_in_use(
    ontology: Ontology,
    *,
    predicates: Iterable[str] = (),
    entity_types: Iterable[str] = (),
) -> dict[str, list[str]]:
    """Names from disabled modules that recorded data still speaks (spec 08 §2.6).

    Disabling a module is an authoring-time control: it removes vocabulary from
    validation and deletes nothing. Serving a store whose claims use vocabulary
    the registry no longer knows would mean rendering rows the API cannot
    explain, so the caller refuses to start instead.

    Pure by design — the caller supplies what the database actually contains, so
    the ontology package needs no store import and this stays testable without
    one.
    """
    observed = {value for value in (*predicates, *entity_types) if value}
    if not observed:
        return {}
    in_use: dict[str, list[str]] = {}
    for name, info in ontology.modules.items():
        if info.enabled:
            continue
        used = sorted(observed.intersection(info.declares))
        if used:
            in_use[name] = used
    return in_use
