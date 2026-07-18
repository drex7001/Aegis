"""Request/response models for API v1 (spec 06)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ClaimIn(BaseModel):
    subject_id: str
    predicate: str
    object_id: str | None = None
    object_value: Any | None = None
    record_id: str
    assertion_type: str = "reported"
    excerpt: str | None = None
    collection_method: str | None = None
    credibility_scheme: str | None = None
    credibility_original: str | None = None
    credibility_normalized: str = "cannot_judge"
    verification_status: str = "unverified"
    analytic_confidence: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    handling_code: str = "open"
    case_id: str | None = None
    jurisdiction: str | None = None
    location_text: str | None = None


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    claim_id: str
    subject_id: str
    predicate: str
    object_id: str | None
    object_value: Any | None
    assertion_type: str
    record_id: str
    excerpt: str | None
    collection_method: str | None
    credibility_scheme: str | None
    credibility_original: str | None
    credibility_normalized: str
    verification_status: str
    analytic_confidence: str | None
    valid_from: date | None
    valid_to: date | None
    recorded_at: datetime
    retracted_at: datetime | None
    retraction_reason: str | None
    handling_code: str
    case_id: str | None
    location_text: str | None
    ontology_version: str


class RetractIn(BaseModel):
    reason: str = Field(min_length=1)


class RelationIn(BaseModel):
    to_claim: str
    relation: str  # corroborates | contradicts


class EntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_id: str
    entity_type: str
    label: str
    created_at: datetime


class EntityDetail(BaseModel):
    entity: EntityOut
    claims_by_predicate: dict[str, list[ClaimOut]]


class SourceIn(BaseModel):
    source_type: str
    name: str = Field(min_length=1)
    url: str | None = None
    reliability_scheme: str | None = None
    reliability_original: str | None = None
    reliability_normalized: str | None = None
    notes: str | None = None


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_id: str
    source_type: str
    name: str
    url: str | None
    reliability_normalized: str | None
    created_at: datetime


class SourceRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    record_id: str
    source_id: str
    content_hash: str
    media_type: str | None
    status: str
    quarantine_reason: str | None
    handling_code: str
    received_at: datetime
    provenance: dict[str, Any]


class SuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    suggestion_id: str
    suggestion_kind: str
    schema_version: int
    payload: dict[str, Any]
    target_action: str
    producer: str
    producer_version: str
    producer_meta: dict[str, Any]
    record_id: str | None
    case_id: str | None
    status: str
    decided_by: str | None
    decided_at: datetime | None
    decision_note: str | None
    # exactly one is set on acceptance, per kind (ADR-031 §2)
    result_claim_id: str | None
    result_decision_id: str | None
    result_relation: dict[str, Any] | None
    created_at: datetime


class AcceptIn(BaseModel):
    edits: dict[str, Any] | None = None
    note: str | None = None


class RejectIn(BaseModel):
    reason: str = Field(min_length=1)


class CaseIn(BaseModel):
    title: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    handling_code: str = "open"


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case_id: str
    title: str
    status: str
    purpose: str
    handling_code: str
    opened_by: str
    opened_at: datetime
    closed_at: datetime | None


class CaseMemberIn(BaseModel):
    user_id: str = Field(min_length=1)
    role: str


class EvidenceIn(BaseModel):
    description: str = Field(min_length=1)
    case_id: str | None = None
    record_id: str | None = None
    content_hash: str | None = None
    storage_uri: str | None = None
    legal_basis: str | None = None
    handling_code: str = "restricted"


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: str
    case_id: str | None
    record_id: str | None
    description: str
    content_hash: str | None
    handling_code: str
    acquired_by: str | None
    created_at: datetime


class CustodyEventIn(BaseModel):
    to_actor: str = Field(min_length=1)
    occurred_at: datetime
    purpose: str = Field(min_length=1)
    from_actor: str | None = None
    hash_checked: bool = False
    note: str | None = None


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    at: datetime
    actor: str
    purpose: str | None
    case_id: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    decision: str
    detail: dict[str, Any]


class MentionOut(BaseModel):
    """The words a claim's argument came from (ADR-029)."""

    model_config = ConfigDict(from_attributes=True)

    mention_id: str
    record_id: str
    raw_text: str
    norm_key: str
    char_start: int | None
    char_end: int | None
    script: str | None
    language: str | None


class GradingOut(BaseModel):
    """The three dimensions, kept apart (Article III).

    There is deliberately no combined score here. A single number would be the
    one thing every caller reached for, and it cannot be reconstructed back
    into the judgements that produced it.
    """

    reliability: str | None  # graded on the source, not the claim
    credibility: str
    verification: str
    analytic_confidence: str | None


class ClaimProvenanceOut(BaseModel):
    """One claim with its evidence — the unit the provenance panel renders."""

    claim: ClaimOut
    grading: GradingOut
    source: SourceOut | None
    record: SourceRecordOut | None
    #: Both directions are reported. Corroboration never cancels contradiction
    #: (Article VIII) — the reader is shown the disagreement, not a net score.
    corroborated_by: list[str]
    contradicted_by: list[str]
    subject_mention: MentionOut | None
    object_mention: MentionOut | None


class IdentityDecisionOut(BaseModel):
    """A human's identity decision: who, when, why, and which revision."""

    model_config = ConfigDict(from_attributes=True)

    decision_id: str
    kind: str
    decided_by: str
    decision_note: str
    parent_revision_id: int
    result_revision_id: int
    decided_at: datetime
    entity_id: str | None = None


class WhyConnectedOut(BaseModel):
    """The answer to GOAL.md §18 for one pair of entities."""

    subject_id: str
    object_id: str
    #: Present when the requested ids resolved elsewhere through a merge, so a
    #: caller following a stale link is told rather than quietly redirected.
    resolved_subject_id: str
    resolved_object_id: str
    claims: list[ClaimProvenanceOut]
    #: DISTINCT source records. Never "independent sources" (ADR-030 §3).
    record_count: int
    contradiction_count: int
    corroboration_count: int
    identity_line: list[IdentityDecisionOut]
    #: True when the claim cap was reached, so a thin panel is never mistaken
    #: for thin evidence.
    truncated: bool
