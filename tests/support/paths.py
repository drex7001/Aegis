"""Stable repository paths for tests at any directory depth."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY_PATH = REPO_ROOT / "ontology" / "aegis.yaml"
SNAPSHOT_ROOT = REPO_ROOT / "tests" / "snapshots"
