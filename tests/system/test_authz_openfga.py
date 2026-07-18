"""OpenFGA dual-write and rebuild system acceptance test (ADR-014)."""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, new_id
from aegis.authz import FGAClient, FGAError, desired_tuples, rebuild, sync
from aegis.ontology import load
from aegis.store import AuthzOutbox
from tests.support.database import migrated_test_engine
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement("Article-VI", "ADR-014", "T12")


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def authz_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


@pytest.fixture(scope="module")
def live_fga(authz_engine: sa.Engine) -> FGAClient:
    del authz_engine
    from aegis.config import get_settings

    if not get_settings().fga_store_id:
        pytest.fail("FGA_STORE_ID is required; run make up && make bootstrap", pytrace=False)
    fga = FGAClient()
    try:
        fga.check("user:probe", "can_view", "case:probe")
    except FGAError as exc:
        pytest.fail(f"OpenFGA is not reachable: {exc}", pytrace=False)
    return fga


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
