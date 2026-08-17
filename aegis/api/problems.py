"""The RFC 7807 error envelope, as part of the contract (spec 06 §7.2).

Aegis has returned `application/problem+json` since Phase 1, but the shape never
reached the OpenAPI document: every operation declared its success codes and
FastAPI's default `422`, and nothing else. The generated client therefore had no
error type, which is why `ui/src/api/client.ts` hand-wrote `ProblemDetail` and
`StaleRevisionProblem` — the two hand-written response types T38 is supposed to
delete (ADR-039).

These models are declaration-only: `aegis/api/errors.py` still builds the bodies,
because an exception handler must be able to answer before any route matched.
`tests/contract/test_error_envelope.py` asserts the two agree, so the document
cannot describe a shape the handlers do not send.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

PROBLEM_MEDIA_TYPE = "application/problem+json"


class ProblemDetail(BaseModel):
    """The base envelope every Aegis error carries."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "about:blank",
                "title": "request failed",
                "status": 404,
                "detail": "Not Found",
            }
        }
    )

    #: Always `about:blank`. Aegis publishes no per-error URIs: a stable error
    #: taxonomy is a disclosure surface, and 404-vs-403 is already chosen to
    #: avoid confirming a resource exists (spec 06 §1 default 4).
    type: str = "about:blank"
    title: str
    status: int
    #: Human-readable prose. **Opaque to clients** — written so that asking
    #: cannot confirm a resource exists, and never parsed for meaning.
    detail: str | None = None


class ValidationError(BaseModel):
    """One field-level failure from request-model validation."""

    model_config = ConfigDict(extra="forbid")

    loc: list[Any]
    msg: str | None = None
    type: str | None = None


class ValidationProblem(ProblemDetail):
    """422 — the body or parameters did not validate.

    Two shapes reach a caller here and both are documented rather than one being
    left to discovery: `path` is a stable ontology/data coordinate from
    `ActionValidationError` (`predicates.member_of`, `actions.record_claim.roles`),
    and `errors` is FastAPI's per-field list.
    """

    path: str | None = None
    errors: list[ValidationError] | None = None


