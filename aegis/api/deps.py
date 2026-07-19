"""API dependencies: sessions, ontology, FGA, and the ``authorize`` gate (T12/T13).

Deny-by-default is enforced structurally: every route must carry a dependency
produced by :func:`authorize` (or ``current_user`` directly); a CI lint test
walks the route table and fails on any ungated route (spec 03 §4 rule 1).

**There is no exemption.** The ``public_route`` marker ADR-019 introduced, and
the branch of :func:`find_ungated_routes` that honored it, were deleted by T22
along with the anonymous ``/api/*`` routes they existed for (ADR-026). An
unauthenticated route is now unrepresentable rather than merely discouraged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Iterator

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from aegis.api.auth import CurrentUser, UserContext
from aegis.audit import append as append_audit
from aegis.authz.fga import FGAClient, FGAError
from aegis.ontology import Ontology

GATE_MARKER = "_aegis_gate"


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.sessionmaker() as session:
        yield session


def get_ontology(request: Request) -> Ontology:
    return request.app.state.ontology


def get_fga(request: Request) -> FGAClient | None:
    """The app's FGA client, or None when unconfigured (dev without bootstrap)."""
    return request.app.state.fga


DbSession = Annotated[Session, Depends(get_session)]
OntologyDep = Annotated[Ontology, Depends(get_ontology)]
FGADep = Annotated[FGAClient | None, Depends(get_fga)]


@dataclass(frozen=True, slots=True)
class AuthContext:
    user: UserContext
    purpose: str | None


def _audit_decision(
    request: Request,
    user: UserContext,
    *,
    action: str,
    decision: str,
    purpose: str | None,
    detail: dict,
) -> None:
    """Denials (and sensitive-read allows) persist even when the request fails."""
    with request.app.state.sessionmaker() as session:
        with session.begin():
            append_audit(
                session,
                actor=user.sub,
                session_id=None,
                purpose=purpose,
                case_id=detail.get("case_id"),
                action=action,
                resource_type="route",
                resource_id=f"{request.method} {request.url.path}",
                decision=decision,
                detail=detail,
            )


def authorize(*roles: str, purpose_required: bool = False):
    """Route gate: role check (RBAC) + purpose capture; FGA checks stay in the
    handlers that know the object (spec 03 §4).

    ``roles`` empty means "any authenticated platform user".  ``purpose_required``
    marks sensitive reads: the ``purpose`` query parameter becomes mandatory and
    the allow itself is audited (GOAL.md §12.4).
    """

    async def gate(
        request: Request,
        user: CurrentUser,
        purpose: Annotated[str | None, Query(description="Reason for access")] = None,
    ) -> AuthContext:
        if roles and not user.has_role(*roles):
            _audit_decision(
                request,
                user,
                action="authz.deny",
                decision="deny",
                purpose=purpose,
                detail={"required_roles": sorted(roles), "roles": sorted(user.roles)},
            )
            raise HTTPException(403, "role not permitted for this operation")
        if purpose_required:
            if not purpose or not purpose.strip():
                raise HTTPException(422, "a purpose query parameter is required here")
            _audit_decision(
                request,
                user,
                action=f"read:{request.url.path}",
                decision="allow",
                purpose=purpose,
                detail={"query": dict(request.query_params)},
            )
        return AuthContext(user=user, purpose=purpose)

    setattr(gate, GATE_MARKER, True)
    return gate


def _dependency_calls(dependant) -> Iterator[object]:
    yield dependant.call
    for sub in dependant.dependencies:
        yield from _dependency_calls(sub)


def find_ungated_routes(app) -> list[str]:
    """Every route must carry an ``authorize``/``current_user`` dependency —
    otherwise it fails CI (spec 03 §4 rule 1). No exemptions exist (ADR-026).

    Mounts and static files are skipped because they have no dependency graph to
    inspect, not because they are trusted: what may be mounted is constrained
    separately by ``tests/component/test_route_gating.py``, which asserts the
    workspace bundle is the only one."""
    from aegis.api.auth import current_user

    ungated: list[str] = []
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        dependant = getattr(route, "dependant", None)
        if endpoint is None or dependant is None:
            continue  # mounts, static files, docs — not API endpoints
        gated = any(
            call is current_user or getattr(call, GATE_MARKER, False)
            for call in _dependency_calls(dependant)
        )
        if not gated:
            methods = ",".join(sorted(getattr(route, "methods", []) or []))
            ungated.append(f"{methods} {route.path}")
    return ungated


def require_fga(fga: FGAClient | None) -> FGAClient:
    if fga is None:
        raise HTTPException(503, "authorization backend (OpenFGA) is not configured")
    return fga


def fga_check_or_404(
    fga: FGAClient | None, user: UserContext, relation: str, object_: str
) -> None:
    """Object-level check; failure is indistinguishable from absence (no leaks)."""
    try:
        allowed = require_fga(fga).check(f"user:{user.sub}", relation, object_)
    except FGAError as exc:
        raise HTTPException(503, f"authorization backend unavailable: {exc}") from exc
    if not allowed:
        raise HTTPException(404, "not found")
