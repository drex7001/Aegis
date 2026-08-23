"""Search quality, measured against the targets defined at phase start (T68).

H-22's objection to the pre-authored plan was that search quality had no
numbers until the phase that was supposed to be gated by them, so ADR-012's
OpenSearch trigger could only ever fire on opinion. T66 put the numbers in
`aegis/search/targets.py`. This measures against them.

Two decisions worth stating, because both are places a quality harness can
quietly flatter itself.

**Precision@5 divides by what was returned, not by 5.** A query with one
correct hit and nothing else would otherwise score 0.2 — punishing a search for
being *precise*. The denominator is `min(k, len(returned))`, so a short, clean
result set scores 1.0, which is what it deserves.

**Every metric is computed over one user's authorized view.** The evaluating
user's `claim_filters` apply exactly as they do in production, so a target can
never be met by widening what is visible (spec 11 §8). A harness that evaluated
as a superuser would measure a system nobody uses.

The identifier gate is deliberately not a threshold. ADR-053 trades recall away
so that a mistyped identifier returns nothing rather than a confident wrong
person; a single fuzzy identifier hit therefore **fails**, rather than lowering
a number somebody can argue is still acceptable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aegis.search.targets import (
    IDENTIFIER_PRECISION,
    LATENCY_BUDGET_MS,
    RESOURCE_TARGETS,
    SCRIPT_TARGETS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLDEN_SET = REPO_ROOT / "data" / "sample" / "search" / "golden-set.json"
DEFAULT_REPORT = REPO_ROOT / "output" / "search-evaluation.json"

#: The two cut-offs the targets are stated at (spec 11 §8).
PRECISION_AT = 5
RECALL_AT = 20


class QualityError(RuntimeError):
    """The golden set is invalid, or one or more quality gates failed."""


# ── the golden set ──────────────────────────────────────────────────────────


class GoldenEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: str
    label: str
    #: Names as written in a source. Each becomes a `mention` resolved to the
    #: entity, which is what makes a romanized query reach a Sinhala name.
    mentions: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)


class GoldenClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    subject: str
    predicate: str
    value: str | None = None
    excerpt: str | None = None
    handling: str = "open"

    @field_validator("value")
    @classmethod
    def fictional_identifier_only(cls, value: str | None) -> str | None:
        """No real national identifier may enter a fixture (`data/real/README.md`).

        Checked here rather than in review because a fixture is exactly where a
        real one would be pasted "just to test the format".
        """
        if value and value.upper().startswith("FIXTURE-ID"):
            return value
        if value and any(char.isdigit() for char in value) and len(value) >= 9:
            raise ValueError(
                f"{value!r} looks like a real identifier; fixtures use the "
                "FIXTURE-ID- placeholder prefix"
            )
        return value


class GoldenDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    text: str
    handling: str = "open"


class GoldenQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str
    #: One of `SCRIPT_TARGETS`. `cross_script` means a Latin query that must
    #: reach a name written in another script — a different task, held to a
    #: different floor, and said to be (spec 11 §3.3).
    script: Literal["latin", "sinhala", "tamil", "cross_script"]
    resource: Literal["entity", "claim", "document"]
    #: Golden-set ids that a correct answer contains. May be empty: "nothing"
    #: is the right answer to a near-miss identifier.
    relevant: list[str] = Field(default_factory=list)
    #: Held to `IDENTIFIER_PRECISION` rather than to a threshold (ADR-053).
    identifier: bool = False
    note: str | None = None

    @model_validator(mode="after")
    def an_identifier_query_states_its_expectation(self) -> "GoldenQuery":
        if self.identifier and not self.note:
            raise ValueError(
                "an identifier query must carry a note saying whether it is an "
                "exact match or a near miss — the two look identical in JSON"
            )
        return self


class GoldenSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_name: Literal["aegis.search-golden/v1"] = Field(alias="schema")
    description: str
    entities: list[GoldenEntity] = Field(min_length=1)
    claims: list[GoldenClaim] = Field(default_factory=list)
    documents: list[GoldenDocument] = Field(default_factory=list)
    queries: list[GoldenQuery] = Field(min_length=1)

    @model_validator(mode="after")
    def every_reference_resolves(self) -> "GoldenSet":
        ids = {item.id for item in (*self.entities, *self.claims, *self.documents)}
        if len(ids) != len(self.entities) + len(self.claims) + len(self.documents):
            raise ValueError("golden-set ids must be unique across all kinds")
        for claim in self.claims:
            if claim.subject not in {entity.id for entity in self.entities}:
                raise ValueError(f"claim {claim.id} names an unknown subject")
        for query in self.queries:
            unknown = sorted(set(query.relevant) - ids)
            if unknown:
                raise ValueError(f"query {query.q!r} expects unknown ids: {unknown}")
        covered = {query.script for query in self.queries}
        missing = set(SCRIPT_TARGETS) - covered
        if missing:
            raise ValueError(
                f"no query exercises {sorted(missing)}; a target with no query "
                "is a number nothing measures"
            )
        covered = {query.resource for query in self.queries}
        missing = set(RESOURCE_TARGETS) - covered
        if missing:
            raise ValueError(f"no query exercises {sorted(missing)}")
        return self


def load_golden_set(path: Path = DEFAULT_GOLDEN_SET) -> tuple[GoldenSet, str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise QualityError(f"cannot read golden set {path}: {exc}") from exc
    try:
        return GoldenSet.model_validate_json(raw), sha256(raw).hexdigest()
    except Exception as exc:
        raise QualityError(f"invalid search golden set: {exc}") from exc


# ── the measurements ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class QueryOutcome:
    q: str
    script: str
    resource: str
    precision_at_5: float
    recall_at_20: float
    latency_ms: float
    returned: int
    identifier: bool
    identifier_violation: bool


@dataclass
class QualityReport:
    schema: str = "aegis.search-quality/v1"
    golden_set_sha256: str = ""
    normalization_version: str = ""
    query_count: int = 0
    by_script: dict[str, dict[str, float]] = field(default_factory=dict)
    by_resource: dict[str, dict[str, float]] = field(default_factory=dict)
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    identifier_precision: float = 1.0
    identifier_violations: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    outcomes: list[dict] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict:
        data = asdict(self)
        data["passed"] = self.passed
        return data


def precision_at_k(returned: Sequence[str], relevant: set[str], k: int) -> float:
    """Correct hits in the first `k`, over how many were actually returned.

    Dividing by `k` would score a query that returned one correct hit and
    nothing else at `1/k` — punishing precision for being precise. When nothing
    is returned and nothing was expected, the answer is 1.0: the search was
    right.
    """
    top = list(returned)[:k]
    if not top:
        return 1.0 if not relevant else 0.0
    return sum(1 for item in top if item in relevant) / len(top)


def recall_at_k(returned: Sequence[str], relevant: set[str], k: int) -> float:
    if not relevant:
        # Nothing to recall. Scoring 0.0 here would drag the average down for
        # a query whose correct answer is "nothing", which is the identifier
        # near-miss case (ADR-053) and a result the gate *wants*.
        return 1.0
    top = set(list(returned)[:k])
    return len(top & relevant) / len(relevant)


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return ordered[index]


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def measure(
    golden: GoldenSet,
    digest: str,
    *,
    run_query,
    normalization_version: str,
) -> QualityReport:
    """Run every golden query through `run_query` and score the answers.

    `run_query(q) -> list[str]` returns golden-set ids in rank order. The
    indirection is what keeps this module database-free and therefore unit
    testable: the integration harness passes a closure over the real route, and
    a test can pass a stub that returns a known ranking.
    """
    report = QualityReport(
        golden_set_sha256=digest,
        normalization_version=normalization_version,
        query_count=len(golden.queries),
    )
    outcomes: list[QueryOutcome] = []

    for query in golden.queries:
        relevant = set(query.relevant)
        started = perf_counter()
        returned = list(run_query(query.q))
        latency_ms = (perf_counter() - started) * 1000

        violation = bool(
            query.identifier and set(returned[:RECALL_AT]) - relevant
        )
        outcome = QueryOutcome(
            q=query.q,
            script=query.script,
            resource=query.resource,
            precision_at_5=precision_at_k(returned, relevant, PRECISION_AT),
            recall_at_20=recall_at_k(returned, relevant, RECALL_AT),
            latency_ms=latency_ms,
            returned=len(returned),
            identifier=query.identifier,
            identifier_violation=violation,
        )
        outcomes.append(outcome)
        if violation:
            report.identifier_violations.append(query.q)

    report.outcomes = [asdict(outcome) for outcome in outcomes]
    report.latency_p50_ms = percentile([o.latency_ms for o in outcomes], 0.50)
    report.latency_p95_ms = percentile([o.latency_ms for o in outcomes], 0.95)
    report.identifier_precision = (
        0.0 if report.identifier_violations else IDENTIFIER_PRECISION
    )

    for label, targets, attribute in (
        ("script", SCRIPT_TARGETS, "script"),
        ("resource", RESOURCE_TARGETS, "resource"),
    ):
        bucket: dict[str, dict[str, float]] = {}
        for name, target in targets.items():
            selected = [o for o in outcomes if getattr(o, attribute) == name]
            precision = _mean([o.precision_at_5 for o in selected])
            recall = _mean([o.recall_at_20 for o in selected])
            bucket[name] = {
                "precision_at_5": round(precision, 4),
                "recall_at_20": round(recall, 4),
                "queries": len(selected),
            }
            if precision < target.precision_at_5:
                report.failures.append(
                    f"{label} {name}: precision@5 {precision:.3f} "
                    f"< {target.precision_at_5}"
                )
            if recall < target.recall_at_20:
                report.failures.append(
                    f"{label} {name}: recall@20 {recall:.3f} < {target.recall_at_20}"
                )
        if label == "script":
            report.by_script = bucket
        else:
            report.by_resource = bucket

    if report.identifier_violations:
        report.failures.append(
            "identifier queries returned a hit that is not an exact match: "
            f"{report.identifier_violations} — ADR-053 makes this a failure, "
            "not a score"
        )
    for name, budget in LATENCY_BUDGET_MS.items():
        measured = getattr(report, f"latency_{name}_ms")
        if measured > budget:
            report.failures.append(f"latency {name} {measured:.0f} ms > {budget} ms")

    return report


__all__ = [
    "DEFAULT_GOLDEN_SET",
    "DEFAULT_REPORT",
    "GoldenSet",
    "PRECISION_AT",
    "QualityError",
    "QualityReport",
    "QueryOutcome",
    "RECALL_AT",
    "load_golden_set",
    "measure",
    "percentile",
    "precision_at_k",
    "recall_at_k",
]
