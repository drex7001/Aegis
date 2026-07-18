"""Projection builder tests (speckit T10).

The acceptance criterion: migrated data → rebuild → semantically equal to the
committed baseline JSON (same nodes/edges/weights/dates).  "Semantically"
means modulo the *declared* legacy transformations, so the baseline edges are
pushed through the same remap table the migration used
(:func:`aegis.migration.remap_edge`) before comparison — splits, credibility
caps and category corrections are part of the contract, not drift.
"""

from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from aegis.evidence import LocalFilesystemVault
from aegis.migration import migrate, remap_edge
from aegis.ontology import load
from aegis.projections import (
    CONFIDENCE_TAGS,
    WEIGHTS,
    build_full_graph,
    refresh_edge_projection,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / "tests" / "snapshots" / "real_graph.baseline.json"


@pytest.fixture(scope="module")
def ontology():
    return load(REPO_ROOT / "ontology" / "aegis.yaml")


@pytest.fixture(scope="module")
def baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


# ── unit: the weight function is committed code with tests (spec 02 §6) ─────


def test_projection_weights_match_spec() -> None:
    assert WEIGHTS == {
        "confirmed": 1.0,
        "probably_true": 0.7,
        "possibly_true": 0.55,
        "doubtful": 0.4,
        "improbable": 0.2,
        "cannot_judge": 0.4,
    }


def test_reverse_maps_cover_every_credibility_value(ontology) -> None:
    for value in ontology.grading.values_for("credibility"):
        assert value in WEIGHTS
        assert CONFIDENCE_TAGS[value] in {"EXTRACTED", "INFERRED", "AMBIGUOUS"}


# ── integration: migrate → rebuild → compare against the baseline ───────────


@pytest.fixture(scope="module")
def projection_engine() -> sa.Engine:
    database_url = os.getenv("AEGIS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("set AEGIS_TEST_DATABASE_URL to run PostgreSQL projection tests")
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    previous = os.environ.get("AEGIS_DATABASE_URL")
    os.environ["AEGIS_DATABASE_URL"] = database_url
    from aegis.config import get_settings

    get_settings.cache_clear()
    command.upgrade(config, "head")
    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE claim_relation, review_queue, claim, identity_membership, "
                "mention, evidence_item, custody_event, derivative, source_record, "
                "source, case_member, case_file, entity, authz_outbox CASCADE"
            )
        )
    yield engine
    engine.dispose()
    if previous is None:
        os.environ.pop("AEGIS_DATABASE_URL", None)
    else:
        os.environ["AEGIS_DATABASE_URL"] = previous
    get_settings.cache_clear()


@pytest.fixture(scope="module")
def rebuilt(projection_engine: sa.Engine, ontology, tmp_path_factory) -> dict:
    vault = LocalFilesystemVault(tmp_path_factory.mktemp("vault"))
    with Session(projection_engine) as session:
        migrate(session, vault=vault)
    with Session(projection_engine) as session:
        refresh_edge_projection(session)
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
def test_sql_weight_function_agrees_with_python(projection_engine: sa.Engine) -> None:
    with projection_engine.connect() as connection:
        for credibility, weight in WEIGHTS.items():
            got = connection.execute(
                sa.text("SELECT projection_weight(:c)"), {"c": credibility}
            ).scalar_one()
            assert got == pytest.approx(weight), credibility
        assert connection.execute(
            sa.text("SELECT handling_code_rank('open'), handling_code_rank('restricted'), "
                    "handling_code_rank('sensitive'), handling_code_rank('mystery')")
        ).one() == (0, 1, 2, 999)


@pytest.mark.integration
def test_cypher_export_path_preserved(rebuilt: dict) -> None:
    from legacy.pipeline.neo4j_export import generate_cypher

    cypher = generate_cypher(rebuilt)
    assert "MERGE (c:Criminal" in cypher
    assert ":KINSHIP" in cypher  # the corrected sibling/spouse layer exports cleanly