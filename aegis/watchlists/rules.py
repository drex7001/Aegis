"""What counts as a detection (T75, spec 12 §11.1).

One rule today, and its name is the whole specification: `exact_identifier`.
An identifier value recorded on a watched entity is watched; a claim recording
that **exact** value on any entity is a detection.

Fuzzy matching is deliberately absent (charter risk table), and its absence is
asserted rather than assumed — `tests/integration/test_watchlists.py` fires a
near-miss at every watchlist it builds and requires silence. The reason is
ADR-053's: a near-match on an identifier is a *different* person with a name
attached, and a watchlist that fires on one teaches its readers to believe the
next one.

`exactness` travels onto every alert so that a future fuzzy rule cannot arrive
without declaring itself to every reader of every alert it produces.
"""

from __future__ import annotations

from aegis.analytics.manifest import digest_of

#: Bumped when the meaning of a detection changes. It is part of the dedupe
#: key on purpose: a rule that now means something different should be allowed
#: to fire again on evidence the old one already reported, because it is not
#: reporting the same thing.
RULE_VERSION = "watchlist-exact-v1"

EXACT_IDENTIFIER = "exact_identifier"
RULES = (EXACT_IDENTIFIER,)

#: The only value `watchlist_alert.exactness` may take today. The CHECK
#: constraint agrees, so a fuzzy rule cannot be added in Python alone.
EXACT = "exact"


def dedupe_key(
    *, watchlist_id: str, rule_version: str, matched_value: str, entity_id: str
) -> str:
    """`(watchlist_id, rule_version, matched_value, entity_id)`, digested.

    Digested rather than concatenated because `matched_value` is free text and
    a delimiter it happens to contain would silently merge two keys. The tuple
    is spec 12 §11.2's, unchanged.
    """
    return digest_of([watchlist_id, rule_version, matched_value, entity_id])


__all__ = ["EXACT", "EXACT_IDENTIFIER", "RULES", "RULE_VERSION", "dedupe_key"]
