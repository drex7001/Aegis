"""Ontology change management — proposals, versions, compatibility (spec 08 §7).

The rule this file enforces: **a version bump says what it is, and the artifact
proves it.** A minor bump that removes a predicate is a lie that only shows up
when a claim recorded under the old version stops being interpretable, which is
years later and unrecoverable (ADR-013 — claims are immutable).

Comparison is against a **committed artifact**, never git history (H-16):
``ontology/release.json`` names the previous version and its content hash, and
``ontology/history/composed-<version>.json`` holds it. A reviewer can run the
check on a bare checkout with no remote, and it answers the same way.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

#: Sections whose keys are vocabulary. Losing a key from any of them means a
#: claim, action call, or generated type that referenced it can no longer be
#: resolved, which is the definition of a breaking change here.
VOCABULARY_SECTIONS = (
    "object_types",
    "predicates",
    "actions",
    "interfaces",
    "shared_properties",
    "categories",
    "event_types",
)

#: Ordered weakest to strongest. A declared class must be at least as strong as
#: the computed one — over-declaring is allowed (a cautious author may call an
#: additive change major), under-declaring is not.
COMPATIBILITY_ORDER = ("patch", "minor", "major")


@dataclass
class CompatibilityReport:
    """What changed between two composed artifacts, and how bad it is."""

    breaking: list[str] = field(default_factory=list)
    additive: list[str] = field(default_factory=list)

    @property
    def computed(self) -> str:
        if self.breaking:
            return "major"
        if self.additive:
            return "minor"
        return "patch"


def _vocabulary(artifact: dict[str, Any], section: str) -> dict[str, Any]:
    return (artifact.get("ontology") or {}).get(section) or {}


def compare(previous: dict[str, Any], current: dict[str, Any]) -> CompatibilityReport:
    """Diff two composed artifacts (spec 08 §7.3 gate 2).

    Deliberately shallow on the *inside* of a declaration: whether a predicate
    gained a category is not what a version bump must protect. What must never
    happen quietly is a name disappearing, a property changing type, or a
    handling code moving — those change what an existing row means.
    """
    report = CompatibilityReport()

    for section in VOCABULARY_SECTIONS:
        before = _vocabulary(previous, section)
        after = _vocabulary(current, section)
        for name in sorted(set(before) - set(after)):
            report.breaking.append(f"{section}.{name}: removed")
        for name in sorted(set(after) - set(before)):
            report.additive.append(f"{section}.{name}: added")

    report.breaking += _property_changes(previous, current)
    report.breaking += _ordered_list_changes(previous, current, "handling_codes")
    report.breaking += _set_removals(previous, current, "source_types")

    # A new handling code or source type is additive; the removals above are not.
    for section in ("handling_codes", "source_types"):
        before = set((previous.get("ontology") or {}).get(section) or ())
        after = set((current.get("ontology") or {}).get(section) or ())
        for value in sorted(after - before):
            report.additive.append(f"{section}.{value}: added")

    return report


def _property_changes(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """A property that changes type or sensitivity reinterprets recorded rows."""
    breaking: list[str] = []
    for section in ("object_types", "shared_properties"):
        before = _vocabulary(previous, section)
        after = _vocabulary(current, section)
        for name in sorted(set(before) & set(after)):
            if section == "shared_properties":
                breaking += _compare_property(f"{section}.{name}", before[name], after[name])
                continue
            old_props = (before[name] or {}).get("properties") or {}
            new_props = (after[name] or {}).get("properties") or {}
            for prop in sorted(set(old_props) - set(new_props)):
                breaking.append(f"{section}.{name}.properties.{prop}: removed")
            for prop in sorted(set(old_props) & set(new_props)):
                breaking += _compare_property(
                    f"{section}.{name}.properties.{prop}", old_props[prop], new_props[prop]
                )
    return breaking


def _compare_property(where: str, before: Any, after: Any) -> list[str]:
    if not isinstance(before, dict) or not isinstance(after, dict):
        return []
    changes: list[str] = []
    for field_name in ("type", "sensitivity", "shared"):
        old, new = before.get(field_name), after.get(field_name)
        if old != new and not (old is None and new is None):
            # A property adopting a shared definition is not a change of
            # meaning *if* the resolved type and sensitivity match — but the
            # artifact stores the declaration, so the resolved form is not
            # visible here. Reporting it is the honest, conservative answer:
            # the author states the class and this check refuses a weaker one.
            changes.append(f"{where}.{field_name}: {old!r} -> {new!r}")
    return changes


def _ordered_list_changes(
    previous: dict[str, Any], current: dict[str, Any], section: str
) -> list[str]:
    """Handling codes are an *ordered* list — the index is the clearance level.

    Reordering them silently reclassifies every row that stores one, so it is
    breaking even when the set is unchanged.
    """
    before = list((previous.get("ontology") or {}).get(section) or ())
    after = list((current.get("ontology") or {}).get(section) or ())
    if before and before != after[: len(before)]:
        return [f"{section}: reordered or truncated ({before} -> {after})"]
    return []


def _set_removals(
    previous: dict[str, Any], current: dict[str, Any], section: str
) -> list[str]:
    before = set((previous.get("ontology") or {}).get(section) or ())
    after = set((current.get("ontology") or {}).get(section) or ())
    return [f"{section}.{value}: removed" for value in sorted(before - after)]


def check(
    repo_root: Path,
    *,
    release: dict[str, Any],
    artifact: dict[str, Any],
) -> list[str]:
    """Every spec 08 §7.3 gate, as a list of errors (empty means green).

    ``release`` is the generated ``ontology/release.json`` content and
    ``artifact`` the composed registry it describes, so this runs on what is
    committed rather than on what a loader could reconstruct.
    """
    errors: list[str] = []
    version = release.get("version")

    errors += _proposal_errors(repo_root, release)
    errors += _compatibility_declaration_errors(release)
    errors += _monotonicity_errors(repo_root, release)

    previous_version = release.get("previous_version")
    if previous_version is None:
        # The first generated release has nothing to diff against. Stated
        # rather than silently skipped, because "no previous artifact" and
        # "no differences" must not look the same in the output.
        return errors

    previous_path = repo_root / "ontology" / "history" / f"composed-{previous_version}.json"
    if not previous_path.exists():
        errors.append(
            f"release.previous_version: {previous_version} is named but "
            f"{previous_path.relative_to(repo_root).as_posix()} is missing — the "
            "compatibility diff has nothing to compare against"
        )
        return errors

    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    errors += _previous_hash_errors(release, previous)

    report = compare(previous, artifact)
    declared = release.get("compatibility")
    if declared in COMPATIBILITY_ORDER:
        if COMPATIBILITY_ORDER.index(declared) < COMPATIBILITY_ORDER.index(report.computed):
            errors.append(
                f"release.compatibility: declared {declared!r} but the diff against "
                f"{previous_version} is {report.computed!r} — "
                + "; ".join(report.breaking or report.additive)
            )
    if report.breaking and declared != "major":
        errors += [f"breaking change without a major bump — {reason}" for reason in report.breaking]
    if report.breaking:
        errors += _major_bump_errors(repo_root, version)
    return errors


def _proposal_errors(repo_root: Path, release: dict[str, Any]) -> list[str]:
    proposal = release.get("proposal")
    if not proposal:
        return [
            "release.proposal: every version bump names the proposal that "
            "justified it (spec 08 §7.1) — add a `release:` block to "
            "ontology/aegis.yaml"
        ]
    path = repo_root / "ontology" / "proposals" / f"{proposal}.md"
    if not path.exists():
        return [
            f"release.proposal: {proposal!r} does not name a file in "
            "ontology/proposals/"
        ]
    return []


def _compatibility_declaration_errors(release: dict[str, Any]) -> list[str]:
    declared = release.get("compatibility")
    if declared is None:
        return [
            "release.compatibility: declare major, minor or patch in the "
            "`release:` block of ontology/aegis.yaml"
        ]
    if declared not in COMPATIBILITY_ORDER:
        return [f"release.compatibility: {declared!r} is not one of {list(COMPATIBILITY_ORDER)}"]
    return []


def _monotonicity_errors(repo_root: Path, release: dict[str, Any]) -> list[str]:
    """Versions only ever go up — for the composition and for every module."""
    errors: list[str] = []
    previous_version = release.get("previous_version")
    if previous_version is None:
        return errors
    try:
        if Version(release["version"]) <= Version(previous_version):
            errors.append(
                f"release.version: {release['version']} does not advance on "
                f"{previous_version}"
            )
    except (InvalidVersion, KeyError):
        errors.append(f"release.version: {release.get('version')!r} is not a valid version")

    previous_path = repo_root / "ontology" / "history" / f"composed-{previous_version}.json"
    if not previous_path.exists():
        return errors
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    before = {module["name"]: module["version"] for module in previous.get("modules", ())}
    for name, current_version in (release.get("modules") or {}).items():
        if name not in before:
            continue
        try:
            if Version(current_version) < Version(before[name]):
                errors.append(
                    f"release.modules.{name}: {current_version} is older than "
                    f"{before[name]} in {previous_version}"
                )
        except InvalidVersion:
            errors.append(f"release.modules.{name}: {current_version!r} is not a valid version")
    return errors


def _previous_hash_errors(release: dict[str, Any], previous: dict[str, Any]) -> list[str]:
    from aegis.ontology.generate import content_hash

    recorded = release.get("previous_content_hash")
    actual = content_hash(previous)
    if recorded and recorded != actual:
        return [
            "release.previous_content_hash: the archived artifact for "
            f"{release.get('previous_version')} has been edited since it was "
            "released — the chain is what makes this check trustworthy"
        ]
    return []


def _major_bump_errors(repo_root: Path, version: str | None) -> list[str]:
    """A major bump keeps the module sources it broke, plus its migration."""
    errors: list[str] = []
    history = repo_root / "ontology" / "history"
    if not any(history.glob(f"aegis-{version}.yaml")) and not any(
        history.glob(f"{version}/*.yaml")
    ):
        errors.append(
            f"a major bump must archive the prior module sources under "
            f"ontology/history/{version}/ (spec 01 §4)"
        )
    return errors
