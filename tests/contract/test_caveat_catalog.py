"""The caveat catalog is complete, quoted correctly, and cannot say "leader" (T66).

T66's acceptance criterion is that *"the caveat catalog covers every planned
metric and 'most connected' is never worded as leadership"*. Both halves are
checked here rather than read, because a governance rule enforced by review is a
governance rule that survives exactly as long as the reviewer's attention.

Three things are proved:

* **Completeness in both directions.** Every metric spec 12 §9.1 says records a
  finding has a caveat, and every caveat belongs to such a metric. A one-way
  check would let a metric ship uncovered, or let a caveat rot after its metric
  was renamed.
* **The spec quotes the code.** Spec 12 §9.3 restates the catalog; the two are
  compared word for word, so the document a reviewer reads and the string a
  finding carries cannot drift apart.
* **The word list bites.** Applying it to a deliberately bad string must fail —
  an exhaustive negative check that passes vacuously proves nothing, which is
  the same trap the P5 mark matrix had to avoid.
"""

from __future__ import annotations

import re

import pytest

from aegis.analytics.caveats import (
    CAVEAT_VERSION,
    CAVEATS,
    DENIAL_MARKERS,
    FORBIDDEN_LANGUAGE,
    caveat_for,
)
from tests.support.paths import REPO_ROOT

pytestmark = pytest.mark.requirement("Article-IX", "T66", "H-23")

SPEC = REPO_ROOT / "speckit" / "specs" / "12-object-sets-analytics.md"


def _spec_text() -> str:
    return SPEC.read_text(encoding="utf-8")


def _section(name: str) -> str:
    """The body of one numbered spec section, up to the next heading of any level.

    Any level matters: §9.3 is followed by `## 10`, not by `### 9.4`, so a
    `###`-only scan would swallow §11's and §12's two-column tables and compare
    this catalog against the wrong rows.
    """
    text = _spec_text()
    start = text.index(f"### {name}")
    rest = text[start:]
    following = re.search(r"\n#{2,4} ", rest[1:])
    return rest if following is None else rest[: following.start() + 1]


def _table_rows(section: str) -> list[list[str]]:
    rows = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line) <= set("|- "):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        rows.append(cells)
    return rows


def _plain(markdown: str) -> str:
    """Strip the emphasis and code markers a table cell carries."""
    return " ".join(markdown.replace("**", "").replace("`", "").split())


# ── completeness ────────────────────────────────────────────────────────────


def _metrics_that_record_findings() -> set[str]:
    """From spec 12 §9.1 — the routes whose "Records a finding" column says yes."""
    metrics = set()
    for cells in _table_rows(_section("9.1")):
        if len(cells) < 3 or cells[2].strip().lower() != "yes":
            continue
        match = re.search(r"/v1/analytics/(\w+)", cells[1])
        assert match, f"a finding-recording row names no analytics route: {cells}"
        metrics.add(match.group(1))
    return metrics


def test_every_finding_recording_metric_has_a_caveat() -> None:
    missing = _metrics_that_record_findings() - set(CAVEATS)
    assert not missing, (
        f"metrics record findings with no Article IX caveat: {sorted(missing)}"
    )


def test_no_caveat_is_orphaned() -> None:
    """The other direction: a caveat whose metric was renamed is dead text."""
    orphans = set(CAVEATS) - _metrics_that_record_findings()
    assert not orphans, f"caveats for metrics no route offers: {sorted(orphans)}"


def test_the_spec_lists_the_same_metrics_as_the_code() -> None:
    """Guards the parser itself: a §9.1 rewrite that breaks it must not pass quietly."""
    assert _metrics_that_record_findings(), "parsed no metrics from spec 12 §9.1"
    assert len(CAVEATS) >= 6, "the phase plans six metrics; the catalog shrank"


# ── the spec quotes the code ────────────────────────────────────────────────


