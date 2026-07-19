"""Security headers and CSP for everything this process serves (T22, ADR-032).

The workspace is served from the same origin as the API it calls, so one
middleware covers both — but they are not the same kind of response and do not
get the same policy:

* **API responses are data.** ``default-src 'none'`` says a JSON body has no
  business loading anything at all; combined with ``nosniff`` it closes the
  content-sniffing path by which a JSON response gets executed as script.
  ``no-store`` keeps authorized rows out of shared caches.
* **The workspace is an application.** It loads its own bundle and talks to
  this API and to Keycloak, and nothing else — ``connect-src`` names exactly
  those two origins, so an injected script cannot exfiltrate to a third.
* **The docs UI pulls Swagger from a CDN.** That is a real exception rather
  than a hidden one: it is scoped to the two docs paths, it is off unless the
  docs are enabled, and it is written here where a reader will find it.

``frame-ancestors 'none'`` is what actually prevents clickjacking;
``X-Frame-Options`` is kept beside it for browsers that predate CSP 2. HSTS is
emitted only over TLS — sending it over plaintext http teaches a browser
nothing, and the dev stack is http by design until the pilot gate.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

#: Swagger UI's assets. Named once so the exception is greppable.
_DOCS_CDN = "https://cdn.jsdelivr.net"

_DOCS_PATHS = frozenset({"/docs", "/redoc", "/docs/oauth2-redirect"})

_BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    ),
}

_API_CSP = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""


def app_csp(issuer_url: str) -> str:
    """The workspace policy: own bundle, own API, and the identity provider.

    ``style-src`` admits ``'unsafe-inline'`` because the graph canvas sets
    element styles at runtime; that is a real weakening, limited to styles, and
    it buys the one capability the canvas cannot work without. Scripts get no
    such exemption — ``script-src 'self'`` with no ``unsafe-inline`` and no
    ``unsafe-eval`` is the line that matters, and the build is configured to
    stay inside it.
    """
    keycloak = _origin(issuer_url)
    connect = " ".join(filter(None, ("'self'", keycloak)))
    return "; ".join(
        [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data:",
            "font-src 'self'",
            f"connect-src {connect}",
            "object-src 'none'",
            "frame-src 'none'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
    )


def _docs_csp() -> str:
    return "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self' {_DOCS_CDN}",
            f"style-src 'self' 'unsafe-inline' {_DOCS_CDN}",
            f"img-src 'self' data: {_DOCS_CDN}",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
        ]
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds the headers above to every response this app produces."""

    def __init__(self, app: ASGIApp, *, issuer_url: str, api_prefixes: tuple[str, ...] = ("/v1", "/openapi.json")) -> None:
        super().__init__(app)
        self._app_csp = app_csp(issuer_url)
        self._docs_csp = _docs_csp()
        self._api_prefixes = api_prefixes

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path

        if path in _DOCS_PATHS:
            csp = self._docs_csp
        elif path.startswith(self._api_prefixes):
            csp = _API_CSP
            response.headers.setdefault("Cache-Control", "no-store")
        else:
            csp = self._app_csp

        response.headers.setdefault("Content-Security-Policy", csp)
        for header, value in _BASE_HEADERS.items():
            response.headers.setdefault(header, value)
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


__all__ = ["SecurityHeadersMiddleware", "app_csp"]
