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
    #: When the *world* event happened, as an interval. Two fields rather than
    #: one because a source that says "some time in 2019" has stated a range,
    #: and collapsing it to a point would invent precision nobody asserted
    #: (spec 02 time model). Both null means the time was never stated — which
    #: is a different fact from `recorded_at`, and must never be rendered as it.
    event_time_earliest: datetime | None
    event_time_latest: datetime | None
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
    # P2 governance seams are visible but deliberately inert until P7.
    collection_policy_ref: str | None
    retention_class: str | None
    authority_ref: str | None
    authority_valid_from: datetime | None
    authority_valid_to: datetime | None


class SourceRecordPageOut(BaseModel):
    items: list[SourceRecordOut]
    next_cursor: str | None = None


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
    retention_class: str | None = None
    authority_ref: str | None = None
    authority_valid_from: datetime | None = None
    authority_valid_to: datetime | None = None
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


class SuggestionPageOut(BaseModel):
    items: list[SuggestionOut]
    next_cursor: str | None = None


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


class EntityCaseOut(BaseModel):
    """One case an entity appears in, that the caller is allowed to know about.

    Deliberately thin. A richer payload here would be a second read surface for
    case data with its own filtering to get right; the object view needs a link
    and a name (spec 09 §6.5).
    """

    model_config = ConfigDict(from_attributes=True)

    case_id: str
    title: str
    status: str


class CasePageOut(BaseModel):
    """Only the cases the caller can view. No total: a count is an existence
    leak (spec 06 §4 default 4, spec 09 §2.4)."""

    items: list[CaseOut]
    next_cursor: str | None = None


class CaseCloseIn(BaseModel):
    reason: str = Field(min_length=1)


class CaseMemberIn(BaseModel):
    user_id: str = Field(min_length=1)
    role: str


class CaseMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case_id: str
    user_id: str
    role: str


# ── investigation: references, hypotheses, tasks (spec 09) ──────────────────


class CaseReferenceIn(BaseModel):
    target_type: Literal["claim", "entity", "evidence_item"]
    target_id: str = Field(min_length=1)
    note: str | None = None


class CaseReferenceOut(BaseModel):
    """A reference the caller can *resolve* — targets they cannot read are
    absent, not marked (ADR-044, spec 09 §6.5)."""

    model_config = ConfigDict(from_attributes=True)

    case_id: str
    target_type: str
    target_id: str
    note: str | None
    linked_by: str
    linked_at: datetime


class HypothesisIn(BaseModel):
    case_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    #: GOAL.md §18: a hypothesis states what would change it. `min_length` here
    #: rejects the empty string; the `required_text_is_substantive` submission
    #: criterion rejects a string of spaces, which this cannot.
    missing_info: str = Field(min_length=1)
    handling_code: str = "open"


class HypothesisRevisionIn(BaseModel):
    note: str = Field(min_length=1)
    statement: str | None = None
    status: Literal["open", "supported", "refuted", "withdrawn"] | None = None
    missing_info: str | None = None


class HypothesisRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hypothesis_id: str
    version: int
    statement: str
    status: str
    missing_info: str
    note: str | None
    authored_by: str
    authored_at: datetime


class HypothesisClaimIn(BaseModel):
    claim_id: str = Field(min_length=1)
    stance: Literal["supports", "contradicts"]
    note: str | None = None


class HypothesisClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    claim_id: str
    stance: str
    note: str | None
    linked_by: str
    linked_at: datetime


class HypothesisOut(BaseModel):
    """A hypothesis with both sides and its whole history.

    ``supporting`` and ``contradicting`` are **always present**, empty or not.
    Article VIII is a rendering obligation, and a client cannot render "no
    contradicting evidence recorded" from a field that was omitted (spec 09 §3.5).
    """

    hypothesis_id: str
    case_id: str
    opened_by: str
    opened_at: datetime
    handling_code: str
    current: HypothesisRevisionOut
    revisions: list[HypothesisRevisionOut]
    supporting: list[HypothesisClaimOut]
    contradicting: list[HypothesisClaimOut]


class HypothesisSummaryOut(BaseModel):
    hypothesis_id: str
    case_id: str
    statement: str
    status: str
    version: int
    opened_by: str
    opened_at: datetime


