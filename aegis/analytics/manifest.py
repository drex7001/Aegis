"""The run manifest, and what makes reproducibility checkable (T72, ADR-055).

H-23's objection to the pre-authored plan was that *"rerunning the same inputs
reproduces the finding"* is not a testable claim: neither an object set nor a
projection is immutable, so "the same inputs" names nothing. ADR-055 replaces
it with a statement that is testable —

> **Equal manifests produce equal finding digests.**

— and this module is what makes a manifest complete enough to mean it.

Three fields carry most of the weight.

**`implementation`** records which library actually ran, with its version.
`aegis/analytics/clustering.py` falls back from Leiden to NetworkX Louvain when
igraph is unavailable. It does label the result — better than the first reading
of it credited — but a label on a summary nobody is obliged to persist is not
provenance. Here the fallback is a different manifest, and therefore a
different run.

**The `projection_*` stamps** record *which* projection was read. Not whether
it was fresh: `is_stale` answers that, and it answers a different question.
Freshness is an operator's question about a cache; provenance is a finding's
question about its own inputs. Recording the stamps is what closes the Phase-5
carryover without changing what `is_stale` means.

**`authorization_digest`** records the clearance and case membership the run
saw. A finding computed under a narrower clearance is a different finding, and
Article VI is the reason the manifest has to say so rather than leave it to be
inferred from who happened to run it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from importlib import metadata
from typing import Any

from aegis.api.auth import UserContext

#: Bumped when a metric's own implementation changes in a way that could move
#: its output. Distinct from the library version, which changes underneath us.
METHOD_VERSION = "analytics-v1"

#: Fields excluded when comparing two manifests for reproducibility. Who ran
#: it, why, and when are facts about the *run*, not about the answer — two
#: analysts asking the same question of the same corpus must get the same
#: finding, or the digest would be measuring the analyst.
NON_REPRODUCIBILITY_FIELDS = frozenset(
    {"run_id", "actor", "purpose", "started_at", "finished_at"}
)


def digest_of(value: Any) -> str:
    """A stable digest over any JSON-able value.

    `sort_keys` and a canonical separator, so two dictionaries that differ only
    in insertion order digest the same. Without that, "equal manifests" would
    depend on the order a dict happened to be built in.
    """
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def authorization_digest(user: UserContext, case_ids) -> str:
    """What the run was allowed to see, as one value.

    Clearance *and* case membership, because either alone would let two
    genuinely different views produce the same digest — and the digest exists
    precisely to stop a finding from one view being compared with a finding
    from another.
    """
    return digest_of(
        {"clearance": user.clearance, "cases": sorted(case_ids), "roles": sorted(user.roles)}
    )


def edge_digest(edges) -> str:
    """A digest over the edge rows consumed, sorted.

    So a projection rebuilt between two runs is visible as a different digest
    even when its stamps happen to match — the rows are what the algorithm
    read, and they are what a later reader needs to know were the same.
    """
    return digest_of(
        sorted(
            [edge.edge_id, edge.subject_id, edge.object_id, edge.predicate]
            for edge in edges
        )
    )


def library_version(name: str) -> str:
    try:
        return f"{name} {metadata.version(name)}"
    except metadata.PackageNotFoundError:
        # Recorded as unknown rather than omitted: a manifest that silently
        # dropped the field would compare equal to one from a different build.
        return f"{name} (version unknown)"


def settings_digest() -> str:
    """The configuration that could change an answer.

    Deliberately narrow. Every setting would make the digest change on an
    unrelated edit and stop anything ever comparing equal; the ones here are
    those an analytic result can actually depend on.
    """
    from aegis.er.settings import RULES_VERSION, SPLINK_MATCH_THRESHOLD, SPLINK_VERSION
    from aegis.projections.edges import (
        AGGREGATION_METHOD,
        AGGREGATION_METHOD_VERSION,
    )

    return digest_of(
        {
            "aggregation_method": AGGREGATION_METHOD,
            "aggregation_method_version": AGGREGATION_METHOD_VERSION,
            "rules_version": RULES_VERSION,
            "splink_version": SPLINK_VERSION,
            "splink_match_threshold": SPLINK_MATCH_THRESHOLD,
        }
    )


def code_version() -> str:
    try:
        return metadata.version("aegis")
    except metadata.PackageNotFoundError:
        return "unknown"


@dataclass
class Manifest:
    """Everything a reader needs to know what a run actually did."""

    method: str
    method_version: str
    implementation: str
    parameters: dict[str, Any] = field(default_factory=dict)
    seed: int | None = None
    input_kind: str = "projection"
    object_set_id: str | None = None
    object_set_version: int | None = None
    evaluation_digest: str | None = None
    edge_digest: str = ""
    projection_built_at_revision_id: int | None = None
    projection_builder_version: str | None = None
    projection_aggregation_method_version: str | None = None
    ontology_version: str = ""
    identity_revision_id: int = 0
    code_version: str = ""
    settings_digest: str = ""
    actor: str = ""
    purpose: str | None = None
    authorization_digest: str = ""
    caveat_version: str = ""

    def reproducibility_key(self) -> str:
        """The digest two runs must share to be expected to agree.

        This is ADR-055's definition, made mechanical: everything except who
        ran it, why, and when.
        """
        payload = {
            name: value
            for name, value in self.__dict__.items()
            if name not in NON_REPRODUCIBILITY_FIELDS
        }
        return digest_of(payload)


__all__ = [
    "METHOD_VERSION",
    "NON_REPRODUCIBILITY_FIELDS",
    "Manifest",
    "authorization_digest",
    "code_version",
    "digest_of",
    "edge_digest",
    "library_version",
    "settings_digest",
]
