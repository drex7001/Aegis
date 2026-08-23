"""Sets compose the same authorization rule search does (T70).

Written because they did not. `aegis/sets/compile.py` shipped at T69 selecting
entities by type with no claim join, so an object set of `type: person`
returned every person in the database — including people the caller had no
readable claim about. `aegis/search/entities.py` had solved this at T23c; the
new module simply had not inherited the answer.

The rule it broke is one this system states everywhere: **an entity carries no
handling code of its own; claims do.** An entity exists, for a given caller,
exactly when some claim they may read mentions it.

So the fix was not a patch. `visible_entity_ids` moved to `aegis/authz/filters`
and both packages compose it, and this file asserts that structurally — because
the next module to select entities will be written by someone who has not read
this paragraph.

Sibling of `test_search_invariants.py`, which makes the same argument for the
search backends.
"""

from __future__ import annotations

import ast

import pytest

from tests.support.paths import REPO_ROOT

pytestmark = pytest.mark.requirement("Article-VI", "B-17", "M-16", "T70")

SETS_PACKAGE = REPO_ROOT / "aegis" / "sets"


def _called_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def _source(name: str) -> str:
    return (SETS_PACKAGE / name).read_text(encoding="utf-8")


# ── the rule that was missed ────────────────────────────────────────────────


def test_the_compiler_scopes_every_set_to_readable_entities() -> None:
    """The T69 hole, closed as a property rather than as a fixed test case."""
    called = _called_names(_source("compile.py"))
    assert "visible_entity_ids" in called, (
        "aegis/sets/compile.py selects entities without composing "
        "visible_entity_ids() — a bare `type` node then returns entities the "
        "caller has no readable claim about (Article VI)"
    )
    assert "claim_filters" in called


def test_only_the_compiler_builds_queries_in_the_sets_package() -> None:
    """One place constructs SQL, so one place has to get the rule right.

    `evaluation.py` selects from `Entity` too, but only over the compiler's own
    subquery — it never builds a predicate of its own. Anything else growing a
    `select()` is a second candidate-generating path, and the point of this
    test is that there should not be one.
    """
    builders = {
        path.name
        for path in SETS_PACKAGE.glob("*.py")
        if "select(" in path.read_text(encoding="utf-8")
    }
    assert builders <= {"compile.py", "evaluation.py", "service.py"}, (
        f"{sorted(builders - {'compile.py', 'evaluation.py', 'service.py'})} "
        "builds queries; candidate generation belongs in compile.py, where the "
        "authorization rule is enforced"
    )


def test_the_shared_helper_is_where_both_packages_can_reach_it() -> None:
    """Non-vacuity, and a guard against it drifting back into one package."""
    from aegis.authz.filters import visible_entity_ids
    from aegis.search.entities import _visible_entity_ids

    assert _visible_entity_ids is visible_entity_ids


# ── limits are the spec's numbers ───────────────────────────────────────────


def test_the_spec_quotes_the_limits_the_code_enforces() -> None:
    """Spec 12 §2.2's table and `aegis/sets/limits.py` are the same numbers."""
    from aegis.sets import limits

    spec = (REPO_ROOT / "speckit" / "specs" / "12-object-sets-analytics.md").read_text(
        encoding="utf-8"
    )
    section = spec[spec.index("### 2.2 Complexity limits") : spec.index("### 2.3")]
    for value in (
        limits.MAX_DEPTH,
        limits.MAX_NODES,
        limits.MAX_SET_REFERENCES,
        limits.MAX_COMPOSITION_DEPTH,
    ):
        assert str(value) in section, f"spec 12 §2.2 does not state {value}"
    assert "50 000" in section, "the cardinality cap is not stated"
    assert str(limits.STATEMENT_TIMEOUT_MS) in section.replace(" ", "")


# ── the FGA model carries the type ──────────────────────────────────────────


def test_the_object_set_type_exists_in_both_model_forms() -> None:
    """`model.fga` is the readable source; `model.json` is what bootstrap pushes.

    They are kept in sync by hand (the header of `model.fga` says so), which
    makes drift a matter of time rather than of care.
    """
    import json

    dsl = (REPO_ROOT / "infra" / "fga" / "model.fga").read_text(encoding="utf-8")
    model = json.loads(
        (REPO_ROOT / "infra" / "fga" / "model.json").read_text(encoding="utf-8")
    )

    assert "type object_set" in dsl
    definition = next(
        td for td in model["type_definitions"] if td["type"] == "object_set"
    )
    assert set(definition["relations"]) == {"case", "editor", "viewer", "evaluator"}


def test_evaluating_is_a_weaker_grant_than_reading_the_definition() -> None:
    """Spec 12 §5.2: running the query and reading the question are different.

    A set filtering on `has_nic = '…'` discloses that identifier to everyone
    who can read the definition, whatever the evaluation returns — so
    `evaluator` has to be grantable without `viewer`, and `viewer` has to imply
    `evaluator`. A model where the two were one relation would make the weaker
    grant unexpressible.
    """
    import json

    model = json.loads(
        (REPO_ROOT / "infra" / "fga" / "model.json").read_text(encoding="utf-8")
    )
    definition = next(
        td for td in model["type_definitions"] if td["type"] == "object_set"
    )
    evaluator = definition["relations"]["evaluator"]["union"]["child"]
    assert {"computedUserset": {"relation": "viewer"}} in evaluator
    assert {"this": {}} in evaluator

    viewer = definition["relations"]["viewer"]["union"]["child"]
    assert {"computedUserset": {"relation": "evaluator"}} not in viewer, (
        "viewer must not derive from evaluator, or the weaker grant would "
        "silently confer the stronger one"
    )
