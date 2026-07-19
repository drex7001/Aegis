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

from sqlalchemy import ColumnElement, not_, or_, select
from sqlalchemy.orm import Session

from aegis.api.auth import UserContext
from aegis.ontology import Ontology
from aegis.store import CaseMember, Claim, Entity


def allowed_handling_codes(ontology: Ontology, clearance: int) -> list[str]:
    return [code for index, code in enumerate(ontology.handling_codes) if index <= clearance]


def member_case_ids(session: Session, user: UserContext) -> list[str]:
    return list(
        session.scalars(select(CaseMember.case_id).where(CaseMember.user_id == user.sub))
    )


def property_sensitivity(ontology: Ontology, predicate: str) -> str | None:
    """Resolve the ontology field sensitivity represented by a claim predicate.

    Most property predicates use the property name directly (for example
    ``aliases``).  Identifier predicates are deliberately verbs (``has_nic``,
    ``reachable_on``); for those the ontology still gives us a domain-neutral
    mapping because each declared subject type has one identifier property.
    If a future module makes that ambiguous we fail closed at the stricter
    declared sensitivity rather than guessing a field name.
    """
    direct = {
        spec.sensitivity
        for object_type in ontology.object_types.values()
        for name, spec in object_type.properties.items()
        if name == predicate and spec.sensitivity is not None
    }
    pred = ontology.predicates.get(predicate)
    if pred is not None and pred.identifier:
        for subject_type in pred.subject:
            object_type = ontology.object_types.get(subject_type)
            if object_type is None:
                continue
            direct.update(
                prop.sensitivity
                for prop in object_type.properties.values()
                if prop.type == "identifier" and prop.sensitivity is not None
            )
    if not direct:
        return None
    return max(direct, key=ontology.handling_rank)


def forbidden_field_predicates(ontology: Ontology, clearance: int) -> list[str]:
    return [
        predicate
        for predicate in ontology.predicates
        if (sensitivity := property_sensitivity(ontology, predicate)) is not None
        and ontology.handling_rank(sensitivity) > clearance
    ]


def hidden_entity_types(ontology: Ontology, clearance: int) -> list[str]:
    """Types whose display title itself is a field above caller clearance."""
    hidden: list[str] = []
    for name, object_type in ontology.object_types.items():
        title = object_type.display.title if object_type.display is not None else None
        prop = object_type.properties.get(title) if title is not None else None
        if (
            prop is not None
            and prop.sensitivity is not None
            and ontology.handling_rank(prop.sensitivity) > clearance
        ):
            hidden.append(name)
    return hidden


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
    forbidden = forbidden_field_predicates(ontology, user.clearance)
    if forbidden:
        # A sensitive property claim is absent as a row.  That keeps its value,
        # its predicate, relations, counts and provenance out together.
        conditions.append(not_(Claim.predicate.in_(forbidden)))
    hidden_types = hidden_entity_types(ontology, user.clearance)
    if hidden_types:
        hidden_ids = select(Entity.entity_id).where(Entity.entity_type.in_(hidden_types))
        # A restricted display title (phone_number.number today) cannot be
        # removed while leaving an id-shaped node behind; that would disclose
        # the field's existence.  Claims touching such an entity are absent.
        conditions.append(not_(Claim.subject_id.in_(hidden_ids)))
        conditions.append(or_(Claim.object_id.is_(None), not_(Claim.object_id.in_(hidden_ids))))
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
