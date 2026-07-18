"""Cross-suite pytest policy and layer classification."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic.config import Config


TESTS_ROOT = Path(__file__).resolve().parent
LAYER_MARKERS = {
    "unit",
    "component",
    "contract",
    "integration",
    "system",
    "e2e",
}


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Return the dedicated test database or fail with setup guidance."""
    database_url = os.getenv("AEGIS_TEST_DATABASE_URL")
    if not database_url:
        pytest.fail(
            "AEGIS_TEST_DATABASE_URL is required for integration/system tests; "
            "start PostgreSQL and point it at a disposable test database",
            pytrace=False,
        )
    return database_url


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    config = Config(str(TESTS_ROOT.parent / "alembic.ini"))
    config.set_main_option("script_location", str(TESTS_ROOT.parent / "migrations"))
    return config


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply exactly one test-layer marker based on directory placement."""
    for item in items:
        try:
            relative = Path(str(item.path)).resolve().relative_to(TESTS_ROOT)
        except ValueError:
            continue
        if not relative.parts or relative.parts[0] not in LAYER_MARKERS:
            raise pytest.UsageError(
                f"{relative} is outside a recognized tests/<layer>/ directory"
            )
        layer = relative.parts[0]
        conflicting = {
            marker.name
            for marker in item.iter_markers()
            if marker.name in LAYER_MARKERS and marker.name != layer
        }
        if conflicting:
            raise pytest.UsageError(
                f"{relative} is in layer {layer!r} but declares {sorted(conflicting)!r}"
            )
        item.add_marker(getattr(pytest.mark, layer))
