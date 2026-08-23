"""The workspace's types come from the contract, not from copies (T37, T38).

ADR-039. `ui/src/api/schema.d.ts` has been generated from the committed OpenAPI
document since Phase 2, so there was never a hand-rolled client to migrate off.
What was hand-written were the shapes the document did not describe — the error
envelope, and the multipart landing body — and T36 put those in the contract so
this file can insist they are gone.

Checked from the Python suite rather than a TypeScript test because it is a
*repository* property: no `.ts` file under `ui/src` may declare an API shape.
The workspace's own type-check proves the generated types compile; only a sweep
proves nothing has quietly grown back beside them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from aegis.ontology import load
from tests.support.paths import ONTOLOGY_PATH, REPO_ROOT

pytestmark = pytest.mark.requirement("ADR-039", "T37", "T38")

UI_SRC = REPO_ROOT / "ui" / "src"
GENERATED = {UI_SRC / "api" / "schema.d.ts", UI_SRC / "api" / "ontology.ts"}

#: An interface or a non-alias type in `ui/src` that names an API payload.
#: Aliases (`export type X = components["schemas"]["Y"]`) are the *point* — they
#: are how a generated shape gets a readable name.
_DECLARATION = re.compile(r"^export (?:interface|type)\s+(\w+)", re.MULTILINE)

#: Local UI concepts that are not API payloads: a route union, a panel's props,
#: a tab id. Naming them here keeps the sweep meaningful instead of forcing
#: every component to stop describing its own inputs.
LOCAL_TYPES = {
    "Route",
    "PanelSelection",
    "ProvenancePanelProps",
    "EntitySearchProps",
    "GraphCanvasProps",
    # T45. None of these describes a payload: `Drill` says which drill-down is
    # open, `DrillHandler` is a callback signature, and `Extent`/`TimedClaim`
    # are the axis arithmetic — millisecond bounds computed from a claim's
    # declared times, which the server neither sends nor could.
    "Drill",
    "DrillHandler",
    "Extent",
    "TimedClaim",
    # T60. The mark vocabulary is how the map *draws*, which the server neither
    # sends nor could: `MarkKind` and `Mark` are a rendering decision, and
    # `MarkInput` is the subset of a feature's properties that decision reads.
    # `GeometryState` is the set of states the renderer knows how to handle —
    # deliberately narrower than the open `string` the contract carries, because
    # a state it has never heard of must draw nothing rather than a default pin.
    #
    # The three shapes that *were* API payloads — `PlaceProperties`,
    # `EventProperties`, `GeoFeature` — are not here. This sweep caught them
    # hand-written in `client.ts` and the fix was to describe them in the
    # OpenAPI document, which is what the docstring says to do.
    "GeometryState",
    "MarkKind",
    "MarkInput",
    "Mark",
    # T62. The workspace's own URL state, which is the opposite of a payload:
    # the server never sends these, it *receives* query parameters derived from
    # them, and each surface derives a different subset. A generated shape for
    # "what the analyst has narrowed to" would have to be invented on the server
    # for the client's benefit, which is the tail wagging the contract.
    "TimeWindow",
    "Selection",
}


def _sources() -> list[Path]:
    return sorted(p for p in UI_SRC.rglob("*.ts*") if p not in GENERATED)


def test_no_hand_written_api_shape_remains_in_the_workspace() -> None:
    """T38's acceptance criterion, as a sweep.

    A declaration is allowed when it is an alias onto a generated schema, or
    when it is a local UI concept listed above. Anything else is a second copy
    of a shape the server already describes — which is what
    `ProblemDetail`, `StaleRevisionProblem` and `LandFileFields` were until
    T36 put them in the contract.
    """
    offenders: dict[str, list[str]] = {}
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        declarations = [
            (match.group(1), text[match.start() : text.find(";", match.start()) + 1])
            for match in _DECLARATION.finditer(text)
        ]
        # Two passes: a name is generated if its declaration reaches the schema
        # directly, or through another name in the same file that does.
        # `LandingOutcome = LandingResult["outcome"]` is a derivation, not a copy.
        generated = {
            name
            for name, body in declarations
            if any(token in body for token in ("components[", "operations[", "typeof "))
        }
        for _ in range(len(declarations)):
            grown = {
                name
                for name, body in declarations
                if any(re.search(rf"\b{other}\b", body) for other in generated)
            }
            if grown <= generated:
                break
            generated |= grown

        for name, _ in declarations:
            if name in LOCAL_TYPES or name in generated:
                continue
            offenders.setdefault(path.relative_to(REPO_ROOT).as_posix(), []).append(name)

    assert not offenders, (
        "these declare an API shape by hand instead of aliasing the generated "
        f"one: {offenders}. If the server does not describe the shape, that is "
        "a gap in the OpenAPI document (spec 06 §7.2), not a reason to copy it."
    )


def test_the_error_envelope_is_aliased_not_redeclared() -> None:
    client = (UI_SRC / "api" / "client.ts").read_text(encoding="utf-8")
    for name in ("ProblemDetail", "StaleRevisionProblem", "LandFileFields"):
        assert f"export type {name}" in client, f"{name} should be a generated alias"
        assert f"export interface {name}" not in client, f"{name} is hand-written again"
    assert 'components["schemas"]["StaleRevisionProblem"]' in client


def test_the_stale_revision_narrowing_reads_a_generated_shape() -> None:
    """`asStaleRevision` is the one error body the client reads for meaning."""
    client = (UI_SRC / "api" / "client.ts").read_text(encoding="utf-8")
    assert "export function asStaleRevision" in client
    assert 'components["schemas"]["InterveningDecision"]' in client


def test_the_client_keeps_only_the_wrapper_and_the_error_class() -> None:
    """Everything else it exports is a generated alias or a call helper."""
    client = (UI_SRC / "api" / "client.ts").read_text(encoding="utf-8")
    assert "export class ApiError" in client
    assert client.count("export class") == 1


# ── the generated constants ─────────────────────────────────────────────────


def test_the_constants_match_the_registry() -> None:
    """Regenerating is a CI gate; this fails the fast suite for the same reason."""
    from aegis.ontology.generate import typescript_constants

    committed = (UI_SRC / "api" / "ontology.ts").read_text(encoding="utf-8")
    assert committed == typescript_constants(load(ONTOLOGY_PATH))


def test_the_constants_expose_predicates_the_route_never_served() -> None:
    """The gap the constants close (ADR-039).

    `GET /v1/ontology/vocabulary` serves handling codes, source types and
    assertion types. It has never served a predicate, so a client had no typed
    way to know one exists — which is exactly what T39 measures.
    """
    document = json.loads((REPO_ROOT / "ui" / "openapi.json").read_text(encoding="utf-8"))
    served = document["components"]["schemas"]["OntologyVocabularyOut"]["properties"]
    assert "predicates" not in served
    assert "object_types" not in served

    constants = (UI_SRC / "api" / "ontology.ts").read_text(encoding="utf-8")
    ontology = load(ONTOLOGY_PATH)
    assert "export type PredicateName" in constants
    for predicate in ontology.predicates:
        assert f'"{predicate}":' in constants


def test_the_workspace_uses_the_generated_constants() -> None:
    """A generated file nothing imports is a file nobody notices going stale."""
    importers = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in _sources()
        if "from \"../api/ontology\"" in path.read_text(encoding="utf-8")
        or 'from "./ontology"' in path.read_text(encoding="utf-8")
    ]
    assert importers, "nothing imports ui/src/api/ontology.ts"
