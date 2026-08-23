"""The caveat catalog — Article IX made structural (spec 12 §9.3).

> *"Association is not guilt. A metric that renders without its caveat is the
> system asserting something it did not compute."*

The charter's risk table names the failure this module exists to prevent:
metrics read as guilt, "most connected" read as leadership. The mitigation it
chose is that caveats are **structural, not UI decoration** — so the text lives
here, in code, and is **copied into every `analytic_finding` row** at write
time. There is no rendering path that fetches a caveat, which is why there is no
rendering path that can fail to.

Two rules make that stick, and both are enforced by
``tests/contract/test_caveat_catalog.py`` rather than by review:

1. **Every metric has one.** A metric added to the analytics service without an
   entry here fails the contract test, so a caveat cannot be an afterthought.
2. **No leadership language** in any metric name, metric label or rendered
   analytics string (:data:`FORBIDDEN_LANGUAGE`). A centrality score is a count
   of what was written down; describing it as seniority, command or importance
   is the system asserting something it did not compute. Caveat text is held to
   the opposite rule (:data:`DENIAL_MARKERS`) for the reason given there.

Wording is versioned. Bumping :data:`CAVEAT_VERSION` does not rewrite issued
findings: a finding records what was said at the time it was made, and silently
improving the disclaimer on a finding somebody already acted on is not an
improvement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

#: Bump when any wording below changes. Findings keep the version they carried.
CAVEAT_VERSION = "1"


@dataclass(frozen=True, slots=True)
class Caveat:
    """What a metric measures, what it does not mean, and what biases it."""

    metric: str
    label: str
    text: str
    version: str = CAVEAT_VERSION


def _caveat(metric: str, label: str, text: str) -> Caveat:
    return Caveat(metric=metric, label=label, text=" ".join(text.split()))


#: One entry per metric the analytics service offers (spec 12 §9.1). Keyed by
#: the metric name that appears in the route path and in the run manifest, so a
#: lookup miss is impossible to paper over.
CAVEATS: Mapping[str, Caveat] = {
    caveat.metric: caveat
    for caveat in (
        _caveat(
            "k_hop",
            "Neighbourhood",
            """
            Everything reachable within the given number of hops through claims
            you are permitted to read. A different clearance produces a
            different neighbourhood. This describes the readable record, not
            the world.
            """,
        ),
        _caveat(
            "shortest_path",
            "Shortest path",
            """
            The shortest route through recorded claims — not the shortest real
            relationship. A path exists because records exist, and a missing
            path means missing records, not absence of connection. A path is
            not a chain of instruction, causation, or responsibility.
            """,
        ),
        _caveat(
            "community",
            "Community",
            """
            A partition computed from edge weights the caller supplied. A cell
            is a question to investigate, not a finding about membership,
            affiliation, or shared purpose. Two people in one cell may never
            have met.
            """,
        ),
        _caveat(
            "betweenness",
            "Betweenness",
            """
            How often an entity lies on a shortest recorded path between
            others. It measures the shape of what has been written down, not
            the flow of anything real. A high score is a reason to ask why the
            records connect through this entity — it is not an answer.
            """,
        ),
        _caveat(
            "degree",
            "Recorded connections",
            """
            A count of recorded connections. An entity scores highly when it is
            frequently reported, which reflects the reporting. This is not a
            measure of influence, seniority, control, or responsibility, and
            the highest score in a graph is not evidence of any of them.
            """,
        ),
        _caveat(
            "shared_identifier",
            "Shared identifier",
            """
            Two records carry the same exact identifier. Identifiers are
            transcribed by people and reused by institutions. This is a strong
            lead and never an identity decision — only a human adjudication
            merges identities (Articles V and VII).
            """,
        ),
    )
}

#: Words that may not appear in a metric name, a metric label, or any rendered
#: analytics string. Each one turns a count of recorded connections into an
#: assertion about a person's role, which is precisely what Article IX forbids
#: and what the charter's risk table predicted would happen by accident.
#:
#: `degree`'s label is "Recorded connections" rather than "Most connected"
#: because a superlative does the same work as these words with none of the
#: vocabulary.
#:
#: **Caveat text is deliberately out of scope**, and this is the subtlety worth
#: reading twice. A caveat's job is to name the wrong reading and deny it, so a
#: word list applied to caveats would forbid the sentence "this is not a measure
#: of seniority" — making every caveat weaker in the name of enforcing them.
#: Caveats are held to :data:`DENIAL_MARKERS` instead, which is the stronger
#: requirement: not "avoids the word" but "says the thing is not true".
FORBIDDEN_LANGUAGE = frozenset(
    {
        "leader",
        "leadership",
        "boss",
        "kingpin",
        "mastermind",
        "ringleader",
        "chief",
        "commander",
        "in charge",
        "runs the",
        "seniority",
        "senior figure",
        "hierarchy",
        "rank",
        "importance",
        "most important",
        "key player",
        "culpable",
        "guilty",
        "guilt",
        "perpetrator",
    }
)


#: A caveat must **deny** a wrong reading, not merely describe a computation.
#: Every entry in :data:`CAVEATS` has to contain one of these as a whole word.
#:
#: The bar is deliberately low, because the failure it guards against is not
#: subtle: a caveat rewritten into a method note — "betweenness is the fraction
#: of shortest paths passing through a node" — is accurate, useless, and
#: contains no negation at all. Anything that still denies something passes.
DENIAL_MARKERS = ("not", "never", "no", "cannot", "nothing")


def caveat_for(metric: str) -> Caveat:
    """The caveat a finding must carry, or a hard failure.

    Deliberately raises rather than returning a default. A missing caveat is
    the exact failure Article IX is about, and a bland placeholder would let a
    finding render as if it had been reviewed.
    """
    try:
        return CAVEATS[metric]
    except KeyError:
        raise KeyError(
            f"no caveat is declared for metric {metric!r} — a metric without "
            "its Article IX caveat may not produce a finding (spec 12 §9.3). "
            f"Declared metrics: {sorted(CAVEATS)}"
        ) from None


__all__ = [
    "CAVEATS",
    "CAVEAT_VERSION",
    "Caveat",
    "DENIAL_MARKERS",
    "FORBIDDEN_LANGUAGE",
    "caveat_for",
]
