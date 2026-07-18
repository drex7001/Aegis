"""Probabilistic ER with Splink on DuckDB (T19; spec 05 §3.2).

Like the deterministic rules, this **only ever writes `er_candidate` rows**.  A
score above threshold is a reason to ask a human, never a reason to merge
(ADR-027, Article VII).

**Weights are declared, not trained.**  Splink can estimate m and u from the
data, but EM on a corpus this size converges to whatever the corpus happens to
contain, and the result would be neither reproducible across runs nor
explainable to a reviewer.  So every level carries an explicit starting
probability, versioned in :mod:`aegis.er.settings`, and the T26 evaluation
harness is what moves them — with the eval diff in the same PR (spec 05 §6).

The full per-feature waterfall Splink computes is persisted verbatim on each
candidate (GOAL.md §10.4).  A score that exists only in a log cannot be
audited, evaluated, or defended to the person it was computed about.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.ids import new_id
from aegis.er.features import FeatureFrame, build_feature_frame
from aegis.er.settings import (
    SPLINK_MATCH_THRESHOLD,
    SPLINK_PRODUCER,
    SPLINK_VERSION,
)
from aegis.store import ErCandidate, IdentityMembership, IdentityNegativeConstraint


@dataclass
class SplinkRunReport:
    """What one Splink run proposed, and what it declined to."""

    compared: int = 0
    emitted: int = 0
    below_threshold: int = 0
    same_entity: int = 0
    already_open: int = 0
    suppressed_constraint: int = 0
    graph_snapshot_id: str | None = None
    settings_version: str = SPLINK_VERSION
    candidates: list[ErCandidate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "compared": self.compared,
            "emitted": self.emitted,
            "below_threshold": self.below_threshold,
            "same_entity": self.same_entity,
            "already_open": self.already_open,
            "suppressed_constraint": self.suppressed_constraint,
            "graph_snapshot_id": self.graph_snapshot_id,
            "settings_version": self.settings_version,
        }


def build_settings():
    """The comparison model (spec 05 §3.2).

    Imported lazily by :func:`run_splink` so that importing ``aegis.er`` does
    not pull pandas and duckdb into every CLI invocation.
    """
    import splink.comparison_level_library as cll
    from splink import SettingsCreator, block_on
    from splink.comparison_library import CustomComparison

    name = CustomComparison(
        output_column_name="name",
        comparison_description="transliteration-aware name similarity",
        comparison_levels=[
            cll.NullLevel("latin_key"),
            # Same characters in the *original* script — the strongest name
            # evidence there is, and it never passed through a romanizer.
            cll.ExactMatchLevel("script_key").configure(
                m_probability=0.55, u_probability=0.00005
            ),
            cll.ExactMatchLevel("latin_key").configure(
                m_probability=0.20, u_probability=0.0004
            ),
            cll.JaroWinklerLevel("latin_key", 0.92).configure(
                m_probability=0.13, u_probability=0.002
            ),
            cll.JaroWinklerLevel("latin_key", 0.85).configure(
                m_probability=0.07, u_probability=0.01
            ),
            cll.ElseLevel().configure(m_probability=0.05, u_probability=0.9875),
        ],
    )
    aliases = CustomComparison(
        output_column_name="alias_keys",
        comparison_description="any alias of A against any alias of B",
        comparison_levels=[
            cll.NullLevel("alias_keys"),
            cll.ArrayIntersectLevel("alias_keys", min_intersection=1).configure(
                m_probability=0.4, u_probability=0.005
            ),
            cll.ElseLevel().configure(m_probability=0.6, u_probability=0.995),
        ],
    )
    affiliation = CustomComparison(
        output_column_name="affiliations",
        comparison_description="shared organizations",
        comparison_levels=[
            cll.NullLevel("affiliations"),
            cll.ArrayIntersectLevel("affiliations", min_intersection=1).configure(
                m_probability=0.5, u_probability=0.05
            ),
            cll.ElseLevel().configure(m_probability=0.5, u_probability=0.95),
        ],
    )
    graph_context = CustomComparison(
        output_column_name="associates",
        comparison_description="shared associates from the recorded graph snapshot",
        comparison_levels=[
            cll.NullLevel("associates"),
            cll.ArrayIntersectLevel("associates", min_intersection=2).configure(
                m_probability=0.35, u_probability=0.01
            ),
            cll.ArrayIntersectLevel("associates", min_intersection=1).configure(
                m_probability=0.25, u_probability=0.05
            ),
            # Never a merge reason by itself (spec 05 §3.2): the weights above
            # are deliberately weaker than a name match, because two people in
            # one network share associates precisely *because* they are two
            # people in one network.
            cll.ElseLevel().configure(m_probability=0.4, u_probability=0.94),
        ],
    )
    date_of_birth = CustomComparison(
        output_column_name="date_of_birth",
        comparison_description="stated date of birth; disagreement is strong negative evidence",
        comparison_levels=[
            cll.NullLevel("date_of_birth"),
            cll.ExactMatchLevel("date_of_birth").configure(
                m_probability=0.9, u_probability=0.02
            ),
            # Two *stated* dates that differ. Agreement is weak evidence (many
            # people share a birthday); disagreement is strong, so this level
            # is what lets the model push a pair down rather than merely fail
            # to push it up.
            cll.ElseLevel().configure(m_probability=0.1, u_probability=0.98),
        ],
    )

    return SettingsCreator(
        link_type="dedupe_only",
        unique_id_column_name="unique_id",
        comparisons=[name, aliases, affiliation, graph_context, date_of_birth],
        blocking_rules_to_generate_predictions=[
            # Spec 05 §3.2. The phonetic block is what makes the seeded
            # transliteration pair comparable at all — its Latin keys differ
            # too much for a prefix block to catch.
            block_on("phonetic_key"),
            block_on("substr(latin_key, 1, 4)"),
            block_on("affiliations"),
        ],
        retain_intermediate_calculation_columns=True,
        additional_columns_to_retain=["entity_id"],
    )


def _existing_pairs(session: Session) -> set[tuple[str, str]]:
    return {
        (a, b)
        for a, b in session.execute(
            select(ErCandidate.mention_a, ErCandidate.mention_b).where(
                ErCandidate.disposition != "superseded"
            )
        )
    }


def _constrained_pairs(session: Session) -> set[tuple[str, str]]:
    return {
        (a, b)
        for a, b in session.execute(
            select(
                IdentityNegativeConstraint.mention_a,
                IdentityNegativeConstraint.mention_b,
            ).where(IdentityNegativeConstraint.superseded_by.is_(None))
        )
    }


def _waterfall(row: dict[str, Any]) -> dict[str, Any]:
    """The per-feature explanation, kept verbatim (GOAL.md §10.4)."""
    features: dict[str, Any] = {"rule": "splink"}
    for key, value in row.items():
        if key.startswith(("gamma_", "bf_", "tf_")):
            features[key] = _plain(value)
    return features


def _plain(value: Any) -> Any:
    """numpy scalars do not survive a JSONB round trip; make them Python."""
    item = getattr(value, "item", None)
    return item() if callable(item) else value


def run_splink(
    session: Session,
    *,
    frame: FeatureFrame | None = None,
    threshold: float = SPLINK_MATCH_THRESHOLD,
) -> SplinkRunReport:
    """Score candidate pairs and persist those above threshold."""
    import pandas as pd
    from splink import DuckDBAPI, Linker

    frame = frame if frame is not None else build_feature_frame(session)
    report = SplinkRunReport(graph_snapshot_id=frame.graph_snapshot_id)
    if len(frame) < 2:
        return report

    linker = Linker(
        pd.DataFrame(frame.rows), build_settings(), db_api=DuckDBAPI()
    )
    predictions = linker.inference.predict(
        threshold_match_probability=0.0
    ).as_pandas_dataframe()
    report.compared = len(predictions)

    entity_by_mention = {row["unique_id"]: row["entity_id"] for row in frame.rows}
    existing = _existing_pairs(session)
    constrained = _constrained_pairs(session)

    for _, prediction in predictions.iterrows():
        row = prediction.to_dict()
        left, right = str(row["unique_id_l"]), str(row["unique_id_r"])
        pair = (left, right) if left < right else (right, left)
        probability = float(row["match_probability"])
        if probability < threshold:
            report.below_threshold += 1
            continue
        if entity_by_mention.get(pair[0]) == entity_by_mention.get(pair[1]):
            report.same_entity += 1
            continue
        # Constraints gate *emission*, not display: a pair a human already
        # rejected is never put back in front of them (spec 05 §3.3).
        if pair in constrained:
            report.suppressed_constraint += 1
            continue
        if pair in existing:
            report.already_open += 1
            continue
        candidate = ErCandidate(
            candidate_id=new_id("cnd"),
            mention_a=pair[0],
            mention_b=pair[1],
            producer=SPLINK_PRODUCER,
            producer_version=SPLINK_VERSION,
            graph_snapshot_id=frame.graph_snapshot_id,
            score=probability,
            features=_waterfall(row),
            # Never pre-verified: the pre-verified band means "confirmable in
            # bulk without reading each one", and a probabilistic score is
            # exactly the thing a human has to read (spec 05 §3.1).
            pre_verified=False,
        )
        session.add(candidate)
        existing.add(pair)
        report.candidates.append(candidate)
        report.emitted += 1

    session.flush()
    return report


__all__ = ["SplinkRunReport", "build_settings", "run_splink"]
