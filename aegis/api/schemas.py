"""Request/response models for API v1 (spec 06)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aegis.queries.graph import MAX_ELEMENTS, MAX_PATH_HOPS, MAX_PATHS, MAX_SEEDS


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


class OntologyVocabularyOut(BaseModel):
    """Closed vocabularies, served so no client hand-writes them (Article XI)."""

    version: str
    handling_codes: list[str]
    source_types: list[str]
    #: Core, not domain: how a claim is asserted is platform epistemics, so this
    #: comes from a code-owned constant rather than `aegis.yaml` (Article XIV).
    assertion_types: list[str]


class LandTextIn(BaseModel):
    """A pasted note (spec 04 §1 — "File / paste / curated entry").

    ``filename`` is not decoration: the ingest key is
    ``sha256(source_system | filename | content hash)``, so it is half of what
    makes re-pasting the same text under the same name a no-op, and it is what
    an operator will recognise the record by later.
    """

    text: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=200)
    source_id: str | None = None
    handling_code: str = "open"
    source_url: str | None = None
    collection_policy: str | None = None
    notes: str | None = None
    source_time: datetime | None = None


class LandingOut(BaseModel):
    """``outcome`` is what *this request* did; ``record.status`` is what the
    record *is*.

    They come apart on the case that matters: re-sending an artifact that
    landed quarantined is ``already_landed`` over a record whose status is
    ``quarantined``. Collapsing them would let a re-upload read as a fresh
    quarantine, or a no-op hide one.
    """

    outcome: Literal["landed", "already_landed", "quarantined"]
    record: SourceRecordOut


class DerivativeOut(BaseModel):
    """A recorded transformation (spec 04 §1 stage 3)."""

    model_config = ConfigDict(from_attributes=True)

    derivative_id: str
    kind: str
    tool: str
    tool_version: str
    params: dict[str, Any]
    content_hash: str
    operator: str
    created_at: datetime


class ExtractIn(BaseModel):
    producer: Literal["structural", "semantic"] = "structural"
    mock: bool = Field(
        default=False,
        description=(
            "semantic only: run the offline deterministic extractor instead of a "
            "model. Output is labelled `model: mock` in producer_meta, so a "
            "suggestion never misrepresents what produced it."
        ),
    )


class ExtractionOut(BaseModel):
    """What one extraction run did — suggestions only, never claims (Article VII)."""

    record_id: str
    producer: str
    suggestions_created: int
    derivative: DerivativeOut | None
    derivative_created: bool


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


class CandidateMentionOut(BaseModel):
    """One side of a candidate pair, with the context needed to judge it.

    ``entity_id`` comes from the mention's *active* membership rather than the
    canonical map: a confirm moves memberships, so the active row is already
    the survivor. A pair whose sides were merged by an earlier decision
    therefore shows one entity on both sides, which is how an analyst tells
    "confirm this" from "already done".
    """

    mention_id: str
    record_id: str
    raw_text: str
    norm_key: str
    script: str | None
    language: str | None
    entity_id: str | None
    entity_label: str | None


class CandidateOut(BaseModel):
    """A machine-proposed pair with its explanation (spec 06 §2.2)."""

    candidate_id: str
    mention_a: CandidateMentionOut
    mention_b: CandidateMentionOut
    producer: str
    producer_version: str
    #: Which projection snapshot graph-context features were computed against.
    #: Without it a score cannot be reproduced (H-07).
    graph_snapshot_id: str | None
    #: ``None`` from rule producers, which compute no probability. A fabricated
    #: 1.0 would be indistinguishable from a model that was certain.
    score: float | None
    #: Verbatim as persisted, because its shape depends on the producer: rules
    #: write ``{"rule": ..., "predicate": ...}``, Splink writes ``gamma_``/
    #: ``bf_``/``tf_`` per column. Grouping it into a waterfall is a rendering
    #: decision, and a server-side flattening would fit one producer while
    #: quietly misrepresenting the others.
    features: dict[str, Any]
    pre_verified: bool
    disposition: str
    created_at: datetime


class EntityHitOut(BaseModel):
    """One search result, with how it was found."""

    entity_id: str
    label: str
    entity_type: str
    score: float
    #: `label`, `alias`, `mention` or `phonetic`. Reported because they are not
    #: equally strong evidence: metaphone collapses genuinely different names,
    #: so a phonetic hit is a lead, and a list that renders it like a name
    #: match invites the reader to treat it as one.
    matched: str


class SearchResultsOut(BaseModel):
    query: str
    results: list[EntityHitOut]


class CandidateListOut(BaseModel):
    """Candidates, plus the revision they were read at.

    The revision travels with the list rather than through a separate lookup
    because that is what makes the concurrency check mean anything: a decision's
    ``parent_revision_id`` is meant to be *the state the analyst was looking at*
    when they decided. Fetching it independently would let a client send a
    revision newer than the screen it decided from, which is the exact race
    spec 05 §2 exists to catch.
    """

    revision_id: int
    candidates: list[CandidateOut]


class _DecisionBase(BaseModel):
    #: The revision the decision was computed against. A stale one in the same
    #: entity scope is a 409 carrying what intervened (specs/05 §2).
    parent_revision_id: int
    note: str = Field(min_length=1)
    protected_person: bool = False


class ConfirmMatchIn(_DecisionBase):
    mode: Literal["confirm_match"] = "confirm_match"
    mention_a: str
    mention_b: str
    candidate_id: str | None = None


class RejectMatchIn(_DecisionBase):
    mode: Literal["reject_match"] = "reject_match"
    mention_a: str
    mention_b: str
    #: Required on reject and nowhere else: it writes a durable constraint that
    #: suppresses this pair from future suggestions, so what that rests on is
    #: recorded with it rather than inferred later.
    evidence_basis: str = Field(min_length=1)
    candidate_id: str | None = None


class SplitEntityIn(_DecisionBase):
    mode: Literal["split_entity"] = "split_entity"
    entity_id: str
    mention_ids: list[str] = Field(min_length=1)
    target_entity_id: str | None = None


class MarkUnresolvedIn(_DecisionBase):
    mode: Literal["mark_unresolved"] = "mark_unresolved"
    mention_a: str
    mention_b: str
    candidate_id: str | None = None


#: Typed per mode rather than one bag of optional fields. The modes genuinely
#: take different arguments — only reject carries an evidence basis, only split
#: names an entity and the mentions leaving it — and a union says so in the
#: OpenAPI document instead of leaving every client to learn it by 422.
DecisionIn = Annotated[
    ConfirmMatchIn | RejectMatchIn | SplitEntityIn | MarkUnresolvedIn,
    Field(discriminator="mode"),
]


class DecisionOut(BaseModel):
    """What an adjudication did, in enough detail to update a screen."""

    decision: IdentityDecisionOut
    moved_mentions: list[str]
    surviving_entity_id: str | None
    new_entity_id: str | None
    #: A split can leave claims it cannot attribute to either side. They are
    #: queued for a human, never reassigned (spec 02 §3.1 rule 4), and are
    #: reported here so the analyst sees the follow-up their decision created
    #: instead of discovering it in the queue later.
    unattributable_claims: list[str]


class BatchConfirmIn(BaseModel):
    #: Bounded because this is one human action standing behind every pair in
    #: it: a batch nobody could read before approving is a rubber stamp.
    candidate_ids: list[str] = Field(min_length=1, max_length=100)
    parent_revision_id: int
    note: str = Field(min_length=1)


class BatchSkipOut(BaseModel):
    candidate_id: str
    reason: str


class BatchConfirmOut(BaseModel):
    """One decision per confirmed pair (ADR-027), plus what was refused.

    Partial rather than all-or-nothing, and the refusals are itemised. Two
    pairs in one batch can share an entity, in which case the second genuinely
    conflicts with the first — reporting that is more useful than either
    failing the batch or hiding it.
    """

    confirmed: list[DecisionOut]
    skipped: list[BatchSkipOut]


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


class GraphExpandIn(BaseModel):
    """A bounded traversal request (specs/06 §2.6).

    Every bound is clamped rather than rejected (specs/06 §4): a client asking
    for six hops gets three and is told the result was truncated, which is more
    useful than a 422 that teaches nothing about the limit.
    """

    #: Empty means the bounded overview — an authorized, capped slice used to
    #: open the canvas before entity search lands (T23c).
    seed_ids: list[str] = Field(default_factory=list, max_length=MAX_SEEDS)
    max_hops: int = Field(default=1, ge=0)
    max_elements: int = Field(default=MAX_ELEMENTS, ge=1)
    #: Ontology predicate categories; unknown names simply match nothing.
    categories: list[str] = Field(default_factory=list)
    valid_from: date | None = None
    valid_to: date | None = None


class GraphPathsIn(BaseModel):
    from_id: str
    to_id: str
    max_hops: int = Field(default=MAX_PATH_HOPS, ge=1)
    max_paths: int = Field(default=MAX_PATHS, ge=1)
    categories: list[str] = Field(default_factory=list)
    valid_from: date | None = None
    valid_to: date | None = None


class GraphNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_id: str
    label: str
    entity_type: str


class GraphEdgeOut(BaseModel):
    """One time segment of one predicate — never a collapsed span (ADR-030).

    There is no ``weight``. ``support`` carries each visible claim's three
    grading dimensions and the corroboration/contradiction counts around them,
    so a reader can reach the evidence instead of trusting a scalar.
    """

    model_config = ConfigDict(from_attributes=True)

    edge_id: str
    subject_id: str
    object_id: str
    predicate: str
    category: str | None
    segment_from: date | None
    segment_to: date | None
    #: DISTINCT records among the claims *this caller* may read.
    record_count: int
    support: dict[str, Any]


class ProjectionStampsOut(BaseModel):
    """Which build produced these rows, and whether it is behind (specs/06 §3)."""

    model_config = ConfigDict(from_attributes=True)

    built_at_revision_id: int | None
    active_revision_id: int
    ontology_version: str | None
    builder_version: str | None
    #: An identity decision landed after this build: the shape is still usable,
    #: but it is not current, and saying so beats looking authoritative.
    stale: bool


class GraphViewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]
    seed_ids: list[str]
    #: Seeds after resolution through the canonical map, so a caller following a
    #: pre-merge link learns why the answer is about a different id.
    resolved_seed_ids: list[str]
    #: True when a bound was hit — the graph is larger than what came back.
    truncated: bool
    stamps: ProjectionStampsOut | None


class GraphPathOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_ids: list[str]
    edge_ids: list[str]


class GraphPathsOut(GraphViewOut):
    paths: list[GraphPathOut]
