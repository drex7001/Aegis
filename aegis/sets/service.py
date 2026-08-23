"""Saving object sets, and the pinning rule that makes them stable (T69, ADR-054).

Everything a set does that could surprise its author later happens **here, at
save**: interfaces are expanded, the ontology version is stamped, limits are
enforced, and composition cycles are refused.

That placement is the design. B-17's objection is that a saved set can widen
under its owner without review — "automatically adding future interface members
changes the meaning of a saved analytic/watchlist" — and the answer is that a
definition records what it meant when it was written. A set that resolved its
interfaces at *evaluation* would be a set whose meaning belongs to whoever
lands the next domain module.

Editing writes a **new version**. Nothing updates one, because a finding names
`(set_id, version)` and has to name something that cannot change under it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aegis.ids import new_id
from aegis.ontology import Ontology
from aegis.sets.grammar import (
    FilterNode,
    GrammarError,
    expand_interfaces,
    interfaces_used,
    parse,
    referenced_sets,
    validate,
)
from aegis.sets.limits import MAX_COMPOSITION_DEPTH
from aegis.sets.sharing import (
    EDITOR,
    VIEWER,
    grant_tuple,
    refuse_undisclosable_difference,
)
from aegis.store import AuthzOutbox, ObjectSet, ObjectSetNotice, ObjectSetVersion


def create_set(
    session: Session,
    *,
    name: str,
    ast: dict[str, Any],
    ontology: Ontology,
    actor: str,
    description: str | None = None,
    case_id: str | None = None,
    track_interface_members: bool = False,
    as_of: datetime | None = None,
    as_of_revision: int | None = None,
    note: str | None = None,
    readable_set_ids: set[str] | None = None,
) -> tuple[ObjectSet, ObjectSetVersion]:
    """A new set and its version 1, owned and editable by its creator."""
    set_id = new_id("oset")
    row = ObjectSet(
        set_id=set_id,
        name=name,
        description=description,
        case_id=case_id,
        owner=actor,
        created_by=actor,
    )
    session.add(row)
    session.flush()
    version = add_version(
        session,
        set_id=set_id,
        ast=ast,
        ontology=ontology,
        actor=actor,
        track_interface_members=track_interface_members,
        as_of=as_of,
        as_of_revision=as_of_revision,
        note=note,
        readable_set_ids=readable_set_ids,
    )
    # The creator is an editor, through the outbox like every other grant
    # (ADR-014). Written here rather than left to the route so a set can never
    # exist that nobody can edit — including its author.
    session.add(AuthzOutbox(op="write", fga_tuple=grant_tuple(actor, EDITOR, set_id)))
    if case_id:
        # Case-scoped sets derive their grants from the case (spec 12 §5.1), so
        # the only tuple needed is the one naming the case.
        session.add(
            AuthzOutbox(
                op="write",
                fga_tuple={
                    "user": f"case:{case_id}",
                    "relation": "case",
                    "object": f"object_set:{set_id}",
                },
            )
        )
    session.flush()
    return row, version


def share(
    session: Session,
    *,
    set_id: str,
    user_sub: str,
    relation: str = VIEWER,
    op: str = "write",
) -> dict[str, str]:
    """Grant or revoke, through the outbox (ADR-014).

    Returns the tuple so the caller can audit *what* was shared with *whom* —
    spec 12 §5.2 rule 3 asks for the audit, and an audit row saying "shared"
    without naming the grant answers no question anybody will later ask.
    """
    tuple_ = grant_tuple(user_sub, relation, set_id)
    session.add(AuthzOutbox(op=op, fga_tuple=tuple_))
    session.flush()
    return tuple_


def add_version(
    session: Session,
    *,
    set_id: str,
    ast: dict[str, Any],
    ontology: Ontology,
    actor: str,
    track_interface_members: bool = False,
    as_of: datetime | None = None,
    as_of_revision: int | None = None,
    note: str | None = None,
    readable_set_ids: set[str] | None = None,
) -> ObjectSetVersion:
    """Validate, pin, and append. Never update.

    `readable_set_ids` is the caller's own view of which set definitions they
    may read, used for the §7 difference rule. `None` means "no composition is
    readable", which is the safe default: a caller that did not say refuses
    every negation over a set rather than permitting one.
    """
    node = parse(ast)
    validate(node, ontology=ontology)
    refuse_undisclosable_difference(node, readable_set_ids=readable_set_ids or set())
    _refuse_cycles(session, set_id=set_id, node=node)

    # Tracking sets keep interfaces unexpanded, so evaluation resolves them
    # against the live composition. Pinned sets — the default — freeze them.
    stored = node if track_interface_members else expand_interfaces(node, ontology=ontology)

    next_version = (
        session.scalar(
            select(func.coalesce(func.max(ObjectSetVersion.version), 0)).where(
                ObjectSetVersion.set_id == set_id
            )
        )
        + 1
    )
    row = ObjectSetVersion(
        set_id=set_id,
        version=next_version,
        ast=stored.model_dump(mode="json", by_alias=True),
        ast_as_written=node.model_dump(mode="json", by_alias=True),
        ontology_version=ontology.version,
        track_interface_members=track_interface_members,
        as_of=as_of,
        as_of_revision=as_of_revision,
        note=note,
        created_by=actor,
    )
    session.add(row)
    session.flush()
    return row


def _refuse_cycles(session: Session, *, set_id: str, node: FilterNode) -> None:
    """Walk the reference graph and refuse a cycle at save (B-17).

    At save and not at run time, and the distinction is the whole point: a
    cycle caught during evaluation is a request that times out differently
    every time, while the definition sits in the database being shared. A cycle
    caught here is a `422` before anyone can act on it.
    """
    seen: set[tuple[str, int]] = set()
    frontier = [(reference, 1) for reference in referenced_sets(node)]

    while frontier:
        (referenced_id, version), depth = frontier.pop()
        if referenced_id == set_id:
            raise GrammarError(
                "ast", f"composition cycle: this set references itself ({set_id})"
            )
        if depth > MAX_COMPOSITION_DEPTH:
            raise GrammarError(
                "ast",
                f"composition nests deeper than {MAX_COMPOSITION_DEPTH}; a set of "
                "sets of sets is a query language, not a filter",
            )
        if (referenced_id, version) in seen:
            continue
        seen.add((referenced_id, version))

        row = session.get(ObjectSetVersion, (referenced_id, version))
        if row is None:
            raise GrammarError(
                "ast", f"set {referenced_id} v{version} does not exist"
            )
        for reference in referenced_sets(parse(row.ast)):
            frontier.append((reference, depth + 1))


def notify_interface_growth(
    session: Session,
    *,
    ontology: Ontology,
    previous_members: dict[str, set[str]],
) -> list[ObjectSetNotice]:
    """One notice per set whose interface gained a member (spec 12 §4.3).

    Sent to **pinned and tracking sets alike**. A tracking set changed; a
    pinned set could have. Telling only the first would mean the owner of a
    pinned set discovers the divergence when somebody questions a number, which
    is the wrong moment.

    `previous_members` is passed in rather than read from history because the
    caller — the ontology release path — is the only thing that knows what the
    interface used to hold.
    """
    notices: list[ObjectSetNotice] = []
    grown = {
        interface: sorted(set(ontology.implementors(interface)) - was)
        for interface, was in previous_members.items()
        if set(ontology.implementors(interface)) - was
    }
    if not grown:
        return notices

    for version in session.scalars(select(ObjectSetVersion)):
        used = interfaces_used(parse(version.ast_as_written))
        for interface, members in grown.items():
            if interface not in used:
                continue
            for member in members:
                notices.append(
                    ObjectSetNotice(
                        notice_id=new_id("osn"),
                        set_id=version.set_id,
                        version=version.version,
                        interface=interface,
                        member=member,
                        ontology_version=ontology.version,
                        tracking=version.track_interface_members,
                    )
                )
    session.add_all(notices)
    session.flush()
    return notices


__all__ = ["add_version", "create_set", "notify_interface_growth", "share"]
