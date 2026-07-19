"""Per-caller request limiting (specs/06 §1 default 6).

T16a rate-limited the anonymous ``/api/*`` routes per IP as interim containment.
T22 deletes those routes, and deleting the control with them would leave the
governed graph routes — the enumeration surface ADR-026 was actually worried
about — with no bound on call *rate* at all, only on response size. So the limit
moves here and gets stronger: per caller instead of per IP, applied by default
to every route rather than to four of them.

The key is a digest of the bearer token, not the ``sub`` inside it. Reading
``sub`` would mean decoding a token the gate has not validated yet (the limiter
runs in middleware, before the route's dependencies), and an unvalidated ``sub``
is attacker-chosen: a caller could rotate it per request to escape the limit, or
pin it to a victim's to exhaust theirs. A token digest can only be changed by
obtaining another token from Keycloak. Unauthenticated requests fall back to the
peer address, which is all there is to key on before a token exists.

This is a bound on abuse, not an authorization decision — like every limit in
specs/06 §1, it constrains what an authorized caller may do at speed, and
constrains nothing about what they may see.
"""

from __future__ import annotations

import hashlib

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from aegis.config import get_settings


def caller_key(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token:
        return "sub:" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]
    return "peer:" + get_remote_address(request)


def build_limiter() -> Limiter:
    limit = get_settings().api_rate_limit_per_minute
    return Limiter(key_func=caller_key, default_limits=[f"{limit}/minute"])


__all__ = ["build_limiter", "caller_key"]
