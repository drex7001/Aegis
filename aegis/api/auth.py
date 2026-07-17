"""OIDC bearer authentication against Keycloak (speckit T11, spec 03 §1).

Tokens are validated locally: signature via the realm's JWKS (fetched once and
cached by :class:`jwt.PyJWKClient`), then issuer, audience, and lifetime.  The
resulting :class:`UserContext` carries exactly what enforcement needs — subject,
platform roles, and the clearance level (an integer index into the ontology's
ordered ``handling_codes``).

AC (tasks T11): no token → 401 · wrong audience → 401.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from aegis.config import Settings, get_settings
from aegis.ontology import KNOWN_ROLES

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


class AuthenticationError(Exception):
    """Token missing, malformed, or failing validation — always maps to 401."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class UserContext:
    """The authenticated caller, as enforcement sees it."""

    sub: str
    username: str
    roles: frozenset[str]
    clearance: int
    claims: dict[str, Any]

    def has_role(self, *roles: str) -> bool:
        return bool(self.roles.intersection(roles))


class OIDCAuthenticator:
    """Validates realm bearer tokens; one instance per process (JWKS cached)."""

    def __init__(self, settings: Settings | None = None, jwks_client: Any | None = None) -> None:
        settings = settings or get_settings()
        self.issuer = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
        self.audience = settings.api_audience
        self._jwks = jwks_client or jwt.PyJWKClient(
            f"{self.issuer}/protocol/openid-connect/certs", cache_keys=True
        )

    def authenticate(self, token: str) -> UserContext:
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
        except jwt.PyJWKClientError as exc:
            raise AuthenticationError(f"unable to resolve signing key: {exc}") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthenticationError(f"malformed token: {exc}") from exc
        try:
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
        except jwt.InvalidAudienceError as exc:
            raise AuthenticationError("token audience is not this API") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthenticationError(f"invalid token: {exc}") from exc

        roles = frozenset(claims.get("realm_access", {}).get("roles", ())) & KNOWN_ROLES
        try:
            clearance = int(claims.get("clearance", 0))
        except (TypeError, ValueError) as exc:
            raise AuthenticationError("clearance claim must be an integer") from exc
        return UserContext(
            sub=claims["sub"],
            username=claims.get("preferred_username", claims["sub"]),
            roles=roles,
            clearance=clearance,
            claims=claims,
        )


_bearer = HTTPBearer(auto_error=False)


def get_authenticator(request: Request) -> OIDCAuthenticator:
    """App-scoped authenticator (created in the app factory; overridable in tests)."""
    authenticator = getattr(request.app.state, "authenticator", None)
    if authenticator is None:  # pragma: no cover - app factory always sets it
        authenticator = OIDCAuthenticator()
        request.app.state.authenticator = authenticator
    return authenticator


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    authenticator: Annotated[OIDCAuthenticator, Depends(get_authenticator)],
) -> UserContext:
    if credentials is None:
        raise HTTPException(401, "missing bearer token", headers=_UNAUTHORIZED_HEADERS)
    try:
        return authenticator.authenticate(credentials.credentials)
    except AuthenticationError as exc:
        raise HTTPException(401, exc.reason, headers=_UNAUTHORIZED_HEADERS) from exc


CurrentUser = Annotated[UserContext, Depends(current_user)]
