"""No unauthenticated read surface exists anywhere in the repo (T52).

The charter's fifth exit criterion, re-verified through the **grown** P4
surface. `test_route_gating.py` established the property at T22, when the
legacy explorer and its anonymous `/api/*` were deleted (ADR-026); this file
re-runs it against everything Phase 4 added and checks the two ways it could
have come back.

It could come back **on the server**: a new route added without a gate, a new
mount, or a resurrected `public_route` exemption. Every one of those is checked
here against the live application rather than against a list somebody maintains.

It could also come back **in the client**: a screen route added outside
`AuthGuard`. The guard wraps the whole route table rather than sitting on
individual routes precisely because per-route guards are how one eventually gets
forgotten — so what this asserts is that the table is still wrapped, and that
every declared path is inside it.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from aegis.api import create_app
from aegis.api.deps import GATE_MARKER, _dependency_calls, find_ungated_routes
from tests.support.paths import REPO_ROOT

pytestmark = pytest.mark.requirement("Article-VI", "ADR-026", "T52")

UI_SRC = REPO_ROOT / "ui" / "src"


@pytest.fixture(scope="module")
def app():
    return create_app()


@pytest.fixture(scope="module")
def client(app) -> TestClient:
    return TestClient(app)


def _api_routes(app):
    routes = []
    for entry in app.routes:
        original = getattr(entry, "original_router", None)
        routes.extend(original.routes if original is not None else [entry])
    return routes


# ── the server ──────────────────────────────────────────────────────────────


def test_every_route_the_phase_added_is_still_gated(app) -> None:
    """Checked against the live dependency graph, not a maintained list."""
    assert find_ungated_routes(app) == []


def test_every_v1_operation_carries_exactly_one_gate(app) -> None:
    """Two gates would be a merge accident; zero would be the finding.

    Exactly one is also what makes `test_authorization_matrix.py` able to read a
    route's policy — a second gate would make "the policy" ambiguous.
    """
    without: list[str] = []
    for route in _api_routes(app):
        operation_id = getattr(route, "operation_id", None)
        dependant = getattr(route, "dependant", None)
        if operation_id is None or dependant is None:
            continue
        gates = [
            call
            for call in _dependency_calls(dependant)
            if getattr(call, GATE_MARKER, False)
        ]
        if len(gates) != 1:
            without.append(f"{operation_id}: {len(gates)} gates")
    assert without == []


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/v1/cases"),
        ("GET", "/v1/hypotheses?case=x"),
        ("POST", "/v1/hypotheses"),
        ("GET", "/v1/tasks?case=x"),
        ("POST", "/v1/tasks"),
        ("GET", "/v1/entities/ent_x/cases"),
        ("POST", "/v1/graph/expand"),
    ],
)
def test_a_phase_4_route_refuses_an_anonymous_caller(
    client: TestClient, method: str, path: str
) -> None:
    """Spot-checked end to end, because a gate that exists but does not fire is
    the failure a dependency-graph walk cannot see."""
    response = client.request(method, path, json={} if method == "POST" else None)
    assert response.status_code == 401, (method, path, response.status_code)
    assert response.headers.get("www-authenticate") == "Bearer"


def test_no_exemption_marker_exists_anywhere_in_the_repo() -> None:
    """`public_route` was the escape hatch ADR-026 deleted.

    Swept over the whole repository rather than over `aegis/`: an exemption
    reintroduced in a script, a fixture or a test helper would be just as real.
    The speckit prose that *records* the deletion is excluded by matching the
    symbol form.
    """
    pattern = re.compile(r"public_route\s*[=(:]")
    skip = {".git", "node_modules", "dist", ".venv", "__pycache__", ".aegis"}
    offenders: list[str] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".ts", ".tsx", ".yaml", ".yml"}:
            continue
        if any(part in skip for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        if pattern.search(text):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == [], offenders


def test_nothing_new_is_mounted(app) -> None:
    """Mounts bypass the dependency lint, so the set of them is pinned.

    Phase 4 added screens, not mounts — a second mount would be a second way to
    serve bytes without a gate, and it would not show up in any route walk.

    **Zero is a legitimate outcome.** `ui/dist` is a build artefact, so a
    Python-only checkout serves the API with no workspace at all; asserting
    exactly one passes on a developer machine and fails in CI, which is how the
    first version of this test found out.
    """
    mounts = [route for route in app.routes if route.__class__.__name__ == "Mount"]
    assert [mount.name for mount in mounts] in ([], ["workspace"])
    for mount in mounts:
        assert mount.path == ""


def test_the_reserved_api_prefix_still_404s(client: TestClient) -> None:
    """`/api` is retired, not unused (ADR-026).

    Two assertions, because the live 404 proves less than it looks like in a
    checkout with no `ui/dist`: with no mount, *everything* 404s. The reservation
    itself is what has to hold — it is the reason the workspace's SPA fallback
    does not turn a call to a deleted anonymous route into a cheerful 200.
    """
    from aegis.api.workspace import RESERVED_PREFIXES

    assert "api" in RESERVED_PREFIXES
    for path in ("/api/graph", "/api/stats", "/api/query/anything"):
        assert client.get(path).status_code == 404, path


# ── the client ──────────────────────────────────────────────────────────────


def test_every_screen_route_sits_inside_the_auth_guard() -> None:
    """One guard around the whole table, and every declared path inside it.

    Per-route guards are how one eventually gets forgotten, which is why `App`
    wraps `<Routes>` rather than each `<Route>`. This asserts the arrangement
    still holds and that no path was declared outside it.
    """
    app_source = (UI_SRC / "App.tsx").read_text(encoding="utf-8")
    guard_open = app_source.index("<AuthGuard>")
    guard_close = app_source.index("</AuthGuard>")
    inside = app_source[guard_open:guard_close]

    declared = set(re.findall(r"path=\{ROUTES\.(\w+)\}", app_source))
    within = set(re.findall(r"path=\{ROUTES\.(\w+)\}", inside))
    assert declared == within, sorted(declared - within)
    # ...and the wildcard, which is the one a redirect could hide outside.
    assert 'path="*"' in inside


def test_every_declared_route_is_rendered() -> None:
    """A route table entry with no `<Route>` is a path that falls to the
    wildcard — which redirects, so it would look like it worked."""
    routes = (UI_SRC / "routing.ts").read_text(encoding="utf-8")
    app_source = (UI_SRC / "App.tsx").read_text(encoding="utf-8")
    declared = set(re.findall(r"^\s{2}(\w+):\s", routes, flags=re.MULTILINE))
    rendered = set(re.findall(r"path=\{ROUTES\.(\w+)\}", app_source))
    assert declared == rendered, sorted(declared ^ rendered)


def test_the_workspace_reaches_no_origin_but_its_own_and_keycloak() -> None:
    """An absolute URL in the client would be a request the CSP's `connect-src`
    never sanctioned — and the first step towards a second, ungoverned API."""
    offenders: list[str] = []
    # A real host, not a placeholder: `placeholder="https://…"` is prose in an
    # input, and reporting it as a violation would teach the next reader to
    # ignore this test.
    absolute = re.compile(r"""["'](https?://[a-zA-Z0-9][a-zA-Z0-9.\-]*(?::\d+)?[^"']*)["']""")
    allowed = re.compile(r"https?://(localhost:8180|127\.0\.0\.1|example\.test)")
    for path in sorted(UI_SRC.rglob("*.ts*")):
        if path.name == "schema.d.ts":
            continue
        for match in absolute.finditer(path.read_text("utf-8")):
            if not allowed.match(match.group(1)):
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {match.group(1)}")
    assert offenders == [], offenders
