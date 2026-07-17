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
from aegis.authz import FGAClient, FGAError, claim_filters, desired_tuples, rebuild, sync
from aegis.ontology import load
from aegis.store import AuthzOutbox, Claim, Entity, Source, SourceRecord

REPO_ROOT = Path(__file__).resolve().parents[1]


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
def authz_engine() -> sa.Engine:
    database_url = os.getenv("AEGIS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("set AEGIS_TEST_DATABASE_URL to run PostgreSQL authz tests")
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    previous = os.environ.get("AEGIS_DATABASE_URL")
    os.environ["AEGIS_DATABASE_URL"] = database_url
    from aegis.config import get_settings

    get_settings.cache_clear()
    command.upgrade(config, "head")
    engine = sa.create_engine(database_url)
    yield engine
    engine.dispose()
    if previous is None:
        os.environ.pop("AEGIS_DATABASE_URL", None)
    else:
        os.environ["AEGIS_DATABASE_URL"] = previous
    get_settings.cache_clear()


@pytest.fixture(scope="module")
def live_fga(authz_engine) -> FGAClient:
    from aegis.config import get_settings

    if not get_settings().fga_store_id:
        pytest.skip("FGA_STORE_ID not configured — run `make bootstrap`")
    fga = FGAClient()
    try:
        fga.check("user:probe", "can_view", "case:probe")
    except FGAError:
        pytest.skip("OpenFGA is not reachable — start the compose stack")
    return fga


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


# ── dual-write drill (ADR-014 AC) ────────────────────────────────────────────


@pytest.mark.integration
def test_dual_write_drill_and_rebuild(authz_engine, ontology, live_fga) -> None:
    user_id = f"drill-{new_id('u')}"
    context = ActionContext(actor="test:drill", purpose="T12 drill")

    # 1. FGA is "down" — the membership write must still commit.
    with Session(authz_engine) as session:
        service = ActionService(session, ontology)
        with session.begin():
            case = service.open_case(context, title="Drill case", purpose="drill")
            case_id = case.case_id
            service.assign_case_member(
                context, case_id=case_id, user_id=user_id, role="analyst"
            )
        pending = session.scalars(
            select(AuthzOutbox).where(AuthzOutbox.processed_at.is_(None))
        ).all()
        assert any(
            row.fga_tuple == {"user": f"user:{user_id}", "relation": "analyst", "object": f"case:{case_id}"}
            for row in pending
        )

    dead_fga = FGAClient(
        api_url="http://127.0.0.1:59999", store_id="dead-store", model_id="dead-model"
    )
    with Session(authz_engine) as session:
        report = sync(session, dead_fga)
        assert not report.ok
        assert report.processed == 0  # grants fail closed while the outbox drains

    # 2. FGA is back — sync drains, the check now allows.
    with Session(authz_engine) as session:
        report = sync(session, live_fga)
        assert report.ok, report.error
        assert report.processed >= 1
    assert live_fga.check(f"user:{user_id}", "can_view", f"case:{case_id}")
    assert live_fga.check(f"user:{user_id}", "can_edit", f"case:{case_id}")
    assert not live_fga.check(f"user:{user_id}", "can_approve", f"case:{case_id}")

    # 3. Idempotent retry: re-writing the same tuple converges silently.
    live_fga.write(
        {"user": f"user:{user_id}", "relation": "analyst", "object": f"case:{case_id}"}
    )

    # 4. Rebuild from Postgres alone reproduces the tuple set.
    with Session(authz_engine) as session:
        desired = desired_tuples(session)
        rebuild_report = rebuild(session, live_fga)
    assert rebuild_report.desired == len(desired)
    assert (f"user:{user_id}", "analyst", f"case:{case_id}") in desired
    in_store = {(t["user"], t["relation"], t["object"]) for t in live_fga.read_all()}
    assert in_store == desired
    assert live_fga.check(f"user:{user_id}", "can_view", f"case:{case_id}")
