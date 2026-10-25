"""Golden test: delivery day 16 January 2026, checked by hand against the raw snapshot.

The expected values in ``golden/delivery_2026-01-16.json`` were read straight from the raw JSON with jq, not
produced by this code, e.g.::

    jq -r '.[] | select(.publishTime=="2026-01-15T07:30:00Z" and .startTime>="2026-01-15T23:00:00Z"
           and .startTime<="2026-01-16T22:00:00Z") | "\\(.startTime) \\(.generation)"' WINDFOR_stream_*.json
    jq -r '.[] | select(.startTime>="2026-01-15T23:00:00Z" and .startTime<="2026-01-16T22:30:00Z")
           | "\\(.startTime) \\(.generation) \\(.publishTime)"' FUELHH_WIND_stream_*.json

and the day's error sum and MAE were added up by hand from those 48 pairs. The day is chosen because 15 January
(its decision day) had the only late run in the snapshot: 11:30 was missing and 12:25 was published instead, and
FUELHH for 10:00-11:30 was also published late, which exercises the strictly-before rule on both datasets.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import pytest

from tests.conftest import GOLDEN_DIR
from windcast.evaluation import ActualIndex, evaluate_cutoff
from windcast.snapshot import Snapshot
from windcast.timeutils import HALF_HOUR, delivery_day_periods, iso_z, parse_hhmm

GOLDEN: dict[str, Any] = json.loads((GOLDEN_DIR / "delivery_2026-01-16.json").read_text())
DAY = dt.date.fromisoformat(GOLDEN["delivery_day"])


def _day(snapshot: Snapshot, actual_index: ActualIndex, cutoff: str) -> Any:
    (result,) = evaluate_cutoff(snapshot.forecasts, actual_index, [DAY], parse_hhmm(cutoff))
    return result


def test_delivery_day_has_48_periods_from_23_00() -> None:
    periods = delivery_day_periods(DAY)
    assert len(periods) == 48
    assert iso_z(periods[0]) == "2026-01-15T23:00:00Z"
    assert iso_z(periods[-1]) == "2026-01-16T22:30:00Z"


@pytest.mark.parametrize(("cutoff", "run"), sorted(GOLDEN["runs_by_cutoff"].items()))
def test_run_in_use_for_each_cutoff(snapshot: Snapshot, actual_index: ActualIndex, cutoff: str, run: str) -> None:
    day = _day(snapshot, actual_index, cutoff)
    assert [iso_z(r) for r in day.runs] == [run]


def test_forecast_and_actual_values_at_09_00(snapshot: Snapshot, actual_index: ActualIndex) -> None:
    day = _day(snapshot, actual_index, "09:00")
    hourly = GOLDEN["hourly_forecast_0900_cutoff"]
    expected_forecast = [hourly[iso_z(p.period_start.replace(minute=0))] for p in day.periods]
    assert [p.forecast_mw for p in day.periods] == expected_forecast
    assert [p.actual_mw for p in day.periods] == GOLDEN["actual_half_hourly"]
    # Each hourly value covers the half-hours starting at its label and 30 minutes later.
    assert all(p.source_start == p.period_start.replace(minute=0) for p in day.periods)
    assert [p.period_start for p in day.periods[1::2]] == [p.period_start + HALF_HOUR for p in day.periods[::2]]


def test_day_error_metrics_match_hand_calculation(snapshot: Snapshot, actual_index: ActualIndex) -> None:
    day = _day(snapshot, actual_index, "09:00")
    errors = [p.error_mw for p in day.periods]
    metrics = GOLDEN["day_metrics_0900_cutoff"]
    assert sum(errors) == metrics["sum_error_mw"]
    assert sum(abs(e) for e in errors) == metrics["sum_abs_error_mw"]
    assert sum(errors) / 48 == pytest.approx(metrics["mean_error_mw"])
    assert sum(abs(e) for e in errors) / 48 == pytest.approx(metrics["mae_mw"])


@pytest.mark.parametrize("cutoff", sorted(GOLDEN["spot_values_other_cutoffs"]))
def test_late_run_values(snapshot: Snapshot, actual_index: ActualIndex, cutoff: str) -> None:
    day = _day(snapshot, actual_index, cutoff)
    by_hour = {iso_z(p.source_start): p.forecast_mw for p in day.periods}
    for hour, value in GOLDEN["spot_values_other_cutoffs"][cutoff].items():
        assert by_hour[hour] == value


@pytest.mark.parametrize(("cutoff", "expected"), sorted(GOLDEN["persistence_by_cutoff"].items()))
def test_persistence_uses_only_outturn_published_before_cutoff(
    snapshot: Snapshot, actual_index: ActualIndex, cutoff: str, expected: dict[str, Any]
) -> None:
    day = _day(snapshot, actual_index, cutoff)
    assert iso_z(day.persistence.period_start) == expected["period_start"]
    assert day.persistence.value_mw == expected["value_mw"]
    assert day.persistence.publish_time < day.cutoff
