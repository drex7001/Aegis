"""The one normalization pipeline, versioned (spec 11 §3, ADR-052, H-22).

H-22 asks for *"one versioned index/query pipeline applied identically at write
and query time"*. Two of those three words were already true before this
module: `norm_key`, `latin_key` and `phonetic_key` were applied at both ends.
What was missing is **versioned** — nothing recorded which revision of them
produced a stored key.

That gap is not cosmetic. Change `collapse_separators` and every stored key
silently stops matching every query key. The failure mode is **missing
results**, which no exception reports, no test notices, and no user can
distinguish from "we do not hold that record". A search that quietly loses
recall is worse than one that is down.

So: one entry point, :func:`search_keys`, called by the write path and the
query path; a version stamped on every row that stores a derived key; and
`aegis search check-index` to fail the build when the two disagree.

**Why bumping is safe, stated once.** Nothing in the claim store depends on a
key. `norm_key` is a blocking and lookup key, never identity (Article V), and
`identity_membership` is keyed by `mention_id`. So a version bump is a
*reindex* — rows are recomputed, never reinterpreted — which is the exact
opposite of `claim.ontology_version` (ADR-013), where the stamp is history and
recomputation is forbidden. A cache may be rebuilt; an assertion may not.
"""

from __future__ import annotations

from dataclasses import dataclass
import unicodedata

from aegis.er.normalize import detect_script, norm_key
from aegis.er.translit import latin_key, phonetic_key

#: Bump when any stage in spec 11 §3.1 changes. Bumping obliges a reindex, and
#: `aegis search check-index` is what makes forgetting it a red build rather
#: than a quiet recall regression.
#:
#: v1 is the first version with a stamp at all, and it includes the format
#: character fix (§3.1 stage 6) — so the migration that introduces the stamp
#: also recomputes every pre-stamp row rather than asserting one.
NORMALIZATION_VERSION = "search-norm-v1"

#: Unicode general category for format characters: zero-width joiner and
#: non-joiner, bidi marks, soft hyphen. Invisible, semantically empty for
#: matching, and inconsistently present in text pasted from the web.
_FORMAT_CATEGORY = "Cf"


def strip_format_characters(text: str) -> str:
    """Remove `Cf` characters entirely — not replace them with a separator.

    This is the one behavioural change T67 makes to the pipeline, and it is a
    bug fix rather than a preference. `collapse_separators` keeps a character
    when it is alphanumeric or a combining mark and turns everything else into
    `_`. A zero-width joiner is neither, so today it becomes `_` and **splits
    the token**: the same Sinhala name copied from two web pages produces two
    different keys, and the two mentions never block together.

    Removing the character instead makes the joined and unjoined spellings one
    key, which is what a reader would say they are.
    """
    return "".join(
        char for char in text if unicodedata.category(char) != _FORMAT_CATEGORY
    )


@dataclass(frozen=True, slots=True)
class SearchKeys:
    """Three keys over one input, plus the version that produced them.

    The original text is carried unchanged. Every stage below is lossy in some
    direction, and a search result that cannot show what it actually matched is
    a result the reader has to take on faith.
    """

    text: str
    norm: str
    latin: str
    phonetic: str
    script: str | None
    version: str = NORMALIZATION_VERSION


def search_keys(text: str) -> SearchKeys:
    """**The** entry point. Write path and query path both call this.

    Not three separate calls to three separate functions at each end: that is
    the arrangement that let write and query drift apart in the first place,
    and `tests/contract/test_normalization_pipeline.py` asserts structurally
    that neither end grows its own.
    """
    cleaned = strip_format_characters(text)
    return SearchKeys(
        text=text,
        norm=norm_key(cleaned),
        latin=latin_key(cleaned),
        phonetic=phonetic_key(cleaned),
        script=detect_script(cleaned),
    )


__all__ = [
    "NORMALIZATION_VERSION",
    "SearchKeys",
    "search_keys",
    "strip_format_characters",
]