class HypothesisListOut(BaseModel):
    items: list[HypothesisSummaryOut]


class TaskIn(BaseModel):
    case_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    kind: Literal["task", "lead"] = "task"
    detail: str | None = None
    owner: str | None = None
    due_date: date | None = None
    hypothesis_id: str | None = None


class TaskUpdateIn(BaseModel):
    status: Literal["open", "in_progress", "blocked", "done", "dropped"] | None = None
    owner: str | None = None
    due_date: date | None = None
    detail: str | None = None
    note: str | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: str
    case_id: str
    kind: str
    title: str
    detail: str | None
    status: str
    owner: str | None
    due_date: date | None
    hypothesis_id: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class TaskListOut(BaseModel):
    items: list[TaskOut]


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


class AuditPageOut(BaseModel):
    items: list[AuditOut]
    next_cursor: str | None = None


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


class ProjectionRebuildOut(BaseModel):
    """What one rebuild produced (spec 06 §2.6, Article XIII)."""

    edges: int
    segments: int
    claims_considered: int
    collapsed_endpoints: int
    #: Endpoints resolved through a mention anchor vs. through the canonical
    #: map. The second kind cannot survive a split, so the ratio is a live
    #: measure of how reversible the projected graph actually is.
    anchor_resolved: int
    map_resolved: int
    built_at_revision_id: int
    ontology_version: str
    builder_version: str
    #: The geometry projection, rebuilt in the same pass (T56). `rejected`
    #: counts geometry claims whose value this build could not read — under
    #: an older ontology, or written before the validator existed. Reported
    #: rather than silently zero: a projection is a cache, so one unreadable
    #: row must not make the other ten thousand unavailable, and the number
    #: is how anyone would ever notice.
    geometry_rows: int = 0
    geometry_invalid: int = 0
    geometry_rejected: int = 0
    geometry_builder_version: str | None = None


class AsOfStampOut(BaseModel):
    """What an answer was computed against (B-11, spec 09 §7).

    Present on **every** response that can take `?asOf=`, not only on the ones
    that did. A stamp that appeared only in as-of mode would leave a caller
    unable to tell a current answer from a historical one without re-reading its
    own request, and the identity revision is the field that makes the
    difference legible: `asOf` alone resolves identity as it is *now*, which is
    almost never what a historical question means.
    """

    #: The recording snapshot, or null for "current".
    as_of: datetime | None
    #: The revision entity arguments were resolved through — echoed whether or
    #: not the caller pinned it (spec 06 §3).
    identity_revision_id: int
    #: The composition version this server is running (ADR-037).
    ontology_version: str


class EntityDetail(BaseModel):
    """One entity's claims, grouped by predicate (spec 06 §2.1).

    Each entry is a full ``ClaimProvenanceOut`` rather than a bare claim, so
    two claims disagreeing about the same property arrive already knowing they
    disagree. Grouping is what puts them side by side; ``contradicted_by`` is
    what stops the reader having to notice unaided (Article VIII).
    """

    entity: EntityOut
    claims_by_predicate: dict[str, list[ClaimProvenanceOut]]
    #: Set when the requested id has been merged away, so a caller following a
    #: stale link is told rather than quietly answered about a different id.
    resolved_entity_id: str
    #: True when the claim cap was reached — a thin panel is never mistaken for
    #: thin evidence.
    truncated: bool = False
    #: What this answer was computed against (T49). Optional in the schema only
    #: so a client built before T49 keeps type-checking; the route always sets it.
    stamp: AsOfStampOut | None = None


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
    next_cursor: str | None = None


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
    next_cursor: str | None = None


class SourcePageOut(BaseModel):
    items: list[SourceOut]
    next_cursor: str | None = None


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
    #: Restrict to the evidence **this case recorded** (T46, spec 09 §2.4).
    #:
    #: Not a display filter: it is added to `claim_filters`, so it narrows edge
    #: visibility *and* every support summary rebuilt from those claims. An edge
    #: supported by one case claim and three open ones renders with a tally of
    #: one, because that is what the case has. A filter applied after the
    #: summaries were computed would overstate the case's evidence, which is the
    #: mistake this parameter exists to make impossible.
    case_id: str | None = None


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
