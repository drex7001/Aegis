"""Serving the workspace bundle: what falls back, and what must not (T22).

Exercised against a temporary bundle rather than the real ``ui/dist``, which is
a build artefact the Python jobs do not produce — so these cases run everywhere
and fail for the reason they name rather than for a missing directory.

The interesting case is not that ``/graph`` reaches the app. It is that
``/api/graph`` does *not*: a mount at ``/`` sees every path no API route
matched, so an unguarded SPA fallback would answer a retired endpoint
(ADR-026) with an HTML page and status 200 — turning "this is gone" into
"this worked", which is worse than either.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.applications import Starlette

from aegis.api.workspace import RESERVED_PREFIXES, workspace_files

pytestmark = pytest.mark.requirement("ADR-026", "ADR-032", "T22")


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    (tmp_path / "index.html").write_text("<title>Aegis workspace</title>", "utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("export const ok = true;", "utf-8")

    app = Starlette()
    app.mount("/", workspace_files(tmp_path), name="workspace")
    return TestClient(app)


def test_the_bundle_is_served(client: TestClient) -> None:
    assert client.get("/").status_code == 200
    assert client.get("/assets/app.js").status_code == 200


def test_a_client_side_route_falls_back_to_the_app(client: TestClient) -> None:
    """`/graph` is a real destination with no file behind it."""
    response = client.get("/graph")

    assert response.status_code == 200
    assert "Aegis workspace" in response.text


def test_the_oidc_redirect_target_falls_back(client: TestClient) -> None:
    """The callback URL must survive a full-page redirect from Keycloak."""
    assert client.get("/auth/callback?code=x&state=y").status_code == 200


@pytest.mark.parametrize("prefix", RESERVED_PREFIXES)
def test_api_prefixes_never_fall_back(client: TestClient, prefix: str) -> None:
    """A missing API path is 404, not a 200 page that merely looks fine."""
    assert client.get(f"/{prefix}/nonexistent").status_code == 404


def test_the_retired_projection_surface_stays_gone(client: TestClient) -> None:
    """The specific regression: ADR-026's routes must not resurrect as HTML."""
    for path in ("/api/graph", "/api/stats", "/api/cells", "/api/query/brokers"):
        assert client.get(path).status_code == 404, path


def test_a_missing_asset_is_a_404_not_the_app(client: TestClient) -> None:
    """A broken asset reference is a build error; serving HTML for it would
    surface as an unreadable syntax error in the console instead."""
    assert client.get("/assets/missing.js").status_code == 404
