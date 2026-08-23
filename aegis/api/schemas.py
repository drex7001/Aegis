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


class EventLinkIn(BaseModel):
    """One participant or place on a `record_event` call (spec 10 §3.2).

    `role` is a **predicate name**, which is the whole design: an undeclared
    role is an undeclared predicate, so the vocabulary is governed by an
    ontology proposal rather than by an enum somebody can widen in Python.
    """

    model_config = ConfigDict(extra="forbid")

    role: str
    entity_id: str
    #: The text this reference was read from, when there is one. Same meaning
    #: and same rules as a claim's object anchor (ADR-029).
    mention_id: str | None = None


class EventIn(BaseModel):
    """Create or extend an occurrence (spec 10 §3.4).

    `summary` is required because it becomes the claim that makes the event
    exist: an entity row is not an assertion and carries no source, so an event
    no claim asserts would be a fact with no provenance (Article I).

    `event_id` extends an occurrence already recorded — the reviewer's move when
    a second report describes the same arrest. There is no automatic occurrence
    merging, because that would be a machine making an identity decision
    (Article VII, spec 10 §3.5).
    """

    event_type: str
    record_id: str
    summary: str
    event_id: str | None = None
    label: str | None = None
    participants: list[EventLinkIn] = Field(default_factory=list)
    places: list[EventLinkIn] = Field(default_factory=list)
    #: The occurrence's time, applied to every claim the call writes. No new
    #: column and no time predicate: the claim envelope has carried intervals
    #: with uncertainty since P1 (spec 10 §3.3).
    event_time_earliest: datetime | None = None
    event_time_latest: datetime | None = None
    assertion_type: str = "reported"
    excerpt: str | None = None
    credibility_normalized: str = "cannot_judge"
    verification_status: str = "unverified"
    analytic_confidence: str | None = None
    handling_code: str = "open"
    case_id: str | None = None


class EventOut(BaseModel):
    """What one `record_event` call created.

    The claim ids are here rather than only the entity id because they are what
    a caller has to be able to point at: every assertion the call made is an
    ordinary claim with its own provenance, and returning the entity alone would
    suggest the occurrence itself was the record.
    """

    entity_id: str
    entity_type: str
    claim_ids: list[str]


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


class AnalyticMetricOut(BaseModel):
    """A metric a caller may run, and what to call it on screen.

    **No caveat text here, deliberately.** A caveat reaches a reader from the
    finding row it was written onto, never from a catalog lookup — if the
    workspace could fetch caveats, there would be a render path that fetches
    one, and therefore a render path that can fail to (spec 12 §9.3).
    """

    metric: str
    label: str


class OntologyVocabularyOut(BaseModel):
    """Closed vocabularies, served so no client hand-writes them (Article XI)."""

    version: str
    handling_codes: list[str]
    source_types: list[str]
    #: Core, not domain: how a claim is asserted is platform epistemics, so this
    #: comes from a code-owned constant rather than `aegis.yaml` (Article XIV).
    assertion_types: list[str]
    #: Platform vocabulary, like `assertion_types`: every deployment has
    #: these metrics and no deployment declares them (Article XIV). Served so
    #: the workspace never hand-writes a label for a machine's reading of a
    #: graph — which is the wording Article IX cares most about.
    analytic_metrics: list[AnalyticMetricOut] = Field(default_factory=list)


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
    #: Claims where this entity is the **object** — what others assert about it
    #: (T57, spec 10 §13). Separate from `claims_by_predicate` on purpose: a
    #: reader has to be able to tell who asserted what about whom, and merging
    #: the two would make "this arrest has Nimal as an arrestee" indistinguishable
    #: from a statement Nimal makes.
    #:
    #: Without it an event's participants would appear on the event's page and on
    #: nobody else's, because participation claims are subjected to the event.
    #: The same hole has always existed for `member_of` — an organization's page
    #: never showed its members — which is why the region is generic rather than
    #: event-shaped.
    inbound_claims_by_predicate: dict[str, list[ClaimProvenanceOut]] = Field(
        default_factory=dict
    )
    #: Set when the requested id has been merged away, so a caller following a
    #: stale link is told rather than quietly answered about a different id.
    resolved_entity_id: str
    #: True when the claim cap was reached — a thin panel is never mistaken for
    #: thin evidence.
    truncated: bool = False
    inbound_truncated: bool = False
    #: What this answer was computed against (T49). Optional in the schema only
    #: so a client built before T49 keeps type-checking; the route always sets it.
    stamp: AsOfStampOut | None = None


