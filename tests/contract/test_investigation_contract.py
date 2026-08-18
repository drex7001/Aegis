"""The investigation model's declarations line up with its code (T43, spec 09).

Three seams that are easy to leave half-connected, each of which would fail
silently rather than loudly:

* the fourth **submission criterion** is registered in both places, so it cannot
  be declared by an ontology that nothing enforces;
* the **FGA model** grows a type per new resource, derived from its case — a
  missing one means `fga_check_or_404` asks about a type OpenFGA has never heard
  of, and the answer to that is "no", which looks like working authorization
  right up until it is not;
* the `.fga` source and the `.json` the bootstrap actually pushes **agree**.
  They are kept in step by hand until the openfga CLI is adopted, which is
  exactly the kind of arrangement that drifts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from aegis.actions.criteria import CRITERIA
from aegis.ontology import load
from aegis.ontology.loader import REF_TARGETS
from aegis.ontology.registries import SUBMISSION_CRITERIA
from tests.support.paths import ONTOLOGY_PATH, REPO_ROOT

pytestmark = pytest.mark.requirement("Article-VI", "ADR-040", "ADR-044", "H-17", "T43")

FGA_DSL = REPO_ROOT / "infra" / "fga" / "model.fga"
FGA_JSON = REPO_ROOT / "infra" / "fga" / "model.json"

#: Resources whose authorization derives entirely from their case (spec 09 §5).
CASE_DERIVED_TYPES = ("evidence_item", "hypothesis", "investigation_task")

#: What T43 declared. Named here so the ontology cannot lose one quietly.
INVESTIGATION_ACTIONS = (
    "close_case",
    "link_case_reference",
    "unlink_case_reference",
    "open_hypothesis",
    "revise_hypothesis",
    "link_hypothesis_claim",
    "unlink_hypothesis_claim",
    "open_task",
    "update_task",
)


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def fga_model() -> dict:
    return json.loads(FGA_JSON.read_text(encoding="utf-8"))


# ── the actions exist and are enforceable ───────────────────────────────────


def test_every_investigation_action_is_declared(ontology) -> None:
    for name in INVESTIGATION_ACTIONS:
        assert name in ontology.actions, name
        assert ontology.owner_module(name) == "platform", name


def test_the_investigation_actions_are_platform_not_domain(ontology) -> None:
    """A domain module that could declare these could invent a write path.

    They are also genuinely domain-neutral: a `border-cargo` deployment gets
    the same cases, hypotheses and tasks (Article XIV).
    """
    for name in INVESTIGATION_ACTIONS:
        assert ontology.owner_module(name) != "criminal_network", name
    assert {"hypothesis", "investigation_task"} <= REF_TARGETS


def test_the_fourth_criterion_is_registered_in_both_places() -> None:
    """A criterion declared but not implemented is a rule that does nothing."""
    assert "required_text_is_substantive" in SUBMISSION_CRITERIA
    assert "required_text_is_substantive" in CRITERIA
    assert set(CRITERIA) == set(SUBMISSION_CRITERIA)


def test_the_hypothesis_actions_demand_a_substantive_note(ontology) -> None:
    """GOAL.md §18's rule, at the point it is enforced.

    Both the parameter's `required: true` and the criterion, because they close
    different holes: absent and blank.
    """
    for name in ("open_hypothesis", "revise_hypothesis"):
        action = ontology.action(name)
        assert "required_text_is_substantive" in action.submission_criteria, name
    opened = ontology.action("open_hypothesis")
    assert opened.parameters["missing_info"].required
    assert opened.parameters["statement"].required


def test_case_scoped_writes_check_membership(ontology) -> None:
    """Anything that names a case must prove the actor works inside it."""
    for name in ("link_case_reference", "unlink_case_reference", "open_hypothesis", "open_task"):
        action = ontology.action(name)
        assert "actor_is_case_member" in action.submission_criteria, name
        assert "case_id" in action.parameters, name


def test_no_investigation_action_declares_a_side_effect(ontology) -> None:
    """Hypotheses and tasks are operational state, never knowledge.

    A `refresh_projection` here would be the first step towards a suspicion
    becoming an edge (Article IX, spec 09 §9).
    """
    for name in INVESTIGATION_ACTIONS:
        assert ontology.action(name).side_effects == [], name


# ── the authorization model ─────────────────────────────────────────────────


def test_every_case_derived_type_exists_in_the_fga_model(fga_model: dict) -> None:
    declared = {entry["type"] for entry in fga_model["type_definitions"]}
    assert set(CASE_DERIVED_TYPES) <= declared, sorted(set(CASE_DERIVED_TYPES) - declared)


def test_hypotheses_and_tasks_derive_their_permissions_from_the_case(
    fga_model: dict,
) -> None:
    """No relation of their own: the case is the resource (spec 09 §5)."""
    for type_name in ("hypothesis", "investigation_task"):
        entry = next(e for e in fga_model["type_definitions"] if e["type"] == type_name)
        relations = entry["relations"]
        assert set(relations) == {"case", "can_view", "can_edit"}, type_name
        for permission in ("can_view", "can_edit"):
            derivation = relations[permission]["tupleToUserset"]
            assert derivation["tupleset"]["relation"] == "case", type_name
            assert derivation["computedUserset"]["relation"] == permission, type_name
        # No direct user grant: a hypothesis cannot be shared past its case.
        assert relations["can_view"].get("this") is None, type_name


def test_the_dsl_and_the_pushed_model_agree(fga_model: dict) -> None:
    """`model.fga` is the readable source; `model.json` is what bootstrap pushes.

    They are synchronized by hand until the openfga CLI is adopted (the header
    of `model.fga` says so), which makes drift a matter of time rather than of
    carelessness.
    """
    dsl = FGA_DSL.read_text(encoding="utf-8")
    dsl_types = set(re.findall(r"^type (\w+)", dsl, flags=re.MULTILINE))
    json_types = {entry["type"] for entry in fga_model["type_definitions"]}
    assert dsl_types == json_types


def test_the_realm_roles_needed_by_the_new_actions_exist(ontology) -> None:
    """A role the realm never mints is an action nobody can call."""
    realm = json.loads(
        (REPO_ROOT / "infra" / "keycloak" / "aegis-realm.json").read_text(encoding="utf-8")
    )
    minted = {role["name"] for role in realm["roles"]["realm"]}
    for name in INVESTIGATION_ACTIONS:
        for role in ontology.action(name).roles:
            assert role in minted, f"{name} requires {role!r}, which the realm never mints"


# ── the schema matches what the actions write ───────────────────────────────


def test_the_migration_creates_every_investigation_table() -> None:
    migration = (
        REPO_ROOT / "migrations" / "versions" / "0010_investigation_model.py"
    ).read_text(encoding="utf-8")
    for table in (
        "case_reference",
        "hypothesis",
        "hypothesis_revision",
        "hypothesis_claim",
        "investigation_task",
    ):
        assert f'"{table}"' in migration, table
    # And gives every one of them back.
    for table in ("case_reference", "hypothesis", "investigation_task"):
        assert f'op.drop_table("{table}")' in migration, table


def test_the_missing_info_rule_is_enforced_in_the_database_too() -> None:
    """Two layers, because a rule held in one place is a rule with a bypass."""
    migration = (
        REPO_ROOT / "migrations" / "versions" / "0010_investigation_model.py"
    ).read_text(encoding="utf-8")
    assert "length(btrim(missing_info)) > 0" in migration


def test_a_hypothesis_carries_no_evidence_grading() -> None:
    """Structural Article IX: a suspicion has no shape a claim would recognise.

    Checked against the model rather than the migration, because it is the
    mapped class an action would have to reach through to record one.
    """
    from aegis.store import Hypothesis, HypothesisRevision

    forbidden = {
        "record_id",
        "credibility_normalized",
        "verification_status",
        "analytic_confidence",
        "predicate",
        "subject_id",
    }
    for model in (Hypothesis, HypothesisRevision):
        assert not forbidden & set(model.__table__.columns.keys()), model.__name__
