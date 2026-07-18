"""Evidence metadata contracts (speckit T5, Constitution Article IV)."""

import pytest
import sqlalchemy as sa

from aegis.store import Base
from tests.support.schema import T4_TABLES


EVIDENCE_TABLES = {"evidence_item", "derivative", "custody_event"}
pytestmark = pytest.mark.requirement("Article-IV", "T5")


def test_evidence_metadata_matches_spec() -> None:
    assert T4_TABLES | EVIDENCE_TABLES <= set(Base.metadata.tables)
    derivative_checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in Base.metadata.tables["derivative"].constraints
        if isinstance(constraint, sa.CheckConstraint)
    }
    assert derivative_checks == {
        "ck_derivative_has_parent": "parent_evidence IS NOT NULL OR parent_record IS NOT NULL"
    }
    assert type(Base.metadata.tables["evidence_item"].c.handling_code.type) is sa.Text
