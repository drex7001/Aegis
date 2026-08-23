"""Document-text search over the projection (spec 11 §2.3, ADR-051).

Full text, not trigram. A document is long and a query is short, so similarity
over the whole body is meaningless — `similarity('...40kB of judgment...',
'perera')` is near zero for a document that mentions Perera on every page.

The `simple` text-search configuration is deliberate and is the honest choice
rather than the sophisticated one: PostgreSQL ships no Sinhala or Tamil
dictionary, and applying `english` to Sinhala would stem it into nonsense while
looking like it worked. `simple` tokenizes and lowercases, which is exactly what
this corpus can support and no more.

**Authorization is one column comparison**, because the projection copies the
record's handling code (ADR-051). That is the whole reason the projection
exists rather than a join to `source_record` at query time: a filter that had to
join back would be one forgotten join away from a leak.

There is no case filter, because `source_record` has no case scope — records
live in the general pool and are handling-filtered (spec 06 §2.3). See the model
for why inventing one would either over-restrict or leak.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ColumnElement, and_, func, literal_column, or_, select
from sqlalchemy.orm import Session

from aegis.api.auth import UserContext
from aegis.ontology import Ontology
from aegis.search.pipeline import NORMALIZATION_VERSION, SearchKeys
from aegis.search.results import DOCUMENT_GROUP, SearchHit
from aegis.store import DocumentTextProjection, SourceRecord

#: `ts_rank_cd` normalization flag 32: "divide the rank by itself + 1", which
#: maps an unbounded rank onto [0, 1). Chosen because every other backend
#: reports a 0–1 score and a shared scale that one backend silently leaves is
#: not a shared scale. Documented in PostgreSQL's ranking section.
_RANK_NORMALIZATION = 32

#: Below this a full-text hit is a stray token, not a document about the query.
#: Deliberately low: `ts_rank_cd/(rank+1)` compresses hard, so 0.05 here is not
#: the same kind of number as the trigram floor and is not comparable to it.
RANK_FLOOR = 0.02

#: The text-search configuration, cast to `regconfig` where it is used.
_SIMPLE = literal_column("'simple'::regconfig")


def _after(score, label, doc_id, after: tuple[float, str, str] | None):
    if after is None:
        return []
    last_score, last_label, last_id = after
    return [
        or_(
            score < last_score,
            and_(score == last_score, label > last_label),
            and_(score == last_score, label == last_label, doc_id > last_id),
        )
    ]


def document_filters(
    user: UserContext, ontology: Ontology, *, as_of: datetime | None = None
) -> list[ColumnElement[bool]]:
    """The always-on conditions for reading an indexed document.

    Deliberately a named function rather than an inline `where`: the structural
    contract test looks for every candidate-generating query to compose a
    filter builder, and an inline comparison would pass review and fail the
    point of the review.
    """
    conditions: list[ColumnElement[bool]] = [
        DocumentTextProjection.handling_rank <= user.clearance,
        # A row built by an older pipeline cannot be compared against a query
        # normalized by the current one (ADR-052). Excluding it is the honest
        # behaviour: `aegis search check-index` is what turns the exclusion
        # into a visible failure rather than quiet under-retrieval.
        DocumentTextProjection.normalization_version == NORMALIZATION_VERSION,
    ]
    if as_of is not None:
        conditions.append(SourceRecord.received_at <= as_of)
    return conditions


def search_documents(
    session: Session,
    *,
    keys: SearchKeys,
    user: UserContext,
    ontology: Ontology,
    limit: int,
    as_of: datetime | None = None,
    after: tuple[float, str, str] | None = None,
) -> list[SearchHit]:
    text = keys.text.strip()
    if not text:
        return []

    # `'simple'::regconfig`, not a bound string: `plainto_tsquery` takes a
    # `regconfig`, and a parameter arrives as `varchar` — which Postgres will
    # not resolve, and which fails at execution rather than at import.
    query = func.plainto_tsquery(_SIMPLE, text)
    score = func.ts_rank_cd(
        DocumentTextProjection.tsv, query, literal_column(str(_RANK_NORMALIZATION))
    )
    label = SourceRecord.record_id

    statement = (
        select(
            DocumentTextProjection.projection_id,
            DocumentTextProjection.record_id,
            score.label("score"),
        )
        .join(
            SourceRecord,
            SourceRecord.record_id == DocumentTextProjection.record_id,
        )
        .where(
            DocumentTextProjection.tsv.op("@@")(query),
            score >= RANK_FLOOR,
            *document_filters(user, ontology, as_of=as_of),
            *_after(score, label, DocumentTextProjection.projection_id, after),
        )
        .order_by(score.desc(), label, DocumentTextProjection.projection_id)
        .limit(limit)
    )

    return [
        SearchHit(
            kind="document",
            id=row.projection_id,
            group=DOCUMENT_GROUP,
            label=row.record_id,
            detail=row.record_id,
            parent_id=row.record_id,
            score=float(row.score),
            matched="text",
        )
        for row in session.execute(statement)
    ]


__all__ = ["RANK_FLOOR", "document_filters", "search_documents"]
