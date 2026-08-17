"""Ontology change management — proposals, versions, compatibility (T35).

Spec 08 §7. The gate exists to stop one specific lie: a bump that calls itself
minor while removing vocabulary. Claims are immutable (ADR-013), so a claim
stamped with the old version becomes uninterpretable and there is no recovery —
the failure surfaces years later as a row nobody can explain.

Comparison is against a **committed artifact**, never git history (H-16), so
every test here builds two artifacts and diffs them directly.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from aegis.ontology import compose, registry
from aegis.ontology.generate import canonical_json, composed_artifact, content_hash
from aegis.ontology.release import COMPATIBILITY_ORDER, check, compare
from tests.support.paths import ONTOLOGY_PATH, REPO_ROOT

pytestmark = pytest.mark.requirement("Article-XI", "H-16", "T35")

PROPOSALS = REPO_ROOT / "ontology" / "proposals"
#: `README.md` documents the directory; `000-template.md` is the skeleton to
#: copy. Neither is a proposal, so neither is held to a proposal's shape.
NOT_PROPOSALS = frozenset({"README", "000-template"})


def _proposals() -> list[Path]:
    return sorted(p for p in PROPOSALS.glob("*.md") if p.stem not in NOT_PROPOSALS)


@pytest.fixture(scope="module")
def artifact() -> dict:
    composition = compose(ONTOLOGY_PATH)
    return composed_artifact(composition, registry(composition))


@pytest.fixture(scope="module")
def release() -> dict:
    return json.loads((REPO_ROOT / "ontology" / "release.json").read_text("utf-8"))


# ── the committed release passes its own gate ───────────────────────────────


def test_the_committed_release_is_green(artifact: dict, release: dict) -> None:
    assert check(REPO_ROOT, release=release, artifact=artifact) == []


def test_the_release_names_an_existing_proposal(release: dict) -> None:
    assert (PROPOSALS / f"{release['proposal']}.md").exists()
    assert release["compatibility"] in COMPATIBILITY_ORDER


def test_the_backfilled_proposals_exist() -> None:
    """One per bump since the workflow could record them (spec 08 §7.1)."""
    assert (PROPOSALS / "000-template.md").exists()
    assert [p.stem for p in _proposals()] == [
        "001-module-composition",
        "002-shared-properties-and-interfaces",
        "003-action-parameters-and-criteria",
        "004-controls-predicate",
    ]


def test_every_proposal_answers_a_competency_question() -> None:
    """A change that answers no new question is a rename (GOAL.md §7.9)."""
    for path in [*_proposals(), PROPOSALS / "000-template.md"]:
        text = path.read_text("utf-8")
        assert "## Competency questions" in text, path.name
        assert "## Compatibility" in text, path.name
        assert "## Migration" in text, path.name


def test_the_chain_reaches_the_previous_artifact(release: dict) -> None:
    previous = REPO_ROOT / "ontology" / "history" / f"composed-{release['previous_version']}.json"
    assert previous.exists()
    assert release["previous_content_hash"] == content_hash(
        json.loads(previous.read_text("utf-8"))
    )


# ── the compatibility diff ──────────────────────────────────────────────────


def _without(artifact: dict, section: str, name: str) -> dict:
    changed = copy.deepcopy(artifact)
    changed["ontology"][section].pop(name)
    return changed


def test_a_removed_predicate_is_breaking(artifact: dict) -> None:
    report = compare(artifact, _without(artifact, "predicates", "member_of"))
    assert report.computed == "major"
    assert "predicates.member_of: removed" in report.breaking


def test_a_removed_object_type_is_breaking(artifact: dict) -> None:
    report = compare(artifact, _without(artifact, "object_types", "vehicle"))
    assert "object_types.vehicle: removed" in report.breaking


def test_a_removed_action_interface_or_shared_property_is_breaking(artifact: dict) -> None:
    for section, name in (
        ("actions", "seal_record"),
        ("interfaces", "party"),
        ("shared_properties", "notes"),
    ):
        report = compare(artifact, _without(artifact, section, name))
        assert f"{section}.{name}: removed" in report.breaking


def test_a_new_predicate_is_additive(artifact: dict) -> None:
    changed = copy.deepcopy(artifact)
    changed["ontology"]["predicates"]["befriended"] = {
        "subject": ["person"],
        "object": ["person"],
    }
    report = compare(artifact, changed)
    assert report.computed == "minor"
    assert report.breaking == []


def test_no_change_is_a_patch(artifact: dict) -> None:
    assert compare(artifact, copy.deepcopy(artifact)).computed == "patch"


def test_a_retyped_property_is_breaking(artifact: dict) -> None:
    """The value in every recorded row would be read differently."""
    changed = copy.deepcopy(artifact)
    changed["ontology"]["object_types"]["person"]["properties"]["date_of_birth"]["type"] = "text"
    report = compare(artifact, changed)
    assert any("date_of_birth.type" in reason for reason in report.breaking)


def test_a_declassified_shared_property_is_breaking(artifact: dict) -> None:
    """Lowering a handling floor exposes rows recorded under the old one."""
    changed = copy.deepcopy(artifact)
    changed["ontology"]["shared_properties"]["registered_identifier"]["sensitivity"] = "open"
    report = compare(artifact, changed)
    assert any(
        "shared_properties.registered_identifier.sensitivity" in reason
        for reason in report.breaking
    )


def test_a_removed_property_is_breaking(artifact: dict) -> None:
    changed = copy.deepcopy(artifact)
    changed["ontology"]["object_types"]["person"]["properties"].pop("notes")
    assert "object_types.person.properties.notes: removed" in compare(artifact, changed).breaking


def test_reordering_handling_codes_is_breaking(artifact: dict) -> None:
    """The index *is* the clearance level, so the set being equal is not enough."""
    changed = copy.deepcopy(artifact)
    changed["ontology"]["handling_codes"] = ["restricted", "open", "sensitive"]
    report = compare(artifact, changed)
    assert any("handling_codes: reordered" in reason for reason in report.breaking)


def test_appending_a_handling_code_is_additive(artifact: dict) -> None:
    changed = copy.deepcopy(artifact)
    changed["ontology"]["handling_codes"] = [*artifact["ontology"]["handling_codes"], "secret"]
    report = compare(artifact, changed)
    assert report.breaking == []
    assert "handling_codes.secret: added" in report.additive


def test_a_removed_source_type_is_breaking(artifact: dict) -> None:
    changed = copy.deepcopy(artifact)
    changed["ontology"]["source_types"] = [
        value for value in artifact["ontology"]["source_types"] if value != "sensor"
    ]
    assert "source_types.sensor: removed" in compare(artifact, changed).breaking


# ── the gate ────────────────────────────────────────────────────────────────


def _staged(tmp_path: Path, previous: dict, release: dict) -> Path:
    """A repo skeleton holding one archived artifact and one proposal."""
    history = tmp_path / "ontology" / "history"
    history.mkdir(parents=True)
    (history / f"composed-{previous['version']}.json").write_text(
        canonical_json(previous), encoding="utf-8", newline="\n"
    )
    proposals = tmp_path / "ontology" / "proposals"
    proposals.mkdir(parents=True)
    if release.get("proposal"):
        (proposals / f"{release['proposal']}.md").write_text("# proposal", encoding="utf-8")
    return tmp_path


def _release(previous: dict, *, version: str, compatibility: str | None, proposal: str | None):
    return {
        "version": version,
        "compatibility": compatibility,
        "proposal": proposal,
        "previous_version": previous["version"],
        "previous_content_hash": content_hash(previous),
        "modules": {module["name"]: module["version"] for module in previous["modules"]},
    }


def test_a_minor_bump_removing_a_predicate_fails(tmp_path: Path, artifact: dict) -> None:
    """The headline case (charter AC): CI refuses the lie."""
    current = _without(artifact, "predicates", "member_of")
    release = _release(artifact, version="1.6.0", compatibility="minor", proposal="004-x")
    errors = check(_staged(tmp_path, artifact, release), release=release, artifact=current)
    assert any("declared 'minor' but the diff" in e and "major" in e for e in errors)
    assert any("breaking change without a major bump" in e for e in errors)


def test_a_bump_without_a_proposal_fails(tmp_path: Path, artifact: dict) -> None:
    release = _release(artifact, version="1.6.0", compatibility="minor", proposal=None)
    errors = check(_staged(tmp_path, artifact, release), release=release, artifact=artifact)
    assert any("release.proposal: every version bump names the proposal" in e for e in errors)


def test_a_proposal_that_does_not_exist_fails(tmp_path: Path, artifact: dict) -> None:
    release = _release(artifact, version="1.6.0", compatibility="minor", proposal="099-ghost")
    staged = _staged(tmp_path, artifact, {**release, "proposal": None})
    errors = check(staged, release=release, artifact=artifact)
    assert any("'099-ghost' does not name a file" in e for e in errors)


def test_a_missing_compatibility_class_fails(tmp_path: Path, artifact: dict) -> None:
    release = _release(artifact, version="1.6.0", compatibility=None, proposal="004-x")
    errors = check(_staged(tmp_path, artifact, release), release=release, artifact=artifact)
    assert any("release.compatibility: declare major, minor or patch" in e for e in errors)


def test_a_version_that_does_not_advance_fails(tmp_path: Path, artifact: dict) -> None:
    release = _release(artifact, version="1.4.0", compatibility="patch", proposal="004-x")
    release["previous_version"] = "1.5.0"
    staged = _staged(tmp_path, {**artifact, "version": "1.5.0"}, release)
    release["previous_content_hash"] = content_hash({**artifact, "version": "1.5.0"})
    errors = check(staged, release=release, artifact=artifact)
    assert any("does not advance on 1.5.0" in e for e in errors)


def test_a_module_version_going_backwards_fails(tmp_path: Path, artifact: dict) -> None:
    release = _release(artifact, version="1.6.0", compatibility="patch", proposal="004-x")
    release["modules"] = {**release["modules"], "platform": "1.0.0"}
    errors = check(_staged(tmp_path, artifact, release), release=release, artifact=artifact)
    assert any("release.modules.platform: 1.0.0 is older than" in e for e in errors)


def test_an_edited_archive_breaks_the_chain(tmp_path: Path, artifact: dict) -> None:
    """The hash is what makes comparing against a committed file trustworthy."""
    release = _release(artifact, version="1.6.0", compatibility="patch", proposal="004-x")
    tampered = copy.deepcopy(artifact)
    tampered["ontology"]["predicates"].pop("member_of")
    staged = _staged(tmp_path, tampered, release)
    release["previous_version"] = tampered["version"]
    errors = check(staged, release=release, artifact=artifact)
    assert any("has been edited since it was released" in e for e in errors)


def test_a_missing_archive_is_reported_not_ignored(tmp_path: Path, artifact: dict) -> None:
    """"No previous artifact" and "no differences" must not look the same."""
    release = _release(artifact, version="1.6.0", compatibility="patch", proposal="004-x")
    staged = _staged(tmp_path, {"version": "0.0.1", "modules": []}, release)
    errors = check(staged, release=release, artifact=artifact)
    assert any("is named but" in e and "is missing" in e for e in errors)


def test_a_major_bump_must_archive_the_prior_sources(tmp_path: Path, artifact: dict) -> None:
    current = _without(artifact, "predicates", "member_of")
    release = _release(artifact, version="2.0.0", compatibility="major", proposal="004-x")
    errors = check(_staged(tmp_path, artifact, release), release=release, artifact=current)
    assert any("must archive the prior module sources" in e for e in errors)
    # ...and the diff itself is not an error once the class is honest.
    assert not any("declared 'major' but" in e for e in errors)


def test_over_declaring_the_class_is_allowed(tmp_path: Path, artifact: dict) -> None:
    """A cautious author may call an additive change major; the reverse is the risk."""
    changed = copy.deepcopy(artifact)
    changed["ontology"]["predicates"]["befriended"] = {"subject": ["person"], "object": ["person"]}
    release = _release(artifact, version="2.0.0", compatibility="major", proposal="004-x")
    errors = check(_staged(tmp_path, artifact, release), release=release, artifact=changed)
    assert errors == []


def test_the_first_release_has_nothing_to_diff(tmp_path: Path, artifact: dict) -> None:
    release = {
        "version": "1.0.0",
        "compatibility": "minor",
        "proposal": "004-x",
        "previous_version": None,
        "previous_content_hash": None,
        "modules": {},
    }
    staged = _staged(tmp_path, {"version": "0.0.0", "modules": []}, release)
    assert check(staged, release=release, artifact=artifact) == []
