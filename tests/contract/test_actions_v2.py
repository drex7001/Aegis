"""Actions v2 declarations — parameters, criteria, side effects (T34).

Spec 08 §6 and §9 rules 15–17; ADR-040. The validator half lives here; the
enforcement half (denials, audited, in a transaction) is
`tests/integration/test_actions_v2.py`, which needs a database.

The rule this file exists to protect: **a criterion must be enforceable before
it can be declared**. An ontology that could name a check nobody implemented
would be a governance rule that silently does nothing, which is worse than no
rule at all.
"""

from __future__ import annotations

import copy

import pytest

from aegis.actions.criteria import CRITERIA
from aegis.ontology import OntologyValidationError, compose, load, load_dict
from aegis.ontology.registries import (
    PAYLOAD_SCHEMAS,
    SIDE_EFFECTS,
    SUBMISSION_CRITERIA,
)
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement("Article-X", "ADR-040", "T34")


@pytest.fixture(scope="module")
def composed() -> dict:
    return compose(ONTOLOGY_PATH).document


@pytest.fixture()
def data(composed: dict) -> dict:
    return copy.deepcopy(composed)


def errors_of(data: dict) -> list[str]:
    with pytest.raises(OntologyValidationError) as excinfo:
        load_dict(data)
    return excinfo.value.errors


# ── the registries agree with the code ──────────────────────────────────────


def test_every_declared_criterion_is_implemented_and_vice_versa() -> None:
    """The two directions matter differently and both are checked.

    A declared-but-unimplemented criterion is a rule that does nothing. An
    implemented-but-unregistered one is dead code the ontology can never reach.
    """
    assert set(CRITERIA) == set(SUBMISSION_CRITERIA)


def test_the_committed_ontology_only_names_registered_things() -> None:
    ont = load(ONTOLOGY_PATH)
    for name, action in ont.actions.items():
        assert set(action.submission_criteria) <= SUBMISSION_CRITERIA, name
        assert {effect.hook for effect in action.side_effects} <= SIDE_EFFECTS, name
        for parameter in action.parameters.values():
            if parameter.type == "json":
                assert parameter.payload_schema in PAYLOAD_SCHEMAS


def test_every_action_declares_parameters_and_at_least_one_criterion() -> None:
    """T34 migrated all thirteen; T43 added nine. None may arrive undeclared.

    The count is a tripwire rather than the invariant — the loop below is the
    rule. It is here so a new action cannot be added without a reviewer seeing
    the number move, which is what caught nothing and is meant to keep catching
    nothing.
    """
    ont = load(ONTOLOGY_PATH)
    assert len(ont.actions) == 22
    for name, action in ont.actions.items():
        assert action.parameters, f"{name} declares no parameters"
        assert "actor_holds_action_role" in action.submission_criteria, name


def test_the_claim_envelope_lives_in_the_platform_module() -> None:
    """A domain module must not be able to widen what a claim may carry."""
    ont = load(ONTOLOGY_PATH)
    assert ont.owner_module("record_claim") == "platform"
    assert len(ont.action("record_claim").parameters) == 27


# ── rule 15: parameter types and modifiers ──────────────────────────────────


def test_an_unknown_parameter_type_fails(data: dict) -> None:
    data["actions"]["open_case"]["parameters"]["title"] = {"type": "freeform"}
    errors = errors_of(data)
    assert any("actions.open_case.parameters.title.type" in e for e in errors)


def test_a_ref_without_a_target_fails(data: dict) -> None:
    data["actions"]["open_case"]["parameters"]["owner"] = {"type": "ref"}
    errors = errors_of(data)
    assert any(
        "actions.open_case.parameters.owner.to: required for a 'ref' parameter" in e
        for e in errors
    )


def test_an_unknown_ref_target_fails(data: dict) -> None:
    data["actions"]["open_case"]["parameters"]["owner"] = {"type": "ref", "to": "planet"}
    errors = errors_of(data)
    assert any(
        "actions.open_case.parameters.owner.to: unknown reference target 'planet'" in e
        for e in errors
    )


def test_a_modifier_on_the_wrong_type_fails(data: dict) -> None:
    """`{type: text, values: [...]}` must not look like it constrains anything."""
    data["actions"]["open_case"]["parameters"]["title"] = {
        "type": "text",
        "values": ["a", "b"],
    }
    errors = errors_of(data)
    assert any(
        "actions.open_case.parameters.title.values: only valid on a 'enum' "
        "parameter, not 'text'" in e
        for e in errors
    )


def test_a_grade_needs_a_declared_dimension(data: dict) -> None:
    data["actions"]["record_claim"]["parameters"]["credibility_normalized"] = {
        "type": "grade",
        "dimension": "vibes",
    }
    errors = errors_of(data)
    assert any(
        "credibility_normalized.dimension: unknown grading dimension 'vibes'" in e
        for e in errors
    )


