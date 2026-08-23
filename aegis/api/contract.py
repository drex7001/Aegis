"""Breaking-change detection for the OpenAPI contract (spec 06 §7.3).

The P2 drift test answers *"does the committed document match the live
routes?"*. It cannot answer *"is this change safe for the client?"* — a route
renamed in Python and faithfully re-exported passes drift and still breaks every
caller.

**Why this reads git and the ontology check does not.** The ontology's
comparison is deliberately git-free (H-16) because claims stamp the ontology
version and stay interpretable forever, so the previous artifact must be a
first-class committed file. Nothing stores an API version: the only meaningful
baseline is "the contract as it stood on the branch we are merging into", which
*is* a git ref. Requiring a version bump and an archived copy per route change
would be ceremony with no consumer (ADR-042).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Any

#: Explicitly declaring a break is the escape hatch. It is a phrase in the
#: change itself rather than a CLI flag, so the reason lands in the history that
#: the break will later be explained from.
BREAKING_MARKER = "BREAKING API CHANGE"

#: Separators for the `git log` scan below. NUL and SOH cannot appear in a
#: commit message, so nothing a human writes can be mistaken for a field
#: boundary — unlike a newline, which every message contains.
_FIELD = chr(0)
_RECORD = chr(1)


@dataclass
class ContractDiff:
    breaking: list[str] = field(default_factory=list)
    additive: list[str] = field(default_factory=list)

    @property
    def is_breaking(self) -> bool:
        return bool(self.breaking)


def _operations(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """operation id -> the operation, with its path and method attached."""
    found: dict[str, dict[str, Any]] = {}
    for path, item in (document.get("paths") or {}).items():
        for method, operation in item.items():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            found[operation["operationId"]] = {**operation, "_path": path, "_method": method}
    return found


def compare(previous: dict[str, Any], current: dict[str, Any]) -> ContractDiff:
    """What changed for a caller between two OpenAPI documents."""
    diff = ContractDiff()
    before, after = _operations(previous), _operations(current)

    for name in sorted(set(before) - set(after)):
        # Covers both a deleted route and a renamed operation id: from the
        # client's side those are the same event — a method that stops existing.
        diff.breaking.append(
            f"{name}: operation removed or renamed (was "
            f"{before[name]['_method'].upper()} {before[name]['_path']})"
        )
    for name in sorted(set(after) - set(before)):
        diff.additive.append(f"{name}: operation added")

    for name in sorted(set(before) & set(after)):
        breaking, additive = _operation_changes(name, before[name], after[name])
        diff.breaking += breaking
        diff.additive += additive
    return diff


def _operation_changes(
    name: str, before: dict[str, Any], after: dict[str, Any]
) -> tuple[list[str], list[str]]:
    changes: list[str] = []
    additive: list[str] = []

    if (before["_path"], before["_method"]) != (after["_path"], after["_method"]):
        changes.append(
            f"{name}: moved from {before['_method'].upper()} {before['_path']} to "
            f"{after['_method'].upper()} {after['_path']}"
        )

    old_codes = set(before.get("responses") or {})
    new_codes = set(after.get("responses") or {})
    for code in sorted(old_codes - new_codes):
        # A client that handles a documented error and stops seeing it declared
        # has no way to know whether the server stopped sending it.
        changes.append(f"{name}: response {code} no longer documented")
    for code in sorted(new_codes - old_codes):
        additive.append(f"{name}: response {code} now documented")

    old_params = _parameters(before)
    new_params = _parameters(after)
    for key in sorted(set(old_params) - set(new_params)):
        changes.append(f"{name}: parameter {key} removed")
    for key in sorted(set(new_params) - set(old_params)):
        if new_params[key]:
            changes.append(f"{name}: new required parameter {key}")
        else:
            additive.append(f"{name}: optional parameter {key} added")
    for key in sorted(set(old_params) & set(new_params)):
        if new_params[key] and not old_params[key]:
            changes.append(f"{name}: parameter {key} became required")
        elif old_params[key] and not new_params[key]:
            additive.append(f"{name}: parameter {key} became optional")

    if _body_required(before) is False and _body_required(after) is True:
        changes.append(f"{name}: request body became required")
    return changes, additive


def _parameters(operation: dict[str, Any]) -> dict[str, bool]:
    """`"name in location"` -> required."""
    return {
        f"{parameter.get('name')} in {parameter.get('in')}": bool(parameter.get("required"))
        for parameter in operation.get("parameters") or []
        if isinstance(parameter, dict)
    }


def _body_required(operation: dict[str, Any]) -> bool | None:
    body = operation.get("requestBody")
    if not isinstance(body, dict):
        return None
    return bool(body.get("required"))


def document_at(ref: str, path: str) -> dict[str, Any] | None:
    """The committed document at a git ref, or None when it is not reachable.

    Returns None rather than raising for a shallow clone, a fresh repository, or
    a first commit that has no baseline — cases where the honest answer is "no
    contract to compare against", not "this change is fine".
    """
    try:
        blob = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


def declaring_commit(baseline: str) -> str | None:
    """The commit on this branch that declares `BREAKING API CHANGE`, or None.

    ADR-042 says the escape hatch is "a phrase in the change itself rather than
    a CLI flag, so the reason lands in the history that the break will later be
    explained from". Until T67 that was only half true: the flag existed and
    **nothing read the phrase**, so CI — which passes no flags — had no way to
    accept an intended break at all. The documented mechanism did not exist.

    This is it. The scan is scoped to `baseline..HEAD`, so a marker can only
    accept a break made on the same branch that declared it; a stale marker from
    an old commit cannot silently license a different break later.

    Returns the subject line of the declaring commit, so the caller can say
    *which* change accepted it rather than merely that something did.
    """
    for revisions in (f"{baseline}..HEAD", "-n1 HEAD"):
        try:
            log = subprocess.run(
                ["git", "log", "--format=%H%x00%s%x00%B%x01", *revisions.split()],
                capture_output=True,
                check=True,
                text=True,
            ).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
        for entry in log.split(_RECORD):
            parts = entry.split(_FIELD)
            if len(parts) == 3 and BREAKING_MARKER in parts[2]:
                return parts[1].strip()
        # A computable range that declares nothing is an answer, not a reason to
        # widen the search: falling through to `HEAD` would scan a commit the
        # range deliberately excluded.
        if revisions != "-n1 HEAD":
            return None
    return None
