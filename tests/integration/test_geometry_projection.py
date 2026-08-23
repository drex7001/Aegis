"""The geometry projection is a cache, and geometry is a claim (T56, B-13).

The headline case is `test_truncate_and_rebuild_reproduces_the_table`: the
charter's fifth exit criterion says no canonical mutable geometry column exists,
and the only way to mean that is to drop the table and get it back.

The rest are the two properties that make map privacy work at all — one row per
*claim* rather than per place, so `claim_filters` composes unchanged — and the
one that keeps the projection honest: an invalid geometry is recorded with its
reason and never repaired.
"""

from __future__ import annotations

import json

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, ActionValidationError, new_id
from aegis.ontology import load
from aegis.projections import rebuild_location_geometry_projection
from aegis.projections.geometry import BUILDER_VERSION
from aegis.store import Claim, Entity, LocationGeometryProjection, Source, SourceRecord
from tests.support.database import migrated_test_engine, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement(
    "Article-I", "Article-XIII", "B-13", "H-21", "ADR-046", "ADR-048", "T56"
)

ANALYST = frozenset({"analyst"})

DISTRICT = {
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [[79.8, 6.9], [79.95, 6.9], [79.95, 7.05], [79.8, 7.05], [79.8, 6.9]]
        ],
    },
    "admin_level": "subdivision",
    "derivation": "admin_unit_boundary",
    "accuracy_m": None,
}

BUILDING = {
    "geometry": {"type": "Point", "coordinates": [79.8612, 6.9271]},
    "admin_level": "not_administrative",
    "derivation": "address_match",
    "accuracy_m": 12,
}

# A bow-tie: the ring crosses itself, so it is syntactically fine and
# topologically invalid. RFC 7946 does not forbid it; PostGIS does not accept it
# as a polygon anyone should trust.
BOWTIE = {
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [[79.8, 6.9], [79.9, 7.0], [79.9, 6.9], [79.8, 7.0], [79.8, 6.9]]
        ],
    },
    "admin_level": "subdivision",
    "derivation": "admin_unit_boundary",
    "accuracy_m": None,
}


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def geometry_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


@pytest.fixture()
def world(geometry_engine: sa.Engine):
    truncate_domain_data(geometry_engine)
    session = Session(geometry_engine)
    ids = {"source": new_id("src"), "record": new_id("rec")}
    with session.begin():
        session.add(
            Source(
                source_id=ids["source"],
                source_type="open_source",
                name="T56 source",
                reliability_normalized="generally_reliable",
            )
        )
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="a" * 64,
                storage_uri="test://t56/one",
            )
        )
        session.flush()
        for slot, label in (("place", "Negombo"), ("other", "Colombo")):
            entity_id = new_id("ent")
            ids[slot] = entity_id
            session.add(
                Entity(entity_id=entity_id, entity_type="location", label=label)
            )
    service = ActionService(session)
    try:
        yield {
            **ids,
            "session": session,
            "service": service,
            "context": ActionContext(
                actor="user:analyst", purpose="T56 test", roles=ANALYST
            ),
        }
    finally:
        session.close()


def _geometry_claim(world, value: dict, *, place: str = "place", **kwargs) -> str:
    claim = world["service"].record_claim(
        world["context"],
        subject_id=world[place],
        predicate="has_geometry",
        object_value=value,
        record_id=world["record"],
        collection_method="curated",
        **kwargs,
    )
    return claim.claim_id


def _rows(session: Session) -> list[LocationGeometryProjection]:
    return list(
        session.scalars(
            select(LocationGeometryProjection).order_by(
                LocationGeometryProjection.claim_id
            )
        )
    )


def _snapshot(session: Session) -> list[tuple]:
    """Every column, geometry included, in a comparable form."""
    return [
        tuple(row)
        for row in session.execute(
            sa.text(
                "SELECT claim_id, place_id, ST_AsGeoJSON(geom), geometry_kind, "
                "       admin_level, accuracy_m, derivation, is_valid, invalid_reason, "
                "       handling_code, handling_rank, case_id, recorded_at, "
                "       retracted_at, ontology_version, builder_version "
                "FROM location_geometry_projection ORDER BY claim_id"
            )
        )
    ]


# ── the criterion ───────────────────────────────────────────────────────────


def test_truncate_and_rebuild_reproduces_the_table(world, ontology) -> None:
    """Charter exit №5, as literally as it can be written.

    "No canonical mutable geometry column exists" is not a claim about naming.
    It is this: drop every geometry row the system has and get all of it back
    from claims alone.
    """
    _geometry_claim(world, DISTRICT)
    _geometry_claim(world, BUILDING, place="other")
    session: Session = world["session"]
    session.commit()

    rebuild_location_geometry_projection(session, ontology=ontology)
    session.commit()
    before = _snapshot(session)
    assert len(before) == 2

    session.execute(sa.text("TRUNCATE location_geometry_projection"))
    session.commit()
    assert _snapshot(session) == []

    report = rebuild_location_geometry_projection(session, ontology=ontology)
    session.commit()
    assert _snapshot(session) == before
    assert report.rows == 2
    assert report.builder_version == BUILDER_VERSION
    assert report.ontology_version == ontology.version


def test_rebuilding_twice_changes_nothing(world, ontology) -> None:
    """Idempotent by construction: a full rebuild, never an incremental patch."""
    _geometry_claim(world, DISTRICT)
    session: Session = world["session"]
    session.commit()

    rebuild_location_geometry_projection(session, ontology=ontology)
    session.commit()
    once = _snapshot(session)
    rebuild_location_geometry_projection(session, ontology=ontology)
    session.commit()
    assert _snapshot(session) == once


# ── one row per claim, which is what map privacy rests on ───────────────────


