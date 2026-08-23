"""One search, three backends, one ranked page (spec 11 §1, §5, ADR-050).

The design decision worth stating is the one that is easy to get wrong:
**groups are how a page is displayed, never how it is fetched.**

The obvious implementation gives each group its own limit and its own cursor.
It is also the implementation B-17 warns about: a caller advancing several
cursors independently sees gaps where a restricted row would have been, and the
gaps are informative. One total ordering over one keyset cursor has no gaps to
leave, because a row the filters excluded was never in the sequence.

So every backend is asked for the same over-fetch, the results are merged into
one order, the page is cut, and only then is the page split into groups. An
empty group is **omitted** rather than returned empty — a present group with no
hits is a count of zero, and §4.2 refuses to give counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from aegis.api.auth import UserContext
from aegis.ontology import Ontology
from aegis.search.claims import search_claims
from aegis.search.documents import search_documents
from aegis.search.entities import MAX_QUERY, search_entities
from aegis.search.pipeline import search_keys
from aegis.search.results import CLAIM_GROUP, DOCUMENT_GROUP, SearchHit, order_key

#: A response is a page, not a corpus dump (spec 11 §5.3).
#:
#: There is deliberately **no cap on the number of groups**. The first draft had
#: one, and it was a silent-data-loss bug: groups were truncated *after* the
#: page was cut and after `has_more` was computed, so a page spanning more
#: groups than the cap dropped hits that the cursor had already accounted for —
#: the reader would never see them, on this page or the next. The page limit is
#: the only bound that is needed, because a page of N hits cannot produce more
#: than N groups.
MAX_LIMIT = 50


@dataclass(frozen=True, slots=True)
class SearchGroup:
    """One display group. Carries no total — see §4.2."""

    group: str
    label: str
    hits: list[SearchHit]


def available_groups(ontology: Ontology) -> list[str]:
    """Every group name, enumerated from the ontology (Article XIV).

    The two non-object groups are code-owned because they are **platform**
    concepts: every deployment has claims and documents, no deployment declares
    them as domain types. Everything else comes from the composed registry, so
    a new domain module's object types are searchable and grouped the day they
    are declared, with no change here.
    """
    return [*sorted(ontology.object_types), CLAIM_GROUP, DOCUMENT_GROUP]


def group_label(ontology: Ontology, group: str) -> str:
    if group == CLAIM_GROUP:
        return "Claims"
    if group == DOCUMENT_GROUP:
        return "Documents"
    object_type = ontology.object_types.get(group)
    return object_type.label if object_type is not None else group


def _requested(ontology: Ontology, types: list[str] | None) -> set[str] | None:
    """`None` means every group; otherwise the requested subset, validated."""
    if not types:
        return None
    known = set(available_groups(ontology))
    return {name for name in types if name in known}


def search(
    session: Session,
    *,
    query: str,
    user: UserContext,
    ontology: Ontology,
    types: list[str] | None = None,
    limit: int = 20,
    as_of: datetime | None = None,
    after: tuple[float, str, str] | None = None,
) -> tuple[list[SearchHit], bool]:
    """One ranked page across every requested group, plus "is there more".

    Returns hits rather than groups so the caller owns pagination: the extra
    row that answers "is there more" must be cut *before* grouping, or a group
    would appear on this page carrying a hit that belongs on the next one.
    """
    text = query.strip()[:MAX_QUERY]
    if not text:
        return [], False

    keys = search_keys(text)
    wanted = _requested(ontology, types)
    over_fetch = min(limit, MAX_LIMIT) + 1

    hits: list[SearchHit] = []
    object_types = set(ontology.object_types)
    if wanted is None or wanted & object_types:
        hits += search_entities(
            session,
            keys=keys,
            user=user,
            ontology=ontology,
            limit=over_fetch,
            as_of=as_of,
            after=after,
        )
    if wanted is None or CLAIM_GROUP in wanted:
        hits += search_claims(
            session,
            keys=keys,
            user=user,
            ontology=ontology,
            limit=over_fetch,
            as_of=as_of,
            after=after,
        )
    if wanted is None or DOCUMENT_GROUP in wanted:
        hits += search_documents(
            session,
            keys=keys,
            user=user,
            ontology=ontology,
            limit=over_fetch,
            as_of=as_of,
            after=after,
        )

    if wanted is not None:
        # The entity backend does not know about groups, so a request for one
        # object type is narrowed here rather than pushed down. Filtering after
        # generation is safe *for this predicate only*: the group name is not
        # authorization, and every hit present already passed the caller's
        # filters inside its own candidate query.
        hits = [hit for hit in hits if hit.group in wanted]

    hits.sort(key=order_key)
    page = hits[: min(limit, MAX_LIMIT)]
    return page, len(hits) > len(page)


def into_groups(ontology: Ontology, hits: list[SearchHit]) -> list[SearchGroup]:
    """Split a page into display groups, ordered by their best hit.

    Ordered by strength rather than alphabetically: the group holding the top
    result is the one the reader wants first, and an alphabetical order would
    bury it under whatever type name sorts earliest.
    """
    ordered: dict[str, list[SearchHit]] = {}
    for hit in hits:
        ordered.setdefault(hit.group, []).append(hit)
    # Sorted explicitly rather than trusting the caller to have ranked the page
    # first. Relying on insertion order made the docstring above a description
    # of what `search()` happens to do, not of what this function guarantees —
    # and a function whose contract holds only for one caller has no contract.
    return [
        SearchGroup(group=name, label=group_label(ontology, name), hits=group_hits)
        for name, group_hits in sorted(
            ordered.items(), key=lambda item: -max(hit.score for hit in item[1])
        )
    ]


__all__ = [
    "MAX_LIMIT",
    "SearchGroup",
    "available_groups",
    "group_label",
    "into_groups",
    "search",
]
