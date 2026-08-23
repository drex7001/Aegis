"""One hit shape and one ordering, shared by every search backend (spec 11 §5).

Three backends produce hits — entities, claims, documents — and they must land
in **one** ranked sequence, not three. That is not a presentation preference:
per-group pagination would mean per-group cursors, and a caller advancing three
cursors independently is exactly the pagination-gap surface B-17 names. One
total order over one keyset cursor has no gaps to leave.

Groups are therefore how a page is *displayed*, never how it is *fetched*.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The non-object groups. Every other group name is an ontology object type, so
#: the group list follows the ontology and never a literal in this file
#: (Article XIV).
CLAIM_GROUP = "claim"
DOCUMENT_GROUP = "document"

#: How a hit was found, reported on every hit because these are not equally
#: strong evidence. `phonetic` is a lead; `label` is a name match; `identifier`
#: is an exact equality and nothing else (ADR-053). A result list that renders
#: them alike invites the reader to treat them alike.
MATCHED_KINDS = frozenset(
    {"label", "alias", "mention", "transliterated", "phonetic", "identifier", "excerpt", "value", "text"}
)


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One result, from any backend, on one 0–1 scale."""

    #: `entity`, `claim` or `document` — what the id refers to.
    kind: str
    #: The id a caller follows to read the thing itself.
    id: str
    #: The display group: an ontology object type, `claim`, or `document`.
    group: str
    label: str
    #: Secondary line: a claim's predicate, a document's record id. Never the
    #: matched text itself — see `aegis/search/claims.py` on why a snippet
    #: without its grading is the thing Article III exists to prevent.
    detail: str | None
    #: The id of the thing that *contains* this hit, when following the hit's
    #: own id would land nowhere a reader can go: a claim's subject entity, a
    #: document's source record. `None` for an entity, which is already the
    #: destination.
    #:
    #: It carries no authorization of its own. Every hit here already passed
    #: the caller's filters inside its candidate query, and a claim the caller
    #: may read is a claim whose subject they may reach.
    parent_id: str | None
    score: float
    matched: str


def order_key(hit: SearchHit) -> tuple[float, str, str]:
    """`(-score, label, id)` — total, stable, and the cursor's contents.

    Negated score so a plain ascending sort puts the best hit first, and the
    tiebreakers are total: two hits can share a score and a label, but not an
    id, so the order is deterministic under concurrent inserts.
    """
    return (-hit.score, hit.label, hit.id)


__all__ = [
    "CLAIM_GROUP",
    "DOCUMENT_GROUP",
    "MATCHED_KINDS",
    "SearchHit",
    "order_key",
]
