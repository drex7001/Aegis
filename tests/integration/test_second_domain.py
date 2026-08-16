"""A claim round-trip on a domain the core has never seen (T31, Article XIV).

`tests/contract/test_second_domain.py` proves the fixture module *composes*
with no core edit. This proves the rest of the stack actually works on it: the
actions layer validates a claim against border-cargo vocabulary, rejects one
that violates it, and the edge projection builds a graph — all with the same
code paths criminal-network uses, differing only in which YAML was loaded.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, ActionValidationError, new_id
from aegis.er.canonical import rebuild_canonical_map
from aegis.er.ledger import open_membership
from aegis.er.normalize import norm_key
from aegis.ontology import load
from aegis.projections import build_full_graph, rebuild_edge_projection
from aegis.store import Claim, Entity, Mention, Source, SourceRecord
from tests.support.database import (
    RESTORE_BASELINE_REVISION,
    TRUNCATE_DOMAIN_TABLES,
    migrated_test_engine,
)
from tests.support.paths import REPO_ROOT

pytestmark = pytest.mark.requirement("Article-XIV", "ADR-037", "B-07", "T31")

COMPOSITION = REPO_ROOT / "tests" / "fixtures" / "ontology" / "border-cargo-composition.yaml"


@pytest.fixture(scope="module")
def border_cargo():
    return load(COMPOSITION)


@pytest.fixture(scope="module")
def cargo_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        with engine.begin() as connection:
            connection.execute(sa.text(TRUNCATE_DOMAIN_TABLES))
            connection.execute(sa.text(RESTORE_BASELINE_REVISION))
        yield engine


@pytest.fixture()
def seeded(cargo_engine: sa.Engine) -> dict[str, str]:
    """A consignment, a port, and the record that says so — all fictional.

    Each entity arrives with the mention that names it and an open membership,
    because that is what an entity *is* in this system (spec 02 §3.2). An
    entity with no membership is orphaned by definition and the canonical map
    tombstones it, so seeding without one would be testing a state the platform
    treats as garbage.
    """
    ids = {
        "source": new_id("src"),
        "record": new_id("rec"),
        "consignment": new_id("ent"),
        "port": new_id("ent"),
        "consignment_mention": new_id("men"),
        "port_mention": new_id("men"),
    }
    with Session(cargo_engine) as session, session.begin():
        session.add(
            Source(
                source_id=ids["source"],
                source_type="open_source",
                name="T31 fictional customs bulletin",
            )
        )
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=f"t31/{ids['record']}",
                content_hash="0" * 64,
                storage_uri="file:///fictional/clearance-notice.txt",
                status="landed",
                handling_code="open",
            )
        )
        session.flush()
        for key, entity_id, mention_id, entity_type, label in (
            ("consignment", ids["consignment"], ids["consignment_mention"], "consignment", "CN-FIXTURE-001"),
            ("port", ids["port"], ids["port_mention"], "port_of_entry", "Port Fictitious"),
        ):
            # The mention key doubles as the graph node id, and every test in
            # this module seeds its own pair into the same database, so it is
            # made unique here — otherwise assertions could not tell one run's
            # consignment from another's.
            key_value = f"{norm_key(label)}-{mention_id[-6:].lower()}"
            ids[f"{key}_key"] = key_value
            session.add(Entity(entity_id=entity_id, entity_type=entity_type, label=label))
            session.add(
                Mention(
                    mention_id=mention_id,
                    record_id=ids["record"],
                    raw_text=label,
                    norm_key=key_value,
                    char_start=0,
                    char_end=len(label),
                )
            )
            session.flush()
            open_membership(session, mention_id=mention_id, entity_id=entity_id)
    return ids


def _service(engine: sa.Engine, ontology) -> tuple[Session, ActionService]:
    session = Session(engine)
    return session, ActionService(session, ontology)


def test_a_claim_in_the_second_domain_records_and_reads_back(
    cargo_engine: sa.Engine, border_cargo, seeded: dict[str, str]
) -> None:
    session, service = _service(cargo_engine, border_cargo)
    with session:
        claim = service.record_claim(
            ActionContext(actor="fixture-analyst"),
            subject_id=seeded["consignment"],
            predicate="cleared_at",
            object_id=seeded["port"],
            record_id=seeded["record"],
            assertion_type="reported",
            collection_method="curated",
        )
        session.commit()
        stored = session.get(Claim, claim.claim_id)
        assert stored is not None
        assert stored.predicate == "cleared_at"
        # The claim stamps the composition version, not a module version
        # (ADR-037) — the fixture composition's own 1.0.0.
        assert stored.ontology_version == border_cargo.version


def test_a_literal_predicate_round_trips(
    cargo_engine: sa.Engine, border_cargo, seeded: dict[str, str]
) -> None:
    session, service = _service(cargo_engine, border_cargo)
    with session:
        claim = service.record_claim(
            ActionContext(actor="fixture-analyst"),
            subject_id=seeded["consignment"],
            predicate="declared_as",
            object_value="machine parts",
            record_id=seeded["record"],
            assertion_type="reported",
            collection_method="curated",
        )
        session.commit()
        assert session.get(Claim, claim.claim_id).object_value == "machine parts"


def test_the_ontology_still_constrains_the_second_domain(
    cargo_engine: sa.Engine, border_cargo, seeded: dict[str, str]
) -> None:
    """Loading a fixture domain does not mean loosening validation."""
    session, service = _service(cargo_engine, border_cargo)
    with session:
        # A predicate this composition does not declare.
        with pytest.raises(ActionValidationError, match="predicates.member_of"):
            service.record_claim(
                ActionContext(actor="fixture-analyst"),
                subject_id=seeded["consignment"],
                predicate="member_of",
                object_id=seeded["port"],
                record_id=seeded["record"],
                assertion_type="reported",
                collection_method="curated",
            )
        # A subject type the predicate does not allow.
        with pytest.raises(ActionValidationError, match="predicates.cleared_at.subject"):
            service.record_claim(
                ActionContext(actor="fixture-analyst"),
                subject_id=seeded["port"],
                predicate="cleared_at",
                object_id=seeded["consignment"],
                record_id=seeded["record"],
                assertion_type="reported",
                collection_method="curated",
            )


def test_the_projection_builds_a_graph_from_the_second_domain(
    cargo_engine: sa.Engine, border_cargo, seeded: dict[str, str]
) -> None:
    session, service = _service(cargo_engine, border_cargo)
    with session:
        service.record_claim(
            ActionContext(actor="fixture-analyst"),
            subject_id=seeded["consignment"],
            predicate="cleared_at",
            object_id=seeded["port"],
            record_id=seeded["record"],
            assertion_type="reported",
            collection_method="curated",
        )
        session.commit()

    with Session(cargo_engine) as session:
        rebuild_canonical_map(session)
        report = rebuild_edge_projection(session, ontology=border_cargo)
        session.commit()
        graph = build_full_graph(session, border_cargo)

    assert report.ontology_version == border_cargo.version
    edges = [
        edge
        for edge in graph["edges"]
        if edge["source"] == seeded["consignment_key"]
        and edge["target"] == seeded["port_key"]
    ]
    assert len(edges) == 1
    assert edges[0]["relation"] == "cleared_at"
    # The layer came from the fixture module's own category, so the projection
    # grouped by a value it had never been told about (Article XIV).
    assert edges[0]["layer"] == "CUSTOMS"
    node_types = {node["node_type"] for node in graph["nodes"]}
    assert node_types == {"CONSIGNMENT", "PORT_OF_ENTRY"}
