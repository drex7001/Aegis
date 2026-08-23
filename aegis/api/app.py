"""API application factory (T13/T14/T22, spec 06).

Wires OIDC auth, the DB sessionmaker, the ontology registry, the FGA client,
RFC 7807 errors, security headers, per-caller rate limiting, the v1 routers, and
the built workspace bundle into one app.

T22 removed two things from this file and they are worth naming, because their
absence is the point: the anonymous ``/api/*`` projection router, and the mount
that served the legacy explorer out of ``legacy/app/static``. With them went the
``public_route`` marker and the escape hatch it kept open in the deny-by-default
lint (ADR-026). Every route this factory installs is gated; the only mount left
is the workspace bundle, which is application code, not corpus data.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from aegis.api.auth import OIDCAuthenticator
from aegis.api.errors import install_error_handlers
from aegis.api.problems import apply_error_responses, retag_problem_media_type
from aegis.api.ratelimit import build_limiter
from aegis.api.routes import (
    audit,
    cases,
    entities,
    evidence,
    geo,
    graph,
    hypotheses,
    identity,
    ingest,
    ontology as ontology_routes,
    projections,
    provenance,
    review,
    search,
    sets,
    sources,
    tasks,
)
from aegis.api.routes import claims as claims_routes
from aegis.api.security import SecurityHeadersMiddleware
from aegis.api.workspace import WORKSPACE_DIR, workspace_files
from aegis.authz.fga import FGAClient, FGAError
from aegis.authz.outbox import dispatch_forever
from aegis.config import get_settings
from aegis.evidence import get_vault
from aegis.ontology import load
from aegis.ontology.modules import disabled_vocabulary_in_use
from aegis.store import Claim, Entity, get_sessionmaker

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _install_openapi(app: FastAPI) -> None:
    """Generate the document once, then correct the error media type.

    FastAPI attaches an additional response's model to the route's media type,
    `application/json`, but those bodies go out as `application/problem+json`.
    The fix has to happen on the finished document because `responses=` has no
    per-response media type (spec 06 §7.2).
    """
    generate = app.openapi

    def openapi() -> dict:
        if app.openapi_schema is None:
            app.openapi_schema = retag_problem_media_type(generate())
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]


class DisabledVocabularyInUseError(RuntimeError):
    """A disabled module's vocabulary is still recorded in the claim store."""


def _refuse_disabled_vocabulary_in_use(app: FastAPI) -> None:
    """Refuse to serve a store the registry can no longer explain (spec 08 §2.6).

    Disabling a module removes vocabulary from validation and deletes nothing —
    claims are immutable (ADR-013). Serving anyway would render rows whose
    predicate the API cannot describe, cannot filter by category, and cannot
    validate an edit against. Failing at startup makes that a deployment
    mistake rather than a silent data-quality one.

    Skipped when no module is disabled, so the common path costs no query, and
    tolerant of an unreachable database: a missing store is the DB layer's error
    to report, not this check's.
    """
    ontology = app.state.ontology
    if not any(not info.enabled for info in ontology.modules.values()):
        return
    with suppress(SQLAlchemyError):
        with app.state.sessionmaker() as session:
            in_use = disabled_vocabulary_in_use(
                ontology,
                predicates=session.scalars(select(Claim.predicate).distinct()),
                entity_types=session.scalars(select(Entity.entity_type).distinct()),
            )
        if in_use:
            detail = "; ".join(
                f"{module}: {', '.join(names)}" for module, names in sorted(in_use.items())
            )
            raise DisabledVocabularyInUseError(
                "refusing to serve — recorded claims still use vocabulary from "
                f"disabled ontology modules ({detail}). Re-enable the module or "
                "migrate the rows; disabling is an authoring control, not a way "
                "to hide data (spec 08 §2.6)."
            )


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _refuse_disabled_vocabulary_in_use(app)
        dispatcher = None
        if app.state.fga is not None:
            dispatcher = asyncio.create_task(
                dispatch_forever(
                    app.state.sessionmaker,
                    app.state.fga,
                    interval_seconds=settings.authz_outbox_interval_seconds,
                    batch_size=settings.authz_outbox_batch_size,
                ),
                name="aegis-authz-outbox",
            )
        app.state.authz_dispatcher_task = dispatcher
        try:
            yield
        finally:
            if dispatcher is not None:
                dispatcher.cancel()
                with suppress(asyncio.CancelledError):
                    await dispatcher

    app = FastAPI(
        title="Aegis API",
        version="1.0.0",
        description="Governed claims-based intelligence platform (speckit Phase 2).",
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.sessionmaker = get_sessionmaker()
    ontology_path = Path(settings.ontology_path)
    app.state.ontology = load(
        ontology_path if ontology_path.is_absolute() else _REPO_ROOT / ontology_path
    )
    app.state.authenticator = OIDCAuthenticator(settings)
    # Built once: the MinIO adapter opens no connection at construction, so
    # this stays honest about startup dependencies while saving a client per
    # request on the ingest path.
    app.state.vault = get_vault()
    app.state.fga = None
    if settings.fga_store_id:
        with suppress(FGAError):
            app.state.fga = FGAClient()

    install_error_handlers(app)
    app.state.limiter = build_limiter()
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        SecurityHeadersMiddleware,
        issuer_url=settings.keycloak_url,
    )

    for router in (
        claims_routes.router,
        entities.router,
        sources.router,
        review.router,
        evidence.router,
        cases.router,
        hypotheses.router,
        tasks.router,
        audit.router,
        provenance.router,
        graph.router,
        geo.router,
        ingest.router,
        identity.router,
        search.router,
        sets.router,
        projections.router,
        ontology_routes.router,
    ):
        # Every `/v1` route can answer 401 and 429 — the token is checked before
        # routing and the limiter runs before the gate validates it — so they
        # are declared once here rather than repeated on every operation
        # (spec 06 §7.2). Route-level `responses` override on conflict.
        app.include_router(router, prefix="/v1")

    # The error envelope becomes part of the contract (spec 06 §7.2), derived
    # from each route's own gate rather than listed in a table beside it.
    apply_error_responses(app)
    _install_openapi(app)

    # The workspace bundle, when it has been built. Mounted last so it cannot
    # shadow an API path, and only when present so a Python-only checkout runs
    # the API without a Node toolchain.
    if WORKSPACE_DIR.is_dir():
        app.mount("/", workspace_files(), name="workspace")

    return app
