"""Transactional Phase-1 write actions (speckit T7).

The service never commits a transaction it did not start.  This lets an API request
compose actions in a larger unit while preserving the core guarantee: domain rows,
authorization outbox rows, and the audit append share one database transaction.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
import secrets
import time
from pathlib import Path
from typing import Any, Iterator, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.audit import append as append_audit
from aegis.config import get_settings
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
    ReviewQueue,
    SourceRecord,
)

ASSERTION_TYPES = frozenset({"observed", "reported", "inferred", "assessed"})
CLAIM_RELATIONS = frozenset({"corroborates", "contradicts"})
CASE_MEMBER_RELATIONS = {
    "analyst": "analyst",
    "investigator": "investigator",
    "supervisor": "supervisor",
    "auditor": "auditor_grant",
}
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_REPO_ROOT = Path(__file__).resolve().parents[2]


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

    def __post_init__(self) -> None:
        if not self.actor.strip():
            raise ValueError("action actor must not be empty")


def new_id(prefix: str) -> str:
    """Generate a prefixed ULID without adding a runtime dependency."""
    value = (int(time.time() * 1000) << 80) | int.from_bytes(secrets.token_bytes(10), "big")
    encoded = ""
    for _ in range(26):
        encoded = _CROCKFORD[value & 31] + encoded
        value >>= 5
    return f"{prefix}_{encoded}"


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

    def _require_action(self, name: str) -> None:
        try:
            action = self.ontology.action(name)
        except OntologyError as exc:
            raise ActionValidationError(f"actions.{name}", "not declared in ontology") from exc
        if not action.audit:  # loader already rejects this; retain the write-side guard.
            raise ActionValidationError(f"actions.{name}.audit", "must be true")

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
        subject_id: str,
        predicate: str,
        record_id: str,
        assertion_type: str,
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
    ) -> Claim:
        try:
            predicate_spec = self.ontology.predicate(predicate)
        except OntologyError as exc:
            raise ActionValidationError(
                f"predicates.{predicate}", "not declared in ontology"
            ) from exc

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
            ontology_version=self.ontology.version,
        )
        self.session.add(row)
        self.session.flush()
        return row

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
        suggestion_id: str | None = None,
    ) -> ReviewQueue:
        self._require_action("submit_suggestion")
        self._validate_suggestion_payload(payload)
        if not producer.strip():
            raise ActionValidationError("review_queue.producer", "must not be empty")
        with self._transaction():
            row = ReviewQueue(
                suggestion_id=suggestion_id or new_id("sug"),
                payload=payload,
                producer=producer,
                producer_meta=producer_meta,
            )
            self.session.add(row)
            self.session.flush()
            self._audit(
                context,
                action="submit_suggestion",
                resource_type="review_queue",
                resource_id=row.suggestion_id,
                detail={"producer": producer},
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
        """Decide a suggestion.  ``edits`` lets the reviewer amend any claim
        field before acceptance (spec 04 §4); the accepted draft — edits
        included — is what gets validated, recorded, and kept on the row.
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
            result: Claim | None = None
            if decision == "accepted":
                draft = {**row.payload, **(edits or {})}
                self._validate_suggestion_payload(draft)
                try:
                    result = self._create_claim(**self._coerce_claim_payload(draft))
                except TypeError as exc:
                    raise ActionValidationError(
                        "review_queue.payload", f"invalid claim draft: {exc}"
                    ) from exc
                if edits:
                    row.payload = draft
            row.status = decision
            row.decided_by = context.actor
            row.decided_at = _utcnow()
            row.decision_note = note
            row.result_claim = result.claim_id if result is not None else None
            self.session.flush()
            self._audit(
                context,
                action="review_suggestion",
                resource_type="review_queue",
                resource_id=suggestion_id,
                case_id=result.case_id if result is not None else None,
                detail={
                    "decision": decision,
                    "result_claim": row.result_claim,
                    "edited_fields": sorted(edits) if edits else [],
                },
            )
        return row

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
