"""The pure-Python rule, pandas ``merge_asof`` and DuckDB ``ASOF JOIN`` must give identical output.

Checked on random inputs (including exact publish/cutoff ties) and on the full snapshot at every cutoff in the
grid, for both alignments.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings

from tests.strategies import forecast_rows, requests, shifts
from windcast import study
from windcast.evaluation import day_ahead_requests
from windcast.selection import SelectionRequest, select_forecasts
from windcast.selection_asof import select_forecasts_duckdb, select_forecasts_pandas
from windcast.snapshot import ForecastRow, Snapshot
from windcast.timeutils import format_hhmm


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(rows=forecast_rows(), reqs=requests(), shift=shifts)
def test_three_implementations_agree_on_random_inputs(
    rows: list[ForecastRow], reqs: list[SelectionRequest], shift: int
) -> None:
    expected = select_forecasts(rows, reqs, shift_minutes=shift)
    assert select_forecasts_pandas(rows, reqs, shift_minutes=shift) == expected
    assert select_forecasts_duckdb(rows, reqs, shift_minutes=shift) == expected


@pytest.mark.slow
@pytest.mark.parametrize("shift", [0, -30])
@pytest.mark.parametrize("cutoff", study.cutoff_grid(), ids=format_hhmm)
def test_three_implementations_agree_on_the_snapshot(snapshot: Snapshot, cutoff: object, shift: int) -> None:
    import datetime as dt

    assert isinstance(cutoff, dt.time)
    reqs = day_ahead_requests(study.DELIVERY_DAYS, cutoff)
    expected = select_forecasts(snapshot.forecasts, reqs, shift_minutes=shift)
    assert all(s is not None for s in expected)
    assert select_forecasts_pandas(snapshot.forecasts, reqs, shift_minutes=shift) == expected
    assert select_forecasts_duckdb(snapshot.forecasts, reqs, shift_minutes=shift) == expected
