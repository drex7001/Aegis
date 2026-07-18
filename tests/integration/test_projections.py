"""Projection rebuild acceptance tests (speckit T10)."""

from __future__ import annotations

from collections import Counter
import json
import os

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from aegis.evidence import LocalFilesystemVault
from aegis.migration import migrate, remap_edge
from aegis.ontology import load
from aegis.er.canonical import rebuild_canonical_map
from aegis.projections import (
    CONFIDENCE_TAGS,
    WEIGHTS,
    build_full_graph,
    rebuild_edge_projection,
)
from tests.support.paths import ONTOLOGY_PATH, REPO_ROOT, SNAPSHOT_ROOT
from tests.support.database import (
    RESTORE_BASELINE_REVISION,
    TRUNCATE_DOMAIN_TABLES,
    migrated_test_engine,
)

BASELINE = SNAPSHOT_ROOT / "real_graph.baseline.json"
pytestmark = pytest.mark.requirement("Article-XIII", "T10")


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def projection_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        with engine.begin() as connection:
            connection.execute(sa.text(TRUNCATE_DOMAIN_TABLES))
            connection.execute(sa.text(RESTORE_BASELINE_REVISION))
        yield engine


@pytest.fixture(scope="module")
def rebuilt(projection_engine: sa.Engine, ontology, tmp_path_factory) -> dict:
    vault = LocalFilesystemVault(tmp_path_factory.mktemp("vault"))
    with Session(projection_engine) as session:
        migrate(session, vault=vault)
    with Session(projection_engine) as session:
        rebuild_canonical_map(session)
        rebuild_edge_projection(session, ontology=ontology)
        session.commit()
        return build_full_graph(session, ontology)


def _expected_edges(baseline: dict, ontology) -> Counter:
    expected: Counter = Counter()
    for edge in baseline["edges"]:
        for draft in remap_edge(edge, ontology):
            endpoints = (
                tuple(sorted((edge["source"], edge["target"])))
                if draft["symmetric"]
                else (edge["source"], edge["target"])
            )
            expected[
                (
                    endpoints,
                    draft["predicate"],
                    (draft["category"] or "uncategorized").upper(),
                    WEIGHTS[draft["credibility_normalized"]],
                    draft["valid_from"],
                    draft["valid_to"],
                    draft["location_text"],
                    CONFIDENCE_TAGS[draft["credibility_normalized"]],
                    "CURATED",
                    edge["source_file"],
                    edge["source_excerpt"],
                )
            ] += 1
    return expected


def _built_edges(graph: dict, ontology) -> Counter:
    built: Counter = Counter()
    for edge in graph["edges"]:
        symmetric = ontology.predicates[edge["relation"]].symmetric
        endpoints = (
            tuple(sorted((edge["source"], edge["target"])))
            if symmetric
            else (edge["source"], edge["target"])
        )
        built[
            (
                endpoints,
                edge["relation"],
                edge["layer"],
                edge["weight"],
                edge["start_date"],
                edge["end_date"],
                edge["location"],
                edge["confidence"],
                edge["extraction_method"],
                edge["source_file"],
                edge["source_excerpt"],
            )
        ] += 1
    return built


@pytest.mark.integration
def test_snapshot_nodes_match_baseline(rebuilt: dict, baseline: dict) -> None:
    assert len(rebuilt["nodes"]) == len(baseline["nodes"]) == 41
    rebuilt_by_id = {n["node_id"]: n for n in rebuilt["nodes"]}
    for expected in baseline["nodes"]:
        node = rebuilt_by_id[expected["node_id"]]
        assert node["name"] == expected["name"]
        assert node["aliases"] == expected["aliases"]
        assert node["affiliations"] == expected["affiliations"]
        assert node["node_type"] == expected["node_type"]
        assert node["nic"] is None
        assert node["source_file"] == expected["source_file"]
        assert node["source_excerpt"] == expected["source_excerpt"]
        assert isinstance(node["cluster_id"], int)


@pytest.mark.integration
def test_snapshot_edges_match_remapped_baseline(rebuilt: dict, baseline: dict, ontology) -> None:
    expected = _expected_edges(baseline, ontology)
    built = _built_edges(rebuilt, ontology)
    missing = expected - built
    surplus = built - expected
    assert not missing, f"projection lost edges: {sorted(missing)[:5]}"
    assert not surplus, f"projection invented edges: {sorted(surplus)[:5]}"
    assert sum(built.values()) == 63  # 57 legacy edges + 6 split halves


@pytest.mark.integration
def test_snapshot_cells_and_meta_shape(rebuilt: dict, baseline: dict) -> None:
    assert set(rebuilt["meta"].keys()) == set(baseline["meta"].keys())
    # source order is not semantically meaningful — compare by key
    by_key = lambda rows: sorted(rows, key=lambda s: s["key"])
    assert by_key(rebuilt["meta"]["sources"]) == by_key(baseline["meta"]["sources"])
    assert set(rebuilt["meta"]["layers"]) >= set(baseline["meta"]["layers"])
    cell_keys = set(baseline["cells"][0].keys())
    members = 0
    names = {n["name"] for n in rebuilt["nodes"]}
    for cell in rebuilt["cells"]:
        assert set(cell.keys()) == cell_keys
        assert set(cell["members"]) <= names
        members += cell["size"]
    assert members == 41


@pytest.mark.integration
def test_handling_rank_sql_is_the_single_definition(projection_engine: sa.Engine) -> None:
    """`projection_weight()` was dropped with the Phase-1 view (T21, ADR-030).

    Only the display weight in the emitter survives, and it has no SQL twin to
    disagree with.  `handling_code_rank` stays because the v2 builder and the
    row filters both key off it, and an unknown code must still fail closed.
    """
    with projection_engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT handling_code_rank('open'), handling_code_rank('restricted'), "
                    "handling_code_rank('sensitive'), handling_code_rank('mystery')")
        ).one() == (0, 1, 2, 999)
        assert not connection.execute(
            sa.text("SELECT 1 FROM pg_proc WHERE proname = 'projection_weight'")
        ).all(), "the aggregate weight function must not survive T21"


@pytest.mark.integration
def test_cypher_export_path_preserved(rebuilt: dict) -> None:
    from aegis.projections.cypher import generate_cypher  # vendored by T21 (H-36)

    cypher = generate_cypher(rebuilt)
    assert "MERGE (c:Criminal" in cypher
    assert ":KINSHIP" in cypher  # the corrected sibling/spouse layer exports cleanly