class PlaceFeaturePropertiesOut(BaseModel):
    """What the map needs to draw one place honestly (spec 10 §9.1).

    A GeoJSON Feature's `properties` is open-ended by the standard, and the
    first cut of this left it as an untyped map — which meant the workspace
    re-declared the shape by hand, which is the thing
    `test_no_hand_written_api_shape_remains_in_the_workspace` exists to refuse.
    It was right: an undescribed shape is a gap in the contract, not a licence
    to copy it.

    The four axes travel together because the renderer needs all four to pick a
    mark: an accuracy without its derivation cannot tell a tight GPS fix from a
    centroid standing for a city.
    """

    entity_id: str
    label: str
    entity_type: str
    #: `ok` | `none_permitted` | `none_recorded` | `invalid` — a place with no
    #: readable geometry is listed and never placed, and *which* kind of nothing
    #: it is matters to the reader (spec 10 §7.3).
    geometry_state: str
    admin_level: str | None = None
    accuracy_m: float | None = None
    derivation: str | None = None
    #: Derived from the geometry by PostGIS, never asserted.
    geometry_kind: str | None = None
    claim_id: str | None = None
    handling_code: str | None = None
    invalid_reason: str | None = None


class EventTimeIntervalOut(BaseModel):
    """One asserted interval, with the claim that asserts it.

    Plural at the call site and attributable here, because an event's time is
    the *set* of intervals its claims assert. Collapsing them to one span is the
    failure B-12 caught in the edge projection: two disjoint reports become one
    continuous occurrence (spec 10 §6.3).
    """

    earliest: datetime | None = None
    latest: datetime | None = None
    claim_id: str


class EventFeaturePropertiesOut(PlaceFeaturePropertiesOut):
    """A place, plus the occurrence that happened there.

    Extends rather than parallels the place properties, because the geometry
    fields mean exactly the same thing and must generalize by exactly the same
    rule — the map's privacy behaviour cannot differ between two of its own
    layers.
    """

    event_id: str
    event_label: str
    event_type: str
    place_id: str
    #: Which end of the occurrence this is — `took_place_at`, `travelled_from`,
    #: `travelled_to`. A journey drawn as one point at its origin would be a lie
    #: of omission, which is why there is a feature per role.
    place_role: str
    time_intervals: list[EventTimeIntervalOut] = Field(default_factory=list)
    #: Computed over claims the caller can already read: a count taken before
    #: filtering is an existence leak wearing a number (spec 10 §7.4).
    participant_count: int = 0


class GeoFeatureOut(BaseModel):
    """One RFC 7946 Feature. `geometry: null` is valid, and is often the answer."""

    type: Literal["Feature"] = "Feature"
    id: str
    geometry: dict[str, Any] | None = None
    properties: EventFeaturePropertiesOut | PlaceFeaturePropertiesOut


class FeatureCollectionOut(BaseModel):
    """An RFC 7946 `FeatureCollection`, with two foreign members.

    `next_cursor` and `stamp` are foreign members, which §6.1 permits: a client
    that only knows GeoJSON ignores them, and a client that knows this API gets
    its page cursor and the as-of stamp in the same response as the features
    rather than having to correlate two calls.
    """

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoFeatureOut]
    next_cursor: str | None = None
    stamp: AsOfStampOut | None = None


class TimelineItemOut(BaseModel):
    """One claim on the timeline (spec 10 §11.1).

    Timeline items are **claims**, not events: an event appears through the
    claims that assert it, which is what makes "no duplicates" structural
    rather than a de-duplication pass.

    `certainty` is derived from the interval, never asserted — so nothing
    downstream can render "some time in March" as 1 March.
    """

    claim_id: str
    subject_id: str
    subject_label: str | None = None
    subject_type: str | None = None
    predicate: str
    object_id: str | None = None
    object_label: str | None = None
    object_value: Any | None = None
    earliest: datetime | None = None
    latest: datetime | None = None
    #: `exact` | `bounded` | `open` | `undated`.
    certainty: str
    record_id: str
    handling_code: str
    recorded_at: datetime


class TimelinePageOut(BaseModel):
    items: list[TimelineItemOut]
    next_cursor: str | None = None
    #: How many readable claims state no time at all. Returned rather than
    #: folded into `items`, because an undated claim is *excluded* from a
    #: bounded window and must still be surfaced — silently dropping it would
    #: let a narrow window look like a complete account (spec 10 §11.2).
    undated_count: int = 0
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


