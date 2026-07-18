"""Deterministic unit tests for ADR-014 revocation retry behavior (T16b)."""

from __future__ import annotations

import asyncio

import pytest

from aegis.authz.fga import FGAError
from aegis.authz.outbox import (
    SyncReport,
    delete_inline_best_effort,
    dispatch_forever,
)


pytestmark = pytest.mark.requirement("Article-VI", "ADR-014", "T16b")


class _FakeFGA:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.deleted: list[dict[str, str]] = []

    def delete(self, tuple_: dict[str, str]) -> None:
        if self.fail:
            raise FGAError("simulated outage")
        self.deleted.append(tuple_)


class _SessionContext:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, *args: object) -> None:
        return None


def test_inline_delete_is_best_effort() -> None:
    tuple_ = {"user": "user:revoked", "relation": "analyst", "object": "case:test"}
    healthy = _FakeFGA()
    assert delete_inline_best_effort(healthy, tuple_)  # type: ignore[arg-type]
    assert healthy.deleted == [tuple_]

    unavailable = _FakeFGA(fail=True)
    assert not delete_inline_best_effort(unavailable, tuple_)  # type: ignore[arg-type]
    assert unavailable.deleted == []


def test_dispatcher_retries_on_the_configured_cadence() -> None:
    clock = iter((10.0, 10.012))
    requested_delays: list[float] = []

    class StopDispatcher(Exception):
        pass

    async def fake_sleep(delay: float) -> None:
        requested_delays.append(delay)
        raise StopDispatcher

    async def measure() -> None:

        def fake_sync(
            session: object,
            fga: object,
            *,
            limit: int,
        ) -> SyncReport:
            return SyncReport(pending=1, failed_id=1, error="simulated outage")

        with pytest.raises(StopDispatcher):
            await dispatch_forever(
                _SessionContext,
                object(),  # type: ignore[arg-type]
                interval_seconds=0.05,
                batch_size=1,
                _sync_fn=fake_sync,
                _clock_fn=lambda: next(clock),
                _sleep_fn=fake_sleep,
            )

    asyncio.run(measure())
    assert requested_delays == pytest.approx([0.038])
