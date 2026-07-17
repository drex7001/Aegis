"""Transactional-outbox dispatcher + full rebuild (T12, ADR-014).

Postgres is the source of truth; FGA tuples are a projection.  ``sync`` drains
pending ``authz_outbox`` rows into FGA **strictly in order** — a failure stops
the drain so a delete/write pair for a role change can never apply reversed.
``rebuild`` re-derives the entire tuple set from Postgres alone and diffs it
against the store, which both repairs drift and proves the projection property
(Article XIII).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.authz.fga import FGAClient, FGAError, Tuple3
from aegis.store import AuthzOutbox, CaseMember, CustodyEvent, EvidenceItem

# case_member.role → FGA relation (mirrors aegis.actions.service.CASE_MEMBER_RELATIONS)
_CASE_RELATIONS = {
    "analyst": "analyst",
    "investigator": "investigator",
    "supervisor": "supervisor",
    "auditor": "auditor_grant",
}


@dataclass
class SyncReport:
    processed: int = 0
    pending: int = 0
    failed_id: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class RebuildReport:
    desired: int = 0
    written: int = 0
    deleted: int = 0
    superseded_outbox_rows: int = 0
    tuples: list[Tuple3] = field(default_factory=list)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sync(session: Session, fga: FGAClient, *, limit: int | None = None) -> SyncReport:
    """Drain pending outbox rows in insertion order; stop at the first failure."""
    report = SyncReport()
    query = (
        select(AuthzOutbox)
        .where(AuthzOutbox.processed_at.is_(None))
        .order_by(AuthzOutbox.outbox_id)
        .with_for_update(skip_locked=False)
    )
    if limit is not None:
        query = query.limit(limit)
    with session.begin():
        rows = session.scalars(query).all()
        for row in rows:
            row.attempts += 1
            try:
                if row.op == "write":
                    fga.write(dict(row.fga_tuple))
                else:
                    fga.delete(dict(row.fga_tuple))
            except FGAError as exc:
                row.last_error = str(exc)
                report.failed_id = row.outbox_id
                report.error = str(exc)
                break
            row.processed_at = _utcnow()
            row.last_error = None
            report.processed += 1
        report.pending = sum(1 for row in rows if row.processed_at is None)
    return report


def desired_tuples(session: Session) -> set[tuple[str, str, str]]:
    """The full FGA tuple set implied by Postgres rows (source of truth)."""
    desired: set[tuple[str, str, str]] = set()
    for member in session.scalars(select(CaseMember)):
        relation = _CASE_RELATIONS.get(member.role)
        if relation is None:
            continue  # unknown roles never become grants — fail closed
        desired.add((f"user:{member.user_id}", relation, f"case:{member.case_id}"))
    for item in session.scalars(select(EvidenceItem).where(EvidenceItem.case_id.isnot(None))):
        desired.add((f"case:{item.case_id}", "case", f"evidence_item:{item.evidence_id}"))
    # current custodian = the latest custody event per evidence item
    latest: dict[str, CustodyEvent] = {}
    for event in session.scalars(select(CustodyEvent)):
        current = latest.get(event.evidence_id)
        if current is None or event.seq > current.seq:
            latest[event.evidence_id] = event
    for event in latest.values():
        desired.add(
            (f"user:{event.to_actor}", "custodian", f"evidence_item:{event.evidence_id}")
        )
    return desired


def rebuild(session: Session, fga: FGAClient) -> RebuildReport:
    """Make the FGA store equal to the Postgres-derived tuple set."""
    report = RebuildReport()
    desired = desired_tuples(session)
    report.desired = len(desired)
    # Close the read transaction that the SELECTs above autobegan, so the outbox
    # write below can open its own; the FGA reconcile between them is external I/O.
    session.commit()
    existing = {
        (t["user"], t["relation"], t["object"]) for t in fga.read_all()
    }
    for user, relation, object_ in sorted(desired - existing):
        fga.write({"user": user, "relation": relation, "object": object_})
        report.written += 1
    for user, relation, object_ in sorted(existing - desired):
        fga.delete({"user": user, "relation": relation, "object": object_})
        report.deleted += 1
    # a full rebuild supersedes anything still queued
    with session.begin():
        pending = session.scalars(
            select(AuthzOutbox).where(AuthzOutbox.processed_at.is_(None))
        ).all()
        for row in pending:
            row.processed_at = _utcnow()
            row.last_error = "superseded by authz rebuild"
            report.superseded_outbox_rows += 1
    report.tuples = [
        {"user": u, "relation": r, "object": o} for u, r, o in sorted(desired)
    ]
    return report
