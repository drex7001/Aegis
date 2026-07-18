"""Mention normalization and script detection (T17; spec 05 §1, H-06).

``norm_key`` is a **blocking and lookup key, never identity** (Article V).  Two
mentions sharing one are a reason to raise a candidate, not to merge.

This replaces the prototype's ``legacy.pipeline.models.slugify`` for anything
Aegis writes.  Slugify folds its input to ASCII and returns the literal
``"unknown"`` when nothing survives — so *every* Sinhala and Tamil name
collapsed to the same key, and a lookup on it would have resolved an arbitrary
entity.  In a Sri Lankan corpus that is not an edge case, it is the corpus.

:func:`norm_key` is deliberately **identical to slugify on pure-ASCII input**,
so keys written by the Phase-1 legacy migration still match.  Where it differs
is precisely where slugify was lossy.
"""

from __future__ import annotations

from hashlib import sha256
import unicodedata

#: Marks that are *part of a letter*, not punctuation: Mn (non-spacing) and Mc
#: (spacing combining).  Python's ``\w`` excludes both, so a naive ``[^\w]+``
#: separator regex silently replaces every Sinhala and Tamil vowel sign with an
#: underscore — mangling precisely the scripts these keys exist to preserve.
_MARK_CATEGORIES = frozenset({"Mn", "Mc"})

#: Unicode block starts → ISO 15924 code, for the scripts this corpus carries.
#: Detection is deliberately coarse: it answers "which writing system is this
#: written in", which is all the blocking rules and the T19 transliteration
#: features need.
_SCRIPT_RANGES: tuple[tuple[int, int, str], ...] = (
    (0x0D80, 0x0DFF, "Sinh"),
    (0x0B80, 0x0BFF, "Taml"),
    (0x0600, 0x06FF, "Arab"),
    (0x0900, 0x097F, "Deva"),
)


def collapse_separators(text: str) -> str:
    """Reduce every run of non-letter characters to a single ``_``.

    A "letter" here includes combining marks, so ``පෙරේරා`` keeps its vowel
    signs instead of decaying into ``ප_ර_ර``.
    """
    out: list[str] = []
    for char in text:
        if char.isalnum() or unicodedata.category(char) in _MARK_CATEGORIES:
            out.append(char)
        elif out and out[-1] != "_":
            out.append("_")
    return "".join(out).strip("_")


def norm_key(text: str) -> str:
    """Deterministic blocking key: same input → same key, always.

    Latin text is ASCII-folded (``José`` → ``jose``) to match the prototype.
    Other scripts are **preserved**: in Sinhala and Tamil the combining marks
    are vowel signs that carry meaning, so folding them away would merge names
    that are not the same name.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    kept: list[str] = []
    for char in decomposed:
        if unicodedata.combining(char) and kept and kept[-1].isascii():
            continue  # a Latin diacritic — fold it, as slugify did
        kept.append(char)
    slug = collapse_separators("".join(kept).lower())
    if not slug:
        # Nothing alphanumeric survived (punctuation, emoji, control chars).
        # The prototype returned the literal "unknown" here, which made every
        # such mention collide; a digest keeps the key deterministic *and*
        # distinct, so it blocks with itself and nothing else.
        return f"u_{sha256(text.encode()).hexdigest()[:16]}"
    return slug


def detect_script(text: str) -> str | None:
    """ISO 15924 code for the dominant script, or ``None`` when undetectable.

    Returns the script of the majority of *letters*; digits, spaces and
    punctuation are ignored because they are shared across writing systems.
    ``None`` for text with no letters at all — an honest answer, not ``"Latn"``.
    """
    counts: dict[str, int] = {}
    for char in text:
        if not char.isalpha():
            continue
        code = ord(char)
        script = "Latn" if char.isascii() else None
        if script is None:
            for start, end, name in _SCRIPT_RANGES:
                if start <= code <= end:
                    script = name
                    break
        if script is None:
            continue
        counts[script] = counts.get(script, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda script: (counts[script], script))


__all__ = ["collapse_separators", "detect_script", "norm_key"]
