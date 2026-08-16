"""`aegis ontology generate` — the Phase 3 codegen targets (T33, ADR-038).

Spec 08 §8. Two properties matter more than the file contents: the output is
**deterministic** (so the drift gate means something) and it is **current**
(so the committed artifacts are not a stale copy of an older ontology).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from aegis.ontology import compose, load, registry
from aegis.ontology.generate import (
    DO_NOT_EDIT,
    canonical_json,
    composed_artifact,
    content_hash,
    plan,
    release_metadata,
    typescript_constants,
)
from tests.support.paths import ONTOLOGY_PATH, REPO_ROOT

pytestmark = pytest.mark.requirement("Article-XI", "ADR-038", "T33")


@pytest.fixture(scope="module")
def composition():
    return compose(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def ontology(composition):
    return registry(composition)


# ── the gate ────────────────────────────────────────────────────────────────


def test_the_committed_artifacts_are_current(composition, ontology) -> None:
    """The drift gate, as a test — so a stale artifact fails the fast suite too.

    CI runs `aegis ontology generate --check` as well; this exists because a
    developer who edits the ontology and runs the tests should learn about it
    then, not after pushing.
    """
    report = plan(
        composition, ontology, repo_root=REPO_ROOT, release=composition.release
    )
    stale = [str(f.path.relative_to(REPO_ROOT)) for f in report.drifted]
    assert stale == [], "run `aegis ontology generate` and commit the result"


def test_every_generated_file_says_so(composition, ontology) -> None:
    report = plan(composition, ontology, repo_root=REPO_ROOT)
    for generated in report.files:
        if generated.path.suffix == ".ts":
            assert DO_NOT_EDIT in generated.content
        else:
            # JSON has no comments; the header lives in the directory READMEs,
            # and the drift gate is what actually stops hand edits.
            assert generated.content.endswith("\n")


# ── determinism ─────────────────────────────────────────────────────────────


def test_generation_is_deterministic(composition, ontology) -> None:
    first = plan(composition, ontology, repo_root=REPO_ROOT)
    second = plan(composition, ontology, repo_root=REPO_ROOT)
    assert [f.content for f in first.files] == [f.content for f in second.files]


def test_canonical_json_sorts_keys_and_ends_with_a_newline() -> None:
    rendered = canonical_json({"b": 1, "a": {"d": 2, "c": 3}})
    assert rendered.index('"a"') < rendered.index('"b"')
    assert rendered.index('"c"') < rendered.index('"d"')
    assert rendered.endswith("\n")


def test_generated_files_use_lf_endings(composition, ontology) -> None:
    """A CRLF checkout must not make every artifact drift."""
    for generated in plan(composition, ontology, repo_root=REPO_ROOT).files:
        assert "\r\n" not in generated.content


# ── the composed artifact (spec 08 §7.2) ────────────────────────────────────


def test_the_artifact_keeps_the_declaration_not_the_resolution(
    composition, ontology
) -> None:
    """Interfaces unexpanded, `shared:` intact — the diff answers "did the
    vocabulary change", and resolution is derived."""
    artifact = composed_artifact(composition, ontology)
    person = artifact["ontology"]["object_types"]["person"]
    assert person["properties"]["nic"] == {"shared": "registered_identifier"}
    assert person["implements"] == ["party", "identifiable"]
    # ...while the resolved registry has the shared values filled in.
    assert ontology.object_type("person").properties["nic"].sensitivity == "restricted"


def test_the_artifact_records_modules_and_ownership(composition, ontology) -> None:
    artifact = composed_artifact(composition, ontology)
    assert [module["name"] for module in artifact["modules"]] == [
        "criminal_network",
        "platform",
    ]
    assert artifact["owners"]["person"] == "criminal_network"
    assert artifact["owners"]["party"] == "platform"
    assert artifact["version"] == ontology.version


def test_the_content_hash_moves_with_the_vocabulary(composition, ontology) -> None:
    artifact = composed_artifact(composition, ontology)
    unchanged = copy.deepcopy(artifact)
    assert content_hash(unchanged) == content_hash(artifact)

    changed = copy.deepcopy(artifact)
    changed["ontology"]["predicates"].pop("member_of")
    assert content_hash(changed) != content_hash(artifact)


# ── release metadata (spec 08 §7.2) ─────────────────────────────────────────


def test_release_metadata_records_the_authored_fields() -> None:
    artifact = {"version": "2.0.0", "modules": [{"name": "platform", "version": "1.1.0"}]}
    metadata = release_metadata(
        artifact,
        release={"proposal": "002-events", "compatibility": "major"},
        previous=None,
    )
    assert metadata["proposal"] == "002-events"
    assert metadata["compatibility"] == "major"
    assert metadata["modules"] == {"platform": "1.1.0"}


def test_release_metadata_is_null_when_nothing_was_declared() -> None:
    """T33 records the absence; T35's CI gate is what rejects it."""
    metadata = release_metadata({"version": "1.0.0", "modules": []}, release=None, previous=None)
    assert metadata["proposal"] is None
    assert metadata["compatibility"] is None


def test_a_bump_chains_to_the_previous_release() -> None:
    artifact = {"version": "1.5.0", "modules": []}
    previous = {"version": "1.4.0", "content_hash": "abc", "previous_version": "1.3.0"}
    metadata = release_metadata(artifact, release=None, previous=previous)
    assert metadata["previous_version"] == "1.4.0"
    assert metadata["previous_content_hash"] == "abc"


