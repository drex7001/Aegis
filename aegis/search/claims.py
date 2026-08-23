"""Claim-text search, and the identifier rule (spec 11 §2.2, ADR-053).

This is the backend where the B-17 invariant costs nothing: the same
`claim_filters` list that authorizes reading a claim authorizes its candidacy,
so "applied in candidate generation" is one `where` clause rather than an
argument.

**A claim hit renders as the claim**, never as a free-floating snippet:
subject, predicate, object, grading, source. A matched fragment shown without
its grading is precisely what Article III exists to prevent — the reader has no
way to tell a court record from an anonymous blog post, and the search result
is where that distinction is easiest to lose.

## The identifier rule, and why it needs no format detection

ADR-053 says identifiers match exactly, never fuzzily. The obvious
implementation — recognise "that looks like a NIC" from its shape — would be
domain knowledge in the core, which Article XIV forbids, and would be wrong the
first time a country changed its format.

The rule is instead expressed on the **claim**, not the query: a predicate the
ontology marks `identifier: true` is compared by **equality on the normalized
value** and is never offered to trigram similarity. A query that exactly equals
a stored identifier hits; a near-miss returns nothing. Nothing here knows what
a NIC looks like, and a second domain's identifiers inherit the rule by
declaring themselves identifiers.

Recall is knowingly traded away. A mistyped identifier returning nothing is the
correct answer, because the alternative is a confident wrong person.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, Select, Text, and_, func, literal_column, or_, select
from sqlalchemy.orm import Session

from aegis.api.auth import UserContext
from aegis.authz.filters import claim_filters
from aegis.ontology import Ontology
from aegis.search.entities import SIMILARITY_FLOOR
from aegis.search.pipeline import SearchKeys
from aegis.search.results import CLAIM_GROUP, SearchHit
from aegis.store import Claim, Entity

#: What an exact identifier match is worth. 1.0 and not "high": an identifier
#: equality is the strongest statement search can make, and anything less would
#: let a fuzzy name match outrank it.
IDENTIFIER_SCORE = 1.0


def _scalar_text(column) -> ColumnElement[str]:
    """JSONB scalar as text.

    `#>> '{}'` rather than a cast: casting JSONB to text keeps the JSON quotes,
    so `"Charlie the Younger"` would be compared *with* them and never match.
    """
    return column.op("#>>", return_type=Text)(literal_column("'{}'::text[]"))


def _identifier_predicates(ontology: Ontology) -> list[str]:
    return [name for name, spec in ontology.predicates.items() if spec.identifier]


def _after(score, label, claim_id, after: tuple[float, str, str] | None):
    if after is None:
        return []
    last_score, last_label, last_id = after
    return [
        or_(
            score < last_score,
            and_(score == last_score, label > last_label),
            and_(score == last_score, label == last_label, claim_id > last_id),
        )
    ]


def _label_of(subject_label: str, predicate: str) -> str:
    return f"{subject_label} — {predicate}"


def search_claims(
    session: Session,
    *,
    keys: SearchKeys,
    user: UserContext,
    ontology: Ontology,
    limit: int,
    as_of=None,
    after: tuple[float, str, str] | None = None,
) -> list[SearchHit]:
    """Claims whose excerpt or literal value matches, under the caller's filters."""
    text = keys.text.strip()
    if not text:
        return []

    filters = claim_filters(session, user, ontology, as_of=as_of)
    identifiers = _identifier_predicates(ontology)
    hits: dict[str, SearchHit] = {}

    for statement in (
        _identifier_matches(text, filters, identifiers, limit, after),
        _excerpt_matches(text, filters, limit, after),
        _value_matches(text, filters, identifiers, limit, after),
    ):
        for row in session.execute(statement):
            hit = SearchHit(
                kind="claim",
                id=row.claim_id,
                group=CLAIM_GROUP,
                label=_label_of(row.subject_label, row.predicate),
                detail=row.predicate,
                parent_id=row.subject_id,
                score=float(row.score),
                matched=row.matched,
            )
            current = hits.get(hit.id)
            if current is None or current.score < hit.score:
                hits[hit.id] = hit
    return list(hits.values())


def _base(filters: list[ColumnElement[bool]]) -> Select:
    return (
        select(
            Claim.claim_id,
            Claim.predicate,
            Claim.subject_id,
            Entity.label.label("subject_label"),
        )
        .join(Entity, Entity.entity_id == Claim.subject_id)
        .where(Entity.tombstoned_at.is_(None), *filters)
    )


def _identifier_matches(
    text: str,
    filters: list[ColumnElement[bool]],
    identifiers: list[str],
    limit: int,
    after: tuple[float, str, str] | None,
):
    """Exact equality only. No `similarity`, no prefix, no phonetics."""
    if not identifiers:
        # `in_([])` is valid SQL but always false; returning a statement that
        # cannot match is fine, and simpler than branching at the call site.
        identifiers = ["\x00-no-identifier-predicates-declared"]
    score = literal_column(str(IDENTIFIER_SCORE))
    label = Entity.label
    return (
        _base(filters)
        .add_columns(
            score.label("score"),
            literal_column("'identifier'").label("matched"),
        )
        .where(
            Claim.predicate.in_(identifiers),
            Claim.object_value.is_not(None),
            _scalar_text(Claim.object_value) == text,
            *_after(score, label, Claim.claim_id, after),
        )
        .order_by(label, Claim.claim_id)
        .limit(limit)
    )


def _excerpt_matches(
    text: str,
    filters: list[ColumnElement[bool]],
    limit: int,
    after: tuple[float, str, str] | None,
):
    score = func.similarity(Claim.excerpt, text)
    label = Entity.label
    return (
        _base(filters)
        .add_columns(score.label("score"), literal_column("'excerpt'").label("matched"))
        .where(
            Claim.excerpt.is_not(None),
            score >= SIMILARITY_FLOOR,
            *_after(score, label, Claim.claim_id, after),
        )
        .order_by(score.desc(), label, Claim.claim_id)
        .limit(limit)
    )


def _value_matches(
    text: str,
    filters: list[ColumnElement[bool]],
    identifiers: list[str],
    limit: int,
    after: tuple[float, str, str] | None,
):
    """Literal values, **excluding** identifier predicates (ADR-053)."""
    value = _scalar_text(Claim.object_value)
    score = func.similarity(value, text)
    label = Entity.label
    statement = (
        _base(filters)
        .add_columns(score.label("score"), literal_column("'value'").label("matched"))
        .where(
            Claim.object_value.is_not(None),
            score >= SIMILARITY_FLOOR,
            *_after(score, label, Claim.claim_id, after),
        )
    )
    if identifiers:
        statement = statement.where(Claim.predicate.not_in(identifiers))
    return statement.order_by(score.desc(), label, Claim.claim_id).limit(limit)


__all__ = ["IDENTIFIER_SCORE", "search_claims"]
