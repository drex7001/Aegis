"""SQLAlchemy mappings for the Phase 1 canonical claim store.

Ontology-owned values deliberately remain plain ``TEXT``.  They are validated by
the actions layer against :mod:`aegis.ontology`, not by database constraints
(ADR-013).  The checks here cover only stable, code-owned structural invariants.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
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
        CheckConstraint(
            "authority_valid_to IS NULL OR authority_valid_from IS NULL "
            "OR authority_valid_to >= authority_valid_from",
            name="ck_source_record_authority_window",
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
    # Governance seams (B-08).  Deliberately inert in Phase 2: stored and
    # displayed, never consulted by a read path or a filter — P7 enforces them
    # (spec 02 §1).  They exist now because retrofitting a classification
    # column onto a populated evidence corpus is far more expensive.
    collection_policy_ref: Mapped[str | None] = mapped_column(Text)
    retention_class: Mapped[str | None] = mapped_column(Text)
    authority_ref: Mapped[str | None] = mapped_column(Text)
    authority_valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authority_valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    # No active memberships and no lineage target.  Retained forever, excluded
    # from projections, id never reused (spec 05 §5).
    tombstoned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Mention(Base):
    """A name-as-written inside one source record (spec 02 §2).

    ``norm_key`` is a *mention key* (the legacy ``slugify()`` output), not an
    identity — identity lives in :class:`IdentityMembership`.  Offsets and
    script are the H-06 minimum: without them a mention cannot be re-anchored
    to the text it was read from, so no claim anchored on it is verifiable.
    """

    __tablename__ = "mention"
    __table_args__ = (
        CheckConstraint(
            "char_end IS NULL OR char_start IS NULL OR char_end >= char_start",
            name="ck_mention_offset_order",
        ),
        Index("ix_mention_norm_key", "norm_key"),
    )

    mention_id: Mapped[str] = mapped_column(Text, primary_key=True)
    record_id: Mapped[str] = mapped_column(
        ForeignKey("source_record.record_id"), nullable=False
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    norm_key: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    script: Mapped[str | None] = mapped_column(Text)  # ISO 15924, when detected
    language: Mapped[str | None] = mapped_column(Text)  # BCP-47, when detected
    context: Mapped[str | None] = mapped_column(Text)


class IdentityRevision(Base):
    """One link in the append-only identity chain (ADR-028, spec 05 §2).

    ``revision_id`` 0 is the migration baseline and the only revision allowed
    to carry ``decision_id IS NULL`` — it is not a decision anyone made.
    """

    __tablename__ = "identity_revision"

    revision_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    decision_id: Mapped[str | None] = mapped_column(
        ForeignKey("identity_decision.decision_id", deferrable=True, initially="DEFERRED")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class IdentityDecision(Base):
    """One human adjudication (Article VII — ``decided_by`` is always a person).

    Every decision creates exactly one revision, and carries the parent
    revision it was computed against for the scoped optimistic-concurrency
    check (spec 05 §2).
    """

    __tablename__ = "identity_decision"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('confirm', 'reject', 'merge', 'split', 'unresolved')",
            name="ck_identity_decision_kind",
        ),
        UniqueConstraint("result_revision_id", name="uq_identity_decision_result"),
    )

    decision_id: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[str] = mapped_column(Text, nullable=False)
    decision_note: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("er_candidate.candidate_id", deferrable=True, initially="DEFERRED")
    )
    input_mentions: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    parent_revision_id: Mapped[int] = mapped_column(
        ForeignKey("identity_revision.revision_id"), nullable=False
    )
    result_revision_id: Mapped[int] = mapped_column(
        ForeignKey(
            "identity_revision.revision_id", deferrable=True, initially="DEFERRED"
        ),
        nullable=False,
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class IdentityMembership(Base):
    """Revision-keyed, reversible mention→entity membership (Article V).

    A membership names the revision that opened it and the revision that
    closed it; history is never deleted.  The membership set at any revision is
    reconstructible, which is what makes reversal *provable* rather than merely
    likely (spec 05 §2).
    """

    __tablename__ = "identity_membership"
    __table_args__ = (
        # THE invariant (ADR-028 §2): at most one active membership per
        # mention, enforced by the database rather than by application code a
        # future caller could forget to run.
        Index(
            "ux_membership_one_active",
            "mention_id",
            unique=True,
            postgresql_where=text("closed_revision_id IS NULL"),
        ),
        Index(
            "ix_identity_membership_active_entity",
            "entity_id",
            postgresql_where=text("closed_revision_id IS NULL"),
        ),
        Index("ix_identity_membership_entity", "entity_id"),
    )

    membership_id: Mapped[str] = mapped_column(Text, primary_key=True)
    mention_id: Mapped[str] = mapped_column(
        ForeignKey("mention.mention_id"), nullable=False
    )
    entity_id: Mapped[str] = mapped_column(
        ForeignKey("entity.entity_id"), nullable=False
    )
    opened_revision_id: Mapped[int] = mapped_column(
        ForeignKey("identity_revision.revision_id"), nullable=False
    )
    closed_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("identity_revision.revision_id")
    )


class ErCandidate(Base):
    """A machine-produced candidate pair, persisted with its explanation.

    Candidates are **not** review_queue rows (ADR-031 §3): high volume, their
    own lifecycle, their own disposition vocabulary.  Nothing here changes
    identity — only a human ``adjudicate_identity`` does (ADR-027).
    """

    __tablename__ = "er_candidate"
    __table_args__ = (
        CheckConstraint(
            "disposition IN ('open', 'confirmed', 'rejected', 'unresolved', 'superseded')",
            name="ck_er_candidate_disposition",
        ),
        # canonical pair ordering — one row per pair, whichever side found it
        CheckConstraint("mention_a < mention_b", name="ck_er_candidate_pair_order"),
        Index(
            "ix_er_candidate_open",
            "disposition",
            postgresql_where=text("disposition = 'open'"),
        ),
        Index("ix_er_candidate_mentions", "mention_a", "mention_b"),
    )

    candidate_id: Mapped[str] = mapped_column(Text, primary_key=True)
    mention_a: Mapped[str] = mapped_column(ForeignKey("mention.mention_id"), nullable=False)
    mention_b: Mapped[str] = mapped_column(ForeignKey("mention.mention_id"), nullable=False)
    producer: Mapped[str] = mapped_column(Text, nullable=False)
    producer_version: Mapped[str] = mapped_column(Text, nullable=False)
    # the projection snapshot graph-context features were computed from (H-07);
    # without it a score is not reproducible
    graph_snapshot_id: Mapped[str | None] = mapped_column(Text)
    score: Mapped[Any | None] = mapped_column(Numeric)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    pre_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    disposition: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'open'")
    )
    decision_id: Mapped[str | None] = mapped_column(
        ForeignKey("identity_decision.decision_id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class IdentityNegativeConstraint(Base):
    """A durable reject: the pair is not re-suggested while it holds (spec 05 §3.3).

    Versioned rather than mutable — a genuinely new evidence *type* may
    supersede it, and the history of both is kept (Article VIII).
    """

    __tablename__ = "identity_negative_constraint"
    __table_args__ = (
        CheckConstraint(
            "mention_a < mention_b", name="ck_identity_negative_constraint_pair_order"
        ),
    )

    constraint_id: Mapped[str] = mapped_column(Text, primary_key=True)
    mention_a: Mapped[str] = mapped_column(ForeignKey("mention.mention_id"), nullable=False)
    mention_b: Mapped[str] = mapped_column(ForeignKey("mention.mention_id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("identity_decision.decision_id"), nullable=False
    )
    evidence_basis: Mapped[str] = mapped_column(Text, nullable=False)
    superseded_by: Mapped[str | None] = mapped_column(
        ForeignKey("identity_negative_constraint.constraint_id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class EntityCanonicalMap(Base):
    """Rebuildable projection of merge lineage (Article XIII, spec 05 §5).

    Losing the whole table loses nothing: it replays from the ledger in
    revision order.  It is never a source of truth.
    """

    __tablename__ = "entity_canonical_map"

    entity_id: Mapped[str] = mapped_column(
        ForeignKey("entity.entity_id"), primary_key=True
    )
    canonical_entity_id: Mapped[str] = mapped_column(
        ForeignKey("entity.entity_id"), nullable=False
    )
    at_revision_id: Mapped[int] = mapped_column(
        ForeignKey("identity_revision.revision_id"), nullable=False
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
            "object_mention_id IS NULL OR object_id IS NOT NULL",
            name="ck_claim_object_anchor_needs_entity",
        ),
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
        Index("ix_claim_subject_mention", "subject_mention_id"),
        Index("ix_claim_object_mention", "object_mention_id"),
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
    # Mention anchors (ADR-029): the textual evidence each entity argument came
    # from.  Nullable because analyst and assessment claims legitimately have
    # none; required for observed/reported by the actions layer, not by a
    # CHECK, since that rule depends on assertion_type semantics the DB does
    # not own (spec 02 §3.1 rule 1).
    subject_mention_id: Mapped[str | None] = mapped_column(
        ForeignKey("mention.mention_id")
    )
    object_mention_id: Mapped[str | None] = mapped_column(ForeignKey("mention.mention_id"))
    # The identity revision current at recorded_at: what identity *meant* when
    # the claim was made.  Not a resolution instruction — projections resolve
    # through the active revision (spec 02 §3.1 rules 2-3).
    identity_revision_id: Mapped[int] = mapped_column(
        ForeignKey("identity_revision.revision_id"), nullable=False
    )
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
    """The typed suggestion envelope (ADR-031, spec 02 §3.2).

    ``suggestion_kind`` is a **closed, code-owned** list — not ontology
    vocabulary — because each kind is a dispatch branch in the actions layer.
    Acceptance never writes tables itself: it calls ``target_action`` with the
    reviewer as actor, which is what makes Article VII mechanically checkable
    per kind rather than by inspection.
    """

    __tablename__ = "review_queue"
    __table_args__ = (
        CheckConstraint(
            "status IN ('suggested', 'accepted', 'rejected', 'superseded', 'expired')",
            name="ck_review_queue_status",
        ),
        CheckConstraint(
            "suggestion_kind IN ('claim_draft', 'identity_candidate', 'claim_relation')",
            name="ck_review_queue_kind",
        ),
        # exactly one typed result on acceptance, per kind
        CheckConstraint(
            "status <> 'accepted' OR num_nonnulls(result_claim_id, "
            "result_decision_id, result_relation) = 1",
            name="ck_review_queue_accepted_result",
        ),
        UniqueConstraint("idempotency_key", name="uq_review_queue_idempotency_key"),
        Index("ix_review_queue_kind_status", "suggestion_kind", "status"),
    )

    suggestion_id: Mapped[str] = mapped_column(Text, primary_key=True)
    suggestion_kind: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    target_action: Mapped[str] = mapped_column(Text, nullable=False)
    producer: Mapped[str] = mapped_column(Text, nullable=False)
    producer_version: Mapped[str] = mapped_column(Text, nullable=False)
    producer_meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    record_id: Mapped[str | None] = mapped_column(ForeignKey("source_record.record_id"))
    case_id: Mapped[str | None] = mapped_column(ForeignKey("case_file.case_id"))
    # a replay updates nothing already decided (spec 04 §5)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    supersedes: Mapped[str | None] = mapped_column(
        ForeignKey("review_queue.suggestion_id")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'suggested'")
    )
    decided_by: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    result_claim_id: Mapped[str | None] = mapped_column(ForeignKey("claim.claim_id"))
    result_decision_id: Mapped[str | None] = mapped_column(
        ForeignKey("identity_decision.decision_id")
    )
    result_relation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
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


class EdgeProjection(Base):
    """Time-segmented traversal projection v2 (spec 02 §7, ADR-029, ADR-030).

    A rebuildable cache with no authority of its own (Article XIII): every row
    is derived from claims, and dropping the table loses nothing.  Three
    properties distinguish it from the Phase-1 view it replaced — entity
    arguments are canonical at build time, one row is one maximal interval
    rather than one collapsed span, and there is **no aggregate weight
    column**.  ``support`` carries the per-claim grading references instead, so
    a contradiction stays visible rather than being averaged away.
    """

    __tablename__ = "edge_projection"
    __table_args__ = (
        Index("ix_edge_projection_subject", "subject_id"),
        Index("ix_edge_projection_object", "object_id"),
        Index("ix_edge_projection_predicate", "predicate"),
        Index("ix_edge_projection_handling", "handling_rank"),
    )

    edge_id: Mapped[str] = mapped_column(Text, primary_key=True)
    subject_id: Mapped[str] = mapped_column(
        ForeignKey("entity.entity_id"), nullable=False
    )
    object_id: Mapped[str] = mapped_column(
        ForeignKey("entity.entity_id"), nullable=False
    )
    predicate: Mapped[str] = mapped_column(Text, nullable=False)
    segment_from: Mapped[date | None] = mapped_column(Date)
    segment_to: Mapped[date | None] = mapped_column(Date)
    claim_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    support: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    handling_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    built_at_revision_id: Mapped[int] = mapped_column(
        ForeignKey("identity_revision.revision_id"), nullable=False
    )
    ontology_version: Mapped[str] = mapped_column(Text, nullable=False)
    builder_version: Mapped[str] = mapped_column(Text, nullable=False)


__all__ = [
    "AuditLog",
    "AuthzOutbox",
    "CaseFile",
    "CaseMember",
    "Claim",
    "ClaimRelation",
    "CustodyEvent",
    "Derivative",
    "EdgeProjection",
    "Entity",
    "EntityCanonicalMap",
    "ErCandidate",
    "EvidenceItem",
    "IdentityDecision",
    "IdentityMembership",
    "IdentityNegativeConstraint",
    "IdentityRevision",
    "Mention",
    "ReviewQueue",
    "Source",
    "SourceRecord",
]
