"""API application factory (T13/T14, spec 06).

Wires OIDC auth, the DB sessionmaker, the ontology registry, the FGA client,
RFC 7807 errors, the v1 routers, the legacy ``/api/*`` projection surface, and
the mounted legacy UI (T14) into one app.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from aegis.api.auth import OIDCAuthenticator
from aegis.api.deps import public_route
from aegis.api.errors import install_error_handlers
from aegis.api.routes import audit, cases, entities, evidence, graph, review, sources
from aegis.api.routes import claims as claims_routes
from aegis.authz.fga import FGAClient, FGAError
from aegis.config import get_settings
from aegis.ontology import load
from aegis.store import get_sessionmaker

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STATIC_DIR = _REPO_ROOT / "legacy" / "app" / "static"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Aegis API",
        version="1.0.0",
        description="Governed claims-based intelligence platform (speckit Phase 1).",
    )

    app.state.settings = settings
    app.state.sessionmaker = get_sessionmaker()
    ontology_path = Path(settings.ontology_path)
    app.state.ontology = load(
        ontology_path if ontology_path.is_absolute() else _REPO_ROOT / ontology_path
    )
    app.state.authenticator = OIDCAuthenticator(settings)
    app.state.fga = None
    if settings.fga_store_id:
        with suppress(FGAError):
            app.state.fga = FGAClient()

    install_error_handlers(app)

    for router in (
        claims_routes.router,
        entities.router,
        sources.router,
        review.router,
        evidence.router,
        cases.router,
        audit.router,
    ):
        app.include_router(router, prefix="/v1")
    # legacy-compatible projection surface (unversioned, spec 06)
    app.include_router(graph.router)

    if _STATIC_DIR.is_dir():
        @app.get("/", include_in_schema=False)
        @public_route
        def index() -> FileResponse:
            return FileResponse(_STATIC_DIR / "index.html")

        app.mount(
            "/static", StaticFiles(directory=_STATIC_DIR), name="static"
        )

    return app
