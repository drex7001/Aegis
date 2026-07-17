"""Ingestion adapter (speckit T9, spec 04).

Raw landing: bytes go into the content-addressed vault, a ``source_record``
row points at them, and the provenance envelope travels with both.  The
``ingest_key`` (sha256 of ``source_system | original_filename | content_hash``)
makes re-landing the same artifact a no-op; the same name arriving with
*different* bytes is a version conflict and lands quarantined for a human
(spec 04 §3).

Extraction: the existing prototype passes (``pipeline.structural_pass`` /
``pipeline.semantic_pass``) are kept unchanged — their outputs now land as
``review_queue`` suggestions, never as claims (Article VII).  Suggestion
payloads are claim drafts in ``record_claim`` field vocabulary; anything the
pass could not resolve (unknown verbs, unmatched entity references) is carried
in ``producer_meta`` so the reviewer resolves it instead of the pipeline
silently dropping it (Article VIII).

Deterministic passes are *eligible* for auto-accept by config per spec 04 §4;
that switch defaults to off and is not implemented in Phase 1 — every
suggestion here waits for ``review_suggestion``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import mimetypes
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, new_id
from aegis.audit import append as append_audit
from aegis.evidence import EvidenceVault, ProvenanceEnvelope
# The extraction passes still grade with the legacy tag rubric; its one
# authoritative mapping lives in the migration adapter (ADR-016).
from aegis.migration.legacy import CONFIDENCE_TAG_GRADING, LEGACY_SCHEME
from aegis.ontology import Ontology
from aegis.store import Entity, IdentityMembership, Mention, ReviewQueue, Source, SourceRecord

DEFAULT_SOURCE_SYSTEM = "manual-upload"
MANUAL_SOURCE_ID = "src_manual_upload"

# Adapter-owned vocabulary: pass-emitted relations that correspond directly to
# an ontology predicate under a different name.
STRUCTURAL_PREDICATES = {"co_located_with": "co_located_in_prison_with"}

COLLECTION_METHODS = {"STRUCTURAL": "structural", "SEMANTIC": "semantic_llm", "CURATED": "curated"}


class IngestionError(RuntimeError):
    """A landing or extraction request that cannot proceed."""


def make_ingest_key(source_system: str, original_filename: str, content_hash: str) -> str:
    return sha256(f"{source_system}|{original_filename}|{content_hash}".encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class LandingResult:
    record: SourceRecord
    created: bool
    quarantined: bool


def ensure_manual_source(session: Session) -> Source:
    """The default source row for operator-initiated uploads."""
    source = session.get(Source, MANUAL_SOURCE_ID)
    if source is None:
        source = Source(
            source_id=MANUAL_SOURCE_ID,
            source_type="investigator",
            name="Manual upload",
            notes="Default source for aegis ingest (spec 04 §6)",
        )
        session.add(source)
        session.flush()
    return source


def land_bytes(
    session: Session,
    vault: EvidenceVault,
    *,
    data: bytes,
    original_filename: str,
    operator: str,
    source_id: str | None = None,
    source_system: str = DEFAULT_SOURCE_SYSTEM,
    media_type: str | None = None,
    source_url: str | None = None,
    collection_policy: str | None = None,
    notes: str | None = None,
    handling_code: str = "open",
    source_time: datetime | None = None,
) -> LandingResult:
    """Raw landing (spec 04 §1 stage 1) in one transaction.

    Returns the (possibly pre-existing) record.  Same name + different bytes
    quarantines the new record as a version conflict.
    """
    envelope = ProvenanceEnvelope(
        source_system=source_system,
        original_filename=original_filename,
        connector="aegis.ingestion",
        connector_version=_connector_version(),
        operator=operator,
        source_url=source_url,
        collection_policy=collection_policy,
        notes=notes,
    )
    stored = vault.put(data, envelope, media_type=media_type)
    ingest_key = make_ingest_key(source_system, original_filename, stored.content_hash)

    def _run() -> LandingResult:
        existing = session.scalar(
            select(SourceRecord).where(SourceRecord.ingest_key == ingest_key)
        )
        if existing is not None:
            return LandingResult(existing, created=False, quarantined=existing.status == "quarantined")

        if source_id is None:
            source = ensure_manual_source(session)
        else:
            source = session.get(Source, source_id)
            if source is None:
                raise IngestionError(f"source {source_id!r} does not exist")

        siblings = session.scalars(
            select(SourceRecord).where(
                SourceRecord.provenance["source_system"].astext == source_system,
                SourceRecord.provenance["original_filename"].astext == original_filename,
                SourceRecord.content_hash != stored.content_hash,
            )
        ).all()
        quarantined = bool(siblings)
        record = SourceRecord(
            record_id=new_id("rec"),
            source_id=source.source_id,
            ingest_key=ingest_key,
            content_hash=stored.content_hash,
            storage_uri=stored.storage_uri,
            media_type=media_type,
            source_time=source_time,
            handling_code=handling_code,
            status="quarantined" if quarantined else "landed",
            quarantine_reason=(
                f"version conflict: {len(siblings)} earlier record(s) of "
                f"{original_filename!r} with different content"
                if quarantined
                else None
            ),
            provenance=envelope.model_dump(mode="json", exclude_none=True),
        )
        session.add(record)
        session.flush()
        append_audit(
            session,
            actor=operator,
            session_id=None,
            purpose="ingestion",
            case_id=None,
            action="ingest.land",
            resource_type="source_record",
            resource_id=record.record_id,
            decision="allow",
            detail={
                "ingest_key": ingest_key,
                "content_hash": stored.content_hash,
                "quarantined": quarantined,
            },
        )
        return LandingResult(record, created=True, quarantined=quarantined)

    if session.in_transaction():
        return _run()
    with session.begin():
        return _run()


def land_file(
    session: Session,
    vault: EvidenceVault,
    *,
    path: Path,
    operator: str,
    source_id: str | None = None,
    **kwargs: Any,
) -> LandingResult:
    media_type = kwargs.pop("media_type", None) or mimetypes.guess_type(path.name)[0]
    return land_bytes(
        session,
        vault,
        data=path.read_bytes(),
        original_filename=path.name,
        operator=operator,
        source_id=source_id,
        media_type=media_type,
        **kwargs,
    )


# ── extraction → review queue ────────────────────────────────────────────────


def run_structural_pass(
    session: Session,
    *,
    record: SourceRecord,
    text: str,
    actor: str,
    ontology: Ontology | None = None,
    pattern_version: str = "v1",
) -> list[ReviewQueue]:
    """Deterministic pass (spec 04 §4): remand-list parse + co-location edges."""
    from pipeline.structural_pass import extract_structural

    result = extract_structural(text, source_file=record.record_id)
    producer_meta = {"rule": "remand-overlap", "pattern_version": pattern_version}
    return _submit_result(
        session,
        record=record,
        result=result,
        producer="structural_pass",
        producer_meta=producer_meta,
        actor=actor,
        ontology=ontology,
    )


def run_semantic_pass(
    session: Session,
    vault: EvidenceVault,
    *,
    record: SourceRecord,
    text: str,
    actor: str,
    ontology: Ontology | None = None,
    model_name: str | None = None,
    mock: bool = False,
    chunk_index: int = 0,
) -> list[ReviewQueue]:
    """LLM pass (Article VII strictly): output lands as suggestions only.

    The pass's parsed output is itself vaulted so every suggestion carries a
    resolvable ``raw_response_ref`` (spec 04 §4 debuggability).
    """
    from pipeline.semantic_pass import SYSTEM_PROMPT, extract_semantic, resolve_model_name

    result = extract_semantic(text, source_file=record.record_id, model_name=model_name, mock=mock)
    resolved_model = "mock" if mock else resolve_model_name(model_name)
    response_bytes = json.dumps(result.to_graph_json(), sort_keys=True).encode()
    stored = vault.put(
        response_bytes,
        ProvenanceEnvelope(
            source_system="semantic-pass",
            original_filename=f"{record.record_id}.extraction.json",
            connector="aegis.ingestion.semantic",
            connector_version=_connector_version(),
            operator=actor,
            notes=f"parsed structured output of {resolved_model}",
        ),
        media_type="application/json",
    )
    producer_meta = {
        "model": resolved_model,
        "prompt_sha256": sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "chunk_index": chunk_index,
        "raw_response_ref": f"sha256:{stored.content_hash}",
    }
    return _submit_result(
        session,
        record=record,
        result=result,
        producer="semantic_pass",
        producer_meta=producer_meta,
        actor=actor,
        ontology=ontology,
    )


def _resolve_entity(session: Session, norm_key: str) -> str | None:
    """Current entity for a mention key, if adjudicated identity exists."""
    return session.scalar(
        select(IdentityMembership.entity_id)
        .join(Mention, Mention.mention_id == IdentityMembership.mention_id)
        .where(Mention.norm_key == norm_key, IdentityMembership.valid_to.is_(None))
        .limit(1)
    )


def _suggestion_exists(session: Session, producer: str, payload: dict[str, Any]) -> bool:
    """Replay safety (spec 04 §5): an identical draft is submitted only once."""
    return (
        session.scalar(
            select(ReviewQueue.suggestion_id)
            .where(ReviewQueue.producer == producer, ReviewQueue.payload == payload)
            .limit(1)
        )
        is not None
    )


def _submit_result(
    session: Session,
    *,
    record: SourceRecord,
    result: Any,  # pipeline.models.ExtractionResult
    producer: str,
    producer_meta: dict[str, Any],
    actor: str,
    ontology: Ontology | None = None,
) -> list[ReviewQueue]:
    service = ActionService(session, ontology)
    ontology = service.ontology
    context = ActionContext(actor=actor, purpose="extraction pass")
    submitted: list[ReviewQueue] = []

    def _submit(payload: dict[str, Any], meta_extra: dict[str, Any]) -> None:
        if _suggestion_exists(session, producer, payload):
            return
        submitted.append(
            service.submit_suggestion(
                context,
                payload=payload,
                producer=producer,
                producer_meta={**producer_meta, **meta_extra},
            )
        )

    resolved: dict[str, str | None] = {}
    for node in result.nodes:
        resolved[node.node_id] = _resolve_entity(session, node.node_id)

    for node in result.nodes:
        if resolved[node.node_id] is not None:
            continue  # already an adjudicated entity — nothing to propose
        _submit(
            {
                "entity_type": node.node_type.value.lower(),
                "label": node.name,
                "aliases": node.aliases,
                "affiliations": node.affiliations,
                "record_id": record.record_id,
                "excerpt": node.source_excerpt,
            },
            {"draft_kind": "entity", "norm_key": node.node_id},
        )

    for edge in result.edges:
        relation = edge.relation
        predicate = STRUCTURAL_PREDICATES.get(relation, relation)
        if predicate not in ontology.predicates:
            predicate = None  # reviewer must choose; raw verb kept in meta
        credibility, verification = CONFIDENCE_TAG_GRADING[edge.confidence.value]
        subject_id = resolved.get(edge.source) or _resolve_entity(session, edge.source)
        object_id = resolved.get(edge.target) or _resolve_entity(session, edge.target)
        needs_entity = [
            ref for ref, entity in ((edge.source, subject_id), (edge.target, object_id))
            if entity is None
        ]
        payload = {
            "subject_id": subject_id,
            "predicate": predicate,
            "object_id": object_id,
            "record_id": record.record_id,
            "assertion_type": "reported",
            "collection_method": COLLECTION_METHODS[edge.extraction_method.value],
            "credibility_scheme": LEGACY_SCHEME,
            "credibility_original": edge.confidence.value,
            "credibility_normalized": credibility,
            "verification_status": verification,
            "valid_from": edge.start_date.isoformat() if edge.start_date else None,
            "valid_to": edge.end_date.isoformat() if edge.end_date else None,
            "location_text": edge.location,
            "excerpt": edge.source_excerpt,
        }
        _submit(
            payload,
            {
                "draft_kind": "claim",
                "raw_relation": relation,
                "subject_ref": edge.source,
                "object_ref": edge.target,
                # unmatched references are flagged, never dropped (Article VIII)
                "needs_entity": needs_entity,
            },
        )

    return submitted


def _connector_version() -> str:
    try:
        from importlib.metadata import version

        return version("aegis")
    except Exception:  # pragma: no cover
        return "unknown"
