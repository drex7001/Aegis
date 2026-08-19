"""The error envelope is part of the contract, and the diff catches breaks (T36).

Spec 06 §7.2–7.3, ADR-039, ADR-042. Two things under test:

* every operation documents the errors it can actually return, with the media
  type it actually sends — the gap that made `ui/src/api/client.ts` hand-write
  `ProblemDetail` and `StaleRevisionProblem`;
* a breaking change to the committed document fails, which the P2 drift test
  cannot see (a renamed operation faithfully re-exported passes drift and
  breaks every caller).
"""

from __future__ import annotations

import copy
import json

import pytest

from aegis.api import create_app
from aegis.api.contract import compare
from aegis.api.problems import (
    PROBLEM_MEDIA_TYPE,
    ROUTE_SPECIFIC_ERRORS,
    ProblemDetail,
    StaleRevisionProblem,
    ValidationProblem,
    _api_routes,
)
from tests.support.paths import REPO_ROOT

pytestmark = pytest.mark.requirement("ADR-039", "ADR-042", "T36")

DOCUMENT = REPO_ROOT / "ui" / "openapi.json"


@pytest.fixture(scope="module")
def document() -> dict:
    return json.loads(DOCUMENT.read_text(encoding="utf-8"))


def _operations(document: dict) -> dict[str, dict]:
    return {
        operation["operationId"]: operation
        for item in document["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }


# ── the envelope is declared ────────────────────────────────────────────────


def test_the_problem_schemas_are_in_the_document(document: dict) -> None:
    schemas = document["components"]["schemas"]
    for name in ("ProblemDetail", "ValidationProblem", "StaleRevisionProblem", "InterveningDecision"):
        assert name in schemas, f"{name} is not in the contract"


def test_every_operation_documents_the_universal_errors(document: dict) -> None:
    """401 and 429 are reachable on every route (spec 06 §7.2)."""
    for name, operation in _operations(document).items():
        assert "401" in operation["responses"], name
        assert "429" in operation["responses"], name
        assert "422" in operation["responses"], name


def test_errors_are_declared_as_problem_json(document: dict) -> None:
    """The server sends `application/problem+json`; the contract must say so.

    FastAPI attaches an additional response's model to the route's own media
    type, `application/json`, so this is corrected on the finished document.
    Success responses stay `application/json` — they really are.
    """
    for name, operation in _operations(document).items():
        for status, response in operation["responses"].items():
            content = response.get("content")
            if not content:
                continue
            if status.startswith("4"):
                assert list(content) == [PROBLEM_MEDIA_TYPE], f"{name} {status}"
            else:
                assert "application/json" in content, f"{name} {status}"


def test_no_5xx_is_documented(document: dict) -> None:
    """A backend being down is a failure, not a contract outcome (spec 06 §7.2)."""
    for name, operation in _operations(document).items():
        assert not [c for c in operation["responses"] if c.startswith("5")], name


def test_the_role_gate_decides_which_operations_document_403(document: dict) -> None:
    """Derived from the gate, not from a table beside it.

    `authorize()` already tags itself with the roles it requires — the same
    metadata the authorization-matrix suite reads — so the document cannot
    claim a 403 the route will never raise, or omit one it will.
    """
    from aegis.api.deps import GATE_ROLES, _dependency_calls

    app = create_app()
    operations = _operations(document)
    for route in _api_routes(app):
        gated = any(
            getattr(call, GATE_ROLES, None) for call in _dependency_calls(route.dependant)
        )
        documented = "403" in operations[route.operation_id]["responses"]
        assert gated == documented, (
            f"{route.operation_id}: role gate={gated} but 403 documented={documented}"
        )


def test_single_resource_routes_document_404(document: dict) -> None:
    """Unauthorized and nonexistent are indistinguishable (spec 06 §1 default 4)."""
    for name, operation in _operations(document).items():
        path = next(
            p for p, item in document["paths"].items() if operation in item.values()
        )
        assert ("{" in path) == ("404" in operation["responses"]), name


def test_the_typed_stale_revision_body_is_declared(document: dict) -> None:
    """The one error body a client reads for meaning (spec 05 §2)."""
    decisions = _operations(document)["recordIdentityDecision"]
    schema = decisions["responses"]["409"]["content"][PROBLEM_MEDIA_TYPE]["schema"]
    assert schema["$ref"].endswith("StaleRevisionProblem")

    properties = document["components"]["schemas"]["StaleRevisionProblem"]["properties"]
    assert "parent_revision_id" in properties
    assert "intervening" in properties


def test_route_specific_errors_all_name_a_real_operation(document: dict) -> None:
    """A rename must not silently drop a documented error."""
    operations = set(_operations(document))
    assert set(ROUTE_SPECIFIC_ERRORS) <= operations, (
        f"unknown operations: {sorted(set(ROUTE_SPECIFIC_ERRORS) - operations)}"
    )


def test_the_handlers_build_the_declared_models() -> None:
    """The runtime and the contract cannot drift: they share the models.

    Asserted on the shapes rather than by mocking a request, because what
    matters is that `errors.py` has no second definition of the envelope.
    """
    from aegis.api import errors

    source = (REPO_ROOT / "aegis" / "api" / "errors.py").read_text(encoding="utf-8")
    assert "from aegis.api.problems import" in source
    assert ValidationProblem.__name__ in source
    assert StaleRevisionProblem.__name__ in source
    assert ProblemDetail(title="t", status=404).type == "about:blank"
    assert errors.install_error_handlers is not None


def test_a_401_still_says_how_to_authenticate() -> None:
    """RFC 7235 §3.1: a 401 carries `WWW-Authenticate`, or it is useless.

    Regression. Wrapping errors in problem+json (T36) rebuilt the response from
    the exception's *body*, which silently dropped the headers the exception
    carried — so every 401 lost the one field that tells a client how to
    authenticate. Nothing failed; it just stopped being correct HTTP. Found by
    T52's re-verification of the authenticated surface.
    """
    from fastapi.testclient import TestClient

    from aegis.api import create_app

    with TestClient(create_app()) as client:
        response = client.get("/v1/cases")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    # ...and it is still a problem document, not a plain body.
    assert response.headers["content-type"].startswith("application/problem+json")


# ── the contract diff ───────────────────────────────────────────────────────


def test_an_identical_document_is_not_a_change(document: dict) -> None:
    diff = compare(document, copy.deepcopy(document))
    assert diff.breaking == []
    assert diff.additive == []


def test_a_renamed_operation_is_breaking(document: dict) -> None:
    """What the P2 drift test cannot see: re-exported faithfully, still broken."""
    changed = copy.deepcopy(document)
    changed["paths"]["/v1/cases"]["post"]["operationId"] = "createCase"
    diff = compare(document, changed)
    assert diff.is_breaking
    assert any("openCase: operation removed or renamed" in line for line in diff.breaking)


def test_a_removed_operation_is_breaking(document: dict) -> None:
    changed = copy.deepcopy(document)
    changed["paths"].pop("/v1/search/entities")
    assert any("searchEntities" in line for line in compare(document, changed).breaking)


def test_a_moved_operation_is_breaking(document: dict) -> None:
    changed = copy.deepcopy(document)
    changed["paths"]["/v1/case-files"] = changed["paths"].pop("/v1/cases")
    assert any("openCase: moved from" in line for line in compare(document, changed).breaking)


def test_dropping_a_documented_response_is_breaking(document: dict) -> None:
    """A client handling a documented error cannot tell it stopped arriving."""
    changed = copy.deepcopy(document)
    changed["paths"]["/v1/identity/decisions"]["post"]["responses"].pop("409")
    assert any(
        "recordIdentityDecision: response 409 no longer documented" in line
        for line in compare(document, changed).breaking
    )


def test_a_new_required_parameter_is_breaking(document: dict) -> None:
    changed = copy.deepcopy(document)
    changed["paths"]["/v1/cases"]["post"].setdefault("parameters", []).append(
        {"name": "jurisdiction", "in": "query", "required": True}
    )
    assert any("new required parameter" in line for line in compare(document, changed).breaking)


def test_a_parameter_becoming_required_is_breaking(document: dict) -> None:
    changed = copy.deepcopy(document)
    for parameter in changed["paths"]["/v1/search/entities"]["get"]["parameters"]:
        parameter["required"] = True
    diff = compare(document, changed)
    assert any("became required" in line for line in diff.breaking)


def test_a_removed_parameter_is_breaking(document: dict) -> None:
    changed = copy.deepcopy(document)
    changed["paths"]["/v1/search/entities"]["get"]["parameters"] = []
    assert any("parameter" in line and "removed" in line for line in compare(document, changed).breaking)


def test_a_new_operation_is_additive(document: dict) -> None:
    changed = copy.deepcopy(document)
    changed["paths"]["/v1/notes"] = {
        "post": {"operationId": "createNote", "responses": {"201": {}}}
    }
    diff = compare(document, changed)
    assert diff.breaking == []
    assert "createNote: operation added" in diff.additive


def test_a_newly_documented_response_is_additive(document: dict) -> None:
    changed = copy.deepcopy(document)
    changed["paths"]["/v1/cases"]["post"]["responses"]["418"] = {"description": "teapot"}
    diff = compare(document, changed)
    assert diff.breaking == []
    assert "openCase: response 418 now documented" in diff.additive


def test_an_optional_parameter_is_additive(document: dict) -> None:
    changed = copy.deepcopy(document)
    changed["paths"]["/v1/cases"]["post"].setdefault("parameters", []).append(
        {"name": "jurisdiction", "in": "query", "required": False}
    )
    diff = compare(document, changed)
    assert diff.breaking == []
    assert any("optional parameter" in line for line in diff.additive)
