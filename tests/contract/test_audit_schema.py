"""Audit ledger schema contract (speckit T6, Constitution Article X)."""

import pytest

from aegis.store import Base


pytestmark = pytest.mark.requirement("Article-X", "T6")


def test_audit_mapping_and_code_owned_constraint() -> None:
    table = Base.metadata.tables["audit_log"]
    assert {
        "id",
        "at",
        "actor",
        "session_id",
        "purpose",
        "case_id",
        "action",
        "resource_type",
        "resource_id",
        "decision",
        "detail",
        "prev_hash",
        "entry_hash",
    } == set(table.c.keys())
    assert {constraint.name for constraint in table.constraints} >= {
        "ck_audit_log_decision"
    }