class SearchHitOut(BaseModel):
    """One result from any backend, on one 0–1 scale."""

    #: `entity`, `claim` or `document` — what `id` refers to.
    kind: str
    id: str
    #: The display group: an ontology object type, `claim`, or `document`.
    group: str
    label: str
    #: Secondary line — a claim's predicate, a document's record id. Never the
    #: matched text: a fragment shown without its grading is what Article III
    #: exists to prevent, and a result list is where that is easiest to lose.
    detail: str | None = None
    #: Where to go when the hit's own id is not a destination: a claim's subject
    #: entity, a document's source record. Null for an entity, which already is
    #: one. Carries no authorization — the hit passed the caller's filters in
    #: its candidate query before it existed.
    parent_id: str | None = None
    score: float
    #: `label`, `alias`, `mention`, `phonetic`, `identifier`, `excerpt`,
    #: `value` or `text`. Reported because they are not equally strong
    #: evidence: metaphone collapses genuinely different names, so a phonetic
    #: hit is a lead, and a list that renders it like a name match invites the
    #: reader to treat it as one.
    matched: str


class SearchGroupOut(BaseModel):
    """A display group. Carries **no total** — a count is an existence leak.

    Empty groups are omitted from the response rather than returned empty,
    for the same reason: a present group with no hits *is* a count of zero.
    """

    group: str
    label: str
    hits: list[SearchHitOut]


class SearchResultsOut(BaseModel):
    """One ranked page, displayed as groups.

    There is no per-group cursor and no per-group limit. Groups are how a page
    is displayed, never how it is fetched: several independent cursors would
    leave informative gaps where restricted rows were removed, which is the
    pagination surface B-17 names (spec 11 §5.1).
    """

    query: str
    groups: list[SearchGroupOut]
    #: Present only when another page exists. Derived from fetching one row
    #: beyond the limit — never from a count.
    next_cursor: str | None = None
    stamp: AsOfStampOut | None = None


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
    #: The **validity** window — when the relationship was true. Filters
    #: `edge_projection.segment_*`, which is derived from `claim.valid_from/to`.
    valid_from: date | None = None
    valid_to: date | None = None
    #: The **event-time** window — when the thing happened (T62, spec 10 §11.2).
    #:
    #: A different axis from `valid_from`/`valid_to`, and kept separate for that
    #: reason: "was a member during 2019" and "an arrest happened in 2019" are
    #: different questions, and one parameter answering both would mean
    #: different things on different surfaces — the inconsistency T62 exists to
    #: remove. This is the window the map and the timeline share, applied here
    #: as a **claim filter** so an edge's support summary is computed from the
    #: same narrowed set the edge's visibility is.
    #:
    #: Intersection, not containment, and an **undated** claim is outside every
    #: bounded window (§11.2).
    event_from: datetime | None = None
    event_to: datetime | None = None
    #: The claim-recording snapshot (B-11, spec 09 §7). Closes the graph half of
    #: Phase 4's `?asOf=` carryover: a time-synced map beside a graph that
    #: silently answered as-of-now would be exactly the inconsistency this phase
    #: is trying to eliminate.
    as_of: datetime | None = None
    as_of_revision: int | None = None
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


class ObjectSetIn(BaseModel):
    """A new set. The AST is validated against the ontology before it is stored."""

    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    case_id: str | None = None
    #: The filter tree (spec 12 §2.1). A dict rather than a typed union here
    #: because the grammar is the authority: `aegis.sets.grammar.parse` refuses
    #: anything it does not recognise, with the path that refused it, and a
    #: second definition of the same shape in this file would be a second
    #: definition to keep in step.
    ast: dict[str, Any]
    #: Off by default (ADR-054). A saved set that widens when a domain module
    #: lands changes the meaning of findings people already acted on.
    track_interface_members: bool = False
    note: str | None = None


class ObjectSetVersionIn(BaseModel):
    ast: dict[str, Any]
    track_interface_members: bool = False
    note: str | None = None


class ObjectSetVersionOut(BaseModel):
    """One immutable version, as this reader may see it.

    A `property` node above the reader's clearance arrives shape-intact and
    value-empty — `{property, op, value: null, withheld: true}`. Removing it
    would misdescribe the set, since the evaluation still uses the condition;
    showing the value would be the leak B-17 names (spec 12 §5.2).
    """

    set_id: str
    version: int
    ast: dict[str, Any]
    ontology_version: str
    track_interface_members: bool
    as_of: datetime | None = None
    as_of_revision: int | None = None
    note: str | None = None
    created_by: str
    created_at: datetime


