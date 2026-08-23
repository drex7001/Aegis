"""Rebuild the searchable-document projection from the vault (T67, ADR-051).

The rule that shapes this module: **a projection builder must not create
canonical rows.** Extraction produces a `derivative`, and a derivative is a
provenance record — tool, version, parameters, operator, output hash. If the
search index could mint one, then rebuilding a cache would write history, and
Article XIII's "truncate and rebuild reproduces it exactly" would stop being
true the moment the tool version changed.

So this indexes what extraction has **already** produced and nothing else:

* a record whose media type is `text/*` — the bytes are the text, and
  `ensure_text` records no derivative for that case either;
* a record with an existing `text` derivative.

A PDF nobody has extracted is absent from document search, and the honest fix
is to extract it (`POST /v1/source-records/{id}/extract`), not to make the
indexer do it quietly.

Quarantined records are skipped. A quarantined record is one the pipeline
refused; surfacing its contents through search would route around the refusal.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from aegis.evidence import EvidenceVault
from aegis.logging import get_logger
from aegis.ontology import Ontology
from aegis.search.pipeline import NORMALIZATION_VERSION
from aegis.store import Derivative, DocumentTextProjection, SourceRecord

logger = get_logger(__name__)

def _projection_id(record_id: str, derivative_id: str | None) -> str:
    """A deterministic id, so truncate-and-rebuild reproduces the table exactly.

    `new_id()` would be wrong here and the reason is Article XIII, not taste:
    the phase-gate check for a projection is that rebuilding it yields the same
    rows, and a random primary key makes every rebuild a different table that
    merely happens to say the same thing. Deriving the id from the pair the
    unique constraint already enforces costs nothing and makes the equality
    checkable.
    """
    return "dtp_" + sha256(f"{record_id}|{derivative_id or ''}".encode()).hexdigest()[:26]


#: Bump when the *shape* of a row changes. Distinct from
#: `NORMALIZATION_VERSION`, which is about how text becomes keys: one is "how
#: this table is built", the other is "how matching works", and conflating them
#: would make either change look like the other.
BUILDER_VERSION = "document-text-v1"


@dataclass(frozen=True, slots=True)
class DocumentProjectionReport:
    indexed: int = 0
    skipped_quarantined: int = 0
    skipped_no_text: int = 0
    skipped_unreadable: int = 0


def _text_for(
    session: Session, vault: EvidenceVault, record: SourceRecord
) -> tuple[str, str | None] | None:
    """`(text, derivative_id)` for an already-extracted record, or None.

    Never extracts. See the module docstring for why that is a rule rather
    than an optimization.
    """
    # Imported here, not at module scope: `aegis.ingestion` imports
    # `aegis.projections` for the MVP fixture, so a top-level import the other
    # way is a cycle. Deferring it keeps the dependency one-directional at
    # import time and honest at call time.
    from aegis.ingestion.derivatives import (
        TEXT_ENCODING,
        TEXT_KIND,
        resolve_media_type,
    )

    media_type = resolve_media_type(record)
    if media_type and media_type.startswith("text/"):
        return vault.get(record.content_hash).decode(TEXT_ENCODING, errors="replace"), None

    derivative = session.scalars(
        select(Derivative)
        .where(
            Derivative.parent_record == record.record_id,
            Derivative.kind == TEXT_KIND,
        )
        .order_by(Derivative.created_at.desc(), Derivative.derivative_id.desc())
        .limit(1)
    ).first()
    if derivative is None:
        return None
    return (
        vault.get(derivative.content_hash).decode(TEXT_ENCODING, errors="replace"),
        derivative.derivative_id,
    )


def rebuild_document_text_projection(
    session: Session, *, vault: EvidenceVault, ontology: Ontology
) -> DocumentProjectionReport:
    """Truncate and rebuild. Nothing else writes to this table."""
    session.execute(delete(DocumentTextProjection))

    from aegis.ingestion.derivatives import TEXT_ENCODING

    indexed = quarantined = no_text = unreadable = 0

    for record in session.scalars(select(SourceRecord).order_by(SourceRecord.record_id)):
        if record.status == "quarantined":
            quarantined += 1
            continue
        try:
            found = _text_for(session, vault, record)
        except Exception:
            # A vault object that cannot be read is a real operational problem,
            # but it is not a reason to abandon the whole rebuild: the honest
            # outcome is an index missing one document and a report that says
            # so, rather than no index at all.
            logger.exception("document_projection_unreadable", record_id=record.record_id)
            unreadable += 1
            continue
        if found is None:
            no_text += 1
            continue

        text, derivative_id = found
        session.add(
            DocumentTextProjection(
                projection_id=_projection_id(record.record_id, derivative_id),
                record_id=record.record_id,
                derivative_id=derivative_id,
                content_hash=sha256(text.encode(TEXT_ENCODING)).hexdigest(),
                text_body=text,
                handling_code=record.handling_code,
                handling_rank=ontology.handling_rank(record.handling_code),
                normalization_version=NORMALIZATION_VERSION,
                builder_version=BUILDER_VERSION,
            )
        )
        indexed += 1

    session.flush()
    return DocumentProjectionReport(
        indexed=indexed,
        skipped_quarantined=quarantined,
        skipped_no_text=no_text,
        skipped_unreadable=unreadable,
    )


__all__ = [
    "BUILDER_VERSION",
    "DocumentProjectionReport",
    "rebuild_document_text_projection",
]
