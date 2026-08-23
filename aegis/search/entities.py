"""Entity search over names, aliases and mention keys (spec 11 §2.1, T23c/T67).

**Authorization is applied in candidate generation, not in hydration**
(ADR-012, B-17). That is the whole shape of this module: an entity carries no
handling code of its own — claims do — so an entity is reachable here only
through a claim the caller may read. Generating candidates first and filtering
afterwards would answer "no results" and "results you may not see" with
different response *sizes*, which is the inference channel spec 06 §6 closes
everywhere else.

Cross-script matching reads the stored ``latin_key``/``phonetic_key``
(ADR-035). ``norm_key`` preserves non-Latin script deliberately, so it can
match a romanization to a romanization and never a Latin query to a Sinhala
name; the stored keys are what can.

T67 changed three things and no behaviour a user would notice: keys come from
the one versioned pipeline (:mod:`aegis.search.pipeline`) rather than three
direct calls, mention rows at an older pipeline version are excluded from the
scan (ADR-052), and hits are the shared :class:`SearchHit` so entities, claims
and documents land in one ranked sequence rather than three.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    and_,
    ColumnElement,
    Select,
    Text,
    case,
    func,
    literal_column,
    or_,
    select,
)
from sqlalchemy.orm import Session

from aegis.api.auth import UserContext
from aegis.authz.filters import claim_filters
from aegis.ontology import Ontology
from aegis.search.pipeline import NORMALIZATION_VERSION, SearchKeys
from aegis.search.results import SearchHit
from aegis.store import Claim, Entity, IdentityMembership, Mention

#: Below this, a trigram match is noise. Postgres' own default is 0.3; this is
#: deliberately stricter, because a name search that returns half the corpus is
#: indistinguishable from one that failed.
SIMILARITY_FLOOR = 0.35

#: What an exact phonetic hit is worth. Deliberately modest and fixed: metaphone
#: collapses genuinely different names, so letting a phonetic match outrank a
#: real name match would be the search stating a confidence it does not have.
PHONETIC_SCORE = 0.5

#: The ontology declares `aliases` as a many-valued text property on the
#: person and organisation types, so an alias is a claim like any other — and
#: is therefore authorization-filtered like any other, for free.
ALIAS_PREDICATE = "aliases"

MAX_QUERY = 200


def _visible_entity_ids(
    session: Session,
    user: UserContext,
    ontology: Ontology,
    *,
    as_of: datetime | None = None,
) -> Select[tuple[str]]:
    """Entities the caller can reach through at least one readable claim.

    Returned as a *subquery*, never a materialized id list: the point is for
    the database to apply this while it chooses candidates, so an entity known
    only through restricted claims is absent from the scan rather than removed
    from its result.
    """
    filters = claim_filters(session, user, ontology, as_of=as_of)
    subject = select(Claim.subject_id.label("entity_id")).where(*filters)
    obj = select(Claim.object_id.label("entity_id")).where(
        Claim.object_id.is_not(None), *filters
    )
    return subject.union(obj).subquery().select()


def search_entities(
    session: Session,
    *,
    keys: SearchKeys,
    user: UserContext,
    ontology: Ontology,
    limit: int,
    as_of: datetime | None = None,
    after: tuple[float, str, str] | None = None,
) -> list[SearchHit]:
    """Rank entities against a free-text query.

    Every branch below is scoped by the same visibility subquery, so widening
    the search can never widen what a caller may see.
    """
    text = keys.text.strip()[:MAX_QUERY]
    if not text:
        return []

    visible = _visible_entity_ids(session, user, ontology, as_of=as_of)
    filters = claim_filters(session, user, ontology, as_of=as_of)

    hits: dict[str, SearchHit] = {}
    branch_limit = max(limit * 3, limit + 1)
    for row in session.execute(_label_matches(text, visible, branch_limit, after)):
        _record(hits, row, "label")
    for row in session.execute(
        _alias_matches(text, visible, filters, branch_limit, after)
    ):
        _record(hits, row, "alias")
    for row in session.execute(_mention_matches(keys, visible, branch_limit, after)):
        _record(hits, row, row.matched)
    return list(hits.values())


def _record(hits: dict[str, SearchHit], row, matched: str) -> None:
    """Keep the strongest evidence for each entity, not the first found."""
    score = float(row.score)
    current = hits.get(row.entity_id)
    if current is not None and current.score >= score:
        return
    hits[row.entity_id] = SearchHit(
        kind="entity",
        id=row.entity_id,
        # The group *is* the ontology type. Nothing here enumerates types, so a
        # new domain module's objects are searchable and grouped the day they
        # are declared (Article XIV).
        group=row.entity_type,
        label=row.label,
        detail=None,
        parent_id=None,
        score=score,
        matched=matched,
    )


def _live(visible: Select[tuple[str]]) -> list[ColumnElement[bool]]:
    return [
        Entity.entity_id.in_(visible),
        # A tombstoned entity is retained forever and excluded from results:
        # its id still resolves, so nothing breaks, but it is not a thing to
        # find by name any more (spec 05 §5).
        Entity.tombstoned_at.is_(None),
    ]


def _after(score, after: tuple[float, str, str] | None) -> list[ColumnElement[bool]]:
    if after is None:
        return []
    last_score, last_label, last_id = after
    return [
        or_(
            score < last_score,
            and_(score == last_score, Entity.label > last_label),
            and_(
                score == last_score,
                Entity.label == last_label,
                Entity.entity_id > last_id,
            ),
        )
    ]


def _label_matches(
    text: str,
    visible: Select[tuple[str]],
    limit: int,
    after: tuple[float, str, str] | None,
):
    score = func.similarity(Entity.label, text)
    return (
        select(
            Entity.entity_id, Entity.label, Entity.entity_type, score.label("score")
        )
        .where(*_live(visible), score >= SIMILARITY_FLOOR, *_after(score, after))
        .order_by(score.desc(), Entity.label, Entity.entity_id)
        .limit(limit)
    )


def _alias_matches(
    text: str,
    visible: Select[tuple[str]],
    filters: list[ColumnElement[bool]],
    limit: int,
    after: tuple[float, str, str] | None,
):
    # `object_value` is JSONB. A plain cast to text keeps the JSON quotes, so
    # `"Charlie the Younger"` would be compared *with* them and never match.
    # `#>> '{}'` extracts the scalar as text, which is what similarity needs.
    alias_text = Claim.object_value.op("#>>", return_type=Text)(
        literal_column("'{}'::text[]")
    )
    score = func.similarity(alias_text, text)
    return (
        select(
            Entity.entity_id, Entity.label, Entity.entity_type, score.label("score")
        )
        .join(Claim, Claim.subject_id == Entity.entity_id)
        .where(
            *_live(visible),
            *filters,
            Claim.predicate == ALIAS_PREDICATE,
            Claim.object_value.is_not(None),
            score >= SIMILARITY_FLOOR,
            *_after(score, after),
        )
        .order_by(score.desc(), Entity.label, Entity.entity_id)
        .limit(limit)
    )


def _mention_matches(
    keys: SearchKeys,
    visible: Select[tuple[str]],
    limit: int,
    after: tuple[float, str, str] | None,
):
    """Match through the mentions currently resolved to each entity.

    Three surfaces, scored so they cannot be confused: a romanized near-match
    scores on its own similarity, while an exact phonetic hit is pinned at a
    deliberately modest 0.5. Metaphone collapses genuinely different names, so
    letting a phonetic hit outrank a real name match would be the search
    telling a confident lie.

    Rows stamped with an older pipeline version are excluded rather than
    compared (ADR-052): a key produced by different rules is not comparable to
    one produced by these, and comparing them anyway is how a reindex people
    forgot becomes silent under-retrieval.
    """
    latin_score = func.greatest(
        func.similarity(Mention.latin_key, keys.latin),
        func.similarity(Mention.norm_key, keys.norm),
    )
    phonetic_hit = (Mention.phonetic_key == keys.phonetic) & (keys.phonetic != "")
    # `case`, not a cast: Postgres will not cast boolean to a numeric type, and
    # the branch says what the 0.5 means anyway.
    phonetic_score = case((phonetic_hit, PHONETIC_SCORE), else_=0.0)
    score = func.greatest(latin_score, phonetic_score)
    matched = case((latin_score >= SIMILARITY_FLOOR, "mention"), else_="phonetic")
    return (
        select(
            Entity.entity_id,
            Entity.label,
            Entity.entity_type,
            score.label("score"),
            matched.label("matched"),
        )
        .join(
            IdentityMembership,
            IdentityMembership.entity_id == Entity.entity_id,
        )
        .join(Mention, Mention.mention_id == IdentityMembership.mention_id)
        .where(
            *_live(visible),
            IdentityMembership.closed_revision_id.is_(None),
            Mention.normalization_version == NORMALIZATION_VERSION,
            or_(latin_score >= SIMILARITY_FLOOR, phonetic_hit),
            *_after(score, after),
        )
        .order_by(score.desc(), Entity.label, Entity.entity_id)
        .limit(limit)
    )


__all__ = ["MAX_QUERY", "SIMILARITY_FLOOR", "search_entities"]