class InterveningDecision(BaseModel):
    """A decision that landed while the analyst was deciding (spec 05 §2)."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str
    kind: str
    decided_by: str
    note: str | None = None
    result_revision_id: int | None = None


class StaleRevisionProblem(ProblemDetail):
    """409 — the identity ledger moved under the decision.

    The one error body a client reads for meaning. Spec 05 §2 requires the
    analyst to be **re-presented** with what changed rather than told to retry,
    so the intervening decisions travel in the body; a bare "conflict" trains
    people to retry until it sticks.
    """

    parent_revision_id: int
    #: Required, not defaulted. The handler always builds the list, and a
    #: default would make the generated client's field optional — teaching
    #: every caller to handle an absence that cannot happen, in the one error
    #: body they are supposed to read.
    intervening: list[InterveningDecision]


def _response(model: type[ProblemDetail], description: str) -> dict[str, Any]:
    return {"model": model, "description": description}


#: Applied to every `/v1` route at `include_router` time. Both are reachable on
#: every operation: the token is checked before routing, and the rate limiter
#: runs before the gate validates it.
DEFAULT_ERRORS: dict[int | str, dict[str, Any]] = {
    401: _response(ProblemDetail, "No credentials, or a token that does not verify."),
    429: _response(ProblemDetail, "Per-caller rate limit exceeded (spec 06 §1.6)."),
}

FORBIDDEN = {403: _response(ProblemDetail, "Authenticated, but the role gate refused.")}
NOT_FOUND = {
    404: _response(
        ProblemDetail,
        "Not found — or found and not visible to this caller. The two are "
        "deliberately indistinguishable (spec 06 §1 default 4).",
    )
}
UNPROCESSABLE = {
    422: _response(ValidationProblem, "The body or parameters did not validate.")
}
TOO_LARGE = {413: _response(ProblemDetail, "Body exceeds the configured limit.")}
CONFLICT = {409: _response(ProblemDetail, "The resource changed under this request.")}
STALE_REVISION = {
    409: _response(
        StaleRevisionProblem,
        "The identity ledger moved: the decision was computed against a "
        "revision that is no longer current, and the intervening decisions "
        "are in the body (spec 05 §2).",
    )
}


#: The codes that cannot be read off a route: a conflict or a size limit is a
#: property of what the handler does, not of how it is gated. Keyed by
#: operation id so a rename shows up here rather than silently dropping a
#: documented error; `test_error_envelope.py` fails on an entry naming an
#: operation that no longer exists.
ROUTE_SPECIFIC_ERRORS: dict[str, dict[int | str, dict[str, Any]]] = {
    # The identity ledger moved under the decision (spec 05 §2).
    "recordIdentityDecision": STALE_REVISION,
    "batchConfirmCandidates": STALE_REVISION,
    # One rebuild at a time, enforced by a Postgres advisory lock (spec 06 §2.6).
    "rebuildProjections": CONFLICT,
    # Extraction refuses a quarantined record (spec 06 §2.3).
    "extractRecord": CONFLICT,
    # Ingest bodies are bounded by AEGIS_INGEST_MAX_BYTES (ADR-034).
    "landFile": TOO_LARGE,
    "landText": TOO_LARGE,
    "registerEvidence": TOO_LARGE,
}


def route_errors(
    *, roles: bool, path_param: bool, operation_id: str | None
) -> dict[int | str, dict[str, Any]]:
    """The error responses one operation can actually return.

    Derived from the route rather than listed in a table, so the document
    cannot drift from the enforcement:

    * **403** when the route declares a role gate — `authorize()` already tags
      itself with the roles it requires, for exactly this kind of check.
    * **404** when the path carries a resource id: unauthorized and nonexistent
      are deliberately indistinguishable on single-resource reads
      (spec 06 §1 default 4), so any such route can answer 404.
    * **422** always — every route accepts at least the `purpose` query
      parameter, and FastAPI documents 422 for all of them anyway. What this
      changes is the *model*: `ValidationProblem` instead of FastAPI's
      `HTTPValidationError`, so a client can read `path` and `errors`.

    5xx is deliberately absent. A backend being unavailable is a failure, not a
    contract outcome, and declaring it per route would suggest the ones without
    it cannot fail.
    """
    responses: dict[int | str, dict[str, Any]] = dict(DEFAULT_ERRORS)
    responses.update(UNPROCESSABLE)
    if roles:
        responses.update(FORBIDDEN)
    if path_param:
        responses.update(NOT_FOUND)
    if operation_id:
        responses.update(ROUTE_SPECIFIC_ERRORS.get(operation_id, {}))
    return responses


def _api_routes(app: Any) -> list[Any]:
    """Every `APIRoute` the app serves, however deeply the routers nest.

    `app.routes` is not flat. Since FastAPI 0.139 an included router appears as
    one `_IncludedRouter` entry that keeps its own routes at their **unprefixed**
    paths, with the prefix held in `include_context`. A one-level scan therefore
    finds no API routes at all — which is exactly how a first version of this
    ran clean and documented nothing.

    Because the paths are unprefixed here, callers must not filter on `/v1`:
    every `APIRoute` reachable this way *is* a versioned route. The app-level
    `/openapi.json` and `/docs` entries are plain Starlette routes and never
    match.
    """
    from fastapi.routing import APIRoute

    found: list[Any] = []
    pending = list(app.routes)
    seen: set[int] = set()
    while pending:
        route = pending.pop()
        if id(route) in seen:
            continue
        seen.add(id(route))
        if isinstance(route, APIRoute):
            found.append(route)
        for attribute in ("routes",):
            pending.extend(getattr(route, attribute, ()) or ())
        nested = getattr(route, "original_router", None)
        if nested is not None:
            pending.extend(nested.routes)
    return found


def apply_error_responses(app: Any) -> None:
    """Attach the derived error responses to every `/v1` operation.

    Runs after the routers are included, because it reads each route's own
    gate. Anything a route declared for itself wins — nothing here can quietly
    replace a documented response.
    """
    from aegis.api.deps import GATE_ROLES, _dependency_calls

    for route in _api_routes(app):
        roles = any(
            getattr(call, GATE_ROLES, None) for call in _dependency_calls(route.dependant)
        )
        derived = route_errors(
            roles=bool(roles),
            path_param="{" in route.path,
            operation_id=route.operation_id,
        )
        route.responses = {**derived, **route.responses}


def retag_problem_media_type(document: dict[str, Any]) -> dict[str, Any]:
    """Move every 4xx schema onto `application/problem+json` (spec 06 §7.2).

    FastAPI attaches an additional response's model to the *route's* media
    type, which is `application/json` — but these bodies are served as
    `application/problem+json` by `aegis/api/errors.py`, and a contract that
    names the wrong media type is a contract a strict client can fail on.
    There is no per-response media type in the `responses=` declaration, so the
    correction happens here, once, on the finished document.

    Success responses are untouched: they really are `application/json`.
    """
    for item in document.get("paths", {}).values():
        for operation in item.values():
            if not isinstance(operation, dict):
                continue
            for status, response in (operation.get("responses") or {}).items():
                if not str(status).startswith("4"):
                    continue
                content = response.get("content")
                if not content or PROBLEM_MEDIA_TYPE in content:
                    continue
                response["content"] = {
                    PROBLEM_MEDIA_TYPE: content.pop("application/json", {}),
                    **content,
                }
    return document
