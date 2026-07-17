"""Row-filter builders (T12, spec 03 §4) — always appended, never optional.

Every knowledge read composes these SQLAlchemy conditions:

* handling ≤ clearance — computed from the ontology's ordered handling codes;
  a handling code the ontology no longer declares matches nothing (fail closed);
* case scope — case-less rows (the general OSINT pool) plus the caller's member
  cases (Postgres ``case_member`` is the source of truth, spec 03 §3);
* retraction — hidden unless the caller is an auditor (spec 03 §2);
* as-of — "what did we know then" reads (ADR-008, spec 06 conventions).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from aegis.api.auth import UserContext
from aegis.ontology import Ontology
from aegis.store import CaseMember, Claim


def allowed_handling_codes(ontology: Ontology, clearance: int) -> list[str]:
    return [code for index, code in enumerate(ontology.handling_codes) if index <= clearance]


def member_case_ids(session: Session, user: UserContext) -> list[str]:
    return list(
        session.scalars(select(CaseMember.case_id).where(CaseMember.user_id == user.sub))
    )


def claim_filters(
    session: Session,
    user: UserContext,
    ontology: Ontology,
    *,
    as_of: datetime | None = None,
) -> list[ColumnElement[bool]]:
    """The always-on conditions for reading ``claim`` rows."""
    conditions: list[ColumnElement[bool]] = [
        Claim.handling_code.in_(allowed_handling_codes(ontology, user.clearance))
    ]
    cases = member_case_ids(session, user)
    case_scope = Claim.case_id.is_(None)
    if cases:
        case_scope = or_(case_scope, Claim.case_id.in_(cases))
    conditions.append(case_scope)
    if "auditor" in user.roles:
        # auditors see retracted content for review; as-of still applies
        if as_of is not None:
            conditions.append(Claim.recorded_at <= as_of)
    elif as_of is not None:
        conditions.append(Claim.recorded_at <= as_of)
        conditions.append(
            or_(Claim.retracted_at.is_(None), Claim.retracted_at > as_of)
        )
    else:
        conditions.append(Claim.retracted_at.is_(None))
    return conditions
