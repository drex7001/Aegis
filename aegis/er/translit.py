"""Transliteration keys for cross-script matching (T19; spec 05 §3.2, GOAL.md §10.3).

The corpus writes the same person as ``Nimal Perera`` and ``නිමල් පෙරේරා``.
Neither :func:`~aegis.er.normalize.norm_key` nor exact matching can see that
those are candidates for the same person, so Splink compares **two** keys:

* a **Latin key** — the name romanized, so the two scripts land in one space;
* a **raw-script key** — the name normalized *without* romanizing, so two
  Sinhala names are compared as Sinhala rather than through a lossy round trip.

Keeping both matters because romanization is lossy in a direction that
manufactures agreement: ``unidecode`` drops Sinhala's inherent vowels, so
distinct names can romanize closer together than they are.  The raw-script key
is what stops that from being invisible.

PyICU is deliberately not a dependency.  It would give a better romanizer, but
it is a heavyweight C binding whose wheels are unreliable on the platforms this
runs on, and the evaluation harness (T26) is what decides whether the romanizer
is good enough — not the name of the library.
"""

from __future__ import annotations

import unicodedata

import jellyfish
from unidecode import unidecode

from aegis.er.normalize import collapse_separators


def latin_key(text: str) -> str:
    """Romanized, lowercased, whitespace-collapsed — the cross-script key."""
    return collapse_separators(unidecode(text).lower())


def script_key(text: str) -> str:
    """Normalized in the original script — no romanization.

    NFKC rather than NFKD: the point is to compare Sinhala to Sinhala, and
    decomposing would separate vowel signs that carry meaning.
    """
    return collapse_separators(unicodedata.normalize("NFKC", text).lower())


def phonetic_key(text: str) -> str:
    """Metaphone over the Latin key — a blocking key, never a match.

    This is what makes the seeded transliteration pair *comparable at all*:
    ``Nimal Perera`` and the romanized ``නිමල් පෙරේරා`` differ enough that a
    prefix block misses them, but both reduce to ``NML PRR``.
    """
    return " ".join(
        jellyfish.metaphone(token) for token in latin_key(text).split("_") if token
    ).strip()


__all__ = ["latin_key", "phonetic_key", "script_key"]
