"""Blocking keys and script detection (T17; spec 05 §1).

``norm_key`` is load-bearing in two directions: it must keep matching the keys
the Phase-1 legacy migration already wrote, and it must stop doing the thing
that made the prototype's version unusable outside Latin script.
"""

from __future__ import annotations

import pytest

from aegis.er.normalize import detect_script, norm_key
from legacy.pipeline.models import slugify

pytestmark = pytest.mark.requirement("Article-V", "H-06", "T17")


@pytest.mark.parametrize(
    "name",
    [
        "Kasun Wijeratne",
        "Rizvi FAROOK",
        'Kasun "Podda" Wijeratne',
        "National Thowheeth Jamaath",
        "José Ferreira",  # Latin diacritics still fold to ASCII
        "  spaced   out  ",
        "O'Brien-Smith",
    ],
)
def test_matches_the_prototype_on_latin_input(name: str) -> None:
    """Phase-1 rows were keyed with slugify; those keys must keep resolving."""
    assert norm_key(name) == slugify(name)


@pytest.mark.parametrize(
    "name",
    ["නිමල් පෙරේරා", "සමන් කුමාර", "முகமது", "ரிஸ்வி"],
)
def test_preserves_non_latin_script(name: str) -> None:
    """The prototype folded these to the literal "unknown" — every Sinhala and
    Tamil name collided on one key, so a lookup resolved an arbitrary entity.
    """
    assert slugify(name) == "unknown"  # the bug being fixed, pinned
    key = norm_key(name)
    assert key not in {"unknown", ""}
    assert key == norm_key(name)  # deterministic


def test_distinct_sinhala_names_get_distinct_keys() -> None:
    assert norm_key("නිමල් පෙරේරා") != norm_key("සමන් කුමාර")


def test_sinhala_vowel_signs_are_preserved_not_merely_distinct() -> None:
    r"""They are combining marks that carry meaning, unlike a Latin accent.

    Asserting only that the two keys *differ* is not enough: an earlier version
    replaced every vowel sign with ``_`` (Python's ``\w`` excludes Unicode
    marks), which kept them distinct while mangling the script the key exists
    to preserve.  So the mark itself must survive.
    """
    key = norm_key("පෙරේරා")
    assert key != norm_key("පරර")
    assert "ෙ" in key or "ේ" in key, f"vowel signs were dropped: {key!r}"
    assert "_" not in key, f"marks became separators: {key!r}"


def test_text_with_no_alphanumerics_gets_a_distinct_deterministic_key() -> None:
    """The prototype returned "unknown" here too, colliding every such mention."""
    first, second = norm_key("!!!"), norm_key("???")
    assert first != second
    assert first == norm_key("!!!")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Kasun Wijeratne", "Latn"),
        ("නිමල් පෙරේරා", "Sinh"),
        ("முகமது", "Taml"),
        ("Kasun නිමල් නිමල්", "Sinh"),  # majority of letters wins
        ("2023-04-21", None),  # no letters — an honest None, not "Latn"
        ("", None),
    ],
)
def test_detect_script(text: str, expected: str | None) -> None:
    assert detect_script(text) == expected
