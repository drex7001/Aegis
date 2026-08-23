"""Travel and movement, proposed from reporting text (T58, spec 04 §4, spec 10 §5).

A deterministic pass over press and border-report text that emits **event
suggestions**: "these people travelled from here to there, around then, and this
report says so."

Article VII is unchanged for events, which is the whole reason this exists. The
pass writes nothing canonical — it submits an ``event_draft`` to the review
queue, and acceptance dispatches through ``record_event`` with the *reviewer* as
actor (ADR-031 §2). Rejection leaves no trace beyond the decided queue row,
because there was never anything else to leave.

**Deterministic, not clever.** The patterns below match the sentence shapes that
actually appear in the corpus this serves, and a sentence the pass cannot read
produces nothing rather than a guess. That is the right trade for a producer
whose output a human has to read anyway: a missed journey costs a reviewer
nothing, and an invented one costs them their trust in the queue.

What it deliberately does not do: resolve place names to coordinates (geocoding
is manual or assisted — spec 10 §10), infer a route between two endpoints
(P6+), or merge two reports of one journey (spec 10 §3.5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, new_id
from aegis.actions.service import suggestion_idempotency_key
from aegis.er.ledger import resolve_norm_key
from aegis.er.mentions import extract_mentions
from aegis.er.normalize import norm_key
from aegis.ontology import Ontology
from aegis.store import Entity, ReviewQueue, SourceRecord

#: Bumped when the patterns change, so two runs of *different* logic are never
#: mistaken for a replay. It rides the idempotency key, which is what makes a
#: re-run of the same version a no-op and a re-run of a new version a fresh
#: proposal the reviewer can compare.
PRODUCER = "travel_pass"
PRODUCER_VERSION = "v1"

#: The event type and roles this pass proposes. Read from the ontology at
#: submission time rather than trusted from here — these are the names the
#: producer *intends*, and `_declared` refuses to emit a draft naming vocabulary
#: the composition does not have (Article XIV: a domain without `travel` gets no
#: travel suggestions, not a crash).
EVENT_TYPE = "travel"
TRAVELLER_ROLE = "has_traveller"
FROM_ROLE = "travelled_from"
TO_ROLE = "travelled_to"

_MONTHS = {
    month: index
    for index, month in enumerate(
        (
            "january february march april may june july august september "
            "october november december"
        ).split(),
        start=1,
    )
}

#: "on 4 April 2019", "on 4 April", "in April 2019". Deliberately narrow: a date
#: this cannot read leaves the event undated, which the timeline renders as
#: undated rather than inventing a midpoint (spec 10 §11.1).
_DATE_RE = re.compile(
    r"\b(?:on\s+)?(?P<day>\d{1,2})\s+(?P<month>[A-Z][a-z]+)\s+(?P<year>\d{4})\b"
)
_MONTH_ONLY_RE = re.compile(r"\bin\s+(?P<month>[A-Z][a-z]+)\s+(?P<year>\d{4})\b")

#: The sentence shape: "<names> travelled|flew|departed from <A> to <B>".
#: `travelled to X from Y` is accepted too, because reporting writes it both
#: ways and refusing one would drop journeys for a word-order reason.
_JOURNEY_RE = re.compile(
    r"(?P<names>[^.;]*?)\s+"
    r"(?:travelled|traveled|flew|departed|crossed|journeyed)\s+"
    r"(?:"
    r"from\s+(?P<origin>[A-Z][\w'\- ]*?)\s+to\s+(?P<destination>[A-Z][\w'\- ]*?)"
    r"|to\s+(?P<destination2>[A-Z][\w'\- ]*?)\s+from\s+(?P<origin2>[A-Z][\w'\- ]*?)"
    r")"
    r"(?=[\s,.;]|$)",
)

#: Names inside the subject phrase, e.g. "Nimal Perera and Kamala Silva".
_NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")

#: Words that begin a subject phrase and are not part of a name.
_LEAD_NOISE = re.compile(
    r"^(?:the|a|an|police|reports?|according to|it is reported that)\s+", re.IGNORECASE
)


@dataclass
class Journey:
    """One reading of one sentence. Not a claim, not yet a suggestion."""

    travellers: list[str]
    origin: str
    destination: str
    earliest: datetime | None
    latest: datetime | None
    sentence: str

    @property
    def summary(self) -> str:
        who = ", ".join(self.travellers) if self.travellers else "An unnamed party"
        return f"{who} travelled from {self.origin} to {self.destination}"


@dataclass
class TravelPassReport:
    """What one run proposed, and what it could not read."""

    suggestions: list[ReviewQueue] = field(default_factory=list)
    journeys: int = 0
    skipped_replays: int = 0
    #: Sentences that matched the journey shape but named nobody. Carried rather
    #: than dropped: "a journey we could not attribute" is a fact a reviewer may
    #: want, and silently discarding it is how a pass looks better than it is.
    unattributed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suggested": len(self.suggestions),
            "journeys": self.journeys,
            "skipped_replays": self.skipped_replays,
            "unattributed": len(self.unattributed),
        }


def parse_journeys(text: str) -> list[Journey]:
    """Read every journey this pass can recognise. Pure: no session, no writes."""
    journeys: list[Journey] = []
    for sentence in _sentences(text):
        match = _JOURNEY_RE.search(sentence)
        if match is None:
            continue
        origin = (match.group("origin") or match.group("origin2") or "").strip()
        destination = (
            match.group("destination") or match.group("destination2") or ""
        ).strip()
        if not origin or not destination or origin == destination:
            # A journey from a place to itself is a sentence the pattern
            # misread, not an event.
            continue
        earliest, latest = _read_date(sentence)
        journeys.append(
            Journey(
                travellers=_names(match.group("names") or ""),
                origin=origin,
                destination=destination,
                earliest=earliest,
                latest=latest,
                sentence=sentence.strip(),
            )
        )
    return journeys


def run_travel_pass(
    session: Session,
    *,
    record: SourceRecord,
    text: str,
    actor: str,
    ontology: Ontology | None = None,
) -> TravelPassReport:
    """Propose every journey in ``text`` as an ``event_draft``.

    Places are resolved to `location` entities, creating one where the corpus has
    never named it — a place with a name and no geometry, which is exactly what
    a press report supports. Coordinates are never invented (spec 10 §10).
    """
    service = ActionService(session, ontology)
    ontology = service.ontology
    context = ActionContext(actor=actor, purpose="travel extraction pass")
    report = TravelPassReport()

    missing = _undeclared(ontology)
    if missing:
        # A composition without travel vocabulary gets no travel suggestions.
        # Not an error: a second domain is allowed not to have journeys.
        return report

    journeys = parse_journeys(text)
    report.journeys = len(journeys)
    if not journeys:
        return report

    # Mentions first, for the same reason the other passes do it: a mention
    # records what the text says, so it is evidence rather than canon, and ER
    # needs them to exist before anything is accepted.
    names = {
        norm_key(name): name
        for journey in journeys
        for name in journey.travellers
    }
    extraction = extract_mentions(session, record=record, text=text, names=names)

    for journey in journeys:
        if not journey.travellers:
            report.unattributed.append(journey.sentence)
            continue
        payload = _payload(session, record, journey, extraction.by_ref)
        key = suggestion_idempotency_key(
            kind="event_draft",
            producer=PRODUCER,
            producer_version=PRODUCER_VERSION,
            payload=payload,
        )
        if _already_suggested(session, key):
            report.skipped_replays += 1
            continue
        report.suggestions.append(
            service.submit_suggestion(
                context,
                payload=payload,
                suggestion_kind="event_draft",
                producer=PRODUCER,
                producer_version=PRODUCER_VERSION,
                producer_meta={
                    "rule": "journey-sentence",
                    "sentence": journey.sentence,
                    # The reviewer sees which places this pass *created* rather
                    # than matched, because a brand-new location is the thing
                    # most worth a second look.
                    "origin": journey.origin,
                    "destination": journey.destination,
                },
                record_id=record.record_id,
                idempotency_key=key,
            )
        )
    return report


# ── internals ───────────────────────────────────────────────────────────────


def _undeclared(ontology: Ontology) -> list[str]:
    """Vocabulary this pass needs and the composition may not have."""
    missing = [
        name
        for name in (TRAVELLER_ROLE, FROM_ROLE, TO_ROLE)
        if name not in ontology.predicates
    ]
    if EVENT_TYPE not in ontology.object_types:
        missing.append(EVENT_TYPE)
    return missing


def _sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.;])\s+", text) if part.strip()]


def _names(phrase: str) -> list[str]:
    cleaned = _LEAD_NOISE.sub("", phrase.strip())
    seen: list[str] = []
    for match in _NAME_RE.finditer(cleaned):
        name = match.group(0)
        if name not in seen:
            seen.append(name)
    return seen


def _read_date(sentence: str) -> tuple[datetime | None, datetime | None]:
    """A stated day is an instant; a stated month is the month (spec 10 §3.3)."""
    match = _DATE_RE.search(sentence)
    if match is not None:
        month = _MONTHS.get(match.group("month").lower())
        if month is not None:
            day = datetime(
                int(match.group("year")), month, int(match.group("day")), tzinfo=timezone.utc
            )
            return day, day.replace(hour=23, minute=59, second=59)
    match = _MONTH_ONLY_RE.search(sentence)
    if match is not None:
        month = _MONTHS.get(match.group("month").lower())
        if month is not None:
            year = int(match.group("year"))
            start = datetime(year, month, 1, tzinfo=timezone.utc)
            next_month = (
                datetime(year + 1, 1, 1, tzinfo=timezone.utc)
                if month == 12
                else datetime(year, month + 1, 1, tzinfo=timezone.utc)
            )
            # The month's bounds, not its midpoint: "in April" is a range the
            # source stated, and narrowing it would be inventing precision.
            return start, next_month - timedelta(seconds=1)
    # Undated, and said so. Never `recorded_at`: when we learned something is
    # not when it happened.
    return None, None


def _payload(
    session: Session,
    record: SourceRecord,
    journey: Journey,
    mention_by_ref: dict[str, Any],
) -> dict[str, Any]:
    participants = []
    for name in journey.travellers:
        key = norm_key(name)
        mention = mention_by_ref.get(key)
        entity_id = resolve_norm_key(session, key)
        # A name nobody has adjudicated has no entity yet. The mention is
        # what the draft carries, and acceptance creates the entity from it
        # inside `record_claim` (spec 02 §3.2) — which is why there is no
        # `entity_draft` kind and why a producer never invents an id.
        entry: dict[str, Any] = {"role": TRAVELLER_ROLE}
        if entity_id is not None:
            entry["entity_id"] = entity_id
        if mention is not None:
            entry["mention_id"] = mention.mention_id
        participants.append(entry)

    return {
        "event_type": EVENT_TYPE,
        "record_id": record.record_id,
        "summary": journey.summary,
        "excerpt": journey.sentence,
        "event_time_earliest": journey.earliest.isoformat() if journey.earliest else None,
        "event_time_latest": journey.latest.isoformat() if journey.latest else None,
        "assertion_type": "reported",
        "participants": participants,
        "places": [
            {"role": FROM_ROLE, "entity_id": _place(session, journey.origin)},
            {"role": TO_ROLE, "entity_id": _place(session, journey.destination)},
        ],
    }


def _place(session: Session, name: str) -> str:
    """The `location` entity for a place name, created if the corpus lacks one.

    A place with a name and no geometry is exactly what a press report supports.
    Coordinates are never inferred here — geocoding is manual or assisted, and a
    locality string turned silently into a point is the false precision this
    phase is built against (spec 10 §10).
    """
    existing = session.scalar(
        select(Entity.entity_id).where(
            Entity.entity_type == "location",
            Entity.label == name,
            Entity.tombstoned_at.is_(None),
        )
    )
    if existing is not None:
        return existing
    entity = Entity(entity_id=new_id("ent"), entity_type="location", label=name)
    session.add(entity)
    session.flush()
    return entity.entity_id


def _already_suggested(session: Session, idempotency_key: str) -> bool:
    return (
        session.scalar(
            select(ReviewQueue.suggestion_id).where(
                ReviewQueue.idempotency_key == idempotency_key
            )
        )
        is not None
    )


__all__ = [
    "PRODUCER",
    "PRODUCER_VERSION",
    "Journey",
    "TravelPassReport",
    "parse_journeys",
    "run_travel_pass",
]
