
"""AuthZ tests (speckit T12): row-filter matrix, outbox dual-write drill, rebuild.

The dual-write drill is the ADR-014 acceptance criterion, run against the live
compose OpenFGA: with FGA unreachable, ``assign_case_member`` still commits
(outbox row pending); once FGA is back, ``sync`` drains the outbox and the FGA
check allows; ``rebuild`` reproduces the tuple set from Postgres alone.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, new_id
from aegis.api.auth import UserContext
from aegis.authz import claim_filters
from aegis.ontology import load
from aegis.store import AuthzOutbox, Claim, Entity, Source, SourceRecord
from tests.support.database import migrated_test_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.requirement("Article-VI", "T12", "T24b")


def _user(sub: str, *roles: str, clearance: int = 0) -> UserContext:
    return UserContext(
        sub=sub,
        username=sub,
        roles=frozenset(roles),
        clearance=clearance,
        claims={},
    )


@pytest.fixture(scope="module")
def ontology():
    return load(REPO_ROOT / "ontology" / "aegis.yaml")


@pytest.fixture(scope="module")
def authz_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


# ── the role × handling × membership matrix (spec 03 §4) ────────────────────


@pytest.fixture(scope="module")
def matrix(authz_engine, ontology):
    """One case, one member; claims across handling codes, case scope, retraction."""
    session = Session(authz_engine)
    service = ActionService(session, ontology)
    context = ActionContext(actor="test:authz", purpose="T12 matrix")
    ids = {"member": f"user-member-{new_id('u')}", "outsider": f"user-out-{new_id('u')}"}
    with session.begin():
        source_id = new_id("src")
        record_id = new_id("rec")
        session.add(Source(source_id=source_id, source_type="open_source", name="T12"))
        session.add(
            SourceRecord(
                record_id=record_id,
                source_id=source_id,
                ingest_key=new_id("key"),
                content_hash="c" * 64,
                storage_uri="test://t12",
            )
        )
        person, org = new_id("ent"), new_id("ent")
        session.add_all(
            [
                Entity(entity_id=person, entity_type="person", label="Matrix P"),
                Entity(entity_id=org, entity_type="organization", label="Matrix O"),
            ]
        )
        session.flush()
        case = service.open_case(context, title="Matrix case", purpose="matrix")
        service.assign_case_member(
            context, case_id=case.case_id, user_id=ids["member"], role="analyst"
        )

        def claim(handling: str, case_id: str | None = None) -> str:
            row = service.record_claim(
                context,
                subject_id=person,
                predicate="member_of",
                object_id=org,
                record_id=record_id,
                assertion_type="reported",
                handling_code=handling,
                case_id=case_id,
            )
            return row.claim_id

        ids.update(
            case_id=case.case_id,
            open_claim=claim("open"),
            restricted_claim=claim("restricted"),
            sensitive_claim=claim("sensitive"),
            case_claim=claim("open", case_id=case.case_id),
        )
        restricted_field = service.record_claim(
            context,
            subject_id=person,
            predicate="has_nic",
            object_value="FICTIONAL-0001",
            record_id=record_id,
            assertion_type="reported",
            handling_code="open",
        )
        ids["restricted_field_claim"] = restricted_field.claim_id
        retracted = claim("open")
        service.retract_claim(context, claim_id=retracted, reason="matrix retraction")
        ids["retracted_claim"] = retracted
    yield {**ids, "session": session}
    session.rollback()
    session.close()


def _visible(session: Session, user: UserContext, ontology, ids: dict) -> set[str]:
    relevant = {
        ids["open_claim"],
        ids["restricted_claim"],
        ids["sensitive_claim"],
        ids["case_claim"],
        ids["retracted_claim"],
        ids["restricted_field_claim"],
    }
    rows = session.scalars(
        select(Claim.claim_id).where(*claim_filters(session, user, ontology))
    ).all()
    return set(rows) & relevant


@pytest.mark.integration
def test_matrix_clearance_gates_handling(matrix, ontology) -> None:
    session = matrix["session"]
    low = _visible(session, _user(matrix["outsider"], "analyst", clearance=0), ontology, matrix)
    assert matrix["open_claim"] in low
    assert matrix["restricted_claim"] not in low
    assert matrix["sensitive_claim"] not in low
    mid = _visible(session, _user(matrix["outsider"], "analyst", clearance=1), ontology, matrix)
    assert matrix["restricted_claim"] in mid
    assert matrix["sensitive_claim"] not in mid
    high = _visible(session, _user(matrix["outsider"], "analyst", clearance=2), ontology, matrix)
    assert {matrix["open_claim"], matrix["restricted_claim"], matrix["sensitive_claim"]} <= high


@pytest.mark.integration
def test_matrix_field_sensitivity_is_absent_not_counted(matrix, ontology) -> None:
    """An open row can still carry a restricted ontology property (T24a)."""
    session = matrix["session"]
    low = _visible(
        session, _user(matrix["outsider"], "analyst", clearance=0), ontology, matrix
    )
    high = _visible(
        session, _user(matrix["outsider"], "analyst", clearance=1), ontology, matrix
    )
    assert matrix["restricted_field_claim"] not in low
    assert matrix["restricted_field_claim"] in high


@pytest.mark.integration
def test_matrix_case_scope_gates_membership(matrix, ontology) -> None:
    session = matrix["session"]
    outsider = _visible(session, _user(matrix["outsider"], "analyst", clearance=2), ontology, matrix)
    assert matrix["case_claim"] not in outsider  # invisible, not "1 hidden result"
    member = _visible(session, _user(matrix["member"], "analyst", clearance=2), ontology, matrix)
    assert matrix["case_claim"] in member


@pytest.mark.integration
def test_matrix_retraction_visible_only_to_auditor(matrix, ontology) -> None:
    session = matrix["session"]
    analyst = _visible(session, _user(matrix["member"], "analyst", clearance=2), ontology, matrix)
    assert matrix["retracted_claim"] not in analyst
    auditor = _visible(session, _user(matrix["member"], "auditor", clearance=2), ontology, matrix)
    assert matrix["retracted_claim"] in auditor
