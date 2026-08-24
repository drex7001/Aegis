"""The response-mode policy is one artifact, and the spec is the other half (T79).

H-25's finding was that spec 03 said "absent" and the Phase 7 plan said "marked"
and nothing chose between them. `aegis/authz/modes.POLICY` is the thing that
chooses. These tests keep it honest in the two ways a policy table goes wrong:
it stops matching the spec, or it stops matching the routes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from aegis.authz.modes import (
    GEOMETRY_EXISTENCE,
    POLICY,
    PROPERTY_SENSITIVITY,
    REDACTION_REASONS,
    SET_FILTER_VALUE,
    ModeError,
    mode_for,
    policy_for,
    withheld_predicates,
)
from aegis.ontology import load

pytestmark = pytest.mark.requirement("Article-VI", "H-25", "ADR-061", "ADR-067", "T79")

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "speckit" / "specs" / "03-security.md"

#: The one read route with no policy row: it returns the schema, which every
#: caller may read — and which is what makes a schema-derived marker safe.
UNGOVERNED = "/v1/ontology/vocabulary"


def _inventory_rows() -> dict[str, str]:
    """Surface id -> declared mode, parsed out of spec 03 §12.1."""
    text = SPEC.read_text(encoding="utf-8")
    table = text.split("### 12.1 API read surfaces", 1)[1].split("### 12.2", 1)[0]
    rows: dict[str, str] = {}
    for line in table.splitlines():
        match = re.match(r"^\|\s*`([a-z_]+)`\s*\|.*\|\s*`(omit|marked|counts)`\s*\|$", line)
        if match:
            rows[match.group(1)] = match.group(2)
    return rows


def test_the_spec_table_parses_at_all() -> None:
    """A parser that silently finds nothing makes every test below vacuous."""
    rows = _inventory_rows()
    assert len(rows) >= 20, f"parsed only {len(rows)} inventory rows: {sorted(rows)}"


def test_policy_and_inventory_agree_in_both_directions() -> None:
    rows = _inventory_rows()
    assert set(POLICY) == set(rows), {
        "policy but not inventory": sorted(set(POLICY) - set(rows)),
        "inventory but not policy": sorted(set(rows) - set(POLICY)),
    }
    for surface, mode in rows.items():
        assert mode_for(surface) == mode, surface


def test_an_unregistered_surface_raises_rather_than_defaulting() -> None:
    """Defaulting to `omit` is the safe answer and the wrong mechanism.

    A new read surface has to be *registered*; a default is how it stops being.
    """
    with pytest.raises(ModeError):
        mode_for("a_surface_nobody_declared")


@pytest.mark.parametrize("surface", sorted(POLICY))
def test_only_a_marking_surface_declares_markers(surface: str) -> None:
    policy = policy_for(surface)
    if policy.mode == "omit":
        assert not policy.marks, f"{surface} omits but declares {sorted(policy.marks)}"
    else:
        assert policy.marks, f"{surface} is {policy.mode} but declares no marker kind"


@pytest.mark.parametrize("surface", sorted(POLICY))
def test_every_policy_row_says_why(surface: str) -> None:
    """The sentence is the point. It is read at the next argument about the row."""
    assert len(policy_for(surface).why.split()) >= 8, surface


def test_geometry_existence_is_the_only_row_derived_marker() -> None:
    """ADR-067's exception has exactly one member, and it is named.

    An exception with one member is a smell; an undocumented one is a defect,
    and this was one until T79. If a second surface ever claims it, that is a
    decision somebody has to write down.
    """
    holders = sorted(
        surface for surface, policy in POLICY.items() if GEOMETRY_EXISTENCE in policy.marks
    )
    assert holders == ["geo"]


def test_counts_never_reaches_an_ordinary_read() -> None:
    """`counts` is disclosure only — GOAL.md §30's "3 hidden results" rule."""
    counting = sorted(surface for surface in POLICY if mode_for(surface) == "counts")
    assert counting == ["disclosure_package", "disclosure_preview"]


def test_a_pending_row_says_which_task_will_route_it() -> None:
    """"Declared but unrouted" is a stated fact, not a gap found at the review."""
    for surface, policy in POLICY.items():
        if policy.pending_task is not None:
            assert re.match(r"^T\d+", policy.pending_task), surface


# ── the marker itself (ADR-067) ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def ontology():
    return load(ROOT / "ontology" / "aegis.yaml")


def test_a_marker_set_comes_from_the_ontology_alone(ontology) -> None:
    """`person` has a restricted identifier; a clearance-0 reader is told so."""
    low = withheld_predicates(ontology, "person", clearance=0)
    assert low, "no predicate is withheld from a clearance-0 reader of a person"
    for name in low:
        assert name in ontology.predicates
        assert "person" in ontology.expand_types(ontology.predicates[name].subject)


def test_clearance_is_the_only_thing_that_shrinks_the_marker_set(ontology) -> None:
    top = len(ontology.handling_codes) - 1
    levels = [
        set(withheld_predicates(ontology, "person", clearance=level))
        for level in range(top + 1)
    ]
    for lower, higher in zip(levels[:-1], levels[1:], strict=True):
        assert higher <= lower, "raising clearance must never add a marker"
    assert not levels[top], "the top clearance is told nothing is withheld"


def test_a_type_is_never_told_about_another_type_s_predicates(ontology) -> None:
    """The marker set is per object type, so it cannot advertise the whole schema."""
    for object_type in ontology.object_types:
        for name in withheld_predicates(ontology, object_type, clearance=0):
            subjects = ontology.expand_types(ontology.predicates[name].subject)
            assert object_type in subjects, (object_type, name)


def test_the_marker_vocabulary_is_closed() -> None:
    """Four kinds, and a fifth is a spec change rather than a constant.

    `object_set_definition` marks a filter *value* rather than a predicate, so
    "every marked surface declares PROPERTY_SENSITIVITY" would be false — which
    is why the invariant worth asserting is that the vocabulary does not grow
    quietly, not that every surface uses the same entry from it.
    """
    known = {
        PROPERTY_SENSITIVITY,
        GEOMETRY_EXISTENCE,
        SET_FILTER_VALUE,
        REDACTION_REASONS,
    }
    used = {kind for policy in POLICY.values() for kind in policy.marks}
    assert used <= known, sorted(used - known)


def test_every_surface_that_renders_object_properties_marks_them() -> None:
    """The surfaces where a missing predicate group would read as "none recorded"."""
    for surface in ("entity_object_view", "geo", "audit"):
        assert PROPERTY_SENSITIVITY in policy_for(surface).marks, surface
