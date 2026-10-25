"""Properties of the core rule, checked on random inputs.

1. A selected forecast is never published at or after its cutoff (strictly before).
2. It is the most recent eligible one: no forward-looking row for the same source hour was published between it
   and the cutoff.
3. ``None`` only when no eligible row exists.
4. Rows targeting an hour before their own run are never selected.
5. The result does not depend on input order and the inputs are not modified.
"""

from __future__ import annotations

import datetime as dt
import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.strategies import at, forecast_rows, requests, shifts
from windcast.selection import (
    Selection,
    SelectionRequest,
    is_forward_looking,
    select_forecasts,
    source_hour,
)
from windcast.snapshot import ForecastRow


def eligible(rows: list[ForecastRow], request: SelectionRequest, shift: int) -> list[ForecastRow]:
    src = source_hour(request.period_start, shift)
    return [r for r in rows if r.start_time == src and is_forward_looking(r) and r.publish_time < request.cutoff]


@settings(max_examples=400)
@given(rows=forecast_rows(), reqs=requests(), shift=shifts)
def test_selected_forecast_is_published_strictly_before_cutoff(
    rows: list[ForecastRow], reqs: list[SelectionRequest], shift: int
) -> None:
    for req, sel in zip(reqs, select_forecasts(rows, reqs, shift_minutes=shift), strict=True):
        if sel is not None:
            assert sel.publish_time < req.cutoff


@settings(max_examples=400)
@given(rows=forecast_rows(), reqs=requests(), shift=shifts)
def test_selected_forecast_is_the_most_recent_eligible_one(
    rows: list[ForecastRow], reqs: list[SelectionRequest], shift: int
) -> None:
    for req, sel in zip(reqs, select_forecasts(rows, reqs, shift_minutes=shift), strict=True):
        candidates = eligible(rows, req, shift)
        if not candidates:
            assert sel is None
            continue
        best = max(candidates, key=lambda r: r.publish_time)
        assert sel == Selection(
            period_start=req.period_start,
            cutoff=req.cutoff,
            publish_time=best.publish_time,
            source_start=best.start_time,
            generation_mw=best.generation_mw,
        )
        assert not any(sel.publish_time < r.publish_time < req.cutoff for r in candidates)


@settings(max_examples=300)
@given(rows=forecast_rows(), reqs=requests(), shift=shifts)
def test_rows_before_their_run_are_never_selected(
    rows: list[ForecastRow], reqs: list[SelectionRequest], shift: int
) -> None:
    for sel in select_forecasts(rows, reqs, shift_minutes=shift):
        if sel is not None:
            assert sel.source_start >= sel.publish_time
            assert sel.source_start == source_hour(sel.period_start, shift)


@settings(max_examples=200)
@given(rows=forecast_rows(), reqs=requests(), shift=shifts, seed=st.integers(0, 2**32 - 1))
def test_result_is_independent_of_row_order_and_inputs_are_untouched(
    rows: list[ForecastRow], reqs: list[SelectionRequest], shift: int, seed: int
) -> None:
    before_rows, before_reqs = list(rows), list(reqs)
    expected = select_forecasts(rows, reqs, shift_minutes=shift)
    shuffled = list(rows)
    random.Random(seed).shuffle(shuffled)
    assert select_forecasts(shuffled, reqs, shift_minutes=shift) == expected
    assert select_forecasts(iter(rows), reqs, shift_minutes=shift) == expected  # any iterable
    assert rows == before_rows
    assert reqs == before_reqs


def test_run_published_exactly_at_cutoff_is_not_used() -> None:
    rows = [
        ForecastRow(at(0), at(600), 100),  # 00:00 run
        ForecastRow(at(540), at(600), 200),  # 09:00 run, published exactly at the cutoff
    ]
    req = SelectionRequest(period_start=at(600), cutoff=at(540))
    (sel,) = select_forecasts(rows, [req])
    assert sel is not None
    assert sel.generation_mw == 100
    (later,) = select_forecasts(rows, [SelectionRequest(at(600), at(541))])
    assert later is not None
    assert later.generation_mw == 200


def test_late_run_falls_back_to_the_previous_one() -> None:
    # The usual 11:30 run is missing and a 12:25 run appears instead (as on 15 Jan 2026).
    rows = [ForecastRow(at(m), at(24 * 60), mw) for m, mw in ((9 * 60 + 30, 1), (12 * 60 + 25, 2))]
    picks = {
        cutoff: select_forecasts(rows, [SelectionRequest(at(24 * 60), at(cutoff))])[0]
        for cutoff in (12 * 60, 12 * 60 + 25, 12 * 60 + 30)
    }
    assert {k: (v.generation_mw if v else None) for k, v in picks.items()} == {720: 1, 745: 1, 750: 2}


def test_alignment_maps_half_hours_to_hourly_labels() -> None:
    h = at(10 * 60)
    assert source_hour(h) == h
    assert source_hour(h + dt.timedelta(minutes=30)) == h
    assert source_hour(h - dt.timedelta(minutes=30), -30) == h
    assert source_hour(h, -30) == h
    assert source_hour(h + dt.timedelta(minutes=30), -30) == h + dt.timedelta(hours=1)


def test_invalid_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="half-hour"):
        source_hour(at(10))
    with pytest.raises(ValueError, match="shift_minutes"):
        source_hour(at(0), 30)
    naive = dt.datetime(2026, 1, 1, 10, 0)  # noqa: DTZ001 - deliberately naive
    with pytest.raises(ValueError, match="naive"):
        select_forecasts([ForecastRow(naive, naive, 1)], [])
    duplicate = [ForecastRow(at(0), at(60), 1), ForecastRow(at(0), at(60), 2)]
    with pytest.raises(ValueError, match="duplicate"):
        select_forecasts(duplicate, [])
