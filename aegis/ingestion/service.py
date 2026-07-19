"""Ingestion adapter (speckit T9, spec 04).

Raw landing: bytes go into the content-addressed vault, a ``source_record``
row points at them, and the provenance envelope travels with both.  The
``ingest_key`` (sha256 of ``source_system | original_filename | content_hash``)
makes re-landing the same artifact a no-op; the same name arriving with
*different* bytes is a version conflict and lands quarantined for a human
(spec 04 §3).

Extraction: the existing prototype passes (``legacy.pipeline.structural_pass`` /
``legacy.pipeline.semantic_pass``) are kept unchanged — their outputs now land as
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
from aegis.actions.service import suggestion_idempotency_key
from aegis.audit import append as append_audit
from aegis.er.ledger import resolve_norm_key
from aegis.er.mentions import extract_mentions
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
    retention_class: str | None = None,
    authority_ref: str | None = None,
    authority_valid_from: datetime | None = None,
    authority_valid_to: datetime | None = None,
    notes: str | None = None,
    handling_code: str = "open",
    source_time: datetime | None = None,
    oversize_bytes: int | None = None,
) -> LandingResult:
    """Raw landing (spec 04 §1 stage 1) in one transaction.

    Returns the (possibly pre-existing) record.  Same name + different bytes
    quarantines the new record as a version conflict; so does an artifact past
    the configured size bound (spec 04 §3).  Quarantine keeps the bytes and
    withholds their *use* — deciding an artifact is too big to exist is not a
    call this layer gets to make.
    """
    if oversize_bytes is None:
        from aegis.config import get_settings

        oversize_bytes = get_settings().ingest_oversize_bytes
    envelope = ProvenanceEnvelope(
        source_system=source_system,
        original_filename=original_filename,
        connector="aegis.ingestion",
        connector_version=_connector_version(),
        operator=operator,
        source_url=source_url,
        collection_policy=collection_policy,
        retention_class=retention_class,
        authority_ref=authority_ref,
        authority_valid_from=authority_valid_from,
        authority_valid_to=authority_valid_to,
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
        # Every failed check is reported, not just the first: an operator who
        # fixes one reason and re-lands should not discover the next one.
        reasons: list[str] = []
        if siblings:
            reasons.append(
                f"version conflict: {len(siblings)} earlier record(s) of "
                f"{original_filename!r} with different content"
            )
        if len(data) > oversize_bytes:
            reasons.append(
                f"oversized: {len(data)} bytes exceeds the {oversize_bytes}-byte bound"
            )
        quarantined = bool(reasons)
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
            quarantine_reason="; ".join(reasons) if reasons else None,
            provenance=envelope.model_dump(mode="json", exclude_none=True),
            collection_policy_ref=collection_policy,
            retention_class=retention_class,
            authority_ref=authority_ref,
            authority_valid_from=authority_valid_from,
            authority_valid_to=authority_valid_to,
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
                "size_bytes": len(data),
                "quarantined": quarantined,
                "quarantine_reasons": reasons,
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
    from legacy.pipeline.structural_pass import extract_structural

    result = extract_structural(text, source_file=record.record_id)
    producer_meta = {"rule": "remand-overlap", "pattern_version": pattern_version}
    return _submit_result(
        session,
        record=record,
        text=text,
        result=result,
        producer="structural_pass",
        producer_version=pattern_version,
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
    from legacy.pipeline.semantic_pass import SYSTEM_PROMPT, extract_semantic, resolve_model_name

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
    prompt_sha256 = sha256(SYSTEM_PROMPT.encode()).hexdigest()
    producer_meta = {
        "model": resolved_model,
        "prompt_sha256": prompt_sha256,
        "chunk_index": chunk_index,
        "raw_response_ref": f"sha256:{stored.content_hash}",
    }
    return _submit_result(
        session,
        record=record,
        text=text,
        result=result,
        producer="semantic_pass",
        # Model *and* prompt: the same model behind a changed prompt is a
        # different producer, and acceptance-rate metrics are computed per
        # (model, prompt hash) (spec 04 §4).
        producer_version=f"{resolved_model}+{prompt_sha256[:12]}",
        producer_meta=producer_meta,
        actor=actor,
        ontology=ontology,
    )


def _suggestion_exists(session: Session, idempotency_key: str) -> bool:
    """Replay safety (spec 04 §5): an identical draft is submitted only once.

    The key is also UNIQUE in the database, so this pre-check is an ergonomic
    skip rather than the guarantee — a race loses on the constraint, not on a
    duplicate row.
    """
    return (
        session.scalar(
            select(ReviewQueue.suggestion_id)
            .where(ReviewQueue.idempotency_key == idempotency_key)
            .limit(1)
        )
        is not None
    )


def _submit_result(
    session: Session,
    *,
    record: SourceRecord,
    text: str,
    result: Any,  # legacy.pipeline.models.ExtractionResult
    producer: str,
    producer_version: str,
    producer_meta: dict[str, Any],
    actor: str,
    ontology: Ontology | None = None,
) -> list[ReviewQueue]:
    service = ActionService(session, ontology)
    ontology = service.ontology
    context = ActionContext(actor=actor, purpose="extraction pass")
    submitted: list[ReviewQueue] = []

    def _submit(payload: dict[str, Any], meta_extra: dict[str, Any]) -> None:
        key = suggestion_idempotency_key(
            kind="claim_draft",
            producer=producer,
            producer_version=producer_version,
            payload=payload,
        )
        if _suggestion_exists(session, key):
            return
        submitted.append(
            service.submit_suggestion(
                context,
                payload=payload,
                suggestion_kind="claim_draft",
                producer=producer,
                producer_version=producer_version,
                producer_meta={**producer_meta, **meta_extra},
                record_id=record.record_id,
                idempotency_key=key,
            )
        )

    # Mentions are persisted here, before any adjudication: a mention records
    # what the text says, so it is evidence, not canon (aegis.er.mentions).
    # ER needs them to exist before anything is accepted — that is the whole
    # point of proposing merges over extracted names.
    extraction = extract_mentions(
        session,
        record=record,
        text=text,
        names={node.node_id: node.name for node in result.nodes},
    )
    mention_by_key = extraction.by_ref

    # A previously unseen name is not a separate entity draft — there is no
    # `entity_draft` kind (ADR-031 §1).  It rides in the claim draft as its
    # mention anchor, and acceptance creates the entity from that mention
    # inside record_claim (spec 02 §3.2).  A node appearing in no edge
    # therefore proposes no claim, which is correct: an entity with no claim
    # about it is not knowledge.
    resolved: dict[str, str | None] = {
        node.node_id: resolve_norm_key(session, node.node_id) for node in result.nodes
    }
    # The pass labelled each node; that label becomes the *proposed* type for
    # an entity created on acceptance.  The reviewer can edit it, and a
    # predicate that allows only one type ignores it anyway.
    node_types: dict[str, str] = {
        node.node_id: node.node_type.value.lower() for node in result.nodes
    }

    for edge in result.edges:
        relation = edge.relation
        predicate = STRUCTURAL_PREDICATES.get(relation, relation)
        if predicate not in ontology.predicates:
            predicate = None  # reviewer must choose; raw verb kept in meta
        credibility, verification = CONFIDENCE_TAG_GRADING[edge.confidence.value]
        subject_id = resolved.get(edge.source) or resolve_norm_key(session, edge.source)
        object_id = resolved.get(edge.target) or resolve_norm_key(session, edge.target)
        subject_mention = mention_by_key.get(edge.source)
        object_mention = mention_by_key.get(edge.target)
        needs_entity = [
            ref for ref, entity in ((edge.source, subject_id), (edge.target, object_id))
            if entity is None
        ]
        payload = {
            "subject_id": subject_id,
            "predicate": predicate,
            "object_id": object_id,
            # The anchor is what makes an unresolved argument acceptable: on
            # acceptance record_claim creates the entity from this mention
            # (spec 02 §3.2).  An argument with neither an entity nor an
            # anchor is one the reviewer must resolve by hand.
            "subject_mention_id": subject_mention.mention_id if subject_mention else None,
            "object_mention_id": object_mention.mention_id if object_mention else None,
            "subject_entity_type": node_types.get(edge.source),
            "object_entity_type": node_types.get(edge.target),
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
                "raw_relation": relation,
                "subject_ref": edge.source,
                "object_ref": edge.target,
                # unmatched references are flagged, never dropped (Article VIII)
                "needs_entity": needs_entity,
                # names the pass reported but that are absent from the text it
                # read — the reviewer sees them; ER never blocks on them
                "unverified_names": extraction.unverified,
            },
        )

    return submitted


def _connector_version() -> str:
    try:
        from importlib.metadata import version

        return version("aegis")
    except Exception:  # pragma: no cover
        return "unknown"
