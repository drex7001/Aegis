"""Opaque keyset cursors shared by Phase-2 collection routes (T24c).

Cursors deliberately carry no authority.  They only remember the final row's
ordering key; every page rebuilds the route's authorization predicates before
using that key.  A route-specific scope prevents accidentally feeding (for
example) an audit cursor to entity search and getting surprising ordering.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any, Sequence

from fastapi import HTTPException

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def page_limit(value: int) -> int:
    """Clamp a requested page size as required by specs/06 section 4."""
    return max(1, min(value, MAX_LIMIT))


def encode_cursor(scope: str, values: Sequence[Any]) -> str:
    payload = {
        "v": 1,
        "s": scope,
        "k": [value.isoformat() if isinstance(value, datetime) else value for value in values],
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str | None, scope: str, size: int) -> list[Any] | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        if payload.get("v") != 1 or payload.get("s") != scope:
            raise ValueError("wrong cursor scope or version")
        values = payload["k"]
        if not isinstance(values, list) or len(values) != size:
            raise ValueError("wrong ordering key")
        return values
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(422, "invalid cursor") from exc


def split_page(rows: Sequence[Any], limit: int, cursor_values) -> tuple[list[Any], str | None]:
    """Return at most ``limit`` rows and a cursor only when another row exists."""
    items = list(rows[:limit])
    next_cursor = cursor_values(items[-1]) if len(rows) > limit and items else None
    return items, next_cursor


__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "decode_cursor",
    "encode_cursor",
    "page_limit",
    "split_page",
]
