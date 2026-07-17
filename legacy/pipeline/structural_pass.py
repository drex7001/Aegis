"""Structural pass: deterministic regex parsing of structured lists.

Targets PCoI-annex-style numbered arrest/remand lists of the form:

    1. Kasun WIJERATNE alias "Podda" (NIC 923456789V) — arrested 2023-02-14 — remanded, Welikada Prison (2023-02-15 to ongoing)

Everything this pass emits is tagged EXTRACTED (weight 1.0): the facts come
verbatim from an official list, and PRISON_CO_LOCATION edges are computed
deterministically from overlapping remand windows at the same facility —
never guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from itertools import combinations
from typing import Optional

from legacy.pipeline.models import (
    ConfidenceTag,
    CriminalNode,
    ExtractionMethod,
    ExtractionResult,
    LayerType,
    TemporalEdge,
)

# One arrest-list line. Dashes may be em/en/hyphen; alias and NIC are optional;
# remand end may be a date or the literal "ongoing".
ARREST_LINE_RE = re.compile(
    r"""^\s*(?P<num>\d+)\.\s+
        (?P<name>.+?)
        (?:\s+alias\s+["“](?P<alias>[^"”]+)["”])?
        (?:\s+\(NIC\s+(?P<nic>\d{9}[VvXx]|\d{12})\))?
        \s*[—–-]+\s*arrested\s+(?P<arrested>\d{4}-\d{2}-\d{2})
        \s*[—–-]+\s*remanded,?\s+(?P<facility>.+?)
        \s*\(\s*(?P<start>\d{4}-\d{2}-\d{2})\s+to\s+(?P<end>\d{4}-\d{2}-\d{2}|ongoing)\s*\)\s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)


@dataclass
class RemandRecord:
    node: CriminalNode
    facility: str
    start: date
    end: Optional[date]  # None = still remanded (ongoing)
    raw_line: str


def parse_arrest_list(text: str, source_file: str) -> list[RemandRecord]:
    records: list[RemandRecord] = []
    for line in text.splitlines():
        match = ARREST_LINE_RE.match(line)
        if not match:
            continue
        name = match.group("name").strip()
        alias = match.group("alias")
        node = CriminalNode(
            name=name,
            aliases=[alias] if alias else [],
            nic=match.group("nic"),
            source_file=source_file,
            source_excerpt=line.strip(),
        )
        end_raw = match.group("end")
        records.append(
            RemandRecord(
                node=node,
                facility=match.group("facility").strip(),
                start=date.fromisoformat(match.group("start")),
                end=None if end_raw.lower() == "ongoing" else date.fromisoformat(end_raw),
                raw_line=line.strip(),
            )
        )
    return records


def _overlap(a: RemandRecord, b: RemandRecord) -> Optional[tuple[date, Optional[date]]]:
    """Intersection of two remand windows; None end means open-ended."""
    start = max(a.start, b.start)
    ends = [e for e in (a.end, b.end) if e is not None]
    end = min(ends) if len(ends) == 2 else (ends[0] if ends else None)
    if end is not None and start > end:
        return None
    return start, end


def co_location_edges(records: list[RemandRecord]) -> list[TemporalEdge]:
    """PRISON_CO_LOCATION edges for every pair with overlapping remand at one facility."""
    edges: list[TemporalEdge] = []
    for a, b in combinations(records, 2):
        if a.facility.casefold() != b.facility.casefold():
            continue
        window = _overlap(a, b)
        if window is None:
            continue
        start, end = window
        edges.append(
            TemporalEdge(
                source=a.node.node_id,
                target=b.node.node_id,
                relation="co_located_with",
                layer=LayerType.PRISON_CO_LOCATION,
                confidence=ConfidenceTag.EXTRACTED,
                start_date=start,
                end_date=end,
                location=a.facility,
                source_file=a.node.source_file,
                source_excerpt=f"{a.raw_line} | {b.raw_line}",
                extraction_method=ExtractionMethod.STRUCTURAL,
            )
        )
    return edges


def extract_structural(text: str, source_file: str) -> ExtractionResult:
    """Full structural pass: parse the list, derive co-location edges."""
    records = parse_arrest_list(text, source_file)
    return ExtractionResult(
        nodes=[r.node for r in records],
        edges=co_location_edges(records),
    )
