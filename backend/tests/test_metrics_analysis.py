"""Metrics and analysis helpers on small synthetic data where the answer is known."""

from __future__ import annotations

import datetime as dt

import pytest

from windcast import analysis
from windcast.evaluation import ActualIndex, CoverageError, PeriodResult, evaluate_cutoff
from windcast.metrics import error_stats, pearson, quantile
from windcast.snapshot import ActualRow, ForecastRow
from windcast.timeutils import HALF_HOUR, delivery_day_periods

T0 = dt.datetime(2026, 1, 15, 23, 0, tzinfo=dt.UTC)


def test_quantile_matches_numpy_linear_interpolation() -> None:
    values = [1.0, 2.0, 3.0, 4.0]
    assert quantile(values, 0.0) == 1.0
    assert quantile(values, 1.0) == 4.0
    assert quantile(values, 0.5) == 2.5
    assert quantile(values, 0.9) == pytest.approx(3.7)
    with pytest.raises(ValueError, match="empty"):
        quantile([], 0.5)


def test_error_stats() -> None:
    s = error_stats([-2, -1, 0, 1, 2, 6])
    assert s.n == 6
    assert s.mean_error_mw == pytest.approx(1.0)
    assert s.mae_mw == pytest.approx(2.0)
    assert s.rmse_mw == pytest.approx((46 / 6) ** 0.5)
    assert s.p50_mw == pytest.approx(0.5)
    assert s.shortfall_share == pytest.approx(0.5)
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)


def _period(day: dt.date, i: int, forecast: int, actual: int, publish_hours_before: float = 20) -> PeriodResult:
    start = T0 + i * HALF_HOUR
    return PeriodResult(
        delivery_day=day,
        period_start=start,
        cutoff=start - dt.timedelta(hours=10),
        publish_time=start - dt.timedelta(hours=publish_hours_before),
        source_start=start.replace(minute=0),
        forecast_mw=forecast,
        actual_mw=actual,
        persistence_mw=actual + 1000,
    )


def test_breakdown_assigns_lead_and_level_buckets() -> None:
    day = dt.date(2026, 1, 16)
    ps = [_period(day, 0, 5000, 4000, 13), _period(day, 1, 19000, 15000, 20)]
    lead = analysis.breakdown(ps, "lead", [(12, 18), (18, 24)], "h")
    assert [b.stats.n if b.stats else 0 for b in lead] == [1, 1]
    level = analysis.breakdown(ps, "level", [(0, 6000), (6000, 18000), (18000, None)], "GW")
    assert [b.label for b in level] == ["0–6 GW", "6–18 GW", "≥18 GW"]
    assert [b.stats.mean_error_mw if b.stats else None for b in level] == [1000, None, 4000]


def test_buffer_backtest_on_known_errors() -> None:
    fit_day, test_day = dt.date(2026, 1, 2), dt.date(2026, 1, 3)
    fit = [_period(fit_day, i, 1000 + e, 1000) for i, e in enumerate(range(0, 1000, 10))]  # errors 0..990
    test = [_period(test_day, i, 1000 + e, 1000) for i, e in enumerate(range(0, 2000, 20))]  # errors 0..1980
    (result,) = analysis.buffer_backtest(fit + test, [fit_day], [test_day], [90], resamples=50, seed=1)
    assert result.buffer_mw == pytest.approx(891.0)  # P90 of 0..990 in steps of 10
    assert result.fit_coverage == pytest.approx(0.90)
    assert result.test_coverage == pytest.approx(0.45)  # errors 0..880 of 0..1980
    assert result.test_coverage_low == result.test_coverage_high == pytest.approx(0.45)  # one test day
    with pytest.raises(ValueError, match="overlap"):
        analysis.buffer_backtest(fit, [fit_day], [fit_day], [90], resamples=1, seed=1)


def test_persistence_skill_sign() -> None:
    day = dt.date(2026, 1, 16)
    ps = [_period(day, i, 1100, 1000) for i in range(4)]  # forecast off by 100, persistence by 1000
    skill = analysis.persistence_skill(ps)
    assert skill.mae_skill == pytest.approx(0.9)


def _actuals(values: list[int], start: dt.datetime) -> list[ActualRow]:
    return [
        ActualRow(start + i * HALF_HOUR, (start + i * HALF_HOUR).date(), 1, start + (i + 1) * HALF_HOUR, v)
        for i, v in enumerate(values)
    ]


def test_lag_scan_finds_a_known_shift() -> None:
    day = dt.date(2026, 1, 16)
    pattern = [1000 + 500 * ((i // 4) % 2) + 37 * i for i in range(120)]
    acts = ActualIndex(_actuals(pattern, T0 - 8 * HALF_HOUR))
    # Forecast for period i equals the outturn one half-hour later: the scan should prefer +30 min.
    ps = [_period(day, i, pattern[i + 9], pattern[i + 8]) for i in range(48)]
    scan = analysis.lag_scan(ps, acts, [-60, -30, 0, 30, 60])
    best = min(scan, key=lambda p: p.mae_mw)
    assert best.shift_minutes == 30
    assert best.mae_mw == 0


def test_evaluate_cutoff_refuses_incomplete_coverage() -> None:
    day = dt.date(2026, 1, 16)
    periods = delivery_day_periods(day)
    acts = ActualIndex(_actuals([1000] * 120, T0 - dt.timedelta(hours=24)))
    run = dt.datetime(2026, 1, 15, 7, 30, tzinfo=dt.UTC)
    hours = sorted({p.replace(minute=0) for p in periods})
    full = [ForecastRow(run, h, 900) for h in hours]
    (result,) = evaluate_cutoff(full, acts, [day], dt.time(9, 0))
    assert len(result.periods) == 48
    assert result.runs == (run,)
    with pytest.raises(CoverageError, match="no forecast"):
        evaluate_cutoff(full[:-1], acts, [day], dt.time(9, 0))
    with pytest.raises(CoverageError, match="no forecast"):
        evaluate_cutoff(full, acts, [day], dt.time(7, 30))  # the only run is not strictly before 07:30
