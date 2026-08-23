"""Co-arrest edges become arrest events (T63, spec 10 §2.4).

The one migration the event-vs-edge rule recommends. `co_arrested_with` is the
single predicate in the shipped ontology that names an **occurrence**: "the 4
February arrest in Dubai" is a thing two sources can independently describe,
disagree about, and be corrected on, and learning of a third arrestee extends it
rather than changing what the existing pairs meant (§2.1).

**Nothing is deleted.** For each co-arrest claim this creates the `arrest`
event, writes one `has_arrestee` claim per participant carrying the original's
full envelope — record, grading, handling code, case, time, excerpt,
jurisdiction, location text — and then *retracts* the original with a reason
naming the event it became. The original stays readable, an auditor still sees
it, and the retraction says why.

**Two claims are two arrests unless a human says otherwise.** Grouping is by
`(record, time, location text)`: same report, same day, same place. That is
conservative on purpose — merging two occurrences that were not the same one is
an identity decision a machine must not make (Article VII), and splitting one
that was is a mistake a reviewer can fix by attaching the second event's claims
to the first with `record_event`.

`location_text` travels as text and is **not** resolved to a `location` entity.
Turning a source's words into a place is an analyst act with its own grading
(spec 02 §9.3), and doing it here would manufacture geography the report did not
assert.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService
from aegis.ontology import Ontology
from aegis.store import Claim, Entity

#: The predicate this migration is about. Named here rather than derived,
#: because *which* pairwise predicates name occurrences is a judgement recorded
#: in spec 10 §2.4 — the core cannot infer it, and pretending otherwise would
#: turn a reviewed list into a heuristic.
SOURCE_PREDICATE = "co_arrested_with"
EVENT_TYPE = "arrest"
ARRESTEE_ROLE = "has_arrestee"

#: Envelope fields carried from the original claim to every claim that replaces
#: it. Losing any of them would make the migration lossy in exactly the way
#: §2.4's "loses no sources or gradings" forbids.
_CARRIED = (
    "assertion_type",
    "excerpt",
    "credibility_scheme",
    "credibility_original",
    "credibility_normalized",
    "verification_status",
    "analytic_confidence",
    "event_time_earliest",
    "event_time_latest",
    "valid_from",
    "valid_to",
    "handling_code",
    "case_id",
    "jurisdiction",
    "location_text",
)


@dataclass
class MigratedArrest:
    """One occurrence, and what it cost to record it that way."""

    event_id: str
    summary: str
    participants: list[str]
    source_claim_ids: list[str]
    new_claim_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "summary": self.summary,
            "participants": self.participants,
            "retracted": self.source_claim_ids,
            "claims": self.new_claim_ids,
        }


@dataclass
class ArrestMigrationReport:
    events: list[MigratedArrest] = field(default_factory=list)
    claims_considered: int = 0
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [event.to_dict() for event in self.events],
            "claims_considered": self.claims_considered,
            "dry_run": self.dry_run,
        }


def _group_key(claim: Claim) -> tuple[Any, ...]:
    """Same report, same day, same place — one occurrence.

    Conservative by construction: two claims that differ on any of these become
    two events. A machine merging occurrences would be making an identity
    decision (Article VII), and a reviewer can always attach the second event's
    claims to the first.
    """
    return (
        claim.record_id,
        claim.event_time_earliest,
        claim.event_time_latest,
        claim.location_text,
    )


def _summary(participants: Sequence[Entity], claim: Claim) -> str:
    """The occurrence, described from what the claim already carried.

    Deliberately mechanical: this is a *derived* description, and writing
    anything the source did not support would be the migration inventing
    content. The excerpt is what a reader should trust, and it travels with
    every claim written below.
    """
    names = ", ".join(entity.label for entity in participants)
    where = f" at {claim.location_text}" if claim.location_text else ""
    when = ""
    if claim.event_time_earliest is not None:
        when = f" on {claim.event_time_earliest.date().isoformat()}"
    return f"{names} arrested together{where}{when}".strip()


def migrate_co_arrests(
    session: Session,
    *,
    context: ActionContext,
    ontology: Ontology | None = None,
    dry_run: bool = False,
) -> ArrestMigrationReport:
    """Turn every non-retracted co-arrest claim into an arrest event.

    Idempotent: an already-retracted claim is skipped, so a re-run after a
    partial migration finishes it rather than duplicating what landed.
    """
    service = ActionService(session, ontology)
    ontology = service.ontology
    report = ArrestMigrationReport(dry_run=dry_run)

    if SOURCE_PREDICATE not in ontology.predicates or EVENT_TYPE not in ontology.object_types:
        # A composition without this vocabulary has nothing to migrate, which
        # is the right answer rather than an error (Article XIV).
        return report

    claims = list(
        session.scalars(
            select(Claim)
            .where(
                Claim.predicate == SOURCE_PREDICATE,
                Claim.retracted_at.is_(None),
            )
            .order_by(Claim.claim_id)
        )
    )
    report.claims_considered = len(claims)
    if not claims:
        return report

    groups: dict[tuple[Any, ...], list[Claim]] = {}
    for claim in claims:
        groups.setdefault(_group_key(claim), []).append(claim)

    for members in groups.values():
        first = members[0]
        participant_ids: list[str] = []
        for claim in members:
            for side in (claim.subject_id, claim.object_id):
                if side and side not in participant_ids:
                    participant_ids.append(side)
        participants = [
            entity
            for entity in (session.get(Entity, pid) for pid in participant_ids)
            if entity is not None
        ]
        summary = _summary(participants, first)

        if dry_run:
            report.events.append(
                MigratedArrest(
                    event_id="(not created)",
                    summary=summary,
                    participants=[entity.label for entity in participants],
                    source_claim_ids=[claim.claim_id for claim in members],
                )
            )
            continue

        envelope = {name: getattr(first, name) for name in _CARRIED}
        # `record_event` refuses an undeclared role and validates every
        # participant against `has_arrestee`'s declared object type, so the
        # migration goes through the same gate a human would (ADR-046).
        result = service.record_event(
            context,
            event_type=EVENT_TYPE,
            record_id=first.record_id,
            summary=summary,
            label=summary,
            participants=[
                {"role": ARRESTEE_ROLE, "entity_id": entity.entity_id}
                for entity in participants
            ],
            **{k: v for k, v in envelope.items() if v is not None and k in _EVENT_PARAMS},
        )
        migrated = MigratedArrest(
            event_id=result.entity_id,
            summary=summary,
            participants=[entity.label for entity in participants],
            source_claim_ids=[claim.claim_id for claim in members],
            new_claim_ids=list(result.claim_ids),
        )
        for claim in members:
            # Retracted, never deleted: the original stays readable to an
            # auditor and the reason names what it became, so the transformation
            # is answerable from the record rather than from this file.
            service.retract_claim(
                context,
                claim_id=claim.claim_id,
                reason=(
                    f"migrated to {EVENT_TYPE} event {result.entity_id} "
                    f"(T63, spec 10 §2.4): the occurrence has identity "
                    f"independent of this pair"
                ),
            )
        report.events.append(migrated)

    return report


#: `record_event` declares a narrower envelope than `record_claim` — no
#: `valid_from`/`valid_to`, no `jurisdiction`, no `location_text`, because an
#: occurrence's validity window and jurisdiction are not concepts it models.
#: Those still reach the *claims* through the action's own envelope where they
#: apply; naming the intersection here keeps the call honest instead of passing
#: fields the generated model would reject.
_EVENT_PARAMS = frozenset(
    {
        "assertion_type",
        "excerpt",
        "credibility_normalized",
        "verification_status",
        "analytic_confidence",
        "event_time_earliest",
        "event_time_latest",
        "handling_code",
        "case_id",
    }
)


__all__ = [
    "ARRESTEE_ROLE",
    "EVENT_TYPE",
    "SOURCE_PREDICATE",
    "ArrestMigrationReport",
    "MigratedArrest",
    "migrate_co_arrests",
]
