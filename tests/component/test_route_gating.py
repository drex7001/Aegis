"""No route is anonymous, and nothing is mounted but the workspace (T22).

Replaces ``test_legacy_containment.py``, which proved the *interim* controls
around the anonymous ``/api/*`` surface — loopback binding, response caps, per-IP
rate limits.  That surface is gone (ADR-026), so the thing worth testing changed
from "is the exposure contained" to "can an exposure be reintroduced".

Three ways it could be, and one test each: a route with no gate (the lint, now
with no exemption branch to slip through), a re-added ``public_route`` marker
(the symbol must not come back), and a mount serving something other than the
workspace bundle — the one place the lint structurally cannot look.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Mount
from typer.testing import CliRunner

import aegis.api.deps as deps
from aegis.api import create_app
from aegis.api.deps import find_ungated_routes
from aegis.api.workspace import WORKSPACE_DIR
from aegis.cli import app as cli_app

pytestmark = pytest.mark.requirement("Article-VI", "ADR-026", "T22")


@pytest.fixture(scope="module")
def app():
    return create_app()


def test_no_ungated_routes(app) -> None:
    assert find_ungated_routes(app) == []


def test_public_route_marker_no_longer_exists() -> None:
    """The escape hatch is deleted, not merely unused.

    While the symbol exists someone can reach for it, and the next anonymous
    route ships without a single test turning red.
    """
    assert not hasattr(deps, "public_route")
    assert not hasattr(deps, "PUBLIC_MARKER")


def test_only_the_workspace_bundle_is_mounted(app) -> None:
    """Mounts bypass the dependency lint, so what may be mounted is pinned here.

    The empty list is a legitimate outcome: ``ui/dist`` is a build artefact, and
    a checkout that has not run the UI build serves the API with no workspace at
    all. Starlette normalizes a mount at ``/`` to the empty path.
    """
    mounts = [route for route in app.routes if isinstance(route, Mount)]
    assert [m.name for m in mounts] in ([], ["workspace"])
    for mount in mounts:
        assert mount.path == ""
        assert Path(mount.app.directory) == WORKSPACE_DIR


def test_legacy_explorer_serving_path_is_gone(app) -> None:
    """``legacy/app`` no longer exists and nothing serves from it."""
    repo_root = WORKSPACE_DIR.parents[1]
    assert not (repo_root / "legacy" / "app").exists()
    assert all(
        "legacy" not in str(getattr(getattr(route, "app", None), "directory", ""))
        for route in app.routes
    )


# ── serving posture: loopback default survives, for pilot-gate reasons ───────


def test_serve_refuses_non_loopback_without_explicit_override() -> None:
    result = CliRunner().invoke(cli_app, ["serve", "--host", "0.0.0.0"])

    assert result.exit_code == 2
    assert "non-loopback binds are refused by default" in result.output


def test_serve_defaults_to_ipv4_loopback(monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: calls.append(kwargs))

    result = CliRunner().invoke(cli_app, ["serve"])

    assert result.exit_code == 0, result.output
    assert calls[0]["host"] == "127.0.0.1"


def test_serve_allows_loopback(monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: calls.append(kwargs))

    result = CliRunner().invoke(cli_app, ["serve", "--host", "::1"])

    assert result.exit_code == 0, result.output
    assert calls == [{"factory": True, "host": "::1", "port": 8000, "reload": False}]


def test_serve_non_loopback_override_warns_about_the_pilot_gate(monkeypatch) -> None:
    """The warning must now cite the reason that still applies.

    It used to say the ``/api/*`` routes were anonymous.  Leaving that text in
    place would be a warning about a risk that no longer exists, printed instead
    of the ones that do.
    """
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: None)

    result = CliRunner().invoke(
        cli_app, ["serve", "--host", "0.0.0.0", "--allow-non-loopback"]
    )

    assert result.exit_code == 0, result.output
    assert "pilot" in result.output.lower()
    assert "/api/*" not in result.output


# ── the graph routes that replaced the anonymous surface ────────────────────


@pytest.mark.parametrize("path", ["/v1/graph/expand", "/v1/graph/paths"])
def test_graph_routes_require_a_token(app, path: str) -> None:
    response = TestClient(app).post(path, json={"from_id": "a", "to_id": "b"})

    assert response.status_code == 401
