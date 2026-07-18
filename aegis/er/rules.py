"""Deterministic ER rules → **candidates**, never merges (T18; spec 05 §3.1).

Nothing in this module changes identity.  Every rule writes an
:class:`~aegis.store.ErCandidate` row and stops; a membership only moves when a
human executes ``adjudicate_identity`` (ADR-027, Article VII).  The value a
deterministic rule adds is *rank*, not authority: an exact registry-identifier
match is pre-verified, so a reviewer can confirm a batch of them in one action
instead of one at a time — but it is still the reviewer who decides.

Two rule families, and the gap between them is the point:

* **Identifier match** — two mentions whose entities carry the same registry
  identifier.  Pre-verified.  The engine names no identifier itself: it asks
  the ontology which predicates are declared ``identifier: true``, so a new
  domain adds identifiers by declaring them (Article XIV).
* **Same ``norm_key`` inside one document** — ranked above cross-document noise
  and **never** pre-verified.  One document listing a name twice is weak
  evidence: documents do list different people who share a common name.

Cross-document name similarity is deliberately absent.  It is Splink's job
(T19), where it arrives with a score and a per-feature waterfall instead of a
bare assertion that two slugs matched.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.actions.ids import new_id
from aegis.er.settings import (
    IDENTIFIER_RULE_PREFIX,
    RULES_VERSION,
    SAME_KEY_IN_DOCUMENT_RULE,
)
from aegis.ontology import Ontology
from aegis.store import (
    Claim,
    ErCandidate,
    IdentityMembership,
    IdentityNegativeConstraint,
    Mention,
)


@dataclass
class RuleRunReport:
    """What one pass of the rule engine proposed, and what it refused to."""

    emitted: int = 0
    pre_verified: int = 0
    already_open: int = 0  # the pair is already awaiting a human
    suppressed_conflict: int = 0  # issuer or validity disagreement (H-07)
    suppressed_constraint: int = 0  # a human already rejected this pair
    same_entity: int = 0  # nothing to propose — already one entity
    candidates: list[ErCandidate] = field(default_factory=list)

    def to_dict(self) -> dict[str, int]:
        return {
            "emitted": self.emitted,
            "pre_verified": self.pre_verified,
            "already_open": self.already_open,
            "suppressed_conflict": self.suppressed_conflict,
            "suppressed_constraint": self.suppressed_constraint,
            "same_entity": self.same_entity,
        }


@dataclass(frozen=True, slots=True)
class _IdentifierHolder:
    """One mention reachable from one identifier claim."""

    mention_id: str
    entity_id: str | None
    claim_id: str
    jurisdiction: str | None
    valid_from: date | None
    valid_to: date | None


def _windows_overlap(left: _IdentifierHolder, right: _IdentifierHolder) -> bool:
    """Do the two validity windows intersect?  Open ends extend forever."""
    left_end, right_start = left.valid_to, right.valid_from
    right_end, left_start = right.valid_to, left.valid_from
    if left_end is not None and right_start is not None and left_end < right_start:
        return False
    if right_end is not None and left_start is not None and right_end < left_start:
        return False
    return True


def _conflict(left: _IdentifierHolder, right: _IdentifierHolder) -> str | None:
    """Why this identifier match must **not** be proposed (H-07).

    Identifiers contain errors, fraud, duplicates and reuse, so an exact string
    match is not by itself evidence of sameness.  A different issuer means two
    registries that never agreed to share a number space; a disjoint validity
    window means the number was reissued.  Either way, suppressing is right:
    the pre-verified band exists so a reviewer can confirm in bulk *without*
    reading each one, and a band that admits reissued identifiers is a band
    that launders wrong merges through a batch button.
    """
    if (
        left.jurisdiction is not None
        and right.jurisdiction is not None
        and left.jurisdiction != right.jurisdiction
    ):
        return "issuer_conflict"
    if not _windows_overlap(left, right):
        return "validity_conflict"
    return None


def _active_entity_by_mention(session: Session) -> dict[str, str]:
    return {
        mention_id: entity_id
        for mention_id, entity_id in session.execute(
            select(IdentityMembership.mention_id, IdentityMembership.entity_id).where(
                IdentityMembership.closed_revision_id.is_(None)
            )
        )
    }


def _constrained_pairs(session: Session) -> set[tuple[str, str]]:
    """Pairs a human rejected, whose constraint has not been superseded.

    Consulted **before** emission (spec 05 §3.3): re-proposing a pair a
    reviewer already ruled on wastes the scarcest resource in the system and
    trains reviewers to click through the queue.
    """
    return {
        (a, b)
        for a, b in session.execute(
            select(
                IdentityNegativeConstraint.mention_a,
                IdentityNegativeConstraint.mention_b,
            ).where(IdentityNegativeConstraint.superseded_by.is_(None))
        )
    }


def _open_or_decided_pairs(session: Session) -> set[tuple[str, str]]:
    """Pairs that already have a candidate row — a re-run must not duplicate."""
    return {
        (a, b)
        for a, b in session.execute(
            select(ErCandidate.mention_a, ErCandidate.mention_b).where(
                ErCandidate.disposition != "superseded"
            )
        )
    }


def run_rules(
    session: Session,
    *,
    ontology: Ontology,
    record_id: str | None = None,
) -> RuleRunReport:
    """Emit deterministic candidates.  Idempotent: a re-run proposes nothing new."""
    report = RuleRunReport()
    entity_by_mention = _active_entity_by_mention(session)
    constrained = _constrained_pairs(session)
    existing = _open_or_decided_pairs(session)

    def _emit(
        left: str,
        right: str,
        *,
        producer: str,
        features: dict[str, Any],
        pre_verified: bool,
    ) -> None:
        pair = (left, right) if left < right else (right, left)
        if entity_by_mention.get(pair[0]) is not None and entity_by_mention.get(
            pair[0]
        ) == entity_by_mention.get(pair[1]):
            report.same_entity += 1
            return
        if pair in constrained:
            report.suppressed_constraint += 1
            return
        if pair in existing:
            report.already_open += 1
            return
        candidate = ErCandidate(
            candidate_id=new_id("cnd"),
            mention_a=pair[0],
            mention_b=pair[1],
            producer=producer,
            producer_version=RULES_VERSION,
            # Rule producers compute no probability.  A fabricated 1.0 would
            # be indistinguishable from a model that was certain, and nothing
            # downstream could tell the two apart (spec 05 §3.1).
            score=None,
            features=features,
            pre_verified=pre_verified,
        )
        session.add(candidate)
        existing.add(pair)
        report.candidates.append(candidate)
        report.emitted += 1
        if pre_verified:
            report.pre_verified += 1

    _run_identifier_rules(session, ontology, entity_by_mention, _emit, report)
    _run_same_key_in_document(session, record_id, _emit)
    session.flush()
    return report


def _run_identifier_rules(
    session: Session,
    ontology: Ontology,
    entity_by_mention: dict[str, str],
    emit: Any,
    report: RuleRunReport,
) -> None:
    identifier_predicates = ontology.identifier_predicates()
    if not identifier_predicates:
        return

    claims = session.scalars(
        select(Claim).where(
            Claim.predicate.in_(list(identifier_predicates)),
            Claim.retracted_at.is_(None),
            Claim.object_value.isnot(None),
        )
    ).all()

    mentions_by_entity: dict[str, list[str]] = defaultdict(list)
    for mention_id, entity_id in entity_by_mention.items():
        mentions_by_entity[entity_id].append(mention_id)

    # (predicate, normalized value) → the mentions asserting it
    groups: dict[tuple[str, str], list[_IdentifierHolder]] = defaultdict(list)
    for claim in claims:
        value = _identifier_value(claim.object_value)
        if value is None:
            continue
        for mention_id in _mentions_for_claim(claim, mentions_by_entity):
            groups[(claim.predicate, value)].append(
                _IdentifierHolder(
                    mention_id=mention_id,
                    entity_id=entity_by_mention.get(mention_id),
                    claim_id=claim.claim_id,
                    jurisdiction=claim.jurisdiction,
                    valid_from=claim.valid_from,
                    valid_to=claim.valid_to,
                )
            )

    for (predicate, value), holders in sorted(groups.items()):
        unique = {holder.mention_id: holder for holder in holders}
        ordered = [unique[key] for key in sorted(unique)]
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                conflict = _conflict(left, right)
                if conflict is not None:
                    report.suppressed_conflict += 1
                    continue
                emit(
                    left.mention_id,
                    right.mention_id,
                    producer=f"{IDENTIFIER_RULE_PREFIX}{predicate}",
                    features={
                        "rule": "identifier_match",
                        "predicate": predicate,
                        # The value itself is not copied into features: an
                        # identifier can be `sensitivity: restricted`, and the
                        # waterfall is rendered in the review UI (T24a would
                        # otherwise have to filter inside a JSONB blob).
                        "claim_ids": sorted({left.claim_id, right.claim_id}),
                        "jurisdictions": sorted(
                            {
                                j
                                for j in (left.jurisdiction, right.jurisdiction)
                                if j is not None
                            }
                        ),
                    },
                    pre_verified=True,
                )


def _identifier_value(object_value: Any) -> str | None:
    """Normalize an identifier for exact comparison — case and spacing only.

    No transliteration, no fuzzy folding: this rule's whole claim to the
    pre-verified band is that it made an *exact* match.
    """
    if not isinstance(object_value, str):
        return None
    normalized = "".join(object_value.split()).upper()
    return normalized or None


def _mentions_for_claim(
    claim: Claim, mentions_by_entity: dict[str, list[str]]
) -> Iterable[str]:
    """The mentions an identifier claim speaks for.

    The anchor when the claim has one — that is the text the identifier was
    read next to.  Otherwise every active mention of the subject, because an
    unanchored claim genuinely applies to the whole entity (spec 02 §3.1).
    """
    if claim.subject_mention_id is not None:
        return [claim.subject_mention_id]
    return mentions_by_entity.get(claim.subject_id, [])


def _run_same_key_in_document(
    session: Session, record_id: str | None, emit: Any
) -> None:
    query = select(Mention.mention_id, Mention.record_id, Mention.norm_key)
    if record_id is not None:
        query = query.where(Mention.record_id == record_id)
    by_document: dict[tuple[str, str], list[str]] = defaultdict(list)
    for mention_id, mention_record, key in session.execute(query):
        by_document[(mention_record, key)].append(mention_id)

    for (_, key), mention_ids in sorted(by_document.items()):
        if len(mention_ids) < 2:
            continue
        ordered = sorted(mention_ids)
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                emit(
                    left,
                    right,
                    producer=SAME_KEY_IN_DOCUMENT_RULE,
                    features={
                        "rule": "same_norm_key_in_document",
                        "norm_key": key,
                    },
                    # Never pre-verified: one document can name two different
                    # people who share a common name (spec 05 §3.1).
                    pre_verified=False,
                )


__all__ = ["RuleRunReport", "run_rules"]
