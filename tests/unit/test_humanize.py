"""The default label for an ontology name (T42, ADR-043, spec 09 §6.2).

Sixty-six properties and predicates would otherwise each need a declared label
repeating their own name, so the generator derives one. This is the whole of
that derivation, which makes it worth pinning precisely: it decides what every
screen calls every field, and it lives in the generator rather than in React so
that a wrong label is fixed by a proposal.
"""

from __future__ import annotations

import pytest

from aegis.ontology.generate import humanize

pytestmark = pytest.mark.requirement("ADR-043", "T42")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("name", "Name"),
        ("date_of_birth", "Date of birth"),
        ("affiliated_with", "Affiliated with"),
        ("phone_number", "Phone number"),
        ("port_of_entry", "Port of entry"),
    ],
)
def test_a_snake_case_name_becomes_a_sentence(name: str, expected: str) -> None:
    assert humanize(name) == expected


def test_sentence_case_not_title_case() -> None:
    """"Date of Birth" is a headline; these are field labels."""
    assert humanize("date_of_birth") == "Date of birth"
    assert humanize("date_of_birth") != "Date Of Birth"


def test_an_acronym_survives_only_by_being_declared() -> None:
    """The known failure, recorded so the workaround is not mistaken for a bug.

    `capitalize()` lowercases the tail, so `nic` cannot become `NIC` here and no
    amount of cleverness should try — an ontology that wants an acronym declares
    a label (proposal 005), which is checked by the generate suite.
    """
    assert humanize("nic") == "Nic"
    assert humanize("has_nic") == "Has nic"


def test_it_never_returns_an_empty_or_underscored_label() -> None:
    """A blank heading is worse than a clumsy one."""
    for name in ("a", "x_y", "leading_trailing"):
        label = humanize(name)
        assert label
        assert "_" not in label
        assert label[0].isupper()
