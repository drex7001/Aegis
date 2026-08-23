"""Engine and session factories.

The one non-obvious thing here is the **connect timeout**. libpq defaults
``connect_timeout`` to 0, meaning "wait for the operating system", and a TCP
connection that is *dropped* rather than *refused* — a firewall, a stopped
container behind a rule, a host that no longer exists — takes minutes to fail
that way. Every connect this process makes serves either a request or the
authorization-outbox dispatcher, and neither of those has minutes.

The dispatcher is why this is a correctness problem and not a preference. It
runs its blocking work through ``asyncio.to_thread``, so the worker sits on the
event loop's **default executor**, which loop shutdown joins and cannot cancel.
An unreachable database therefore made application shutdown block for the full
OS timeout — found while diagnosing a local test run where two app-startup
tests took 130 seconds each and the stack showed ``psycopg.waiting.wait_conn``
under ``concurrent.futures.thread.shutdown``.

Bounding the connect turns that into an error the dispatcher logs and retries
on its ordinary cadence, and a shutdown that completes.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from aegis.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all canonical tables (speckit spec 02)."""


def _connect_args(url: str, timeout_seconds: int) -> dict[str, int]:
    """``connect_timeout`` for PostgreSQL, nothing for anything else.

    Applied by backend rather than unconditionally: ``connect_timeout`` is a
    libpq parameter, and passing it to a driver that does not know it is a
    ``TypeError`` at connect time — a failure mode worse than the one this
    exists to fix.
    """
    if not make_url(url).get_backend_name().startswith("postgresql"):
        return {}
    return {"connect_timeout": timeout_seconds}


def get_engine(url: str | None = None) -> Engine:
    settings = get_settings()
    resolved = url or settings.database_url
    return create_engine(
        resolved,
        connect_args=_connect_args(resolved, settings.database_connect_timeout_seconds),
    )


def get_sessionmaker(engine: Engine | None = None) -> sessionmaker:
    return sessionmaker(bind=engine or get_engine())
