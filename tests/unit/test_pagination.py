from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from aegis.api.pagination import decode_cursor, encode_cursor, page_limit

pytestmark = pytest.mark.requirement("M-12", "spec-06-4", "T24c")


def test_cursor_round_trips_an_ordering_key_but_not_authority() -> None:
    at = datetime(2026, 7, 19, tzinfo=timezone.utc)
    cursor = encode_cursor("review-queue", [at, "sug_01"])

    assert decode_cursor(cursor, "review-queue", 2) == [at.isoformat(), "sug_01"]
    with pytest.raises(HTTPException) as error:
        decode_cursor(cursor, "audit", 2)
    assert error.value.status_code == 422


def test_page_limit_clamps_instead_of_rejecting() -> None:
    assert page_limit(500) == 200
    assert page_limit(0) == 1