def test_the_spec_table_quotes_every_caveat_verbatim() -> None:
    quoted = {
        _plain(cells[0]): _plain(cells[1])
        for cells in _table_rows(_section("9.3"))
        if len(cells) == 2 and cells[0] not in {"Metric", "---"}
    }
    for metric, caveat in CAVEATS.items():
        assert metric in quoted, f"spec 12 §9.3 does not list {metric!r}"
        assert quoted[metric] == _plain(caveat.text), (
            f"spec 12 §9.3 and aegis/analytics/caveats.py disagree on {metric!r}:\n"
            f"  spec: {quoted[metric]}\n"
            f"  code: {_plain(caveat.text)}"
        )


# ── the leadership rule ─────────────────────────────────────────────────────


def _offending(text: str) -> list[str]:
    lowered = text.lower()
    return sorted(word for word in FORBIDDEN_LANGUAGE if word in lowered)


@pytest.mark.parametrize("metric", sorted(CAVEATS))
def test_no_metric_name_or_label_uses_leadership_language(metric: str) -> None:
    caveat = CAVEATS[metric]
    assert not _offending(caveat.metric), f"{metric}: name uses {_offending(caveat.metric)}"
    assert not _offending(caveat.label), f"{metric}: label uses {_offending(caveat.label)}"


def test_no_label_reaches_for_a_superlative_instead() -> None:
    """"Most connected" does the same work with none of the vocabulary."""
    for caveat in CAVEATS.values():
        assert "most " not in caveat.label.lower(), (
            f"{caveat.metric}: a superlative label ({caveat.label!r}) ranks people "
            "without saying what the ranking means"
        )


def test_the_word_list_actually_catches_something() -> None:
    """An exhaustive negative check that passes vacuously proves nothing."""
    assert _offending("The most connected node is the group's leader")
    assert _offending("Ranked by importance")
    assert not _offending("A count of recorded connections")


@pytest.mark.parametrize("metric", sorted(CAVEATS))
def test_every_caveat_denies_something(metric: str) -> None:
    """A caveat rewritten into a method note is accurate, useless, and denies nothing."""
    words = set(re.findall(r"[a-z]+", CAVEATS[metric].text.lower()))
    assert words & set(DENIAL_MARKERS), (
        f"{metric}: the caveat describes a computation without denying any "
        f"wrong reading of it — {CAVEATS[metric].text!r}"
    )


def test_the_denial_rule_actually_catches_something() -> None:
    method_note = "Betweenness is the fraction of shortest paths through a node."
    words = set(re.findall(r"[a-z]+", method_note.lower()))
    assert not words & set(DENIAL_MARKERS)


def test_degree_denies_the_reading_the_charter_predicted() -> None:
    """The risk table's named failure, asserted directly rather than by word list."""
    text = CAVEATS["degree"].text.lower()
    assert "not a measure of influence" in text
    assert "seniority" in text, "the caveat must name the wrong reading to deny it"
    assert "highest score" in text and "not evidence" in text


# ── versioning and lookup ───────────────────────────────────────────────────


@pytest.mark.parametrize("metric", sorted(CAVEATS))
def test_every_caveat_carries_the_current_version(metric: str) -> None:
    assert CAVEATS[metric].version == CAVEAT_VERSION


def test_an_undeclared_metric_raises_rather_than_defaulting() -> None:
    """A bland placeholder would let a finding render as if it had been reviewed."""
    with pytest.raises(KeyError) as excinfo:
        caveat_for("influence_score")
    assert "influence_score" in str(excinfo.value)
    assert "spec 12" in str(excinfo.value)


def test_caveat_text_is_a_single_normalized_paragraph() -> None:
    """It is copied into a database column and rendered as-is."""
    for caveat in CAVEATS.values():
        assert "\n" not in caveat.text
        assert "  " not in caveat.text
        assert len(caveat.text) > 100, f"{caveat.metric}: too short to say anything"
