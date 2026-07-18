"""Transliteration keys (T19; spec 05 §3.2, GOAL.md §10.3).

All names here are fictional.  The property that matters is *not* that the
romanizer is good — it is not, and spec 05 §6 says so — but that the three keys
fail in different directions, so no single lossy step can quietly decide that
two people are one.
"""

from __future__ import annotations

import pytest

from aegis.er.translit import latin_key, phonetic_key, script_key

pytestmark = pytest.mark.requirement("Article-V", "H-08", "T19")

LATIN = "Nimal Perera"
SINHALA = "නිමල් පෙරේරා"


def test_romanization_brings_two_scripts_into_one_space() -> None:
    assert latin_key(LATIN) == "nimal_perera"
    # lossy — unidecode drops Sinhala's inherent vowels — but comparable
    assert latin_key(SINHALA) == "niml_pereeraa"


def test_the_phonetic_key_is_what_puts_the_pair_in_one_block() -> None:
    """Their Latin keys differ enough that a prefix block misses them."""
    assert phonetic_key(LATIN) == phonetic_key(SINHALA) == "NML PRR"
    assert latin_key(LATIN)[:4] != latin_key(SINHALA)[:4]


def test_the_script_key_does_not_romanize() -> None:
    """It is what stops a lossy romanization manufacturing agreement.

    Two names that romanize identically must still be distinguishable as
    written, or the Latin key becomes the only opinion in the model.
    """
    assert script_key(LATIN) != script_key(SINHALA)
    assert "න" in script_key(SINHALA)
    # vowel signs survive: the key is a real Sinhala string, not a skeleton
    assert "ි" in script_key(SINHALA)


def test_common_transliteration_variants_share_a_phonetic_key() -> None:
    assert phonetic_key("Mohamed") == phonetic_key("Mohammed")
    assert phonetic_key("Rizvi") == phonetic_key("Risvi")


def test_distinct_names_do_not_share_a_phonetic_key() -> None:
    """A blocking key that matched everything would block nothing."""
    assert phonetic_key(LATIN) != phonetic_key("Anura Silva")


@pytest.mark.parametrize("key", [latin_key, script_key, phonetic_key])
def test_keys_are_deterministic_and_survive_empty_input(key) -> None:
    assert key(LATIN) == key(LATIN)
    assert key("") == ""
