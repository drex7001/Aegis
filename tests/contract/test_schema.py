"""Core claim-store metadata contracts (speckit T4)."""

import pytest
import sqlalchemy as sa
from sqlalchemy import CheckConstraint

from aegis.store import Base
from tests.support.schema import (
    EXPECTED_CHECKS,
    LEDGER_CHECKS,
    LEDGER_TABLES,
    ONTOLOGY_COLUMNS,
    T4_TABLES,
)


pytestmark = pytest.mark.requirement("Article-XI", "Article-XIV", "T4")


def _metadata_checks(table_names: set[str]) -> dict[str, str]:
    return {
        constraint.name: str(constraint.sqltext).lower()
        for table_name, table in Base.metadata.tables.items()
        if table_name in table_names
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def test_core_metadata_declares_t4_tables() -> None:
    assert T4_TABLES <= set(Base.metadata.tables)


def test_checks_cover_only_code_owned_invariants() -> None:
    checks = _metadata_checks(T4_TABLES)
    assert set(checks) == EXPECTED_CHECKS
    for sqltext in checks.values():
        assert all(column not in sqltext for column in ONTOLOGY_COLUMNS)


@pytest.mark.requirement("Article-V", "ADR-028", "T17")
def test_ledger_metadata_declares_its_tables_and_invariants() -> None:
    assert LEDGER_TABLES <= set(Base.metadata.tables)
    assert set(_metadata_checks(LEDGER_TABLES)) == LEDGER_CHECKS


@pytest.mark.requirement("Article-V", "ADR-028", "T17")
def test_one_active_membership_is_a_partial_unique_index() -> None:
    """The invariant must live in the schema, not in a service method.

    A uniqueness rule enforced only by application code is one forgotten call
    site away from two active memberships, which is exactly the state that
    makes a merge irreversible (ADR-028 §2).
    """
    indexes = {
        index.name: index for index in Base.metadata.tables["identity_membership"].indexes
    }
    invariant = indexes["ux_membership_one_active"]
    assert invariant.unique
    assert [column.name for column in invariant.columns] == ["mention_id"]
    assert "closed_revision_id is null" in str(
        invariant.dialect_options["postgresql"]["where"]
    ).lower()


@pytest.mark.requirement("ADR-029", "T17")
def test_claim_carries_its_identity_context() -> None:
    """Anchors are nullable; the revision stamp never is (spec 02 §3.1)."""
    claim = Base.metadata.tables["claim"]
    assert claim.c["subject_mention_id"].nullable
    assert claim.c["object_mention_id"].nullable
    assert not claim.c["identity_revision_id"].nullable


@pytest.mark.requirement("B-08", "T17")
def test_governance_seams_are_present_and_inert() -> None:
    """P2 stores and displays them; P7 enforces them (spec 02 §1)."""
    seams = Base.metadata.tables["source_record"].c
    for name in (
        "collection_policy_ref",
        "retention_class",
        "authority_ref",
        "authority_valid_from",
        "authority_valid_to",
    ):
        assert seams[name].nullable, f"{name} must not be enforced in P2"


def test_ontology_vocabulary_columns_are_plain_text() -> None:
    locations = {
        "source.source_type",
        "source.reliability_normalized",
        "source_record.handling_code",
        "entity.entity_type",
        "case_file.handling_code",
        "case_member.role",
        "claim.predicate",
        "claim.credibility_normalized",
        "claim.verification_status",
        "claim.analytic_confidence",
        "claim.handling_code",
    }
    for location in locations:
        table_name, column_name = location.split(".")
        assert type(Base.metadata.tables[table_name].c[column_name].type) is sa.Text


def test_geometry_lives_only_in_the_projection() -> None:
    """B-13's spot check at the metadata level (spec 10 §6.2, T56).

    "No canonical mutable geometry column exists" is checked two ways: the
    integration suite truncates the projection and rebuilds it byte-identically,
    and this walks every mapped table to prove no *other* one has grown a
    geometry column since. The second matters because the first would keep
    passing if someone added `entity.geom` beside it.
    """
    from aegis.store.models import Geometry

    carriers = {
        table_name
        for table_name, table in Base.metadata.tables.items()
        for column in table.columns
        if isinstance(column.type, Geometry)
    }
    assert carriers == {"location_geometry_projection"}
    assert "geom" not in Base.metadata.tables["entity"].c
    assert "precision" not in Base.metadata.tables["entity"].c
