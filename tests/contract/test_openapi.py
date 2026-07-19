"""The OpenAPI document is a contract with the workspace (T22, ADR-032 §2).

``ui/openapi.json`` is committed so the UI build needs no running API, and the
TypeScript client is generated from it. That makes drift the failure mode worth
testing: a route renamed in Python and not re-exported produces a client that
type-checks perfectly and 404s at runtime, which is the worst possible place to
find out.

Operation ids are the other half. They are the generated client's function
names, so they are API surface: renaming one breaks callers exactly as renaming
a path would. P3 T36 adds the CI drift gate for the ontology-generated SDK; this
is the P2 form of the same guarantee.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis.api import create_app

pytestmark = pytest.mark.requirement("ADR-032", "T22")

DOCUMENT = Path(__file__).resolve().parents[2] / "ui" / "openapi.json"


@pytest.fixture(scope="module")
def live() -> dict:
    return create_app().openapi()


@pytest.fixture(scope="module")
def committed() -> dict:
    return json.loads(DOCUMENT.read_text(encoding="utf-8"))


def _operations(document: dict) -> dict[str, str]:
    return {
        operation["operationId"]: f"{method.upper()} {path}"
        for path, item in document["paths"].items()
        for method, operation in item.items()
        if "operationId" in operation
    }


def test_committed_document_matches_the_routes(live: dict, committed: dict) -> None:
    assert committed == live, (
        "ui/openapi.json is stale — run `aegis api export-openapi` and commit "
        "the result with the route change that caused it"
    )


def test_every_operation_declares_a_stable_id(live: dict) -> None:
    """No route may fall back to FastAPI's generated id.

    The default is derived from the Python function name *and* the path, so an
    innocuous refactor renames a client method. An explicit id is a promise that
    it will not.
    """
    unnamed = [
        f"{method.upper()} {path}"
        for path, item in live["paths"].items()
        for method, operation in item.items()
        if not operation.get("operationId")
        or "_" in operation["operationId"]  # FastAPI's default shape
    ]
    assert unnamed == []


def test_operation_ids_are_unique(live: dict) -> None:
    ids = [
        operation["operationId"]
        for item in live["paths"].values()
        for operation in item.values()
    ]
    assert len(ids) == len(set(ids))


def test_the_retired_anonymous_routes_are_not_in_the_document(live: dict) -> None:
    """ADR-026: gone from the surface, not merely undocumented."""
    assert not [path for path in live["paths"] if path.startswith("/api/")]


def test_every_documented_path_is_versioned(live: dict) -> None:
    assert all(path.startswith("/v1/") for path in live["paths"])