def test_regenerating_without_a_bump_preserves_the_chain() -> None:
    """Running the generator twice must not erase where this version came from."""
    artifact = {"version": "1.4.0", "modules": []}
    previous = {
        "version": "1.4.0",
        "content_hash": "current",
        "previous_version": "1.3.0",
        "previous_content_hash": "older",
    }
    metadata = release_metadata(artifact, release=None, previous=previous)
    assert metadata["previous_version"] == "1.3.0"
    assert metadata["previous_content_hash"] == "older"


def test_the_committed_release_matches_the_committed_artifact() -> None:
    release = json.loads((REPO_ROOT / "ontology" / "release.json").read_text("utf-8"))
    artifact = json.loads(
        (REPO_ROOT / "ontology" / "history" / f"composed-{release['version']}.json").read_text(
            "utf-8"
        )
    )
    assert release["content_hash"] == content_hash(artifact)
    assert release["modules"] == {
        module["name"]: module["version"] for module in artifact["modules"]
    }


# ── the workspace constants ─────────────────────────────────────────────────


def test_the_constants_carry_the_whole_registry(ontology) -> None:
    """The gap this closes: `/v1/ontology/vocabulary` serves no predicates."""
    rendered = typescript_constants(ontology)
    for predicate in ontology.predicates:
        assert f'"{predicate}":' in rendered
    for object_type in ontology.object_types:
        assert f'"{object_type}":' in rendered
    for interface in ontology.interfaces:
        assert f'"{interface}":' in rendered
    assert f'ONTOLOGY_VERSION = "{ontology.version}"' in rendered


def test_handling_codes_keep_their_order(ontology) -> None:
    """Clearance is an index into the list, so sorting it would be a bug."""
    rendered = typescript_constants(ontology)
    assert '["open", "restricted", "sensitive"]' in rendered


def test_a_predicate_reports_its_expansion_and_its_declaration(ontology) -> None:
    rendered = typescript_constants(ontology)
    assert (
        '"member_of": { subject: ["person"], object: ["organization"]' in rendered
    )
    assert '"has_nic": { subject: ["person"], object: "literal"' in rendered


def test_the_committed_constants_match_the_registry(ontology) -> None:
    committed = (REPO_ROOT / "ui" / "src" / "api" / "ontology.ts").read_text("utf-8")
    assert committed == typescript_constants(ontology)


# ── drift detection ─────────────────────────────────────────────────────────


def test_drift_is_detected_when_a_generated_file_is_edited(
    tmp_path: Path, composition, ontology
) -> None:
    report = plan(composition, ontology, repo_root=tmp_path)
    assert len(report.drifted) == len(report.files), "nothing exists in an empty tree"

    for generated in report.files:
        generated.write()
    assert plan(composition, ontology, repo_root=tmp_path, release=composition.release).drifted == []

    constants = tmp_path / "ui" / "src" / "api" / "ontology.ts"
    constants.write_text(constants.read_text("utf-8") + "\n// hand edit\n", encoding="utf-8")
    drifted = plan(composition, ontology, repo_root=tmp_path, release=composition.release).drifted
    assert [f.path.name for f in drifted] == ["ontology.ts"]


def test_a_vocabulary_change_drifts_the_artifacts(tmp_path: Path, composition, ontology) -> None:
    """The case the gate exists for: ontology edited, artifacts not regenerated."""
    for generated in plan(
        composition, ontology, repo_root=tmp_path, release=composition.release
    ).files:
        generated.write()

    document = copy.deepcopy(composition.document)
    document["predicates"]["befriended"] = {"subject": ["person"], "object": ["person"]}
    changed = registry(
        type(composition)(
            document=document,
            modules=composition.modules,
            owners={**composition.owners, "befriended": "criminal_network"},
            source=composition.source,
            release=composition.release,
        )
    )
    drifted = {
        f.path.name
        for f in plan(composition, changed, repo_root=tmp_path, release=composition.release).drifted
    }
    assert "ontology.ts" in drifted


# ── the second domain generates too ─────────────────────────────────────────


def test_the_fixture_domain_generates_without_core_changes(tmp_path: Path) -> None:
    fixture = REPO_ROOT / "tests" / "fixtures" / "ontology" / "border-cargo-composition.yaml"
    fixture_composition = compose(fixture)
    fixture_ontology = registry(fixture_composition)
    report = plan(fixture_composition, fixture_ontology, repo_root=tmp_path)
    for generated in report.files:
        generated.write()

    constants = (tmp_path / "ui" / "src" / "api" / "ontology.ts").read_text("utf-8")
    assert '"consignment":' in constants
    assert '"cleared_at":' in constants
    assert '"person":' not in constants


def test_the_manifest_release_block_is_optional(tmp_path: Path) -> None:
    """An ontology without a `release:` block still composes (T35 adds the gate)."""
    manifest = yaml.safe_load(ONTOLOGY_PATH.read_text("utf-8"))
    manifest.pop("release", None)
    for entry in manifest["composition"]:
        entry["path"] = str((ONTOLOGY_PATH.parent / entry["path"]).resolve())
    path = tmp_path / "aegis.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    assert load(path).version == manifest["version"]
    assert compose(path).release == {"proposal": None, "compatibility": None}
