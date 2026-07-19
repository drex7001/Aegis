"""AuthN tests (speckit T11): OIDC bearer validation.

No live Keycloak needed — tokens are signed with a test RSA key and the JWKS
client is stubbed to return it, which exercises everything *after* key
retrieval exactly as production does.

AC: no token → 401 · wrong audience → 401.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aegis.api.auth import (
    AuthenticationError,
    CurrentUser,
    OIDCAuthenticator,
    UserContext,
)
from aegis.config import Settings

ISSUER = "http://localhost:8180/realms/aegis"
AUDIENCE = "aegis-api"

pytestmark = pytest.mark.requirement("Article-VI", "T11")

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()


class _StubSigningKey:
    key = _PUBLIC_KEY


class _StubJWKSClient:
    def get_signing_key_from_jwt(self, token: str) -> _StubSigningKey:
        return _StubSigningKey()


def make_token(**overrides) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-123",
        "preferred_username": "dev-analyst",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "realm_access": {"roles": ["analyst", "offline_access"]},
        "clearance": 2,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, _PRIVATE_KEY, algorithm="RS256")


@pytest.fixture()
def authenticator() -> OIDCAuthenticator:
    settings = Settings(
        AEGIS_DATABASE_URL="postgresql+psycopg://unused:unused@localhost/unused",
        KEYCLOAK_URL="http://localhost:8180",
        KEYCLOAK_REALM="aegis",
        AEGIS_API_AUDIENCE=AUDIENCE,
    )
    return OIDCAuthenticator(settings, jwks_client=_StubJWKSClient())


def test_valid_token_yields_user_context(authenticator: OIDCAuthenticator) -> None:
    context = authenticator.authenticate(make_token())
    assert isinstance(context, UserContext)
    assert context.sub == "user-123"
    assert context.username == "dev-analyst"
    assert context.clearance == 2
    # only platform roles survive; Keycloak built-ins are dropped
    assert context.roles == frozenset({"analyst"})
    assert context.has_role("analyst", "supervisor")
    assert not context.has_role("auditor")


def test_wrong_audience_rejected(authenticator: OIDCAuthenticator) -> None:
    with pytest.raises(AuthenticationError, match="audience"):
        authenticator.authenticate(make_token(aud="account"))


def test_wrong_issuer_rejected(authenticator: OIDCAuthenticator) -> None:
    with pytest.raises(AuthenticationError, match="invalid token"):
        authenticator.authenticate(make_token(iss="http://evil.example/realms/aegis"))


def test_expired_token_rejected(authenticator: OIDCAuthenticator) -> None:
    expired = datetime.now(timezone.utc) - timedelta(minutes=1)
    with pytest.raises(AuthenticationError, match="invalid token"):
        authenticator.authenticate(make_token(exp=expired))


def test_missing_subject_rejected(authenticator: OIDCAuthenticator) -> None:
    with pytest.raises(AuthenticationError):
        authenticator.authenticate(make_token(sub=None))


def test_garbage_token_rejected(authenticator: OIDCAuthenticator) -> None:
    with pytest.raises(AuthenticationError):
        authenticator.authenticate("not-a-jwt")


def test_non_integer_clearance_rejected(authenticator: OIDCAuthenticator) -> None:
    with pytest.raises(AuthenticationError, match="clearance"):
        authenticator.authenticate(make_token(clearance="TOP SECRET"))


def test_missing_clearance_defaults_to_zero(authenticator: OIDCAuthenticator) -> None:
    context = authenticator.authenticate(make_token(clearance=None))
    assert context.clearance == 0


# ── the FastAPI dependency: 401 semantics over HTTP ─────────────────────────


@pytest.fixture()
def client(authenticator: OIDCAuthenticator) -> TestClient:
    app = FastAPI()
    app.state.authenticator = authenticator

    @app.get("/protected")
    def protected(user: CurrentUser) -> dict:
        return {"sub": user.sub, "roles": sorted(user.roles)}

    return TestClient(app)


def test_no_token_is_401(client: TestClient) -> None:
    response = client.get("/protected")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_wrong_audience_is_401(client: TestClient) -> None:
    response = client.get(
        "/protected", headers={"Authorization": f"Bearer {make_token(aud='account')}"}
    )
    assert response.status_code == 401


def test_valid_token_is_200(client: TestClient) -> None:
    response = client.get(
        "/protected", headers={"Authorization": f"Bearer {make_token()}"}
    )
    assert response.status_code == 200
    assert response.json() == {"sub": "user-123", "roles": ["analyst"]}


# ── clock skew between Keycloak and this process (T22) ──────────────────────
#
# Found by driving a real browser login against the dev stack: the Keycloak
# container ran ~2s ahead of the host, and with zero leeway PyJWT rejected every
# freshly minted token with "not yet valid (iat)". Zero looks stricter than a
# small tolerance but is not safer — it is the difference between a platform
# that works and one that refuses every valid token (RFC 7519 §4.1.4).


def _authenticator(skew: int) -> OIDCAuthenticator:
    return OIDCAuthenticator(
        Settings(
            AEGIS_DATABASE_URL="postgresql+psycopg://unused:unused@localhost/unused",
            KEYCLOAK_URL="http://localhost:8180",
            KEYCLOAK_REALM="aegis",
            AEGIS_API_AUDIENCE=AUDIENCE,
            AEGIS_OIDC_CLOCK_SKEW_SECONDS=skew,
        ),
        jwks_client=_StubJWKSClient(),
    )


@pytest.mark.requirement("T22")
def test_token_minted_slightly_ahead_is_accepted() -> None:
    ahead = datetime.now(timezone.utc) + timedelta(seconds=5)
    token = make_token(iat=ahead, exp=ahead + timedelta(minutes=5))

    assert _authenticator(60).authenticate(token).sub == "user-123"


@pytest.mark.requirement("T22")
def test_token_minted_far_ahead_is_still_rejected() -> None:
    """Leeway is a tolerance for drift, not an acceptance of arbitrary futures."""
    ahead = datetime.now(timezone.utc) + timedelta(minutes=10)

    with pytest.raises(AuthenticationError):
        _authenticator(60).authenticate(
            make_token(iat=ahead, exp=ahead + timedelta(minutes=5))
        )


@pytest.mark.requirement("T22")
def test_expired_token_beyond_the_leeway_is_still_rejected() -> None:
    past = datetime.now(timezone.utc) - timedelta(minutes=10)

    with pytest.raises(AuthenticationError):
        _authenticator(60).authenticate(
            make_token(iat=past, exp=past + timedelta(minutes=1))
        )


@pytest.mark.requirement("T22")
def test_leeway_does_not_extend_a_token_indefinitely() -> None:
    """A token 61s expired must fail with 60s of leeway — the window is the
    tolerance, not a grace period that grows with it."""
    past = datetime.now(timezone.utc) - timedelta(seconds=61)

    with pytest.raises(AuthenticationError):
        _authenticator(60).authenticate(make_token(iat=past, exp=past))
