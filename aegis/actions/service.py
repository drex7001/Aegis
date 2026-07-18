"""Transactional Phase-1 write actions (speckit T7).

The service never commits a transaction it did not start.  This lets an API request
compose actions in a larger unit while preserving the core guarantee: domain rows,
authorization outbox rows, and the audit append share one database transaction.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterator, Literal, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.ids import new_id
from aegis.audit import append as append_audit
from aegis.config import get_settings
from aegis.er.adjudication import (
    ADJUDICATION_MODES,
    AdjudicationError,
    AdjudicationResult,
    confirm_match,
    mark_unresolved,
    reject_match,
    split_entity,
)
from aegis.er.canonical import canonical_entity
from aegis.er.ledger import (
    active_entity_for_mention,
    active_revision_id,
    open_membership,
)
from aegis.ontology import KNOWN_ROLES, Ontology, OntologyError, load
from aegis.store import (
    AuthzOutbox,
    CaseFile,
    CaseMember,
    Claim,
    ClaimRelation,
    CustodyEvent,
    Entity,
    EvidenceItem,
    Mention,
    ReviewQueue,
    SourceRecord,
)

ASSERTION_TYPES = frozenset({"observed", "reported", "inferred", "assessed"})
#: Claims that assert what a *source* said must be able to point at the words
#: (ADR-029 §1); inferred and assessed claims are the analyst's own reasoning.
ANCHOR_REQUIRED_ASSERTIONS = frozenset({"observed", "reported"})
#: ...unless a human entered the claim directly, in which case they are the
#: adjudicator and no extractor recorded an offset for them (spec 04 §1).
ANCHOR_EXEMPT_COLLECTION_METHODS = frozenset({"curated", "manual", None})
CLAIM_RELATIONS = frozenset({"corroborates", "contradicts"})
CASE_MEMBER_RELATIONS = {
    "analyst": "analyst",
    "investigator": "investigator",
    "supervisor": "supervisor",
    "auditor": "auditor_grant",
}
_REPO_ROOT = Path(__file__).resolve().parents[2]

#: ``suggestion_kind`` is a **closed, code-owned** list (ADR-031 §1) — not
#: ontology vocabulary — because each kind is a dispatch branch here.  Adding a
#: kind is a schema + mapping change, never a queue migration.
SUGGESTION_KINDS: dict[str, str] = {
    "claim_draft": "record_claim",
    "identity_candidate": "adjudicate_identity",
    "claim_relation": "link_claims",
}
SUGGESTION_SCHEMA_VERSION = 1


def suggestion_idempotency_key(
    *,
    kind: str,
    producer: str,
    producer_version: str,
    payload: dict[str, Any],
) -> str:
    """Stable digest of what a producer proposed (spec 02 §3.2, spec 04 §5).

    Re-running an extraction pass replays the same inputs, so it computes the
    same key and the UNIQUE constraint stops the replay from re-suggesting
    anything already decided.  Only the *proposal* is digested — never the
    reviewer's edits, which arrive after the key is fixed.
    """
    digest = json.dumps(payload, sort_keys=True, default=str)
    return sha256(
        f"{kind}|{producer}|{producer_version}|{digest}".encode()
    ).hexdigest()


class ActionValidationError(ValueError):
    """A write rejected before persistence, with a stable ontology/data path."""

    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


@dataclass(frozen=True, slots=True)
class ActionContext:
    actor: str
    purpose: str | None = None
    session_id: str | None = None
    case_id: str | None = None
    #: Roles the actor holds, for the ontology's per-action `roles` gate.
    #: Empty means "not supplied" and skips the check — the Phase-1 actions
    #: are gated at the API layer and pass no roles here.
    roles: frozenset[str] = frozenset()
    #: The second approver, where the ontology declares `dual_control_for`.
    second_actor: str | None = None

    def __post_init__(self) -> None:
        if not self.actor.strip():
            raise ValueError("action actor must not be empty")


def _default_ontology() -> Ontology:
    path = Path(get_settings().ontology_path)
    return load(path if path.is_absolute() else _REPO_ROOT / path)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ActionService:
    def __init__(self, session: Session, ontology: Ontology | None = None) -> None:
        self.session = session
        self.ontology = ontology or _default_ontology()

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        if self.session.in_transaction():
            # A SAVEPOINT makes the action atomic even if an outer request catches
            # the exception and continues its transaction.
            with self.session.begin_nested():
                yield
        else:
            with self.session.begin():
                yield

    def _require_action(
        self,
        name: str,
        context: ActionContext | None = None,
        *,
        dual_control_flags: Sequence[str] = (),
    ) -> None:
        """Gate a write on what the ontology declares about the action.

        ``context`` is optional only because the Phase-1 actions predate role
        enforcement here; the API layer gates them by role independently
        (spec 03 §3). Passing it enforces the ontology's own `roles` list at
        the write, which is what makes the declaration load-bearing rather
        than documentation (spec 05 §3.4).
        """
        try:
            action = self.ontology.action(name)
        except OntologyError as exc:
            raise ActionValidationError(f"actions.{name}", "not declared in ontology") from exc
        if not action.audit:  # loader already rejects this; retain the write-side guard.
            raise ActionValidationError(f"actions.{name}.audit", "must be true")
        if context is not None and action.roles and not (set(action.roles) & context.roles):
            raise ActionValidationError(
                f"actions.{name}.roles",
                f"requires one of {sorted(action.roles)}; actor holds "
                f"{sorted(context.roles) or 'none'}",
            )
        required = set(action.dual_control_for or ()) & set(dual_control_flags)
        if required and context is not None and context.second_actor is None:
            raise ActionValidationError(
                f"actions.{name}.dual_control_for",
                f"{sorted(required)} requires a second approver; the decision was "
                "not written",
            )
        if required and context is not None and context.second_actor == context.actor:
            raise ActionValidationError(
                f"actions.{name}.dual_control_for",
                "the second approver must be a different person",
            )

    def _handling(self, value: str, path: str = "handling_codes") -> None:
        if value not in self.ontology.handling_codes:
            raise ActionValidationError(
                f"{path}.{value}",
                f"not declared (expected one of {self.ontology.handling_codes})",
            )

    def _grade(self, dimension: str, value: str | None) -> None:
        if value is None:
            return
        allowed = self.ontology.grading.values_for(dimension)
        if value not in allowed:
            raise ActionValidationError(
                f"grading.{dimension}.{value}", f"not declared (expected one of {allowed})"
            )

    def _entity(self, entity_id: str, path: str) -> Entity:
        if not entity_id:
            # e.g. an extraction draft whose entity reference was never resolved
            raise ActionValidationError(path, "an entity id is required")
        entity = self.session.get(Entity, entity_id)
        if entity is None:
            raise ActionValidationError(path, f"entity {entity_id!r} does not exist")
        if entity.entity_type not in self.ontology.object_types:
            raise ActionValidationError(
                f"object_types.{entity.entity_type}", "entity type is not declared"
            )
        return entity

    def _audit(
        self,
        context: ActionContext,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        detail: dict[str, Any],
        case_id: str | None = None,
    ) -> None:
        append_audit(
            self.session,
            actor=context.actor,
            session_id=context.session_id,
            purpose=context.purpose,
            case_id=case_id if case_id is not None else context.case_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            decision="allow",
            detail=detail,
        )

    def _outbox(self, op: Literal["write", "delete"], tuple_: dict[str, str]) -> None:
        self.session.add(AuthzOutbox(op=op, fga_tuple=tuple_))

    def _create_claim(
        self,
        *,
        predicate: str,
        record_id: str,
        assertion_type: str,
        # Optional because a draft may name its subject by *mention* instead:
        # entity creation folds into acceptance (spec 02 §3.2).  Exactly one of
        # the two must arrive, which is checked below.
        subject_id: str | None = None,
        object_id: str | None = None,
        object_value: Any | None = None,
        claim_id: str | None = None,
        excerpt: str | None = None,
        collection_method: str | None = None,
        credibility_scheme: str | None = None,
        credibility_original: str | None = None,
        credibility_normalized: str = "cannot_judge",
        verification_status: str = "unverified",
        analytic_confidence: str | None = None,
        event_time_earliest: datetime | None = None,
        event_time_latest: datetime | None = None,
        valid_from: date | None = None,
        valid_to: date | None = None,
        handling_code: str = "open",
        case_id: str | None = None,
        jurisdiction: str | None = None,
        location_text: str | None = None,
        supersedes: str | None = None,
        subject_mention_id: str | None = None,
        object_mention_id: str | None = None,
        # Proposed type for an entity created from a mention.  The producer
        # knows it (an extractor labelled the node); the reviewer can edit it
        # before accepting.  Ignored when the argument is an existing entity.
        subject_entity_type: str | None = None,
        object_entity_type: str | None = None,
    ) -> Claim:
        try:
            predicate_spec = self.ontology.predicate(predicate)
        except OntologyError as exc:
            raise ActionValidationError(
                f"predicates.{predicate}", "not declared in ontology"
            ) from exc

        # Entity creation folds into acceptance (spec 02 §3.2): an argument
        # given as a mention rather than an entity is resolved — or, when the
        # mention has never been adjudicated, an entity is created for it here,
        # in this transaction.  There is no entity_draft kind precisely so that
        # a new entity always arrives attached to a claim about it.
        subject_id = subject_id or self._entity_from_mention(
            subject_mention_id,
            "claim.subject_id",
            predicate_spec.subject,
            subject_entity_type,
        )
        if object_id is None and object_value is None and object_mention_id is not None:
            object_id = self._entity_from_mention(
                object_mention_id,
                "claim.object_id",
                predicate_spec.entity_object_types,
                object_entity_type,
            )

        subject = self._entity(subject_id, "claim.subject_id")
        if subject.entity_type not in predicate_spec.subject:
            raise ActionValidationError(
                f"predicates.{predicate}.subject",
                f"entity type {subject.entity_type!r} is not allowed",
            )
        if (object_id is None) == (object_value is None):
            raise ActionValidationError(
                "claim.object", "exactly one of object_id or object_value is required"
            )

        if object_id is None:
            if not predicate_spec.allows_literal:
                raise ActionValidationError(
                    f"predicates.{predicate}.object", "requires an entity object_id"
                )
        else:
            if not predicate_spec.allows_entity:
                raise ActionValidationError(
                    f"predicates.{predicate}.object", "requires a literal object_value"
                )
            object_entity = self._entity(object_id, "claim.object_id")
            if object_entity.entity_type not in predicate_spec.entity_object_types:
                raise ActionValidationError(
                    f"predicates.{predicate}.object",
                    f"entity type {object_entity.entity_type!r} is not allowed",
                )
            if subject_id == object_id:
                raise ActionValidationError("claim.object_id", "self-claims are forbidden")
            if predicate_spec.symmetric and object_id < subject_id:
                subject_id, object_id = object_id, subject_id
                # The anchors travel with the arguments they anchor.  Leaving
                # them behind would attach each claim to the other side's
                # mention, which is worse than no anchor: it looks verified.
                subject_mention_id, object_mention_id = (
                    object_mention_id,
                    subject_mention_id,
                )

        if assertion_type not in ASSERTION_TYPES:
            raise ActionValidationError(
                f"claim.assertion_type.{assertion_type}",
                f"not supported (expected one of {sorted(ASSERTION_TYPES)})",
            )
        self._grade("credibility", credibility_normalized)
        self._grade("verification", verification_status)
        self._grade("analytic_confidence", analytic_confidence)
        if analytic_confidence is not None and assertion_type != "assessed":
            raise ActionValidationError(
                "claim.analytic_confidence", "is only valid for assessed claims"
            )
        self._handling(handling_code)
        if event_time_earliest and event_time_latest and event_time_latest < event_time_earliest:
            raise ActionValidationError(
                "claim.event_time_latest", "must be on or after event_time_earliest"
            )
        if valid_from and valid_to and valid_to < valid_from:
            raise ActionValidationError("claim.valid_to", "must be on or after valid_from")
        if self.session.get(SourceRecord, record_id) is None:
            raise ActionValidationError("claim.record_id", f"record {record_id!r} does not exist")
        if case_id is not None and self.session.get(CaseFile, case_id) is None:
            raise ActionValidationError("claim.case_id", f"case {case_id!r} does not exist")
        if supersedes is not None and self.session.get(Claim, supersedes) is None:
            raise ActionValidationError(
                "claim.supersedes", f"claim {supersedes!r} does not exist"
            )
        self._check_anchor("subject", subject_mention_id, subject_id)
        self._check_anchor("object", object_mention_id, object_id)
        self._require_anchors(
            assertion_type,
            collection_method,
            subject_mention_id=subject_mention_id,
            object_mention_id=object_mention_id,
            object_id=object_id,
        )

        row = Claim(
            claim_id=claim_id or new_id("clm"),
            subject_id=subject_id,
            predicate=predicate,
            object_id=object_id,
            object_value=object_value,
            assertion_type=assertion_type,
            record_id=record_id,
            excerpt=excerpt,
            collection_method=collection_method,
            credibility_scheme=credibility_scheme,
            credibility_original=credibility_original,
            credibility_normalized=credibility_normalized,
            verification_status=verification_status,
            analytic_confidence=analytic_confidence,
            event_time_earliest=event_time_earliest,
            event_time_latest=event_time_latest,
            valid_from=valid_from,
            valid_to=valid_to,
            handling_code=handling_code,
            case_id=case_id,
            jurisdiction=jurisdiction,
            location_text=location_text,
            supersedes=supersedes,
            subject_mention_id=subject_mention_id,
            object_mention_id=object_mention_id,
            # What identity meant when the claim was made (ADR-029 §2).  A
            # record, not a resolution instruction: projections resolve through
            # the *active* revision, and only an as-of query pins this one.
            identity_revision_id=active_revision_id(self.session),
            ontology_version=self.ontology.version,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def _require_anchors(
        self,
        assertion_type: str,
        collection_method: str | None,
        *,
        subject_mention_id: str | None,
        object_mention_id: str | None,
        object_id: str | None,
    ) -> None:
        """ADR-029 rule 1, enforced here rather than by a CHECK.

        A claim that says the source *observed* or *reported* something must be
        able to point at the words.  ``inferred`` and ``assessed`` claims are
        an analyst's own reasoning and legitimately have no mention, so the
        rule keys off ``assertion_type`` — semantics the database does not own.

        Curated and manual collection are exempt for the same reason: a human
        entering a claim from a document they read is the adjudicator, and no
        extractor recorded an offset for them.
        """
        if assertion_type not in ANCHOR_REQUIRED_ASSERTIONS:
            return
        if collection_method in ANCHOR_EXEMPT_COLLECTION_METHODS:
            return
        if subject_mention_id is None:
            raise ActionValidationError(
                "claim.subject_mention_id",
                f"an anchor is required for {assertion_type!r} claims — the "
                "source text the subject was read from",
            )
        if object_id is not None and object_mention_id is None:
            raise ActionValidationError(
                "claim.object_mention_id",
                f"an anchor is required for {assertion_type!r} claims — the "
                "source text the object was read from",
            )

    def _entity_from_mention(
        self,
        mention_id: str | None,
        path: str,
        allowed_types: Sequence[str],
        requested_type: str | None = None,
    ) -> str | None:
        """Resolve a mention to its entity, creating one if nobody has ruled yet.

        Creating an entity for an unadjudicated mention is **not** a merge: it
        is a single-mention entity at the current revision, which is exactly
        what "this text names someone we have no other record of" means
        (spec 02 §3.2).  Merging it into anything later is an
        ``adjudicate_identity`` decision like any other.
        """
        if mention_id is None:
            return None
        mention = self.session.get(Mention, mention_id)
        if mention is None:
            raise ActionValidationError(path, f"mention {mention_id!r} does not exist")
        existing = active_entity_for_mention(self.session, mention_id)
        if existing is not None:
            return existing
        if not allowed_types:
            raise ActionValidationError(
                path, "this predicate takes no entity argument to create"
            )
        entity = Entity(
            entity_id=new_id("ent"),
            entity_type=self._entity_type_for(allowed_types, requested_type, path),
            label=mention.raw_text,  # display only; rebuilt from name claims
        )
        self.session.add(entity)
        self.session.flush()
        open_membership(
            self.session, mention_id=mention_id, entity_id=entity.entity_id
        )
        return entity.entity_id

    @staticmethod
    def _entity_type_for(
        allowed_types: Sequence[str], requested_type: str | None, path: str
    ) -> str:
        """The type of an entity created from a mention.

        The predicate narrows the choice; where it still leaves more than one,
        the producer must have proposed one.  Guessing here would silently
        decide whether a name is a person or an organization — a judgement the
        text supports and the schema does not.
        """
        candidates = [value for value in allowed_types if value != "literal"]
        if requested_type is not None:
            if requested_type not in candidates:
                raise ActionValidationError(
                    path,
                    f"entity type {requested_type!r} is not allowed here "
                    f"(expected one of {sorted(candidates)})",
                )
            return requested_type
        if len(candidates) != 1:
            raise ActionValidationError(
                path,
                "cannot create an entity from a mention: the predicate allows "
                f"{sorted(candidates)}, so the type must be proposed explicitly",
            )
        return candidates[0]

    def _check_anchor(
        self, role: Literal["subject", "object"], mention_id: str | None, entity_id: str | None
    ) -> None:
        """A mention anchor must be real and must not contradict its argument.

        The DB enforces "no object anchor without an object entity"; what it
        cannot express is that an anchor already adjudicated onto *another*
        entity makes the claim's own attribution incoherent (spec 02 §3.1).
        An anchor on a mention nobody has ruled on yet is fine — that is the
        normal state of freshly extracted text.
        """
        if mention_id is None:
            return
        if entity_id is None:
            raise ActionValidationError(
                f"claim.{role}_mention_id",
                f"cannot anchor a {role} that is not an entity argument",
            )
        if self.session.get(Mention, mention_id) is None:
            raise ActionValidationError(
                f"claim.{role}_mention_id", f"mention {mention_id!r} does not exist"
            )
        owner = active_entity_for_mention(self.session, mention_id)
        if owner is None:
            # Writing this claim *is* the statement that this text names this
            # entity, so the mention attaches here rather than being left
            # belonging to nothing.  Not an adjudication: an unresolved mention
            # joining an entity is resolution (spec 02 §3.2), and a mention
            # that already belongs elsewhere is rejected below instead.
            open_membership(self.session, mention_id=mention_id, entity_id=entity_id)
            return
        if owner != entity_id:
            raise ActionValidationError(
                f"claim.{role}_mention_id",
                f"mention {mention_id!r} belongs to entity {owner!r}, not {entity_id!r}",
            )

    def record_claim(self, context: ActionContext, **claim: Any) -> Claim:
        self._require_action("record_claim")
        with self._transaction():
            row = self._create_claim(**claim)
            self._audit(
                context,
                action="record_claim",
                resource_type="claim",
                resource_id=row.claim_id,
                case_id=row.case_id,
                detail={
                    "subject_id": row.subject_id,
                    "predicate": row.predicate,
                    "object_id": row.object_id,
                    "ontology_version": row.ontology_version,
                },
            )
        return row

    def adjudicate_identity(
        self,
        context: ActionContext,
        *,
        mode: str,
        parent_revision_id: int,
        note: str,
        protected_person: bool = False,
        **params: Any,
    ) -> AdjudicationResult:
        """The single action behind confirm / reject / split / unresolved.

        One transaction writes the decision, its revision, the membership
        changes and the audit row (spec 05 §4).  ``decided_by`` is
        ``context.actor`` and nothing else — a rule is never a decider
        (ADR-027, Article VII).
        """
        self._require_action(
            "adjudicate_identity",
            context,
            dual_control_flags=("protected_person",) if protected_person else (),
        )
        if mode not in ADJUDICATION_MODES:
            raise ActionValidationError(
                f"adjudicate_identity.mode.{mode}",
                f"not supported (expected one of {sorted(ADJUDICATION_MODES)})",
            )
        # An evidence note is required on every mode, always (spec 05 §2): a
        # merge nobody explained is a merge nobody can review later.
        if not note.strip():
            raise ActionValidationError(
                "adjudicate_identity.note", "an evidence note is required"
            )
        handler = {
            "confirm_match": confirm_match,
            "reject_match": reject_match,
            "split_entity": split_entity,
            "mark_unresolved": mark_unresolved,
        }[mode]
        with self._transaction():
            try:
                result = handler(
                    self.session,
                    actor=context.actor,
                    note=note,
                    parent_revision_id=parent_revision_id,
                    **params,
                )
            except TypeError as exc:
                raise ActionValidationError(
                    f"adjudicate_identity.{mode}", f"invalid arguments: {exc}"
                ) from exc
            except AdjudicationError as exc:
                raise ActionValidationError(f"adjudicate_identity.{mode}", str(exc)) from exc
            # Claims a split could not attribute are queued for a human, never
            # reassigned (spec 02 §3.1 rule 4).
            for claim_id in result.unattributable_claims:
                self._queue_reattribution(context, claim_id, result)
            self._audit(
                context,
                action="adjudicate_identity",
                resource_type="identity_decision",
                resource_id=result.decision.decision_id,
                detail={
                    "mode": mode,
                    "note": note,
                    "parent_revision_id": parent_revision_id,
                    "result_revision_id": result.revision.revision_id,
                    "moved_mentions": result.moved_mentions,
                    "surviving_entity_id": result.surviving_entity_id,
                    "new_entity_id": result.new_entity_id,
                    "second_actor": context.second_actor,
                    "unattributable_claims": result.unattributable_claims,
                },
            )
        return result

    def _queue_reattribution(
        self, context: ActionContext, claim_id: str, result: AdjudicationResult
    ) -> None:
        """Surface an unanchored claim a split could not attribute.

        The queue row is a **`claim_draft`**, not a bespoke kind: the correction
        is a replacement claim pointing at the other entity and superseding this
        one.  That keeps the closed kind list at three (ADR-031 §1) *and*
        honours "no claim row is ever rewritten by an identity decision" — the
        original stays exactly as written, and a human decides whether a
        superseding claim should exist.
        """
        claim = self.session.get(Claim, claim_id)
        if claim is None or result.new_entity_id is None:
            return
        # Repoint whichever argument actually named the split entity. A claim
        # can reach here from either position (a symmetric predicate is
        # order-normalized at write time) and may name an id that was absorbed
        # by an earlier merge, so both ends are compared *after* resolution.
        # Repointing the subject unconditionally would propose a claim about
        # the wrong pair.
        surviving = result.surviving_entity_id
        subject_id = claim.subject_id
        object_id = claim.object_id
        subject_resolves = canonical_entity(self.session, claim.subject_id)
        object_resolves = (
            canonical_entity(self.session, claim.object_id)
            if claim.object_id is not None
            else None
        )
        if subject_resolves == surviving and claim.subject_mention_id is None:
            subject_id = result.new_entity_id
        elif object_resolves == surviving and claim.object_mention_id is None:
            object_id = result.new_entity_id
        payload = {
            "subject_id": subject_id,
            "predicate": claim.predicate,
            "object_id": object_id,
            "object_value": claim.object_value,
            "assertion_type": claim.assertion_type,
            "record_id": claim.record_id,
            "collection_method": claim.collection_method,
            "excerpt": claim.excerpt,
            "supersedes": claim.claim_id,
        }
        self.submit_suggestion(
            context,
            payload={key: value for key, value in payload.items() if value is not None},
            suggestion_kind="claim_draft",
            producer="split-readjudication",
            producer_version=result.decision.decision_id,
            producer_meta={
                "reason": "unanchored claim on a split entity (spec 02 §3.1 rule 4)",
                "decision_id": result.decision.decision_id,
                "original_claim_id": claim.claim_id,
                "candidate_entities": [
                    result.surviving_entity_id,
                    result.new_entity_id,
                ],
            },
            record_id=claim.record_id,
            case_id=claim.case_id,
        )

    def retract_claim(
        self, context: ActionContext, *, claim_id: str, reason: str
    ) -> Claim:
        self._require_action("retract_claim")
        if not reason.strip():
            raise ActionValidationError("claim.retraction_reason", "must not be empty")
        with self._transaction():
            row = self.session.get(Claim, claim_id)
            if row is None:
                raise ActionValidationError("claim.claim_id", f"claim {claim_id!r} does not exist")
            if row.retracted_at is not None:
                raise ActionValidationError("claim.retracted_at", "claim is already retracted")
            row.retracted_at = _utcnow()
            row.retraction_reason = reason
            self.session.flush()
            self._audit(
                context,
                action="retract_claim",
                resource_type="claim",
                resource_id=claim_id,
                case_id=row.case_id,
                detail={"reason": reason},
            )
        return row

    def link_claims(
        self,
        context: ActionContext,
        *,
        from_claim: str,
        to_claim: str,
        relation: str,
    ) -> ClaimRelation:
        self._require_action("link_claims")
        if relation not in CLAIM_RELATIONS:
            raise ActionValidationError(
                f"claim_relation.relation.{relation}",
                f"not supported (expected one of {sorted(CLAIM_RELATIONS)})",
            )
        if from_claim == to_claim:
            raise ActionValidationError("claim_relation.to_claim", "cannot link a claim to itself")
        with self._transaction():
            left = self.session.get(Claim, from_claim)
            right = self.session.get(Claim, to_claim)
            if left is None:
                raise ActionValidationError("claim_relation.from_claim", "claim does not exist")
            if right is None:
                raise ActionValidationError("claim_relation.to_claim", "claim does not exist")
            row = ClaimRelation(
                from_claim=from_claim,
                to_claim=to_claim,
                relation=relation,
                created_by=context.actor,
            )
            self.session.add(row)
            self.session.flush()
            resource_id = f"{from_claim}:{relation}:{to_claim}"
            self._audit(
                context,
                action="link_claims",
                resource_type="claim_relation",
                resource_id=resource_id,
                case_id=left.case_id or right.case_id,
                detail={"from_claim": from_claim, "to_claim": to_claim, "relation": relation},
            )
        return row

    def _validate_suggestion_payload(self, payload: dict[str, Any]) -> None:
        predicate = payload.get("predicate")
        if predicate is not None and predicate not in self.ontology.predicates:
            raise ActionValidationError(f"predicates.{predicate}", "not declared in ontology")
        for dimension, field in (
            ("credibility", "credibility_normalized"),
            ("verification", "verification_status"),
            ("analytic_confidence", "analytic_confidence"),
        ):
            if field in payload:
                self._grade(dimension, payload[field])
        if "handling_code" in payload:
            self._handling(payload["handling_code"])

    def submit_suggestion(
        self,
        context: ActionContext,
        *,
        payload: dict[str, Any],
        producer: str,
        producer_meta: dict[str, Any],
        suggestion_kind: str = "claim_draft",
        producer_version: str = "unversioned",
        record_id: str | None = None,
        case_id: str | None = None,
        idempotency_key: str | None = None,
        supersedes: str | None = None,
        expires_at: datetime | None = None,
        suggestion_id: str | None = None,
    ) -> ReviewQueue:
        self._require_action("submit_suggestion")
        if suggestion_kind not in SUGGESTION_KINDS:
            raise ActionValidationError(
                f"review_queue.suggestion_kind.{suggestion_kind}",
                f"not a known kind (expected one of {sorted(SUGGESTION_KINDS)})",
            )
        if suggestion_kind == "claim_draft":
            self._validate_suggestion_payload(payload)
        if not producer.strip():
            raise ActionValidationError("review_queue.producer", "must not be empty")
        if not producer_version.strip():
            raise ActionValidationError("review_queue.producer_version", "must not be empty")
        with self._transaction():
            row = ReviewQueue(
                suggestion_id=suggestion_id or new_id("sug"),
                suggestion_kind=suggestion_kind,
                schema_version=SUGGESTION_SCHEMA_VERSION,
                payload=payload,
                target_action=SUGGESTION_KINDS[suggestion_kind],
                producer=producer,
                producer_version=producer_version,
                producer_meta=producer_meta,
                record_id=record_id if record_id is not None else payload.get("record_id"),
                case_id=case_id if case_id is not None else payload.get("case_id"),
                idempotency_key=idempotency_key
                or suggestion_idempotency_key(
                    kind=suggestion_kind,
                    producer=producer,
                    producer_version=producer_version,
                    payload=payload,
                ),
                supersedes=supersedes,
                expires_at=expires_at,
            )
            self.session.add(row)
            self.session.flush()
            self._audit(
                context,
                action="submit_suggestion",
                resource_type="review_queue",
                resource_id=row.suggestion_id,
                detail={
                    "producer": producer,
                    "producer_version": producer_version,
                    "suggestion_kind": suggestion_kind,
                },
            )
        return row

    @staticmethod
    def _coerce_claim_payload(payload: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        for field in ("event_time_earliest", "event_time_latest"):
            value = result.get(field)
            if isinstance(value, str):
                result[field] = datetime.fromisoformat(value.replace("Z", "+00:00"))
        for field in ("valid_from", "valid_to"):
            value = result.get(field)
            if isinstance(value, str):
                result[field] = date.fromisoformat(value)
        return result

    def review_suggestion(
        self,
        context: ActionContext,
        *,
        suggestion_id: str,
        decision: Literal["accepted", "rejected"],
        note: str | None = None,
        edits: dict[str, Any] | None = None,
    ) -> ReviewQueue:
        """Decide a suggestion.  ``edits`` lets the reviewer amend any field
        before acceptance (spec 04 §4); the accepted draft — edits included —
        is what gets validated, recorded, and kept on the row.

        Acceptance **dispatches through the kind's declared action** with the
        reviewer as actor (ADR-031 §2); this method never writes a canonical
        table itself.  That is what makes Article VII's "only a human-executed
        action writes canon" mechanically checkable per kind.
        """
        self._require_action("review_suggestion")
        if decision not in {"accepted", "rejected"}:
            raise ActionValidationError(
                f"review_queue.status.{decision}", "must be accepted or rejected"
            )
        if edits and decision != "accepted":
            raise ActionValidationError(
                "review_queue.edits", "edits are only valid when accepting"
            )
        with self._transaction():
            row = self.session.get(ReviewQueue, suggestion_id)
            if row is None:
                raise ActionValidationError(
                    "review_queue.suggestion_id", f"suggestion {suggestion_id!r} does not exist"
                )
            if row.status != "suggested":
                raise ActionValidationError("review_queue.status", "suggestion is already decided")
            detail: dict[str, Any] = {
                "decision": decision,
                "suggestion_kind": row.suggestion_kind,
                "target_action": row.target_action,
                "edited_fields": sorted(edits) if edits else [],
            }
            case_id: str | None = None
            if decision == "accepted":
                draft = {**row.payload, **(edits or {})}
                case_id = self._dispatch_acceptance(context, row, draft)
                if edits:
                    row.payload = draft
                detail["result_claim_id"] = row.result_claim_id
                detail["result_decision"] = row.result_decision_id
                detail["result_relation"] = row.result_relation
            row.status = decision
            row.decided_by = context.actor
            row.decided_at = _utcnow()
            row.decision_note = note
            self.session.flush()
            self._audit(
                context,
                action="review_suggestion",
                resource_type="review_queue",
                resource_id=suggestion_id,
                case_id=case_id,
                detail=detail,
            )
        return row

    def _dispatch_acceptance(
        self, context: ActionContext, row: ReviewQueue, draft: dict[str, Any]
    ) -> str | None:
        """Run the accepted draft through ``row.target_action``.

        Returns the case the result belongs to, for the audit row.  Each branch
        sets exactly one typed result column — the DB enforces that count.
        """
        if row.suggestion_kind == "claim_draft":
            self._validate_suggestion_payload(draft)
            try:
                claim = self._create_claim(**self._coerce_claim_payload(draft))
            except TypeError as exc:
                raise ActionValidationError(
                    "review_queue.payload", f"invalid claim draft: {exc}"
                ) from exc
            row.result_claim_id = claim.claim_id
            return claim.case_id
        if row.suggestion_kind == "claim_relation":
            try:
                relation = ClaimRelation(
                    from_claim=draft["from_claim"],
                    to_claim=draft["to_claim"],
                    relation=draft["relation"],
                    created_by=context.actor,
                )
            except KeyError as exc:
                raise ActionValidationError(
                    "review_queue.payload", f"claim_relation draft is missing {exc}"
                ) from exc
            if relation.relation not in CLAIM_RELATIONS:
                raise ActionValidationError(
                    f"claim_relation.relation.{relation.relation}",
                    f"not supported (expected one of {sorted(CLAIM_RELATIONS)})",
                )
            for field in ("from_claim", "to_claim"):
                if self.session.get(Claim, getattr(relation, field)) is None:
                    raise ActionValidationError(
                        f"claim_relation.{field}", "claim does not exist"
                    )
            self.session.add(relation)
            self.session.flush()
            row.result_relation = {
                "from_claim": relation.from_claim,
                "to_claim": relation.to_claim,
                "relation": relation.relation,
            }
            return None
        # identity_candidate dispatches to adjudicate_identity, which lands in
        # T20 with the ledger write and the scoped concurrency check.  Nothing
        # produces this kind yet (T18/T19 do), so this is an unreachable
        # branch guarding against a producer arriving before its consumer.
        raise ActionValidationError(
            f"review_queue.suggestion_kind.{row.suggestion_kind}",
            f"acceptance dispatches to {row.target_action!r}, which is not "
            "implemented until T20",
        )

    def register_evidence(
        self,
        context: ActionContext,
        *,
        description: str,
        evidence_id: str | None = None,
        case_id: str | None = None,
        record_id: str | None = None,
        content_hash: str | None = None,
        storage_uri: str | None = None,
        acquired_at: datetime | None = None,
        acquired_by: str | None = None,
        legal_basis: str | None = None,
        handling_code: str = "restricted",
    ) -> EvidenceItem:
        self._require_action("register_evidence")
        self._handling(handling_code)
        if not description.strip():
            raise ActionValidationError("evidence_item.description", "must not be empty")
        if (content_hash is None) != (storage_uri is None):
            raise ActionValidationError(
                "evidence_item.content_hash", "content_hash and storage_uri must be provided together"
            )
        with self._transaction():
            if case_id is not None and self.session.get(CaseFile, case_id) is None:
                raise ActionValidationError("evidence_item.case_id", "case does not exist")
            if record_id is not None and self.session.get(SourceRecord, record_id) is None:
                raise ActionValidationError("evidence_item.record_id", "record does not exist")
            row = EvidenceItem(
                evidence_id=evidence_id or new_id("evd"),
                case_id=case_id,
                record_id=record_id,
                description=description,
                content_hash=content_hash,
                storage_uri=storage_uri,
                acquired_at=acquired_at,
                acquired_by=acquired_by or context.actor,
                legal_basis=legal_basis,
                handling_code=handling_code,
            )
            self.session.add(row)
            if case_id is not None:
                self._outbox(
                    "write",
                    {
                        "user": f"case:{case_id}",
                        "relation": "case",
                        "object": f"evidence_item:{row.evidence_id}",
                    },
                )
            self.session.flush()
            self._audit(
                context,
                action="register_evidence",
                resource_type="evidence_item",
                resource_id=row.evidence_id,
                case_id=case_id,
                detail={"content_hash": content_hash, "physical": content_hash is None},
            )
        return row

    def add_custody_event(
        self,
        context: ActionContext,
        *,
        evidence_id: str,
        to_actor: str,
        occurred_at: datetime,
        purpose: str,
        from_actor: str | None = None,
        hash_checked: bool = False,
        note: str | None = None,
    ) -> CustodyEvent:
        self._require_action("transfer_custody")
        if not to_actor.strip():
            raise ActionValidationError("custody_event.to_actor", "must not be empty")
        if not purpose.strip():
            raise ActionValidationError("custody_event.purpose", "must not be empty")
        if occurred_at.tzinfo is None:
            raise ActionValidationError("custody_event.occurred_at", "must be timezone-aware")
        with self._transaction():
            evidence = self.session.scalar(
                select(EvidenceItem)
                .where(EvidenceItem.evidence_id == evidence_id)
                .with_for_update()
            )
            if evidence is None:
                raise ActionValidationError("custody_event.evidence_id", "evidence does not exist")
            previous = self.session.scalar(
                select(CustodyEvent)
                .where(CustodyEvent.evidence_id == evidence_id)
                .order_by(CustodyEvent.seq.desc())
                .limit(1)
            )
            if previous is None:
                if from_actor is not None:
                    raise ActionValidationError(
                        "custody_event.from_actor", "must be null for the first custody event"
                    )
                seq = 1
                actual_from = None
            else:
                actual_from = previous.to_actor
                if from_actor is not None and from_actor != actual_from:
                    raise ActionValidationError(
                        "custody_event.from_actor",
                        f"must match current custodian {actual_from!r}",
                    )
                if occurred_at < previous.occurred_at:
                    raise ActionValidationError(
                        "custody_event.occurred_at", "must not precede the previous event"
                    )
                if to_actor == actual_from:
                    raise ActionValidationError(
                        "custody_event.to_actor", "must differ from the current custodian"
                    )
                seq = previous.seq + 1
                self._outbox(
                    "delete",
                    {
                        "user": f"user:{actual_from}",
                        "relation": "custodian",
                        "object": f"evidence_item:{evidence_id}",
                    },
                )
            row = CustodyEvent(
                evidence_id=evidence_id,
                seq=seq,
                from_actor=actual_from,
                to_actor=to_actor,
                occurred_at=occurred_at,
                purpose=purpose,
                hash_checked=hash_checked,
                note=note,
            )
            self.session.add(row)
            self._outbox(
                "write",
                {
                    "user": f"user:{to_actor}",
                    "relation": "custodian",
                    "object": f"evidence_item:{evidence_id}",
                },
            )
            self.session.flush()
            self._audit(
                context,
                action="transfer_custody",
                resource_type="custody_event",
                resource_id=f"{evidence_id}:{seq}",
                case_id=evidence.case_id,
                detail={"from_actor": actual_from, "to_actor": to_actor, "seq": seq},
            )
        return row

    transfer_custody = add_custody_event

    def release_quarantine(
        self,
        context: ActionContext,
        *,
        record_id: str,
        note: str,
    ) -> SourceRecord:
        """Release a quarantined source record back to ``landed`` (spec 04 §3)."""
        self._require_action("release_quarantine")
        if not note.strip():
            raise ActionValidationError("source_record.release_note", "must not be empty")
        with self._transaction():
            record = self.session.get(SourceRecord, record_id)
            if record is None:
                raise ActionValidationError(
                    "source_record.record_id", f"record {record_id!r} does not exist"
                )
            if record.status != "quarantined":
                raise ActionValidationError(
                    "source_record.status", "record is not quarantined"
                )
            reason = record.quarantine_reason
            record.status = "landed"
            record.quarantine_reason = None
            self.session.flush()
            self._audit(
                context,
                action="release_quarantine",
                resource_type="source_record",
                resource_id=record_id,
                detail={"note": note, "was": reason},
            )
        return record

    def open_case(
        self,
        context: ActionContext,
        *,
        title: str,
        purpose: str,
        handling_code: str = "open",
        case_id: str | None = None,
    ) -> CaseFile:
        self._require_action("open_case")
        self._handling(handling_code)
        if not title.strip():
            raise ActionValidationError("case_file.title", "must not be empty")
        if not purpose.strip():
            raise ActionValidationError("case_file.purpose", "must not be empty")
        with self._transaction():
            row = CaseFile(
                case_id=case_id or new_id("cas"),
                title=title,
                purpose=purpose,
                handling_code=handling_code,
                opened_by=context.actor,
            )
            self.session.add(row)
            self.session.flush()
            self._audit(
                context,
                action="open_case",
                resource_type="case_file",
                resource_id=row.case_id,
                case_id=row.case_id,
                detail={"title": title, "handling_code": handling_code},
            )
        return row

    def assign_case_member(
        self,
        context: ActionContext,
        *,
        case_id: str,
        user_id: str,
        role: str,
    ) -> CaseMember:
        self._require_action("assign_case_member")
        if role not in KNOWN_ROLES:
            raise ActionValidationError(f"roles.{role}", "not a platform role")
        if role not in CASE_MEMBER_RELATIONS:
            raise ActionValidationError(
                f"case_member.role.{role}", "cannot be assigned as a case membership"
            )
        if not user_id.strip():
            raise ActionValidationError("case_member.user_id", "must not be empty")
        with self._transaction():
            if self.session.get(CaseFile, case_id) is None:
                raise ActionValidationError("case_member.case_id", "case does not exist")
            row = self.session.get(CaseMember, (case_id, user_id))
            old_role = row.role if row is not None else None
            if old_role == role:
                raise ActionValidationError("case_member.role", "user already has this case role")
            if row is None:
                row = CaseMember(case_id=case_id, user_id=user_id, role=role)
                self.session.add(row)
            else:
                self._outbox(
                    "delete",
                    {
                        "user": f"user:{user_id}",
                        "relation": CASE_MEMBER_RELATIONS[old_role],
                        "object": f"case:{case_id}",
                    },
                )
                row.role = role
            self._outbox(
                "write",
                {
                    "user": f"user:{user_id}",
                    "relation": CASE_MEMBER_RELATIONS[role],
                    "object": f"case:{case_id}",
                },
            )
            self.session.flush()
            self._audit(
                context,
                action="assign_case_member",
                resource_type="case_member",
                resource_id=f"{case_id}:{user_id}",
                case_id=case_id,
                detail={"old_role": old_role, "role": role, "user_id": user_id},
            )
        return row

    def remove_case_member(
        self,
        context: ActionContext,
        *,
        case_id: str,
        user_id: str,
    ) -> CaseMember:
        self._require_action("remove_case_member")
        if not user_id.strip():
            raise ActionValidationError("case_member.user_id", "must not be empty")
        with self._transaction():
            row = self.session.get(CaseMember, (case_id, user_id))
            if row is None:
                raise ActionValidationError("case_member", "membership does not exist")
            relation = CASE_MEMBER_RELATIONS.get(row.role)
            if relation is None:
                raise ActionValidationError(
                    f"case_member.role.{row.role}", "cannot be revoked as a case membership"
                )
            old_role = row.role
            self._outbox(
                "delete",
                {
                    "user": f"user:{user_id}",
                    "relation": relation,
                    "object": f"case:{case_id}",
                },
            )
            self.session.delete(row)
            self.session.flush()
            self._audit(
                context,
                action="remove_case_member",
                resource_type="case_member",
                resource_id=f"{case_id}:{user_id}",
                case_id=case_id,
                detail={"old_role": old_role, "user_id": user_id},
            )
        return row


def _service(session: Session, ontology: Ontology | None) -> ActionService:
    return ActionService(session, ontology)


def record_claim(session: Session, context: ActionContext, *, ontology: Ontology | None = None, **kwargs: Any) -> Claim:
    return _service(session, ontology).record_claim(context, **kwargs)


def retract_claim(session: Session, context: ActionContext, *, ontology: Ontology | None = None, **kwargs: Any) -> Claim:
    return _service(session, ontology).retract_claim(context, **kwargs)


def link_claims(session: Session, context: ActionContext, *, ontology: Ontology | None = None, **kwargs: Any) -> ClaimRelation:
    return _service(session, ontology).link_claims(context, **kwargs)


def submit_suggestion(session: Session, context: ActionContext, *, ontology: Ontology | None = None, **kwargs: Any) -> ReviewQueue:
    return _service(session, ontology).submit_suggestion(context, **kwargs)


def review_suggestion(session: Session, context: ActionContext, *, ontology: Ontology | None = None, **kwargs: Any) -> ReviewQueue:
    return _service(session, ontology).review_suggestion(context, **kwargs)


def register_evidence(session: Session, context: ActionContext, *, ontology: Ontology | None = None, **kwargs: Any) -> EvidenceItem:
    return _service(session, ontology).register_evidence(context, **kwargs)


def add_custody_event(session: Session, context: ActionContext, *, ontology: Ontology | None = None, **kwargs: Any) -> CustodyEvent:
    return _service(session, ontology).add_custody_event(context, **kwargs)


def open_case(session: Session, context: ActionContext, *, ontology: Ontology | None = None, **kwargs: Any) -> CaseFile:
    return _service(session, ontology).open_case(context, **kwargs)


def assign_case_member(session: Session, context: ActionContext, *, ontology: Ontology | None = None, **kwargs: Any) -> CaseMember:
    return _service(session, ontology).assign_case_member(context, **kwargs)


def remove_case_member(session: Session, context: ActionContext, *, ontology: Ontology | None = None, **kwargs: Any) -> CaseMember:
    return _service(session, ontology).remove_case_member(context, **kwargs)
