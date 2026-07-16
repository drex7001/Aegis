"""SQLAlchemy mappings for the Phase 1 canonical claim store.

Ontology-owned values deliberately remain plain ``TEXT``.  They are validated by
the actions layer against :mod:`aegis.ontology`, not by database constraints
(ADR-013).  The checks here cover only stable, code-owned structural invariants.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegis.store.engine import Base


class Source(Base):
    __tablename__ = "source"

    source_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    reliability_scheme: Mapped[str | None] = mapped_column(Text)
    reliability_original: Mapped[str | None] = mapped_column(Text)
    reliability_normalized: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class SourceRecord(Base):
    __tablename__ = "source_record"
    __table_args__ = (
        CheckConstraint(
            "status IN ('landed', 'quarantined', 'processed')",
            name="ck_source_record_status",
        ),
        Index("ix_source_record_content_hash", "content_hash"),
    )

    record_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("source.source_id"), nullable=False)
    ingest_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str | None] = mapped_column(Text)
    source_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    handling_code: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'open'")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'landed'")
    )
    quarantine_reason: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class Entity(Base):
    __tablename__ = "entity"
    __table_args__ = (
        Index(
            "ix_entity_label_trgm",
            "label",
            postgresql_using="gin",
            postgresql_ops={"label": "gin_trgm_ops"},
        ),
    )

    entity_id: Mapped[str] = mapped_column(Text, primary_key=True)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class CaseFile(Base):
    __tablename__ = "case_file"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'closed', 'sealed')", name="ck_case_file_status"
        ),
    )

    case_id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'open'")
    )
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    handling_code: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'open'")
    )
    opened_by: Mapped[str] = mapped_column(Text, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Claim(Base):
    __tablename__ = "claim"
    __table_args__ = (
        CheckConstraint(
            "(object_id IS NULL) <> (object_value IS NULL)",
            name="ck_claim_object_exactly_one",
        ),
        CheckConstraint("subject_id <> object_id", name="ck_claim_no_self_reference"),
        CheckConstraint(
            "event_time_latest IS NULL OR event_time_earliest IS NULL "
            "OR event_time_latest >= event_time_earliest",
            name="ck_claim_event_time_order",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_claim_valid_date_order",
        ),
        Index("ix_claim_subject_id", "subject_id"),
        Index("ix_claim_object_id", "object_id"),
        Index("ix_claim_predicate", "predicate"),
        Index("ix_claim_record_id", "record_id"),
        Index(
            "ix_claim_active_edges",
            "subject_id",
            "object_id",
            "predicate",
            postgresql_where=text("retracted_at IS NULL"),
        ),
    )

    claim_id: Mapped[str] = mapped_column(Text, primary_key=True)
    subject_id: Mapped[str] = mapped_column(ForeignKey("entity.entity_id"), nullable=False)
    predicate: Mapped[str] = mapped_column(Text, nullable=False)
    object_id: Mapped[str | None] = mapped_column(ForeignKey("entity.entity_id"))
    # ``none_as_null`` is essential to the object XOR invariant: Python ``None``
    # means SQL NULL here, not the distinct JSON scalar ``null``.
    object_value: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True))
    assertion_type: Mapped[str] = mapped_column(Text, nullable=False)
    record_id: Mapped[str] = mapped_column(
        ForeignKey("source_record.record_id"), nullable=False
    )
    excerpt: Mapped[str | None] = mapped_column(Text)
    collection_method: Mapped[str | None] = mapped_column(Text)
    credibility_scheme: Mapped[str | None] = mapped_column(Text)
    credibility_original: Mapped[str | None] = mapped_column(Text)
    credibility_normalized: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'cannot_judge'")
    )
    verification_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'unverified'")
    )
    analytic_confidence: Mapped[str | None] = mapped_column(Text)
    event_time_earliest: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_time_latest: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    retracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retraction_reason: Mapped[str | None] = mapped_column(Text)
    handling_code: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'open'")
    )
    case_id: Mapped[str | None] = mapped_column(ForeignKey("case_file.case_id"))
    jurisdiction: Mapped[str | None] = mapped_column(Text)
    location_text: Mapped[str | None] = mapped_column(Text)
    supersedes: Mapped[str | None] = mapped_column(ForeignKey("claim.claim_id"))
    ontology_version: Mapped[str] = mapped_column(Text, nullable=False)


class ClaimRelation(Base):
    __tablename__ = "claim_relation"
    __table_args__ = (
        CheckConstraint(
            "relation IN ('corroborates', 'contradicts')",
            name="ck_claim_relation_relation",
        ),
    )

    from_claim: Mapped[str] = mapped_column(
        ForeignKey("claim.claim_id"), primary_key=True
    )
    to_claim: Mapped[str] = mapped_column(ForeignKey("claim.claim_id"), primary_key=True)
    relation: Mapped[str] = mapped_column(Text, primary_key=True)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class ReviewQueue(Base):
    __tablename__ = "review_queue"
    __table_args__ = (
        CheckConstraint(
            "status IN ('suggested', 'accepted', 'rejected')",
            name="ck_review_queue_status",
        ),
    )

    suggestion_id: Mapped[str] = mapped_column(Text, primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    producer: Mapped[str] = mapped_column(Text, nullable=False)
    producer_meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'suggested'")
    )
    decided_by: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    result_claim: Mapped[str | None] = mapped_column(ForeignKey("claim.claim_id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class CaseMember(Base):
    __tablename__ = "case_member"

    case_id: Mapped[str] = mapped_column(ForeignKey("case_file.case_id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)


class AuthzOutbox(Base):
    __tablename__ = "authz_outbox"
    __table_args__ = (
        CheckConstraint("op IN ('write', 'delete')", name="ck_authz_outbox_op"),
        Index(
            "ix_authz_outbox_pending",
            "processed_at",
            postgresql_where=text("processed_at IS NULL"),
        ),
    )

    outbox_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    op: Mapped[str] = mapped_column(Text, nullable=False)
    fga_tuple: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    last_error: Mapped[str | None] = mapped_column(Text)


class EvidenceItem(Base):
    __tablename__ = "evidence_item"
    __table_args__ = (
        Index("ix_evidence_item_content_hash", "content_hash"),
        Index("ix_evidence_item_case_id", "case_id"),
    )

    evidence_id: Mapped[str] = mapped_column(Text, primary_key=True)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("case_file.case_id"))
    record_id: Mapped[str | None] = mapped_column(ForeignKey("source_record.record_id"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(Text)
    storage_uri: Mapped[str | None] = mapped_column(Text)
    acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acquired_by: Mapped[str | None] = mapped_column(Text)
    legal_basis: Mapped[str | None] = mapped_column(Text)
    handling_code: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'restricted'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class Derivative(Base):
    __tablename__ = "derivative"
    __table_args__ = (
        CheckConstraint(
            "parent_evidence IS NOT NULL OR parent_record IS NOT NULL",
            name="ck_derivative_has_parent",
        ),
        Index("ix_derivative_content_hash", "content_hash"),
    )

    derivative_id: Mapped[str] = mapped_column(Text, primary_key=True)
    parent_evidence: Mapped[str | None] = mapped_column(
        ForeignKey("evidence_item.evidence_id")
    )
    parent_record: Mapped[str | None] = mapped_column(ForeignKey("source_record.record_id"))
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    tool: Mapped[str] = mapped_column(Text, nullable=False)
    tool_version: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    operator: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class CustodyEvent(Base):
    __tablename__ = "custody_event"

    evidence_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_item.evidence_id"), primary_key=True
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_actor: Mapped[str | None] = mapped_column(Text)
    to_actor: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    hash_checked: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("false")
    )
    note: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint("decision IN ('allow', 'deny')", name="ck_audit_log_decision"),
        Index("ix_audit_log_at", "at"),
        Index("ix_audit_log_actor_at", "actor", "at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str | None] = mapped_column(Text)
    case_id: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(Text)
    resource_id: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    prev_hash: Mapped[str] = mapped_column(Text, nullable=False)
    entry_hash: Mapped[str] = mapped_column(Text, nullable=False)


__all__ = [
    "AuditLog",
    "AuthzOutbox",
    "CaseFile",
    "CaseMember",
    "Claim",
    "ClaimRelation",
    "CustodyEvent",
    "Derivative",
    "Entity",
    "EvidenceItem",
    "ReviewQueue",
    "Source",
    "SourceRecord",
]