class ObjectSetOut(BaseModel):
    set_id: str
    name: str
    description: str | None = None
    case_id: str | None = None
    owner: str
    created_at: datetime
    latest: ObjectSetVersionOut


class ObjectSetPageOut(BaseModel):
    """Sets the caller may see. **No total** — a count is an existence leak."""

    items: list[ObjectSetOut]
    next_cursor: str | None = None


class ObjectSetMemberOut(BaseModel):
    entity_id: str
    label: str
    entity_type: str


class ObjectSetEvaluationOut(BaseModel):
    """What a set evaluates to **for this caller**.

    Never for its owner: a shared set is a shared question, not lent clearance
    (spec 12 §6). `truncated` is the honest alternative to a count — it says
    there is more without saying how much more.
    """

    set_id: str
    version: int
    members: list[ObjectSetMemberOut]
    truncated: bool
    #: SHA-256 over the sorted member ids. Two callers evaluating one set get
    #: different digests, which is what makes it usable as an analytic input:
    #: a finding computed under a narrower clearance is a different finding
    #: (ADR-055).
    evaluation_digest: str


class ObjectSetShareIn(BaseModel):
    user_sub: str
    #: `viewer` reads the definition, `evaluator` only runs it, `editor`
    #: writes a version. The weaker grant exists because running a saved query
    #: and reading it are different disclosures (spec 12 §5.2).
    relation: str = "viewer"
    revoke: bool = False


class ObjectSetNoticeOut(BaseModel):
    notice_id: str
    set_id: str
    version: int
    interface: str
    member: str
    ontology_version: str
    #: Whether this set actually widened, or merely could have.
    tracking: bool
    created_at: datetime


class AnalyticRunOut(BaseModel):
    """The manifest, as a reader sees it (spec 12 §8.2).

    Complete enough that "reproduce this" is a mechanical instruction, which
    is what ADR-055 replaced "rerunning the same inputs reproduces the
    finding" with — the second was not testable, because neither an object set
    nor a projection is immutable.
    """

    run_id: str
    method: str
    method_version: str
    #: Which library actually ran, with its version. A Leiden run and a
    #: Louvain fallback are different manifests, and therefore different runs.
    implementation: str
    parameters: dict[str, Any]
    #: Null means **unseeded** — recorded as such rather than pretending to a
    #: determinism the run did not have.
    seed: int | None = None
    input_kind: str
    object_set_id: str | None = None
    object_set_version: int | None = None
    evaluation_digest: str | None = None
    edge_digest: str
    #: *Which* projection was read — not whether it was fresh. Freshness is
    #: `is_stale`'s question and it answers a different one.
    projection_built_at_revision_id: int | None = None
    projection_builder_version: str | None = None
    projection_aggregation_method_version: str | None = None
    ontology_version: str
    identity_revision_id: int
    code_version: str
    settings_digest: str
    actor: str
    purpose: str | None = None
    #: The clearance and case membership the run saw. A finding computed under
    #: a narrower clearance is a different finding (Article VI).
    authorization_digest: str
    caveat_version: str
    started_at: datetime
    finished_at: datetime | None = None


class AnalyticFindingOut(BaseModel):
    """One result, carrying the caveat it was issued with (Article IX).

    `caveat_text` is stored on the row and returned from it — never looked up
    when it renders. There is no render path that fetches a caveat, so there
    is no render path that can fail to (spec 12 §9.3).
    """

    finding_id: str
    run_id: str
    finding_type: str
    subjects: list[str]
    value: dict[str, Any]
    caveat_text: str
    caveat_version: str
    finding_digest: str
    promoted_claim_id: str | None = None
    #: Derived from the claims that contributed, never chosen: a finding over
    #: restricted evidence is restricted.
    handling_code: str
    created_at: datetime


class AnalyticRunResultOut(BaseModel):
    """A run and what it found. The manifest always ships with the findings.

    Together rather than separately, because a finding without its manifest is
    a number whose provenance a reader has to go and look for — and the going
    and looking is exactly what does not happen.
    """

    run: AnalyticRunOut
    findings: list[AnalyticFindingOut]


class AnalyticRunIn(BaseModel):
    """What to run it over. Omitting the set runs over the whole readable graph."""

    object_set_id: str | None = None
    object_set_version: int | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class AnalyticFindingPageOut(BaseModel):
    items: list[AnalyticFindingOut]
    next_cursor: str | None = None
