"""A new predicate reaches API validation and the client with no domain code (T39).

The Phase 3 charter's **first** exit criterion, and the one that makes the rest
of the phase worth having: if adding a predicate still required a Python edit,
module composition would be filing rather than architecture.

Proposal 004 added `controls` to the criminal-network module. What this file
asserts is not that the predicate exists — that is one line of YAML — but that
**nothing else had to change**: no branch in `aegis/`, no type in `ui/src`, no
hand-written entry anywhere. The API half lives in
`tests/integration/test_ontology_change_flow.py`, where a database is available.
"""

from __future__ import annotations

import json
import re

import pytest

from aegis.ontology import load
from tests.support.paths import ONTOLOGY_PATH, REPO_ROOT

pytestmark = pytest.mark.requirement("Article-XI", "Article-XIV", "T39")

#: The change proposal 004 made, and the only name it introduced.
NEW_PREDICATE = "controls"
PROPOSAL = "004-controls-predicate"

#: Code names a predicate as a **quoted string** — `predicate == "controls"`,
#: `PREDICATES["controls"]`. A bare substring sweep would also catch the word in
#: prose and `aria-controls` in JSX, and reporting those as violations would
#: teach the next reader to ignore this test. The border-cargo sweep (T31) can
#: afford a plain substring because `consignment` and `port_of_entry` are not
#: English; `controls` is.
_QUOTED = re.compile(rf"""["']{NEW_PREDICATE}["']""")


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


# ── it arrived through the workflow ─────────────────────────────────────────


def test_the_change_came_with_a_proposal() -> None:
    """Not an assertion about paperwork: the release gate refuses without it."""
    path = REPO_ROOT / "ontology" / "proposals" / f"{PROPOSAL}.md"
    assert path.exists()
    release = json.loads((REPO_ROOT / "ontology" / "release.json").read_text("utf-8"))
    assert release["proposal"] == PROPOSAL
    assert release["compatibility"] == "minor"
    assert release["previous_version"] == "1.5.0"


def test_the_predicate_is_owned_by_the_domain_module(ontology) -> None:
    assert ontology.owner_module(NEW_PREDICATE) == "criminal_network"
    assert ontology.modules["criminal_network"].version == "1.2.0"


# ── it targets an interface, and the expansion is what ships ────────────────


def test_the_subject_is_declared_as_an_interface_and_expands(ontology) -> None:
    """`subject: [party]` — the first shipped predicate to target an interface.

    The expansion is what the store sees: a claim records concrete entity
    types, never an interface (spec 08 §4). Both forms survive so the client
    can say `party` while the actions layer checks `person`.
    """
    predicate = ontology.predicate(NEW_PREDICATE)
    assert predicate.subject_interfaces == ("party",)
    assert predicate.subject == ["person", "organization"]
    assert predicate.entity_object_types == ["organization"]
    assert not predicate.allows_literal


def test_widening_the_interface_would_widen_the_predicate(ontology) -> None:
    """The property that makes the interface worth targeting.

    A third `party` implementor would reach this predicate without the line
    being touched — which is the difference between an interface and a
    two-element list.
    """
    assert set(ontology.implementors("party")) == set(ontology.predicate(NEW_PREDICATE).subject)


# ── nothing else changed ────────────────────────────────────────────────────


def test_no_core_module_names_the_new_predicate() -> None:
    """Zero hand-written domain code — the criterion, as a sweep.

    Same shape as the border-cargo test (T31), applied to the real ontology:
    if a predicate needs a branch in `aegis/`, the ontology is not the single
    domain artifact Article XI says it is.
    """
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted((REPO_ROOT / "aegis").rglob("*.py"))
        if _QUOTED.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        f"{offenders} name {NEW_PREDICATE!r}. A new predicate must need no code."
    )


def test_no_workspace_source_names_the_new_predicate() -> None:
    """...and none in the UI either, outside the generated constants."""
    generated = {
        REPO_ROOT / "ui" / "src" / "api" / "ontology.ts",
        REPO_ROOT / "ui" / "src" / "api" / "schema.d.ts",
    }
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted((REPO_ROOT / "ui" / "src").rglob("*.ts*"))
        if path not in generated and _QUOTED.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


# ── it reaches the client ───────────────────────────────────────────────────


def test_the_generated_client_exposes_it(ontology) -> None:
    """The half `GET /v1/ontology/vocabulary` cannot do (ADR-039).

    The route serves handling codes, source types and assertion types — never a
    predicate — so before the generated constants a client had no typed way to
    learn this predicate exists.
    """
    constants = (REPO_ROOT / "ui" / "src" / "api" / "ontology.ts").read_text("utf-8")
    assert f'"{NEW_PREDICATE}": {{' in constants
    assert 'subjectInterfaces: ["party"]' in constants
    assert f'"{NEW_PREDICATE}": {{ subject: ["organization", "person"]' in constants


def test_the_composed_artifact_records_the_declaration(ontology) -> None:
    """The archived artifact keeps the *declaration*, so the diff stays readable."""
    artifact = json.loads(
        (REPO_ROOT / "ontology" / "history" / f"composed-{ontology.version}.json").read_text(
            "utf-8"
        )
    )
    declared = artifact["ontology"]["predicates"][NEW_PREDICATE]
    assert declared["subject"] == ["party"], "unexpanded, as declared"
    assert artifact["owners"][NEW_PREDICATE] == "criminal_network"
