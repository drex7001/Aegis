"""Grouping displays a page; it must never shrink one (T67, spec 11 §5.1).

Written after a bug in the first draft of `into_groups`, and shaped by it. That
draft capped the number of groups at twelve, and truncated **after** the page
was cut and after `next_cursor` was computed — so a page spanning more groups
than the cap dropped hits the cursor had already passed. Nobody would ever see
them: not on that page, and not on the next one, because the cursor had moved
beyond them.

The bug was **latent, not live**, and the distinction is worth stating rather
than overclaiming: the composition declares nine object types plus `claim` and
`document`, so eleven groups against a cap of twelve. Two more object types —
one ordinary domain-module addition — and it would have started dropping hits,
in a way no existing test could see, because every fixture seeds two or three
groups.

So the invariant is the test: **grouping is a partition.** Every hit in, every
hit out, exactly once.
"""

from __future__ import annotations

import pytest

from aegis.ontology import load
from aegis.search.results import SearchHit
from aegis.search.service import available_groups, group_label, into_groups
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement("spec-11-5", "T67")


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


def _hit(group: str, index: int, score: float) -> SearchHit:
    return SearchHit(
        kind="entity",
        id=f"{group}_{index}",
        group=group,
        label=f"{group} {index}",
        detail=None,
        parent_id=None,
        score=score,
        matched="label",
    )


def _page(ontology, per_group: int = 1) -> list[SearchHit]:
    """One hit in **every** declared group — the case no fixture reaches."""
    return [
        _hit(group, index, 1.0 - (position / 100))
        for position, group in enumerate(available_groups(ontology))
        for index in range(per_group)
    ]


def test_grouping_keeps_every_hit(ontology) -> None:
    page = _page(ontology)
    regrouped = [hit for group in into_groups(ontology, page) for hit in group.hits]
    assert sorted(hit.id for hit in regrouped) == sorted(hit.id for hit in page)


def test_grouping_is_a_partition(ontology) -> None:
    """No hit in two groups, no hit in none."""
    page = _page(ontology, per_group=3)
    groups = into_groups(ontology, page)
    seen = [hit.id for group in groups for hit in group.hits]
    assert len(seen) == len(set(seen)) == len(page)
    for group in groups:
        assert all(hit.group == group.group for hit in group.hits)


def test_the_group_count_is_close_enough_to_the_old_cap_to_matter(ontology) -> None:
    """How near the latent bug was, recorded as a number rather than a claim.

    Eleven groups against a cap of twelve. This is not a test of the fixture's
    width — it is the evidence that the removed cap was one domain-module
    addition away from silently dropping results.
    """
    assert 8 <= len(available_groups(ontology)) <= 12


def test_a_group_keeps_its_hits_in_rank_order(ontology) -> None:
    page = sorted(_page(ontology, per_group=3), key=lambda hit: -hit.score)
    for group in into_groups(ontology, page):
        scores = [hit.score for hit in group.hits]
        assert scores == sorted(scores, reverse=True)


def test_groups_are_ordered_by_their_best_hit(ontology) -> None:
    """The group holding the top result comes first, not the one sorting first.

    Alphabetical order would bury the best answer under whichever type name
    happens to start with an early letter.
    """
    page = [_hit("person", 0, 0.2), _hit("arrest", 0, 0.9)]
    assert [group.group for group in into_groups(ontology, page)] == ["arrest", "person"]


def test_an_empty_page_produces_no_groups(ontology) -> None:
    """Not one empty group each — an empty group is a count of zero (§4.2)."""
    assert into_groups(ontology, []) == []


def test_every_declared_group_has_a_label(ontology) -> None:
    for group in available_groups(ontology):
        label = group_label(ontology, group)
        assert label and label != group or group in {"claim", "document"}, (
            f"{group} falls back to its raw name; the ontology should supply a label"
        )


def test_the_group_list_is_the_ontology_plus_two_platform_kinds(ontology) -> None:
    """Article XIV: nothing enumerates domain types."""
    groups = set(available_groups(ontology))
    assert groups - {"claim", "document"} == set(ontology.object_types)
