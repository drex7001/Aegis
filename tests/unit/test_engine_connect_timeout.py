"""An unreachable database must fail, not hang.

Sibling of `test_config_defaults.py`, and found the same way: a local test run
that should take under a minute took 4:47, and two app-startup tests accounted
for 260 s of it at **130 s each**. The faulthandler stack named the cause
exactly —

    psycopg.waiting.wait_conn
    ...
    concurrent.futures.thread.shutdown
    asyncio.base_events._do_shutdown

— the authorization-outbox dispatcher's blocking work runs through
`asyncio.to_thread`, so it sits on the event loop's **default executor**, which
loop shutdown *joins* and cannot cancel. libpq's `connect_timeout` defaults to
0, meaning "wait for the operating system", and a TCP connection that is
dropped rather than refused takes minutes to fail that way. So an unreachable
database blocked application shutdown for the full OS timeout.

That is a robustness defect independently of whose machine has the firewall: a
process whose shutdown depends on a network peer being reachable does not shut
down. Bounding the connect turns it into an error the dispatcher logs and
retries on its ordinary cadence.
"""

from __future__ import annotations

import pytest

from aegis.config import Settings, get_settings
from aegis.store.engine import _connect_args, get_engine

# No task id: this is a defect found while preparing T67, not part of any P6
# task's scope. The Phase 6 exit review records it as a defect rather than as
# a deliverable.
pytestmark = pytest.mark.requirement("ADR-014")

POSTGRES_URL = "postgresql+psycopg://aegis:aegis-dev@127.0.0.1:5433/aegis"


def test_a_postgres_engine_is_built_with_a_bounded_connect_timeout(monkeypatch) -> None:
    """Asserted at the call, because SQLAlchemy does not keep `connect_args`.

    An engine merges them into the pool's creator closure at connect time and
    retains nothing readable, so `engine.dialect.create_connect_args(url)`
    reports only what the *URL* carries — which is exactly the mistake this
    comment exists to stop the next reader repeating.
    """
    captured: dict[str, object] = {}

    def fake_create_engine(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("aegis.store.engine.create_engine", fake_create_engine)
    get_engine(POSTGRES_URL)

    timeout = captured["connect_args"]["connect_timeout"]
    assert timeout == get_settings().database_connect_timeout_seconds
    assert timeout > 0


def test_the_timeout_is_short_enough_to_be_a_timeout() -> None:
    """A bound nobody reaches before giving up is not a bound.

    The number itself is a judgement call; that it is *far* below the OS
    default this exists to escape is not.
    """
    assert 1 <= Settings.model_fields["database_connect_timeout_seconds"].default <= 30


def test_a_non_postgres_url_is_left_alone() -> None:
    """`connect_timeout` is a libpq parameter.

    Passing it to a driver that does not know it is a `TypeError` at connect
    time — a worse failure than the hang this fixes, and one that would only
    appear wherever a non-PostgreSQL URL is used.
    """
    assert _connect_args("sqlite+pysqlite:///:memory:", 10) == {}


def test_the_backend_check_actually_discriminates() -> None:
    """Non-vacuity: a rule that returns {} for everything would pass above."""
    assert _connect_args(POSTGRES_URL, 7) == {"connect_timeout": 7}


def test_a_sqlite_engine_still_builds() -> None:
    """The `TypeError` above, asserted rather than reasoned about."""
    engine = get_engine("sqlite+pysqlite:///:memory:")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("select 1").scalar() == 1
