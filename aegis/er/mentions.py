"""Mention extraction (T17; spec 02 §2, spec 05 §1, H-06).

A mention is a **name-as-written inside one source record** — a record of what
the text says, not a claim about the world and not an identity decision.  That
is why extraction may persist mentions directly while it may not persist
claims: nothing here is canon, and nothing here decides who anyone is.

**Offsets are recorded only when they are true.**  Spec 02 §2 says "offsets
into the derivative text, *when known*", and on real text they often are not:
this corpus writes ``Kasun "Podda" WIJERATNE`` where an extractor reports
``Kasun Wijeratne``, so the reported name is not a contiguous span even though
it is plainly present.  Locating is therefore case-insensitive **exact** match
and nothing more — no fuzzy alignment, because an offset that needed fuzz to
find would misrepresent where the source actually says what it says.

A name that cannot be located still becomes a mention, with NULL offsets, and
is listed in :attr:`MentionExtraction.unverified` so the reviewer can see which
names the pass could not point at in the text.  Refusing to create it would
lose the extractor's output entirely (Article VIII); pretending to know its
offsets would be worse.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.ids import new_id
from aegis.er.normalize import detect_script, norm_key
from aegis.er.translit import latin_key, phonetic_key
from aegis.store import Mention, SourceRecord

#: Characters of surrounding text kept with each mention, for the reviewer and
#: for the T19 graph-context features.
CONTEXT_WINDOW = 120


@dataclass(frozen=True, slots=True)
class MentionExtraction:
    """What one extraction pass found, and what it could not verify.

    ``by_ref`` is keyed by the caller's own reference for each name — the
    producer's node id, not our ``norm_key``.  The two agree for ASCII names
    but not for Sinhala or Tamil ones, where the producer's key is lossy
    (:mod:`aegis.er.normalize`), so keying on ours would silently drop
    exactly the anchors this corpus most needs.
    """

    by_ref: dict[str, Mention]
    created: list[Mention]
    reused: list[Mention]
    unverified: list[str]  # names absent from the text they were read from

    def to_dict(self) -> dict[str, object]:
        return {
            "created": len(self.created),
            "reused": len(self.reused),
            "unverified": sorted(self.unverified),
        }


def _locate(text: str, name: str) -> tuple[int, int] | None:
    """First occurrence of ``name`` in ``text``, case-insensitively.

    Case folding only — no fuzzy matching.  A name that needs fuzziness to be
    located is not verifiably *at* a position, and claiming an offset for it
    would misrepresent the source (see the module docstring).
    """
    index = text.lower().find(name.lower())
    if index < 0:
        return None
    return index, index + len(name)


def extract_mentions(
    session: Session,
    *,
    record: SourceRecord,
    text: str,
    names: dict[str, str],
) -> MentionExtraction:
    """Persist one mention per name that is verifiably present in ``text``.

    ``names`` maps the caller's reference for each name to the name as the
    producer reported it; the result is keyed back by those references.

    Idempotent: re-running an extraction pass over the same record finds the
    existing rows by (norm_key, offset) and reuses them, so a replay adds
    nothing (spec 04 §5).
    """
    existing = {
        (row.norm_key, row.char_start): row
        for row in session.scalars(
            select(Mention).where(Mention.record_id == record.record_id)
        )
    }
    by_ref: dict[str, Mention] = {}
    created: list[Mention] = []
    reused: list[Mention] = []
    unverified: list[str] = []

    for ref, name in names.items():
        if not name.strip():
            continue
        span = _locate(text, name)
        if span is None:
            unverified.append(name)
        start, end = span if span is not None else (None, None)
        key = norm_key(name)
        found = existing.get((key, start))
        if found is not None:
            by_ref[ref] = found
            reused.append(found)
            continue
        row = Mention(
            mention_id=new_id("men"),
            record_id=record.record_id,
            # As the source writes it when we could find it; as the producer
            # reported it when we could not.
            raw_text=text[start:end] if span is not None else name,
            norm_key=key,
            # Written here, once, rather than recomputed per ER run (ADR-035).
            # Keyed off the same string `raw_text` records, so the stored keys
            # and a freshly computed one can never disagree about the input.
            latin_key=latin_key(name),
            phonetic_key=phonetic_key(name),
            char_start=start,
            char_end=end,
            script=detect_script(name),
            # Language is deliberately left unset.  There is no language
            # detector here, and a Latin-script name in this corpus is as
            # likely to be romanized Sinhala or Tamil as English — guessing
            # "en" would be wrong far more often than it was useful.  T19's
            # transliteration features work from `script`, which is decidable.
            language=None,
            context=_context(text, start, end) if span is not None else None,
        )
        session.add(row)
        existing[(key, start)] = row  # two refs may name the same span
        by_ref[ref] = row
        created.append(row)

    session.flush()
    return MentionExtraction(
        by_ref=by_ref, created=created, reused=reused, unverified=unverified
    )


def _context(text: str, start: int, end: int) -> str:
    left = max(0, start - CONTEXT_WINDOW)
    right = min(len(text), end + CONTEXT_WINDOW)
    return text[left:right]


__all__ = ["CONTEXT_WINDOW", "MentionExtraction", "extract_mentions"]
