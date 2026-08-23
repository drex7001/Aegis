"""The only place an object set becomes SQL — and it is always parameterized.

Every node compiles to a **subquery over entity ids**, and the caller's row
filters are composed into each one. That is not a convenience: an object set
that generated candidates and filtered them afterwards would be the same B-17
leak the search route closes, arriving through a different door (spec 12 §6).

Two properties this module is responsible for:

**Totality.** `_compile` handles every node the grammar can produce and raises
on anything else. A compiler that silently ignored a node it did not recognise
would evaluate a *different, wider* set than the one that was saved — and the
caller would have no way to know, because the definition would still read
correctly.

**No string ever becomes syntax.** Values are bound parameters, and identifiers
come from the ontology rather than from the definition. There is nothing here
that concatenates a user value into SQL, which is why `test_object_set_grammar`
can assert the property structurally rather than by reviewing each branch.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import ColumnElement, Select, Text, and_, func, literal_column, not_, or_, select
from sqlalchemy.orm import Session

from aegis.api.auth import UserContext
from aegis.authz.filters import claim_filters, visible_entity_ids
from aegis.ontology import Ontology
from aegis.sets.grammar import (
    AndNode,
    CaseNode,
    FilterNode,
    NotNode,
    OrNode,
    PredicateNode,
    PropertyNode,
    SearchNode,
    SetNode,
    TimeNode,
    TypeNode,
)
from aegis.store import Claim, Entity


class CompileError(RuntimeError):
    """A node the compiler cannot turn into a query.

    Loud rather than ignored: an unhandled node evaluated as "no constraint"
    would widen the set silently, which is the one failure mode a saved,
    shared, analytic-feeding definition must not have.
    """


def compile_set(
    node: FilterNode,
    *,
    session: Session,
    user: UserContext,
    ontology: Ontology,
    as_of: datetime | None = None,
    resolve_set=None,
) -> Select:
    """A `SELECT entity_id` the caller is authorized to see.

    `resolve_set` turns a `SetNode` into another AST, so composition works
    without this module knowing how versions are stored. Passing `None` refuses
    composition rather than ignoring it — the same reasoning as `CompileError`.
    """
    filters = claim_filters(session, user, ontology, as_of=as_of)
    condition = _compile(
        node,
        session=session,
        user=user,
        ontology=ontology,
        filters=filters,
        as_of=as_of,
        resolve_set=resolve_set,
    )
    return (
        select(Entity.entity_id)
        .where(
            Entity.tombstoned_at.is_(None),
            # An entity carries no handling code of its own; claims do. Without
            # this, a bare `type: person` node would return every person in the
            # database — including people the caller has no readable claim
            # about. Found by a T70 test, in a compiler that had not inherited
            # the rule search learned at T23c.
            Entity.entity_id.in_(
                visible_entity_ids(session, user, ontology, as_of=as_of)
            ),
            condition,
        )
        .distinct()
    )


def _claim_subquery(filters: list[ColumnElement[bool]], *conditions: ColumnElement[bool]):
    """Entity ids reachable through a claim the caller may read.

    The filters go **inside** this subquery, every time. That is what makes the
    authorization part of candidate generation rather than a step after it.
    """
    subject = select(Claim.subject_id).where(*filters, *conditions)
    obj = select(Claim.object_id).where(
        Claim.object_id.is_not(None), *filters, *conditions
    )
    return Entity.entity_id.in_(subject.union(obj))


def _scalar_text(column) -> ColumnElement[str]:
    return column.op("#>>", return_type=Text)(literal_column("'{}'::text[]"))


def _compile(
    node: FilterNode,
    *,
    session: Session,
    user: UserContext,
    ontology: Ontology,
    filters: list[ColumnElement[bool]],
    as_of: datetime | None,
    resolve_set,
) -> ColumnElement[bool]:
    recurse = lambda child: _compile(  # noqa: E731 — one line, one meaning
        child,
        session=session,
        user=user,
        ontology=ontology,
        filters=filters,
        as_of=as_of,
        resolve_set=resolve_set,
    )

    if isinstance(node, TypeNode):
        # Interfaces are expanded at save (ADR-054), so by the time a stored
        # definition reaches here it names types. An unexpanded interface is a
        # caller compiling an as-written AST, which is a bug worth naming.
        if node.interface:
            raise CompileError(
                f"interface {node.interface!r} reached the compiler unexpanded — "
                "a stored definition holds expanded types (ADR-054)"
            )
        return Entity.entity_type == node.object_type

    if isinstance(node, PredicateNode):
        conditions = [Claim.predicate == node.predicate]
        if node.direction == "subject":
            subject = select(Claim.subject_id).where(*filters, *conditions)
            if node.target:
                subject = subject.where(Claim.object_id == node.target)
            return Entity.entity_id.in_(subject)
        if node.direction == "object":
            obj = select(Claim.object_id).where(
                Claim.object_id.is_not(None), *filters, *conditions
            )
            if node.target:
                obj = obj.where(Claim.subject_id == node.target)
            return Entity.entity_id.in_(obj)
        if node.target:
            conditions.append(
                or_(Claim.subject_id == node.target, Claim.object_id == node.target)
            )
        return _claim_subquery(filters, *conditions)

    if isinstance(node, PropertyNode):
        predicate = Claim.predicate == node.property
        value = _scalar_text(Claim.object_value)
        if node.op == "exists":
            return _claim_subquery(filters, predicate, Claim.object_value.is_not(None))
        if node.op == "absent":
            # "No readable claim says this" — which is what absence means under
            # Article VI, and is deliberately not the same as "it is not true".
            return not_(
                _claim_subquery(filters, predicate, Claim.object_value.is_not(None))
            )
        if node.op == "eq":
            return _claim_subquery(filters, predicate, value == str(node.value))
        if node.op == "neq":
            return not_(_claim_subquery(filters, predicate, value == str(node.value)))
        if node.op == "contains":
            return _claim_subquery(
                filters, predicate, value.ilike(f"%{node.value}%")
            )
        raise CompileError(f"property operator {node.op!r} has no compilation")

    if isinstance(node, TimeNode):
        column_pairs = {
            "event": (Claim.event_time_earliest, Claim.event_time_latest),
            "validity": (Claim.valid_from, Claim.valid_to),
            "recorded": (Claim.recorded_at, Claim.recorded_at),
        }
        start, end = column_pairs[node.field]
        conditions: list[ColumnElement[bool]] = []
        if node.from_ is not None:
            lower = _as_bound(node.from_, node.field)
            conditions.append(or_(end.is_(None), end >= lower))
        if node.to is not None:
            upper = _as_bound(node.to, node.field)
            conditions.append(or_(start.is_(None), start <= upper))
        return _claim_subquery(filters, *conditions)

    if isinstance(node, CaseNode):
        # Not authorization. `claim_filters` already decided what is readable;
        # a case the caller cannot see simply matches nothing, because an error
        # would disclose that it exists (spec 06 §2.5).
        return _claim_subquery(filters, Claim.case_id == node.case_id)

    if isinstance(node, SearchNode):
        from aegis.search.entities import _visible_entity_ids, search_entities
        from aegis.search.pipeline import search_keys

        hits = search_entities(
            session,
            keys=search_keys(node.q),
            user=user,
            ontology=ontology,
            limit=1_000,
            as_of=as_of,
        )
        if not hits:
            # `in_([])` is false for every row, which is the correct answer: a
            # search matching nothing constrains the set to nothing.
            return literal_column("false") == literal_column("true")
        return Entity.entity_id.in_([hit.id for hit in hits])

    if isinstance(node, SetNode):
        if resolve_set is None:
            raise CompileError(
                f"composition reached the compiler with no resolver: set "
                f"{node.set_id} v{node.version}"
            )
        return recurse(resolve_set(node.set_id, node.version))

    if isinstance(node, AndNode):
        return and_(*[recurse(child) for child in node.children])
    if isinstance(node, OrNode):
        return or_(*[recurse(child) for child in node.children])
    if isinstance(node, NotNode):
        return not_(recurse(node.child))

    raise CompileError(f"no compilation for node kind {type(node).__name__}")


def _as_bound(value, field: str):
    """A date bound as the column's own type.

    `recorded_at` is a timestamp and the others are dates; comparing a date to
    a timestamp works, but only by an implicit cast that midnight-truncates in
    a direction nobody chose. Making it explicit is one line and removes the
    question.
    """
    if field == "recorded":
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    return value


__all__ = ["CompileError", "compile_set"]