def test_an_empty_enum_fails(data: dict) -> None:
    data["actions"]["link_claims"]["parameters"]["relation"] = {
        "type": "enum",
        "values": [],
    }
    errors = errors_of(data)
    assert any("relation.values" in e for e in errors)


def test_a_json_parameter_needs_a_registered_schema(data: dict) -> None:
    """Otherwise `json` is a hole straight through the closed kind list."""
    data["actions"]["submit_suggestion"]["parameters"]["payload"] = {
        "type": "json",
        "payload_schema": "anything_goes",
        "required": True,
    }
    errors = errors_of(data)
    assert any(
        "payload.payload_schema: unregistered schema 'anything_goes'" in e
        for e in errors
    )


def test_a_json_parameter_without_a_schema_fails(data: dict) -> None:
    data["actions"]["submit_suggestion"]["parameters"]["payload"] = {"type": "json"}
    errors = errors_of(data)
    assert any(
        "payload.payload_schema: required for a 'json' parameter" in e for e in errors
    )


def test_a_required_parameter_may_not_carry_a_default(data: dict) -> None:
    data["actions"]["open_case"]["parameters"]["title"] = {
        "type": "text",
        "required": True,
        "default": "Untitled",
    }
    errors = errors_of(data)
    assert any(
        "title.default: a required parameter has no default" in e for e in errors
    )


def test_a_non_snake_case_parameter_fails(data: dict) -> None:
    data["actions"]["open_case"]["parameters"]["caseTitle"] = {"type": "text"}
    errors = errors_of(data)
    assert any("actions.open_case.parameters.caseTitle: name must be snake_case" in e for e in errors)


# ── rule 16: submission criteria ────────────────────────────────────────────


def test_an_unimplemented_criterion_fails(data: dict) -> None:
    """The charter's rule, as an error message a reader can act on."""
    data["actions"]["open_case"]["submission_criteria"] = ["actor_is_well_rested"]
    errors = errors_of(data)
    assert any(
        "actions.open_case.submission_criteria: 'actor_is_well_rested' is not "
        "implemented" in e
        for e in errors
    )


def test_a_p7_criterion_is_not_declarable_yet(data: dict) -> None:
    """`target_not_sealed` arrives with the phase that can enforce it (§6.3)."""
    data["actions"]["record_claim"]["submission_criteria"] = ["target_not_sealed"]
    errors = errors_of(data)
    assert any("'target_not_sealed' is not implemented" in e for e in errors)


def test_a_duplicate_criterion_fails(data: dict) -> None:
    data["actions"]["open_case"]["submission_criteria"] = [
        "actor_holds_action_role",
        "actor_holds_action_role",
    ]
    errors = errors_of(data)
    assert any(
        "actions.open_case.submission_criteria: duplicate criterion" in e for e in errors
    )


# ── rule 17: side effects parse, nothing runs them ──────────────────────────


def test_side_effects_parse_into_hook_and_target() -> None:
    ont = load(ONTOLOGY_PATH)
    effects = ont.action("record_claim").side_effects
    assert [(e.hook, e.target) for e in effects] == [
        ("refresh_projection", "edge_projection")
    ]


def test_an_unknown_side_effect_hook_fails(data: dict) -> None:
    data["actions"]["open_case"]["side_effects"] = [{"page_the_minister": "immediately"}]
    errors = errors_of(data)
    assert any(
        "actions.open_case.side_effects.page_the_minister: unknown hook" in e
        for e in errors
    )


def test_no_side_effect_engine_exists() -> None:
    """Spec 08 §6.5 — declarations are stored, execution waits for a consumer.

    Asserted as an absence because that is the promise: nothing in the actions
    package dispatches a declared hook, so a `notify:` in the ontology cannot
    quietly start sending anything.
    """
    from pathlib import Path

    from tests.support.paths import REPO_ROOT

    actions = Path(REPO_ROOT / "aegis" / "actions")
    for path in actions.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "side_effects" not in source or "_generated" in path.as_posix(), (
            f"{path.name} reads side_effects — P3 declares them and runs none "
            "(spec 08 §6.5)"
        )


# ── the generated request models ────────────────────────────────────────────


def test_the_generated_model_forbids_an_undeclared_parameter() -> None:
    from pydantic import ValidationError

    from aegis.actions._generated.requests import REQUEST_MODELS

    model = REQUEST_MODELS["open_case"]
    assert model(title="T", purpose="P").handling_code == "open"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        model(title="T", purpose="P", budget=10)


def test_every_action_has_a_generated_model() -> None:
    from aegis.actions._generated.requests import REQUEST_MODELS

    assert set(REQUEST_MODELS) == set(load(ONTOLOGY_PATH).actions)


def test_a_declared_default_is_not_optional() -> None:
    """A parameter with a default is never absent, so it is never None."""
    from aegis.actions._generated.requests import REQUEST_MODELS

    request = REQUEST_MODELS["record_claim"](predicate="known_as", record_id="rec_1")
    assert request.assertion_type == "reported"
    assert request.credibility_normalized == "cannot_judge"
    assert request.handling_code == "open"
    assert request.subject_id is None
