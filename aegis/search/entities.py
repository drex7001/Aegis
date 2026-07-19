"""Entity search over names, aliases and mention keys (spec 06 §2.1, T23c).

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
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import (
    ColumnElement,
    Float,
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
from aegis.er.normalize import norm_key
from aegis.er.translit import latin_key, phonetic_key
from aegis.ontology import Ontology
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


@dataclass(frozen=True, slots=True)
class EntityHit:
    entity_id: str
    label: str
    entity_type: str
    #: Best trigram similarity across every field that matched, 0–1. Reported
    #: so a caller can see *how* close a hit is rather than only its rank.
    score: float
    #: Which surface matched — `label`, `alias`, `mention` or `phonetic`. A
    #: phonetic hit is a much weaker claim than a name hit, and a list that
    #: does not say so invites a reader to treat them alike.
    matched: str


def _visible_entity_ids(
    session: Session, user: UserContext, ontology: Ontology
) -> Select[tuple[str]]:
    """Entities the caller can reach through at least one readable claim.

    Returned as a *subquery*, never a materialized id list: the point is for
    the database to apply this while it chooses candidates, so an entity known
    only through restricted claims is absent from the scan rather than removed
    from its result.
    """
    filters = claim_filters(session, user, ontology)
    subject = select(Claim.subject_id.label("entity_id")).where(*filters)
    obj = select(Claim.object_id.label("entity_id")).where(
        Claim.object_id.is_not(None), *filters
    )
    return subject.union(obj).subquery().select()


def search_entities(
    session: Session,
    *,
    query: str,
    user: UserContext,
    ontology: Ontology,
    limit: int = 20,
) -> list[EntityHit]:
    """Rank entities against a free-text query.

    Every branch below is scoped by the same visibility subquery, so widening
    the search can never widen what a caller may see.
    """
    text = query.strip()[:MAX_QUERY]
    if not text:
        return []

    visible = _visible_entity_ids(session, user, ontology)
    keys = {
        "norm": norm_key(text),
        "latin": latin_key(text),
        "phonetic": phonetic_key(text),
    }

    hits: dict[str, EntityHit] = {}
    for row in session.execute(_label_matches(text, visible, limit)):
        _record(hits, row.entity_id, row.label, row.entity_type, float(row.score), "label")
    for row in session.execute(_alias_matches(text, visible, limit)):
        _record(hits, row.entity_id, row.label, row.entity_type, float(row.score), "alias")
    for row in session.execute(_mention_matches(keys, visible, limit)):
        _record(
            hits, row.entity_id, row.label, row.entity_type, float(row.score), row.matched
        )

    ranked = sorted(hits.values(), key=lambda hit: (-hit.score, hit.label, hit.entity_id))
    return ranked[:limit]


def _record(
    hits: dict[str, EntityHit],
    entity_id: str,
    label: str,
    entity_type: str,
    score: float,
    matched: str,
) -> None:
    """Keep the strongest evidence for each entity, not the first found."""
    current = hits.get(entity_id)
    if current is not None and current.score >= score:
        return
    hits[entity_id] = EntityHit(
        entity_id=entity_id,
        label=label,
        entity_type=entity_type,
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


def _label_matches(text: str, visible: Select[tuple[str]], limit: int):
    score = func.similarity(Entity.label, text)
    return (
        select(
            Entity.entity_id, Entity.label, Entity.entity_type, score.label("score")
        )
        .where(*_live(visible), score >= SIMILARITY_FLOOR)
        .order_by(score.desc())
        .limit(limit)
    )


def _alias_matches(text: str, visible: Select[tuple[str]], limit: int):
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
            Claim.predicate == ALIAS_PREDICATE,
            Claim.object_value.is_not(None),
            score >= SIMILARITY_FLOOR,
        )
        .order_by(score.desc())
        .limit(limit)
    )


def _mention_matches(keys: dict[str, str], visible: Select[tuple[str]], limit: int):
    """Match through the mentions currently resolved to each entity.

    Three surfaces, scored so they cannot be confused: a romanized near-match
    scores on its own similarity, while an exact phonetic hit is pinned at a
    deliberately modest 0.5. Metaphone collapses genuinely different names, so
    letting a phonetic hit outrank a real name match would be the search
    telling a confident lie.
    """
    latin_score = func.greatest(
        func.similarity(Mention.latin_key, keys["latin"]),
        func.similarity(Mention.norm_key, keys["norm"]),
    )
    phonetic_hit = (Mention.phonetic_key == keys["phonetic"]) & (keys["phonetic"] != "")
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
            or_(latin_score >= SIMILARITY_FLOOR, phonetic_hit),
        )
        .order_by(score.desc())
        .limit(limit)
    )


__all__ = ["EntityHit", "SIMILARITY_FLOOR", "search_entities"]
