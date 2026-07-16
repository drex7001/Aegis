"""Synchronous append-only audit hash chain (Article X, ADR-015)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Literal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from aegis.store import AuditLog

GENESIS_HASH = "0" * 64
_LOCK_KEY = "aegis.audit_log.chain.v1"


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("audit timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def canonical_event(row: AuditLog) -> dict[str, Any]:
    """Return every immutable event field in its version-1 canonical form."""
    return {
        "id": row.id,
        "at": _timestamp(row.at),
        "actor": row.actor,
        "session_id": row.session_id,
        "purpose": row.purpose,
        "case_id": row.case_id,
        "action": row.action,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "decision": row.decision,
        "detail": row.detail,
    }


def canonical_json(event: dict[str, Any]) -> str:
    """Stable UTF-8 JSON used by writers and independent verification."""
    return json.dumps(
        event,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def calculate_hash(prev_hash: str, event: dict[str, Any]) -> str:
    return hashlib.sha256(
        prev_hash.encode("ascii") + canonical_json(event).encode("utf-8")
    ).hexdigest()


def append(
    session: Session,
    *,
    actor: str,
    action: str,
    decision: Literal["allow", "deny"],
    session_id: str | None = None,
    purpose: str | None = None,
    case_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
    at: datetime | None = None,
) -> AuditLog:
    """Append one chained row without committing the caller's transaction.

    The transaction-scoped advisory lock serializes every application append,
    including the first row where ``SELECT .. FOR UPDATE`` has nothing to lock.
    """
    if not actor.strip():
        raise ValueError("audit actor must not be empty")
    if not action.strip():
        raise ValueError("audit action must not be empty")

    # Also proves detail is canonical-JSON-compatible before any row is added.
    event_detail = detail or {}
    canonical_json(event_detail)

    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": _LOCK_KEY})
    previous = session.scalar(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))
    prev_hash = previous.entry_hash if previous is not None else GENESIS_HASH
    next_id = session.scalar(
        text("SELECT nextval(pg_get_serial_sequence('audit_log', 'id'))")
    )
    if next_id is None:  # pragma: no cover - broken schema, defensive only
        raise RuntimeError("audit_log id sequence is unavailable")

    row = AuditLog(
        id=next_id,
        at=at or datetime.now(timezone.utc),
        actor=actor,
        session_id=session_id,
        purpose=purpose,
        case_id=case_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        decision=decision,
        detail=event_detail,
        prev_hash=prev_hash,
        entry_hash="",
    )
    row.entry_hash = calculate_hash(prev_hash, canonical_event(row))
    session.add(row)
    session.flush()
    return row


@dataclass(frozen=True, slots=True)
class VerificationReport:
    valid: bool
    checked: int
    failed_id: int | None = None
    reason: str | None = None
    expected: str | None = None
    actual: str | None = None


def verify(session: Session) -> VerificationReport:
    """Recompute the whole chain, stopping at the first altered row."""
    expected_prev = GENESIS_HASH
    checked = 0
    for row in session.scalars(select(AuditLog).order_by(AuditLog.id)).yield_per(1000):
        if row.prev_hash != expected_prev:
            return VerificationReport(
                False,
                checked,
                row.id,
                "previous hash does not match the verified chain head",
                expected_prev,
                row.prev_hash,
            )
        expected_entry = calculate_hash(row.prev_hash, canonical_event(row))
        if row.entry_hash != expected_entry:
            return VerificationReport(
                False,
                checked,
                row.id,
                "entry hash does not match canonical event data",
                expected_entry,
                row.entry_hash,
            )
        checked += 1
        expected_prev = row.entry_hash
    return VerificationReport(True, checked)
