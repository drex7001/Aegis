"""RFC 7807 problem+json error handling (spec 06)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from aegis.actions import ActionValidationError
from aegis.er.adjudication import StaleRevisionError

_MEDIA_TYPE = "application/problem+json"


def _problem(status: int, title: str, detail: str, **extra: object) -> JSONResponse:
    body = {"type": "about:blank", "title": title, "status": status, "detail": detail}
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type=_MEDIA_TYPE)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ActionValidationError)
    async def _on_action_error(_: Request, exc: ActionValidationError) -> JSONResponse:
        # Validation failures carry a stable ontology/data path (ADR-013).
        return _problem(422, "validation failed", exc.message, path=exc.path)

    @app.exception_handler(StaleRevisionError)
    async def _on_stale_revision(_: Request, exc: StaleRevisionError) -> JSONResponse:
        # 409 rather than 422: the body was well-formed and the decision was
        # valid when the analyst computed it — what changed is the world. The
        # intervening decisions travel in the response because spec 05 §2 asks
        # for the analyst to be *re-presented* with what happened; a bare
        # "conflict" trains people to retry until it sticks. `result_revision_id`
        # is what a reconsidered decision would send as its new parent.
        return _problem(
            409,
            "stale revision",
            str(exc),
            parent_revision_id=exc.parent_revision_id,
            intervening=[
                {
                    "decision_id": decision.decision_id,
                    "kind": decision.kind,
                    "decided_by": decision.decided_by,
                    "note": decision.decision_note,
                    "result_revision_id": decision.result_revision_id,
                }
                for decision in exc.intervening
            ],
        )

    @app.exception_handler(StarletteHTTPException)
    async def _on_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _problem(exc.status_code, "request failed", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _on_request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # errors() may carry exception objects in ctx; keep only serializable parts.
        errors = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return _problem(
            422, "invalid request", "request body or parameters are invalid", errors=errors
        )