def test_two_geometries_for_one_place_are_two_rows(world, ontology) -> None:
    """The design decision, asserted (spec 10 §6.1, §7.2).

    A location may carry a `sensitive` building polygon and an `open` district
    polygon; a viewer sees whichever they may read, because both are rows and
    the ordinary claim filter removes one of them. A table keyed by place would
    have had to pick a winner, and picking a winner is where map privacy dies.
    """
    _geometry_claim(world, DISTRICT, handling_code="open")
    _geometry_claim(world, BUILDING, handling_code="sensitive")
    session: Session = world["session"]
    session.commit()

    rebuild_location_geometry_projection(session, ontology=ontology)
    session.commit()

    rows = _rows(session)
    assert len(rows) == 2
    assert {row.place_id for row in rows} == {world["place"]}
    by_handling = {row.handling_code: row for row in rows}
    assert by_handling["open"].admin_level == "subdivision"
    assert by_handling["open"].handling_rank == 0
    assert by_handling["sensitive"].admin_level == "not_administrative"
    assert by_handling["sensitive"].handling_rank == 2


def test_every_governance_column_the_claim_carries_is_copied(world, ontology) -> None:
    """So a filter never has to join back to `claim` to decide what is visible."""
    claim_id = _geometry_claim(world, DISTRICT, handling_code="restricted")
    session: Session = world["session"]
    session.commit()
    rebuild_location_geometry_projection(session, ontology=ontology)
    session.commit()

    claim = session.get(Claim, claim_id)
    row = _rows(session)[0]
    assert row.claim_id == claim.claim_id
    assert row.handling_code == claim.handling_code == "restricted"
    assert row.case_id == claim.case_id
    assert row.recorded_at == claim.recorded_at
    assert row.retracted_at is None
    assert row.ontology_version == ontology.version


def test_a_retracted_claim_keeps_its_row_and_its_retraction(world, ontology) -> None:
    """Retracted is not deleted: an auditor still reads it, so the filter needs
    the column rather than the absence."""
    claim_id = _geometry_claim(world, DISTRICT)
    session: Session = world["session"]
    session.commit()
    world["service"].retract_claim(
        world["context"], claim_id=claim_id, reason="wrong district"
    )
    session.commit()

    rebuild_location_geometry_projection(session, ontology=ontology)
    session.commit()
    row = _rows(session)[0]
    assert row.claim_id == claim_id
    assert row.retracted_at is not None


# ── geometry is derived, and never repaired ─────────────────────────────────


def test_the_geometry_kind_is_derived_not_asserted(world, ontology) -> None:
    _geometry_claim(world, DISTRICT)
    _geometry_claim(world, BUILDING, place="other")
    session: Session = world["session"]
    session.commit()
    rebuild_location_geometry_projection(session, ontology=ontology)
    session.commit()

    kinds = {row.place_id: row.geometry_kind for row in _rows(session)}
    assert kinds[world["place"]] == "Polygon"
    assert kinds[world["other"]] == "Point"


def test_an_invalid_geometry_is_recorded_with_its_reason_never_repaired(
    world, ontology
) -> None:
    """`ST_MakeValid` would change what a source said.

    The bow-tie passes every RFC 7946 rule — closed ring, four positions, valid
    coordinates — and is topologically nonsense. It is stored with `is_valid`
    false, a NULL geometry and PostGIS's own reason, so a reader learns *why*
    rather than seeing it silently absent.
    """
    _geometry_claim(world, BOWTIE)
    session: Session = world["session"]
    session.commit()

    report = rebuild_location_geometry_projection(session, ontology=ontology)
    session.commit()

    row = _rows(session)[0]
    assert row.is_valid is False
    assert row.geom is None
    assert row.invalid_reason
    assert report.invalid == 1
    assert report.rows == 1


def test_a_geometry_the_validator_cannot_read_is_counted_not_fatal(
    world, ontology
) -> None:
    """A projection is a cache: one unreadable row must not make the rest
    unavailable — and the count is how anyone would ever notice."""
    claim_id = _geometry_claim(world, DISTRICT)
    session: Session = world["session"]
    session.commit()
    # Written straight to the column, because the action layer would refuse it —
    # which is the point: this is the row an *older* ontology could have left.
    session.execute(
        sa.text("UPDATE claim SET object_value = :v WHERE claim_id = :id"),
        {"v": json.dumps({"precision": "city"}), "id": claim_id},
    )
    session.commit()

    report = rebuild_location_geometry_projection(session, ontology=ontology)
    session.commit()
    assert report.rejected == 1
    assert report.rows == 0
    assert _rows(session) == []


# ── the write refuses what the map could not draw honestly ──────────────────


def test_the_action_layer_refuses_a_point_claiming_a_country(world) -> None:
    """The write-side half of "no bare pin exists" (spec 10 §4.3 rule 6)."""
    with pytest.raises(ActionValidationError) as exc:
        _geometry_claim(
            world,
            {
                "geometry": {"type": "Point", "coordinates": [80.7, 7.87]},
                "admin_level": "country",
                "derivation": "source_stated_coordinates",
                "accuracy_m": None,
            },
        )
    assert "claim.object_value.derivation" in str(exc.value)


def test_a_non_geo_literal_claim_is_untouched_by_the_geo_validator(world) -> None:
    """Only `geo` is checked. Text is what the source said."""
    session: Session = world["session"]
    entity_id = new_id("ent")
    with session.begin_nested():
        session.add(Entity(entity_id=entity_id, entity_type="person", label="Someone"))
    claim = world["service"].record_claim(
        world["context"],
        subject_id=entity_id,
        predicate="known_as",
        object_value="Nandana",
        record_id=world["record"],
        collection_method="curated",
    )
    assert claim.object_value == "Nandana"
