"""CSP and security headers on everything served (T22, ADR-032 §1).

The workspace and the API share an origin, which is what makes these headers
load-bearing rather than decorative: a CSP wide enough for the application would
otherwise also apply to every JSON response, and one narrow enough for JSON
would stop the application from starting.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aegis.api import create_app
from aegis.api.security import app_csp

pytestmark = pytest.mark.requirement("ADR-032", "T22")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _directives(policy: str) -> dict[str, str]:
    return {
        part.strip().split(" ", 1)[0]: part.strip()
        for part in policy.split(";")
        if part.strip()
    }


def test_api_responses_may_load_nothing(client: TestClient) -> None:
    """A JSON body has no legitimate reason to fetch anything."""
    response = client.get("/v1/claims/clm_missing")  # 401; headers still apply

    directives = _directives(response.headers["content-security-policy"])
    assert directives["default-src"] == "default-src 'none'"
    assert directives["frame-ancestors"] == "frame-ancestors 'none'"


def test_api_responses_are_not_cached(client: TestClient) -> None:
    """Authorized rows must not land in a shared cache."""
    assert client.get("/v1/claims/clm_missing").headers["cache-control"] == "no-store"


def test_baseline_headers_on_every_response(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cross-origin-opener-policy"] == "same-origin"
    assert "camera=()" in response.headers["permissions-policy"]


def test_hsts_only_over_tls(client: TestClient) -> None:
    """Sending HSTS over plaintext teaches a browser nothing and hides that TLS
    is still missing — the pilot gate's job, not a header's."""
    assert "strict-transport-security" not in client.get("/openapi.json").headers

    secure = TestClient(create_app(), base_url="https://testserver")
    assert "strict-transport-security" in secure.get("/openapi.json").headers


def test_docs_exception_is_scoped_to_the_docs(client: TestClient) -> None:
    """Swagger's CDN is allowed on /docs and nowhere else."""
    docs = client.get("/docs").headers["content-security-policy"]
    api = client.get("/openapi.json").headers["content-security-policy"]

    assert "cdn.jsdelivr.net" in docs
    assert "cdn.jsdelivr.net" not in api


# ── the workspace policy itself ──────────────────────────────────────────────


def test_workspace_policy_admits_the_identity_provider_and_nothing_else() -> None:
    policy = _directives(app_csp("https://sso.example.test/"))

    assert policy["connect-src"] == "connect-src 'self' https://sso.example.test"
    assert policy["default-src"] == "default-src 'self'"


def test_workspace_policy_forbids_inline_and_eval_scripts() -> None:
    """The line that actually matters.

    ``style-src`` admits inline styles because the graph canvas sets them at
    runtime; scripts get no such allowance, and a build that needed one would
    fail here rather than quietly widening the policy.
    """
    policy = _directives(app_csp("https://sso.example.test/"))

    assert policy["script-src"] == "script-src 'self'"
    assert policy["object-src"] == "object-src 'none'"
    assert policy["frame-ancestors"] == "frame-ancestors 'none'"


def test_workspace_policy_survives_an_issuer_without_a_scheme() -> None:
    """A misconfigured issuer must narrow the policy, never widen it."""
    policy = _directives(app_csp("not-a-url"))

    assert policy["connect-src"] == "connect-src 'self'"
