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

from aegis.api.auth import OIDCAuthenticator
from aegis.api.errors import install_error_handlers
from aegis.api.ratelimit import build_limiter
from aegis.api.routes import (
    audit,
    cases,
    entities,
    evidence,
    graph,
    identity,
    ingest,
    ontology as ontology_routes,
    provenance,
    review,
    search,
    sources,
)
from aegis.api.routes import claims as claims_routes
from aegis.api.security import SecurityHeadersMiddleware
from aegis.api.workspace import WORKSPACE_DIR, workspace_files
from aegis.authz.fga import FGAClient, FGAError
from aegis.authz.outbox import dispatch_forever
from aegis.config import get_settings
from aegis.evidence import get_vault
from aegis.ontology import load
from aegis.store import get_sessionmaker

_REPO_ROOT = Path(__file__).resolve().parents[2]


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
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
        audit.router,
        provenance.router,
        graph.router,
        ingest.router,
        identity.router,
        search.router,
        ontology_routes.router,
    ):
        app.include_router(router, prefix="/v1")

    # The workspace bundle, when it has been built. Mounted last so it cannot
    # shadow an API path, and only when present so a Python-only checkout runs
    # the API without a Node toolchain.
    if WORKSPACE_DIR.is_dir():
        app.mount("/", workspace_files(), name="workspace")

    return app
