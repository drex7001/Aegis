"""Evaluating a set: one snapshot, one authorization context (T70, M-16).

> An evaluation request opens **one** repeatable-read transaction, resolves
> **one** authorization context, and evaluates every node — including every
> composed subset — inside it.

M-16's objection is precise and worth restating rather than paraphrasing:
*"union/intersection/difference over caller-filtered dynamic sets can change
between subqueries and can reveal information through timing/cardinality."* If
`A ∪ B` reads A, something is recorded, and then reads B, the result is not a
set operation over anything — it is two answers about two different corpora
glued together, and the difference between them is observable.

So the snapshot is taken once, and every operand sees it.

**A set never evaluates with its owner's clearance.** The authorization context
comes from the caller, once, and every subquery composes that same filter list —
including subsets owned by other people. That is what makes composition safe
rather than clever: a row the caller cannot see is in *neither* operand, so it
is in no result and changes no cardinality. `difference` cannot be used to
probe, because there is nothing on the far side of the filter to probe for.

The one deliberate exception is the watchlist sweep (spec 12 §11.3), which runs
under the *owner's* context and says so in its manifest. It is not this code
path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from aegis.api.auth import UserContext
from aegis.ontology import Ontology
from aegis.sets.compile import compile_set
from aegis.sets.grammar import FilterNode, parse
from aegis.sets.limits import MAX_EVALUATED_OBJECTS, STATEMENT_TIMEOUT_MS
from aegis.store import Entity, ObjectSetVersion


@dataclass(frozen=True, slots=True)
class EvaluatedMember:
    entity_id: str
    label: str
    entity_type: str


@dataclass
class Evaluation:
    """What an evaluation returns. Deliberately without a total.

    `truncated` is the honest alternative to a count: it says "there is more"
    without saying how much more, which is the same bargain every other
    authorization-filtered collection on this system makes (spec 06 §4).
    """

    members: list[EvaluatedMember] = field(default_factory=list)
    truncated: bool = False
    #: SHA-256 over the sorted member ids — the input digest an analytic run
    #: records so "the same inputs" is checkable rather than hoped (ADR-055).
    evaluation_digest: str = ""
    set_id: str | None = None
    version: int | None = None


def evaluation_digest(entity_ids) -> str:
    """Order-independent, because membership is a set and not a ranking."""
    joined = "\n".join(sorted(entity_ids))
    return sha256(joined.encode("utf-8")).hexdigest()


def resolver(session: Session):
    """Turn `set_id, version` into the stored AST, for composition.

    Reads the **stored** (expanded) AST, so a composed subset means what it
    meant when it was saved — the pinning rule applies through composition too,
    or a composed set would inherit whichever member list its operand happens
    to have today.
    """

    def resolve(set_id: str, version: int) -> FilterNode:
        row = session.get(ObjectSetVersion, (set_id, version))
        if row is None:
            raise LookupError(f"object set {set_id} v{version} does not exist")
        return parse(row.ast)

    return resolve


def evaluate(
    session: Session,
    node: FilterNode,
    *,
    user: UserContext,
    ontology: Ontology,
    as_of: datetime | None = None,
    set_id: str | None = None,
    version: int | None = None,
) -> Evaluation:
    """Members of a definition, under the caller's filters and one snapshot.

    The caller owns the transaction; this sets the isolation level and the
    statement timeout on it. Doing it here rather than asking every caller to
    remember is the point — M-16 is not a rule that survives being optional.
    """
    _one_snapshot(session)

    statement = compile_set(
        node,
        session=session,
        user=user,
        ontology=ontology,
        as_of=as_of,
        resolve_set=resolver(session),
    )
    # One row beyond the cap, so "there is more" is an observation rather than
    # a count — the same trick every paginated route here uses.
    rows = list(
        session.execute(
            select(Entity.entity_id, Entity.label, Entity.entity_type)
            .where(Entity.entity_id.in_(statement))
            .order_by(Entity.label, Entity.entity_id)
            .limit(MAX_EVALUATED_OBJECTS + 1)
        )
    )
    truncated = len(rows) > MAX_EVALUATED_OBJECTS
    rows = rows[:MAX_EVALUATED_OBJECTS]

    return Evaluation(
        members=[
            EvaluatedMember(
                entity_id=row.entity_id, label=row.label, entity_type=row.entity_type
            )
            for row in rows
        ],
        truncated=truncated,
        evaluation_digest=evaluation_digest(row.entity_id for row in rows),
        set_id=set_id,
        version=version,
    )


def evaluate_version(
    session: Session,
    version: ObjectSetVersion,
    *,
    user: UserContext,
    ontology: Ontology,
) -> Evaluation:
    """Evaluate a stored version, honouring its own as-of pin (spec 12 §4.4).

    A pinned set answers the same question forever, which is what makes it a
    legitimate analytic input. An unpinned one answers today's, which is what
    makes it a legitimate watchlist. The pin travels with the version rather
    than with the request, so nobody can accidentally evaluate a pinned set at
    "now" and compare the result to a finding.
    """
    node = parse(version.ast)
    if version.track_interface_members:
        # A tracking set stores its interfaces unexpanded, so they resolve
        # against whatever composition is live — which is the whole opt-in.
        from aegis.sets.grammar import expand_interfaces

        node = expand_interfaces(node, ontology=ontology)
    return evaluate(
        session,
        node,
        user=user,
        ontology=ontology,
        as_of=version.as_of,
        set_id=version.set_id,
        version=version.version,
    )


def _one_snapshot(session: Session) -> None:
    """The resource bound. The snapshot itself comes from somewhere better.

    B-17's bound first: a definition inside the complexity limits can still be
    expensive over a large corpus, and a query that runs forever is a denial of
    service the limits did not catch. `SET LOCAL` scopes it to this
    transaction.

    **On M-16's snapshot**, which is the interesting half. The first version of
    this issued `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ` and failed:
    PostgreSQL only accepts that as a transaction's first statement, and by the
    time an evaluation runs the caller has usually done something. Working
    around it — rolling back the caller's transaction to get a clean one —
    would have been a library silently discarding a caller's uncommitted work.

    The requirement is met by construction instead, and more simply.
    `compile_set` produces **one** `SELECT`, with every operand and every
    composed subset as a subquery inside it, and `evaluate` runs it once. A
    single statement sees a single snapshot at *any* isolation level, so
    `A ∪ B` cannot be two answers about two different corpora — there is no
    moment between the operands for the corpus to change in.

    That is a stronger guarantee than the isolation level would have given, and
    it is the one `test_composition_is_a_single_statement` pins. If an
    evaluation ever needs a second statement, that test fails and this comment
    is where the reader lands: at that point the caller must supply a
    REPEATABLE READ transaction, because construction will no longer do it.
    """
    session.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))


__all__ = [
    "EvaluatedMember",
    "Evaluation",
    "evaluate",
    "evaluate_version",
    "evaluation_digest",
    "resolver",
]
