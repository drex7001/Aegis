"""Numeric search-quality targets, defined at phase start (spec 11 §8, H-22).

H-22's objection to the pre-authored plan was that P6 postponed precision and
recall targets to the phase itself, while ADR-012's OpenSearch trigger depends
on them — so the trigger could never fire on evidence, only on opinion. The fix
is that the numbers exist **before** the implementation does, in code, where the
CI gate reads the same constants the spec quotes.

Nothing here runs a query. This module is the target table and the trigger
condition; `aegis/search/quality.py` (T68) computes the measurements and
compares them against these values, and
``tests/contract/test_search_targets.py`` fails when spec 11 §8 and this file
disagree.

The precedent is ``aegis/er/settings.py``: a quality gate whose thresholds live
in one importable place cannot be quietly relaxed in a test file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class QualityTarget:
    """A floor, not a goal. Below either number the gate fails."""

    #: Of the first five results, the fraction that are true matches.
    precision_at_5: float
    #: Of the true matches that exist, the fraction found in the first twenty.
    recall_at_20: float


#: Per writing system. Cross-script is its own row because it is a different
#: task: `latin_key` romanization is lossy in a direction that manufactures
#: agreement (spec 11 §3.3), so a Latin query reaching a Sinhala name is held to
#: a lower floor **and said to be**, rather than being allowed to drag the
#: same-script numbers down while looking like one metric.
SCRIPT_TARGETS: Mapping[str, QualityTarget] = {
    "latin": QualityTarget(precision_at_5=0.90, recall_at_20=0.85),
    "sinhala": QualityTarget(precision_at_5=0.80, recall_at_20=0.70),
    "tamil": QualityTarget(precision_at_5=0.80, recall_at_20=0.70),
    "cross_script": QualityTarget(precision_at_5=0.70, recall_at_20=0.60),
}

#: Per searchable resource. A document hit is a weaker signal than an entity
#: hit — the text is long, the query is short — so the floors differ.
RESOURCE_TARGETS: Mapping[str, QualityTarget] = {
    "entity": QualityTarget(precision_at_5=0.85, recall_at_20=0.80),
    "claim": QualityTarget(precision_at_5=0.75, recall_at_20=0.70),
    "document": QualityTarget(precision_at_5=0.70, recall_at_20=0.60),
}

#: Latency budget over the fictional corpus, single connection, in CI.
LATENCY_BUDGET_MS: Mapping[str, int] = {"p50": 150, "p95": 400}

#: One statement timeout per search request (spec 11 §5.3). A pathological
#: trigram query fails as a 503 rather than holding a connection open.
STATEMENT_TIMEOUT_MS = 3_000

#: Identifiers are matched by exact equality, never by similarity (ADR-053).
#: This is a pass/fail assertion rather than a threshold on purpose: a single
#: fuzzy identifier hit is a confident wrong person, so it fails the gate
#: instead of lowering a score somebody can argue is still acceptable.
IDENTIFIER_PRECISION = 1.0

#: The ADR-012 trigger, written next to the numbers that watch it (T68 AC).
#: If it fires, remediation lands inside Phase 6 before its gate (H-22) — not
#: as a Phase 9 surprise.
OPENSEARCH_TRIGGER = (
    "Fires when the golden set fails any target in this module after a "
    "documented tuning attempt, or p95 exceeds "
    f"{LATENCY_BUDGET_MS['p95']} ms on the real corpus, or the corpus passes "
    "500 000 searchable rows."
)

#: The row count in the trigger above, separated so the gate can read it.
OPENSEARCH_TRIGGER_ROWS = 500_000


__all__ = [
    "IDENTIFIER_PRECISION",
    "LATENCY_BUDGET_MS",
    "OPENSEARCH_TRIGGER",
    "OPENSEARCH_TRIGGER_ROWS",
    "QualityTarget",
    "RESOURCE_TARGETS",
    "SCRIPT_TARGETS",
    "STATEMENT_TIMEOUT_MS",
]
