"""Deterministic unit tests for ADR-014 revocation retry behavior (T16b)."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import time

from aegis.authz.fga import FGAError
from aegis.authz.outbox import (
    SyncReport,
    delete_inline_best_effort,
    dispatch_forever,
)


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
    interval = 0.05

    async def measure() -> float:
        attempts: list[float] = []
        retry_seen = asyncio.Event()
        loop = asyncio.get_running_loop()

        def fake_sync(
            session: object,
            fga: object,
            *,
            limit: int,
        ) -> SyncReport:
            attempts.append(time.monotonic())
            if len(attempts) == 1:
                return SyncReport(pending=1, failed_id=1, error="simulated outage")
            loop.call_soon_threadsafe(retry_seen.set)
            return SyncReport(processed=1)

        task = asyncio.create_task(
            dispatch_forever(
                _SessionContext,
                object(),  # type: ignore[arg-type]
                interval_seconds=interval,
                batch_size=1,
                _sync_fn=fake_sync,
            )
        )
        try:
            await asyncio.wait_for(retry_seen.wait(), timeout=0.5)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        return attempts[1] - attempts[0]

    measured = asyncio.run(measure())
    assert interval * 0.75 <= measured <= interval + 0.15
