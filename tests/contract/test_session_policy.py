"""Session lifetimes and the absence of an ambient credential (T42, H-19).

Two properties that are cheap to hold and easy to lose silently.

**Session lifetimes** were not declared at all until T42: the realm inherited
whatever the running Keycloak version defaulted to, which is not a policy. The
values are argued in `speckit/specs/03-security.md` §1.1; this file's job is
that they cannot quietly disappear again.

**The CSRF model** is that there is nothing to defend: authentication is a
bearer token in a header, Aegis sets no cookie and reads none, so a cross-site
request carries no authority. The browser attaches cookies automatically and an
`Authorization` header never — which is a property one well-meaning
"just use a session cookie" change would remove. So it is asserted, in the
document the client is generated from and in the live route table.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis.api import create_app

pytestmark = pytest.mark.requirement("Article-VI", "H-19", "T42")

ROOT = Path(__file__).resolve().parents[2]
REALM = ROOT / "infra" / "keycloak" / "aegis-realm.json"

#: setting -> seconds. Spec 03 §1.1 argues each number.
REQUIRED_LIFETIMES = {
    "ssoSessionIdleTimeout": 1800,
    "ssoSessionMaxLifespan": 28800,
    "ssoSessionIdleTimeoutRememberMe": 1800,
    "ssoSessionMaxLifespanRememberMe": 28800,
    "accessTokenLifespan": 300,
    "clientSessionIdleTimeout": 1800,
    "clientSessionMaxLifespan": 28800,
}


@pytest.fixture(scope="module")
def realm() -> dict:
    return json.loads(REALM.read_text(encoding="utf-8"))


def test_the_realm_declares_every_session_lifetime(realm: dict) -> None:
    missing = [name for name in REQUIRED_LIFETIMES if name not in realm]
    assert not missing, f"the realm would inherit Keycloak's defaults for {missing}"


def test_the_lifetimes_are_the_values_the_spec_argues(realm: dict) -> None:
    assert {name: realm[name] for name in REQUIRED_LIFETIMES} == REQUIRED_LIFETIMES


def test_remember_me_cannot_outlive_the_ordinary_session(realm: dict) -> None:
    """An unset RememberMe variant reverts to the default and undoes the policy."""
    assert realm["ssoSessionIdleTimeoutRememberMe"] <= realm["ssoSessionIdleTimeout"]
    assert realm["ssoSessionMaxLifespanRememberMe"] <= realm["ssoSessionMaxLifespan"]


def test_the_access_token_is_shorter_than_the_session(realm: dict) -> None:
    """The token lifespan is what bounds the post-logout window (spec 03 §1.1)."""
    assert realm["accessTokenLifespan"] < realm["ssoSessionIdleTimeout"]


def test_the_realm_still_imports_as_plain_keycloak_json(realm: dict) -> None:
    """No commentary keys: Keycloak's realm import rejects unknown properties,
    so the rationale lives in the spec and in this file, never in the JSON."""
    assert not [key for key in realm if key.startswith("_")]
    assert realm["realm"] == "aegis"


# ── no ambient credential (the CSRF model) ──────────────────────────────────


def test_no_route_authenticates_with_a_cookie() -> None:
    """The documented contract: not one security scheme is cookie-borne."""
    document = create_app().openapi()
    schemes = (document.get("components") or {}).get("securitySchemes") or {}
    cookie_schemes = [
        name for name, scheme in schemes.items() if scheme.get("in") == "cookie"
    ]
    assert not cookie_schemes, cookie_schemes


def test_no_route_reads_a_cookie_parameter() -> None:
    """And the live routes agree with the document.

    A cookie parameter is how an ambient credential arrives without anyone
    declaring a security scheme for it, which is exactly the change this test
    exists to catch.
    """
    document = create_app().openapi()
    offenders = []
    for path, operations in document["paths"].items():
        for method, operation in operations.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            for parameter in operation.get("parameters") or []:
                if parameter.get("in") == "cookie":
                    offenders.append(f"{method.upper()} {path}: {parameter['name']}")
    assert not offenders, offenders


def test_the_app_sets_no_authentication_cookie() -> None:
    """Aegis has no session store, so no response may start one.

    Checked on a real unauthenticated request rather than by reading code: a
    cookie set by middleware would not appear in any route signature.
    """
    from fastapi.testclient import TestClient

    with TestClient(create_app()) as client:
        response = client.get("/v1/ontology/vocabulary")
    assert response.status_code == 401
    assert "set-cookie" not in {name.lower() for name in response.headers}


def test_the_spec_states_the_model_it_relies_on() -> None:
    """An unwritten security property is one a future change removes unnoticed."""
    spec = (ROOT / "speckit" / "specs" / "03-security.md").read_text(encoding="utf-8")
    assert "### 1.1 Session lifetimes" in spec
    assert "### 1.2 There is no ambient credential" in spec
    assert "### 1.3 Multi-tab behaviour" in spec
