"""Interim containment for the anonymous legacy projection surface (T16a)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from aegis.api import create_app
from aegis.api.routes import graph
from aegis.cli import app as cli_app
from aegis.config import get_settings


pytestmark = pytest.mark.requirement("Article-VI", "ADR-026", "T16a")


def test_serve_refuses_non_loopback_without_explicit_override() -> None:
    result = CliRunner().invoke(cli_app, ["serve", "--host", "0.0.0.0"])

    assert result.exit_code == 2
    assert "non-loopback binds are refused by default" in result.output


def test_serve_allows_loopback(monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: calls.append(kwargs))

    result = CliRunner().invoke(cli_app, ["serve", "--host", "::1"])

    assert result.exit_code == 0, result.output
    assert calls == [
        {
            "factory": True,
            "host": "::1",
            "port": 8000,
            "reload": False,
        }
    ]


def test_serve_defaults_to_ipv4_loopback(monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: calls.append(kwargs))

    result = CliRunner().invoke(cli_app, ["serve"])

    assert result.exit_code == 0, result.output
    assert calls[0]["host"] == "127.0.0.1"


def test_serve_allows_explicit_non_loopback_override(monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: calls.append(kwargs))

    result = CliRunner().invoke(
        cli_app,
        ["serve", "--host", "0.0.0.0", "--allow-non-loopback"],
    )

    assert result.exit_code == 0, result.output
    assert calls[0]["host"] == "0.0.0.0"
    assert "WARNING: non-loopback bind explicitly enabled" in result.output


def test_legacy_graph_rejects_response_over_cap(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_LEGACY_API_MAX_RESPONSE_BYTES", "1024")
    monkeypatch.setattr(
        graph,
        "_load_graph",
        lambda: {"nodes": [{"name": "x" * 2048}], "edges": [], "cells": []},
    )
    get_settings.cache_clear()
    try:
        response = TestClient(create_app()).get("/api/graph")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 413
    assert "exceeds the configured 1024-byte cap" in response.json()["detail"]


def test_legacy_routes_are_rate_limited_per_client(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_LEGACY_API_RATE_LIMIT_PER_MINUTE", "2")
    monkeypatch.setattr(
        graph,
        "_load_graph",
        lambda: {"nodes": [], "edges": [], "cells": []},
    )
    get_settings.cache_clear()
    client = TestClient(create_app(), client=("t16a-rate-client", 50000))
    try:
        first = client.get("/api/stats")
        second = client.get("/api/stats")
        limited = client.get("/api/stats")
    finally:
        get_settings.cache_clear()

    assert first.status_code == 200
    assert second.status_code == 200
    assert limited.status_code == 429
