"""Submission criteria — the write-side gate the ontology declares (spec 08 §6.3).

Each criterion is a named predicate over (actor, supplied parameters, target
state) that the actions layer evaluates *before* the write. A failure is an
audited denial, not a silent 403 (§6.4).

Phase 3 registers exactly three, and each makes an **existing** policy
declarative rather than inventing a new one — T34 closes the gap ADR-040 found
(the ontology's `roles` list fired for one action out of thirteen), it does not
tighten what analysts may do.

**Who a criterion applies to.** Two of the three key off `context.roles` being
non-empty, which is the platform's signal for "an authenticated person is
asking". The migration adapter, the CLI, the fixture loader and the projection
rebuilder are not people, hold no roles, and are not case members; gating them
on human authorization would mean inventing a service account for every
maintenance command. The API layer supplies roles on every route, so the
callers these criteria exist for always carry them.

The names are declared in `aegis.ontology.registries` because the loader
validates against them and cannot import this module. `test_actions_v2.py`
asserts the two agree in both directions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from sqlalchemy.orm import Session

from aegis.ontology import ActionSpec
from aegis.ontology.registries import SUBMISSION_CRITERIA
from aegis.store import CaseMember

if TYPE_CHECKING:  # pragma: no cover - typing only
    from aegis.actions.service import ActionContext


@dataclass(frozen=True, slots=True)
class CriterionResult:
    """Whether a criterion held, and — when it did not — why, in words a denial
    audit row can carry."""

    passed: bool
    detail: str = ""

    def __bool__(self) -> bool:
        return self.passed


PASSED = CriterionResult(True)


@dataclass(frozen=True, slots=True)
class CriterionInput:
    """Everything a criterion may look at.

    The session is the **action's own** session, so a criterion reads the same
    uncommitted state the write will land in. That is what lets
    `actor_is_case_member` consult the canonical `case_member` table rather
    than a projection of it.
    """

    action: str
    spec: ActionSpec
    context: "ActionContext"
    session: Session
    #: What the caller supplied, already checked against the declared
    #: parameters — so a criterion may read `parameters["case_id"]` without
    #: wondering whether the action has one.
    parameters: dict[str, Any] = field(default_factory=dict)
    #: Flags the caller passes for `dual_control_for` matching.
    dual_control_flags: frozenset[str] = frozenset()

    @property
    def human_caller(self) -> bool:
        """True when an authenticated person is asking (see the module docstring)."""
        return bool(self.context.roles)


Criterion = Callable[[CriterionInput], CriterionResult]


def actor_holds_action_role(request: CriterionInput) -> CriterionResult:
    """The actor holds one of the action's declared `roles`.

    The gap ADR-040 found: this check existed in `_require_action` but ran only
    when a caller passed an `ActionContext` carrying roles — which happened for
    `adjudicate_identity` and nothing else. The API layer now supplies roles on
    every route, so the declaration is load-bearing for all thirteen actions.
    """
    if not request.human_caller:
        return PASSED
    if set(request.spec.roles) & set(request.context.roles):
        return PASSED
    return CriterionResult(
        False,
        f"requires one of {sorted(request.spec.roles)}; actor holds "
        f"{sorted(request.context.roles)}",
    )


def actor_is_case_member(request: CriterionInput) -> CriterionResult:
    """A case-scoped write is made by someone working inside that case.

    Checked against the canonical `case_member` table, not OpenFGA: FGA is a
    projection of these rows (ADR-014), the row is the fact, and reading it
    costs no network call inside the write's transaction. The API's
    `fga_check_or_404` stays where it is — it answers a *read* question
    (does this resource exist for you) that must not become a 403 here.
    """
    case_id = request.parameters.get("case_id")
    if not request.human_caller or case_id is None:
        return PASSED
    if request.session.get(CaseMember, (case_id, request.context.actor)) is not None:
        return PASSED
    return CriterionResult(
        False,
        f"the write is scoped to case {case_id!r}, which the actor is not a "
        "member of",
    )


def second_approver_present(request: CriterionInput) -> CriterionResult:
    """Where `dual_control_for` fires, a distinct second actor signed off."""
    required = set(request.spec.dual_control_for or ()) & set(request.dual_control_flags)
    if not required:
        return PASSED
    if request.context.second_actor is None:
        return CriterionResult(
            False,
            f"{sorted(required)} requires a second approver; the decision was "
            "not written",
        )
    if request.context.second_actor == request.context.actor:
        return CriterionResult(False, "the second approver must be a different person")
    return PASSED


#: name -> implementation. Every key must appear in
#: `aegis.ontology.registries.SUBMISSION_CRITERIA` and vice versa; the
#: assertion below turns a mismatch into an import-time failure rather than a
#: criterion that silently never runs.
CRITERIA: dict[str, Criterion] = {
    "actor_holds_action_role": actor_holds_action_role,
    "actor_is_case_member": actor_is_case_member,
    "second_approver_present": second_approver_present,
}

assert set(CRITERIA) == set(SUBMISSION_CRITERIA), (
    "aegis.actions.criteria and aegis.ontology.registries disagree about which "
    f"criteria exist: {set(CRITERIA) ^ set(SUBMISSION_CRITERIA)}"
)


def evaluate(request: CriterionInput) -> tuple[str, str] | None:
    """Run the action's declared criteria; return (name, detail) on the first failure.

    Declaration order is evaluation order, so an action can put the most
    fundamental check first and the denial names that one rather than a
    consequence of it.
    """
    for name in request.spec.submission_criteria:
        result = CRITERIA[name](request)
        if not result:
            return name, result.detail
    return None
