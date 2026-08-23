"""Search-quality targets are numbers, and the spec quotes them (T66, H-22).

T66's acceptance criterion is that *"precision/recall targets are numbers, not
adjectives"*. That is only checkable if the targets are data, so they are:
`aegis/search/targets.py` holds them and spec 11 §8 restates them. This module
proves the two agree.

H-22's underlying objection was that ADR-012's OpenSearch trigger depends on
numbers the plan deferred — so the trigger could only ever fire on opinion. The
last test here is the one that closes it: the trigger condition has to name the
same latency budget the targets declare, so the number that fires it and the
number that gates CI cannot drift apart.
"""

from __future__ import annotations

import re

import pytest

from aegis.search.targets import (
    IDENTIFIER_PRECISION,
    LATENCY_BUDGET_MS,
    OPENSEARCH_TRIGGER,
    OPENSEARCH_TRIGGER_ROWS,
    RESOURCE_TARGETS,
    SCRIPT_TARGETS,
    STATEMENT_TIMEOUT_MS,
)
from tests.support.paths import REPO_ROOT

pytestmark = pytest.mark.requirement("H-22", "ADR-012", "ADR-053", "T66")

SPEC = REPO_ROOT / "speckit" / "specs" / "11-search.md"


def _section_8() -> str:
    text = SPEC.read_text(encoding="utf-8")
    start = text.index("## 8. Numeric targets")
    rest = text[start:]
    return rest[: rest.index("\n## 9.")]


def _rows() -> list[list[str]]:
    rows = []
    for line in _section_8().splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line) <= set("|- "):
            continue
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows


def _key(label: str) -> str:
    """"Cross-script (Latin query → …)" -> "cross_script"."""
    head = label.split("(")[0]
    head = head.replace("**", "").replace("`", "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", head).strip("_")


def _number(cell: str) -> float | None:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", cell.replace("≤", "").replace("≥", ""))
    return float(match.group(1)) if match else None


def _quoted_targets() -> dict[str, tuple[float, float]]:
    """Every row of §8 that quotes a precision and a recall."""
    found: dict[str, tuple[float, float]] = {}
    for cells in _rows():
        if len(cells) < 3 or "precision" in cells[1].lower():
            continue
        precision, recall = _number(cells[1]), _number(cells[2])
        if precision is None or recall is None:
            continue
        found[_key(cells[0])] = (precision, recall)
    return found


# ── the spec quotes the code ────────────────────────────────────────────────


@pytest.mark.parametrize("script", sorted(SCRIPT_TARGETS))
def test_spec_quotes_each_script_target(script: str) -> None:
    quoted = _quoted_targets()
    assert script in quoted, f"spec 11 §8 does not state a target for {script!r}"
    target = SCRIPT_TARGETS[script]
    assert quoted[script] == (target.precision_at_5, target.recall_at_20), (
        f"spec 11 §8 and aegis/search/targets.py disagree on {script!r}: "
        f"spec {quoted[script]} vs code "
        f"{(target.precision_at_5, target.recall_at_20)}"
    )


@pytest.mark.parametrize("resource", sorted(RESOURCE_TARGETS))
def test_spec_quotes_each_resource_target(resource: str) -> None:
    quoted = _quoted_targets()
    assert resource in quoted, f"spec 11 §8 does not state a target for {resource!r}"
    target = RESOURCE_TARGETS[resource]
    assert quoted[resource] == (target.precision_at_5, target.recall_at_20)


def test_the_parser_found_the_tables_at_all() -> None:
    """Guards the two tests above: an empty parse must not read as agreement."""
    quoted = _quoted_targets()
    assert len(quoted) >= len(SCRIPT_TARGETS) + len(RESOURCE_TARGETS)


def test_no_target_row_was_left_undeclared_in_code() -> None:
    """The other direction — a spec row with no constant is a target nothing gates."""
    declared = set(SCRIPT_TARGETS) | set(RESOURCE_TARGETS)
    assert not set(_quoted_targets()) - declared


# ── they really are numbers ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name,target",
    sorted({**SCRIPT_TARGETS, **RESOURCE_TARGETS}.items()),
)
def test_every_target_is_a_usable_fraction(name: str, target) -> None:
    for label, value in (
        ("precision@5", target.precision_at_5),
        ("recall@20", target.recall_at_20),
    ):
        assert isinstance(value, float), f"{name}.{label} is not a number"
        assert 0.0 < value <= 1.0, f"{name}.{label} = {value} is not a fraction"


def test_cross_script_is_held_to_a_lower_floor_and_says_so() -> None:
    """Romanization is lossy in a direction that manufactures agreement.

    Holding it to the same-script floor would either fail forever or drag the
    same-script numbers down while looking like one metric (spec 11 §3.3).
    """
    cross = SCRIPT_TARGETS["cross_script"]
    for script in ("latin", "sinhala", "tamil"):
        assert cross.precision_at_5 <= SCRIPT_TARGETS[script].precision_at_5
        assert cross.recall_at_20 <= SCRIPT_TARGETS[script].recall_at_20


def test_sinhala_and_tamil_are_not_quietly_easier_than_latin() -> None:
    """A floor set above what the pipeline can do is a gate nobody can pass."""
    for script in ("sinhala", "tamil"):
        assert SCRIPT_TARGETS[script].precision_at_5 < SCRIPT_TARGETS["latin"].precision_at_5


# ── identifiers, and the trigger ────────────────────────────────────────────


def test_identifier_precision_is_absolute():
    """ADR-053: a fuzzy identifier hit is a confident wrong person."""
    assert IDENTIFIER_PRECISION == 1.0
    assert "1.00" in _section_8(), "spec 11 §8 must state the identifier target"
    assert "never fuzzily" in _section_8()


def test_the_latency_budget_is_ordered_and_inside_the_timeout() -> None:
    assert LATENCY_BUDGET_MS["p50"] < LATENCY_BUDGET_MS["p95"] < STATEMENT_TIMEOUT_MS


def test_the_trigger_names_the_numbers_that_watch_it() -> None:
    """H-22: the trigger must fire on evidence, not on opinion."""
    assert str(LATENCY_BUDGET_MS["p95"]) in OPENSEARCH_TRIGGER
    assert "500 000" in OPENSEARCH_TRIGGER
    assert OPENSEARCH_TRIGGER_ROWS == 500_000


def test_the_spec_states_the_trigger_beside_the_targets() -> None:
    """The T68 AC: "the trigger condition is written next to the numbers it watches"."""
    text = SPEC.read_text(encoding="utf-8")
    trigger = text[text.index("## 10. The OpenSearch trigger") :]
    assert str(LATENCY_BUDGET_MS["p95"]) in trigger
    assert "before its gate" in trigger, (
        "H-22 requires remediation inside Phase 6, not as a Phase 9 surprise"
    )
