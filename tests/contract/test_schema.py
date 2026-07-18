"""Core claim-store metadata contracts (speckit T4)."""

import pytest
import sqlalchemy as sa
from sqlalchemy import CheckConstraint

from aegis.store import Base
from tests.support.schema import EXPECTED_CHECKS, ONTOLOGY_COLUMNS, T4_TABLES


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
