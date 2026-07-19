"""Serving the built workspace bundle (T22, ADR-032).

This is what replaces the mounted legacy explorer. Two things about it are
deliberate:

**It is a mount, not a route.** The deny-by-default lint walks routes carrying a
FastAPI dependency graph and requires each to be gated; a static-file mount has
no dependency graph and is skipped. That is correct rather than convenient — the
login shell must be reachable before there is anyone to authorize, and these
files are the application, not the corpus. Nothing here reads the database.
``tests/component/test_route_gating.py`` pins the distinction: every API route
gated, exactly one mount, and it points at the bundle directory.

**Unknown paths fall back to ``index.html``, except under a reserved prefix.**
The workspace routes client-side, so ``/graph`` is a real destination that no
file corresponds to. Falling back keeps deep links and the OIDC redirect target
working without a catch-all route that the lint would then have to make an
exception for.

But the mount sits at ``/`` and sees everything the API did not match, so an
unguarded fallback turns every missing API path into an HTML page with status
200 — a caller of a retired route (``/api/graph``, ADR-026) would get a
cheerful success instead of "this is gone", and a typo in a client would look
like a rendering bug rather than a 404. API prefixes therefore never fall back,
including ``/api``, which is reserved precisely because it *used* to exist.
"""

from __future__ import annotations

from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

#: Vite's build output. Absent in a source checkout that has not run the UI
#: build; the app then simply serves no workspace, which is what CI's
#: Python-only jobs want.
WORKSPACE_DIR = Path(__file__).resolve().parents[2] / "ui" / "dist"

#: Path prefixes the workspace must never answer for. ``api`` is retired rather
#: than unused (ADR-026) and stays listed so it keeps returning 404 forever.
RESERVED_PREFIXES = ("v1", "api", "docs", "redoc", "openapi.json")


class SinglePageApp(StaticFiles):
    """Static files with an SPA fallback for unmatched application paths."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            # A missing *asset* is a build error and should stay a 404; only
            # extensionless, non-API paths are plausible client-side routes.
            if "." in Path(path).name:
                raise
            # ``StaticFiles`` hands us an OS-joined relative path, so the
            # separator is a backslash on Windows; splitting on "/" would let
            # every reserved prefix through on one platform only.
            parts = Path(path).parts
            if parts and parts[0] in RESERVED_PREFIXES:
                raise
            return await super().get_response("index.html", scope)


def workspace_files(directory: Path = WORKSPACE_DIR) -> SinglePageApp:
    return SinglePageApp(directory=directory, html=True)


__all__ = ["WORKSPACE_DIR", "SinglePageApp", "workspace_files"]
