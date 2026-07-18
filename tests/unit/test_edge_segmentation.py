"""Interval segmentation in isolation (T21; spec 02 §7, ADR-030).

The database tests prove the projection segments correctly; these prove *why*,
against the cases that are easy to get subtly wrong — unbounded ends, exact
adjacency, full containment, and identical intervals.  A segmenter that is
merely "close" fabricates time, which is the whole thing ADR-030 forbids.
"""

from __future__ import annotations

from datetime import date

import pytest

from aegis.projections.edges import _Interval, _intervals, _segment, _to_bound

pytestmark = pytest.mark.requirement("ADR-030", "T21")

_NEG_INF = date.min
_POS_INF = date.max


class _FakeClaim:
    def __init__(self, claim_id: str, valid_from: date | None, valid_to: date | None):
        self.claim_id = claim_id
        self.valid_from = valid_from
        self.valid_to = valid_to


def _bounds(segments):
    """Segments as inclusive (from, to, claims), the way they are stored."""
    return [
        (_to_bound(low, upper=False), _to_bound(high, upper=True), claims)
        for low, high, claims in segments
    ]


def test_a_single_unbounded_claim_is_one_unbounded_segment() -> None:
    segments = _segment(_intervals([_FakeClaim("c1", None, None)]))
    assert _bounds(segments) == [(None, None, ("c1",))]


def test_disjoint_intervals_leave_the_gap_uncovered() -> None:
    segments = _segment(
        _intervals(
            [
                _FakeClaim("c1", date(2019, 1, 1), date(2019, 12, 31)),
                _FakeClaim("c2", date(2023, 1, 1), date(2023, 12, 31)),
            ]
        )
    )
    assert _bounds(segments) == [
        (date(2019, 1, 1), date(2019, 12, 31), ("c1",)),
        (date(2023, 1, 1), date(2023, 12, 31), ("c2",)),
    ]


def test_adjacent_intervals_touch_without_a_phantom_day() -> None:
    """Half-open internals are what make this work; closed ones lose a day."""
    segments = _segment(
        _intervals(
            [
                _FakeClaim("c1", date(2019, 1, 1), date(2019, 12, 31)),
                _FakeClaim("c2", date(2020, 1, 1), date(2020, 12, 31)),
            ]
        )
    )
    assert _bounds(segments) == [
        (date(2019, 1, 1), date(2019, 12, 31), ("c1",)),
        (date(2020, 1, 1), date(2020, 12, 31), ("c2",)),
    ]


def test_overlap_becomes_three_segments() -> None:
    segments = _segment(
        _intervals(
            [
                _FakeClaim("c1", date(2019, 1, 1), date(2020, 12, 31)),
                _FakeClaim("c2", date(2020, 1, 1), date(2021, 12, 31)),
            ]
        )
    )
    assert _bounds(segments) == [
        (date(2019, 1, 1), date(2019, 12, 31), ("c1",)),
        (date(2020, 1, 1), date(2020, 12, 31), ("c1", "c2")),
        (date(2021, 1, 1), date(2021, 12, 31), ("c2",)),
    ]


def test_full_containment_becomes_three_segments() -> None:
    segments = _segment(
        _intervals(
            [
                _FakeClaim("outer", date(2019, 1, 1), date(2022, 12, 31)),
                _FakeClaim("inner", date(2020, 1, 1), date(2020, 12, 31)),
            ]
        )
    )
    assert _bounds(segments) == [
        (date(2019, 1, 1), date(2019, 12, 31), ("outer",)),
        (date(2020, 1, 1), date(2020, 12, 31), ("inner", "outer")),
        (date(2021, 1, 1), date(2022, 12, 31), ("outer",)),
    ]


def test_identical_intervals_collapse_into_one_segment() -> None:
    """Same span, same claim set — one maximal interval, not two rows."""
    segments = _segment(
        _intervals(
            [
                _FakeClaim("c1", date(2019, 1, 1), date(2019, 12, 31)),
                _FakeClaim("c2", date(2019, 1, 1), date(2019, 12, 31)),
            ]
        )
    )
    assert _bounds(segments) == [
        (date(2019, 1, 1), date(2019, 12, 31), ("c1", "c2"))
    ]


def test_an_open_end_stays_open_past_the_last_boundary() -> None:
    segments = _segment(
        _intervals(
            [
                _FakeClaim("bounded", date(2019, 1, 1), date(2019, 12, 31)),
                _FakeClaim("open", date(2019, 1, 1), None),
            ]
        )
    )
    assert _bounds(segments) == [
        (date(2019, 1, 1), date(2019, 12, 31), ("bounded", "open")),
        (date(2020, 1, 1), None, ("open",)),
    ]


def test_an_open_start_stays_open_before_the_first_boundary() -> None:
    segments = _segment(
        _intervals(
            [
                _FakeClaim("open", None, date(2020, 12, 31)),
                _FakeClaim("late", date(2020, 1, 1), date(2020, 12, 31)),
            ]
        )
    )
    assert _bounds(segments) == [
        (None, date(2019, 12, 31), ("open",)),
        (date(2020, 1, 1), date(2020, 12, 31), ("late", "open")),
    ]


def test_neighbouring_segments_with_one_claim_set_are_merged() -> None:
    """Maximality: a cut point that changes nothing must not split a segment.

    Three claims spanning the same window produce interior boundaries that all
    three cover; the result must still be a single row.
    """
    segments = _segment(
        [
            _Interval(date(2019, 1, 1), date(2021, 1, 1), "c1"),
            _Interval(date(2019, 1, 1), date(2021, 1, 1), "c2"),
            _Interval(date(2019, 1, 1), date(2021, 1, 1), "c3"),
        ]
    )
    assert len(segments) == 1
    assert segments[0][2] == ("c1", "c2", "c3")


def test_intervals_convert_null_bounds_to_sentinels() -> None:
    [interval] = _intervals([_FakeClaim("c1", None, None)])
    assert interval.start == _NEG_INF and interval.end == _POS_INF


def test_bounds_round_trip_back_to_null() -> None:
    assert _to_bound(_NEG_INF, upper=False) is None
    assert _to_bound(_POS_INF, upper=True) is None
    assert _to_bound(date(2020, 1, 1), upper=False) == date(2020, 1, 1)
    # the stored upper bound is inclusive; the internal one is exclusive
    assert _to_bound(date(2021, 1, 1), upper=True) == date(2020, 12, 31)
