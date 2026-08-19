"""RFC 7807 problem+json error handling (spec 06 §7.2).

Every body here is built from the models in ``aegis/api/problems.py`` — the same
models the OpenAPI document declares. Before T36 the shapes lived only in this
file and the document said nothing about them, which is how ``ui/src/api/client.ts``
ended up hand-writing ``ProblemDetail`` and ``StaleRevisionProblem``. Building
from the models is what stops the contract and the runtime drifting apart; a
test asserting they agree would only notice afterwards.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from aegis.actions import ActionValidationError
from aegis.api.problems import (
    PROBLEM_MEDIA_TYPE,
    InterveningDecision,
    ProblemDetail,
    StaleRevisionProblem,
    ValidationError,
    ValidationProblem,
)
from aegis.er.adjudication import StaleRevisionError


def _json(
    problem: ProblemDetail, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        problem.model_dump(mode="json", exclude_none=True),
        status_code=problem.status,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ActionValidationError)
    async def _on_action_error(_: Request, exc: ActionValidationError) -> JSONResponse:
        # Validation failures carry a stable ontology/data path (ADR-013).
        return _json(
            ValidationProblem(
                title="validation failed", status=422, detail=exc.message, path=exc.path
            )
        )

    @app.exception_handler(StaleRevisionError)
    async def _on_stale_revision(_: Request, exc: StaleRevisionError) -> JSONResponse:
        # 409 rather than 422: the body was well-formed and the decision was
        # valid when the analyst computed it — what changed is the world. The
        # intervening decisions travel in the response because spec 05 §2 asks
        # for the analyst to be *re-presented* with what happened; a bare
        # "conflict" trains people to retry until it sticks. `result_revision_id`
        # is what a reconsidered decision would send as its new parent.
        return _json(
            StaleRevisionProblem(
                title="stale revision",
                status=409,
                detail=str(exc),
                parent_revision_id=exc.parent_revision_id,
                intervening=[
                    InterveningDecision(
                        decision_id=decision.decision_id,
                        kind=decision.kind,
                        decided_by=decision.decided_by,
                        note=decision.decision_note,
                        result_revision_id=decision.result_revision_id,
                    )
                    for decision in exc.intervening
                ],
            )
        )

    @app.exception_handler(StarletteHTTPException)
    async def _on_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # The exception's headers travel with it. Rebuilding the response as
        # problem+json used to drop them, which silently cost every 401 its
        # `WWW-Authenticate: Bearer` — required by RFC 7235 §3.1 and the only
        # thing telling a client *how* to authenticate. Found by T52's
        # re-verification of the authenticated surface.
        return _json(
            ProblemDetail(title="request failed", status=exc.status_code, detail=str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _on_request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # errors() may carry exception objects in ctx; keep only serializable parts.
        return _json(
            ValidationProblem(
                title="invalid request",
                status=422,
                detail="request body or parameters are invalid",
                errors=[
                    ValidationError(
                        loc=list(e.get("loc", ())), msg=e.get("msg"), type=e.get("type")
                    )
                    for e in exc.errors()
                ],
            )
        )
