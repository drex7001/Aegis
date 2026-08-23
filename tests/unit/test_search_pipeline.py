"""The normalization pipeline, stage by stage (T67; spec 11 §3, ADR-052).

H-22's warning is the shape of this module: *do not strip Sinhala or Tamil
diacritics wholesale — that collapses distinct names rather than normalizing
equivalent encodings.* So the two halves of the diacritic rule are asserted
**together**, because either one alone reads as a policy the code does not have:

* a Latin diacritic **is** folded (`José` → `jose`), deliberately;
* a Sinhala vowel sign **is not**, ever.

Everything here is fictional. The Sinhala and Tamil strings are names invented
for the test set, not people.
"""

from __future__ import annotations

import unicodedata

import pytest

from aegis.er.normalize import norm_key
from aegis.search.pipeline import (
    NORMALIZATION_VERSION,
    search_keys,
    strip_format_characters,
)

pytestmark = pytest.mark.requirement("H-22", "ADR-052", "T67")

ZWJ = "‍"
ZWNJ = "‌"

#: A fictional Sinhala name. Its vowel signs are the thing H-22 protects.
SINHALA = "නිමල් පෙරේරා"
#: A fictional Tamil name.
TAMIL = "அருள் ராஜா"


# ── stage 6: format characters ──────────────────────────────────────────────


@pytest.mark.parametrize("invisible", [ZWJ, ZWNJ, "‎", "­"])
def test_a_format_character_inside_a_word_does_not_split_it(invisible: str) -> None:
    """The bug ADR-052's first version bump exists to fix.

    `collapse_separators` keeps a character when it is alphanumeric or a
    combining mark and turns everything else into `_`. A zero-width joiner is
    neither, so it used to *split the token*: the same name copied from two web
    pages produced two keys and the two mentions never blocked together.
    """
    assert search_keys(f"Nimal{invisible}Perera").norm == search_keys("NimalPerera").norm


def test_the_format_fix_is_not_vacuous() -> None:
    """Without the strip, the two spellings really do produce different keys.

    An assertion that two things are equal proves nothing if they were always
    equal. This is the control.
    """
    assert norm_key(f"Nimal{ZWJ}Perera") != norm_key("NimalPerera")
    assert strip_format_characters(f"Nimal{ZWJ}Perera") == "NimalPerera"


def test_a_format_character_survives_in_the_original_text() -> None:
    """Keys are normalized; the text is not. A hit has to show what it matched."""
    raw = f"Nimal{ZWJ}Perera"
    assert search_keys(raw).text == raw


# ── stages 2 and 3: the two halves of the diacritic rule ────────────────────


def test_a_latin_diacritic_is_folded() -> None:
    assert search_keys("José Ferreira").norm == search_keys("Jose Ferreira").norm


def test_a_sinhala_vowel_sign_is_never_folded() -> None:
    """H-22, directly: folding these collapses names that are not the same name.

    `පෙරේරා` without its vowel signs is a different string and, in a corpus of
    real people, a different person. The assertion is that the marks survive
    into the key — not merely that two spellings differ.
    """
    key = search_keys(SINHALA).norm
    assert any(unicodedata.category(char) in {"Mn", "Mc"} for char in key), (
        f"the Sinhala key {key!r} lost its combining marks"
    )


def test_a_tamil_vowel_sign_is_never_folded() -> None:
    key = search_keys(TAMIL).norm
    assert any(unicodedata.category(char) in {"Mn", "Mc"} for char in key)


def test_stripping_sinhala_marks_would_collapse_distinct_names() -> None:
    """Why the rule above is a rule.

    Two fictional Sinhala names that differ **only** in a vowel sign keep
    different keys. Under wholesale mark-stripping they would become one key,
    which is the failure H-22 describes: not normalization, erasure.
    """
    one, other = "පෙරේරා", "පෙරෙරා"
    assert one != other
    assert search_keys(one).norm != search_keys(other).norm

    stripped = {
        "".join(c for c in unicodedata.normalize("NFD", name) if not unicodedata.combining(c))
        for name in (one, other)
    }
    assert len(stripped) == 1, "the control failed: these names differ by more than a mark"


# ── stage 1: canonical equivalence ──────────────────────────────────────────


def test_nfc_and_nfd_spellings_of_one_name_agree() -> None:
    """Canonically equivalent sequences must not be two different names."""
    name = "José Ferreira"
    composed = unicodedata.normalize("NFC", name)
    decomposed = unicodedata.normalize("NFD", name)
    assert composed != decomposed, "the control failed: these are the same bytes"
    assert search_keys(composed).norm == search_keys(decomposed).norm


def test_case_is_folded() -> None:
    assert search_keys("NIMAL PERERA").norm == search_keys("nimal perera").norm


# ── the keys, and what each claims ──────────────────────────────────────────


def test_the_latin_key_reaches_across_scripts_and_the_norm_key_does_not() -> None:
    """ADR-035's whole point, asserted as a difference rather than described.

    `norm_key` preserves script, so nothing derived from a Latin query can ever
    match a Sinhala name through it. The romanized key is what can — and it is
    lossy in the direction that manufactures agreement, which is why it is
    ranked below a same-script hit rather than beside it.
    """
    sinhala = search_keys(SINHALA)
    latin = search_keys("Nimal Perera")
    assert sinhala.norm != latin.norm
    assert sinhala.latin and latin.latin
    assert sinhala.script == "Sinh"
    assert latin.script == "Latn"


def test_every_key_carries_the_running_version() -> None:
    assert search_keys("anything").version == NORMALIZATION_VERSION


def test_an_unkeyable_string_gets_a_digest_not_a_shared_literal() -> None:
    """The prototype returned `"unknown"`, so every such mention collided."""
    first = search_keys("!!!").norm
    second = search_keys("???").norm
    assert first.startswith("u_") and second.startswith("u_")
    assert first != second


def test_the_pipeline_is_deterministic() -> None:
    assert search_keys(SINHALA) == search_keys(SINHALA)
