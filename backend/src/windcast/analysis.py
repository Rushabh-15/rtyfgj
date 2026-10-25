"""Accuracy analysis on top of ``evaluation``: breakdowns, persistence skill, the buffer back-test, lag scans and
the all-vintage view that separates lead time from hour of day."""

from __future__ import annotations

import datetime as dt
import math
import random
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from windcast.evaluation import ActualIndex, PeriodResult
from windcast.metrics import ErrorStats, error_stats, mean, pearson, quantile
from windcast.selection import is_forward_looking, source_hour
from windcast.snapshot import ForecastRow
from windcast.timeutils import HALF_HOUR, LONDON, delivery_day_periods


@dataclass(frozen=True, slots=True)
class Breakdown:
    label: str
    lo: float
    hi: float | None
    stats: ErrorStats | None  # None when the bucket is empty


def _bucket_label(lo: float, hi: float | None, unit: str) -> str:
    return f"≥{lo:g}{unit}" if hi is None else f"{lo:g}–{hi:g}{unit}"


def breakdown(
    periods: Iterable[PeriodResult],
    key: str,
    buckets: Sequence[tuple[int, int | None]],
    unit: str,
) -> list[Breakdown]:
    """Error statistics per bucket of ``key`` ("lead" in hours or "level" = forecast MW)."""
    groups: dict[int, list[float]] = defaultdict(list)
    for p in periods:
        value = p.lead_hours if key == "lead" else float(p.forecast_mw)
        for i, (lo, hi) in enumerate(buckets):
            if value >= lo and (hi is None or value < hi):
                groups[i].append(p.error_mw)
                break
    rows = []
    for i, (lo, hi) in enumerate(buckets):
        errors = groups.get(i)
        label = (
            _bucket_label(lo / 1000, None if hi is None else hi / 1000, " GW")
            if key == "level"
            else (_bucket_label(lo, hi, " h"))
        )
        rows.append(Breakdown(label, lo, hi, error_stats(errors) if errors else None))
    return rows


@dataclass(frozen=True, slots=True)
class Skill:
    forecast: ErrorStats
    persistence: ErrorStats
    mae_skill: float  # 1 - MAE_forecast / MAE_persistence; > 0 means the forecast is better
    rmse_skill: float


def persistence_skill(periods: Sequence[PeriodResult]) -> Skill:
    forecast = error_stats(p.error_mw for p in periods)
    persistence = error_stats(p.persistence_error_mw for p in periods)
    return Skill(
        forecast=forecast,
        persistence=persistence,
        mae_skill=1 - forecast.mae_mw / persistence.mae_mw,
        rmse_skill=1 - forecast.rmse_mw / persistence.rmse_mw,
    )


@dataclass(frozen=True, slots=True)
class BufferResult:
    """Buy ``buffer_mw`` beyond the forecast-implied volume to cover wind shortfalls in ``target`` % of half-hours."""

    target: int
    buffer_mw: float  # fitted on the fit days
    fit_coverage: float
    test_coverage: float
    test_coverage_low: float  # 95% day-block bootstrap interval
    test_coverage_high: float
    full_month_buffer_mw: float  # refitted on every day, for carrying forward
    fit_periods: int
    test_periods: int


def _coverage(errors: Sequence[float], buffer_mw: float) -> float:
    return sum(1 for e in errors if e <= buffer_mw) / len(errors)


def buffer_backtest(
    periods: Sequence[PeriodResult],
    fit_days: Sequence[dt.date],
    test_days: Sequence[dt.date],
    targets: Sequence[int],
    *,
    resamples: int,
    seed: int,
) -> list[BufferResult]:
    """Fit the buffer as the target quantile of shortfall on ``fit_days``; measure coverage on ``test_days``.

    Half-hours within a day are correlated, so the interval resamples whole test days (block bootstrap).
    """
    fit_set, test_set = set(fit_days), set(test_days)
    if fit_set & test_set:
        raise ValueError("fit and test days overlap")
    fit_errors = sorted(float(p.error_mw) for p in periods if p.delivery_day in fit_set)
    all_errors = sorted(float(p.error_mw) for p in periods)
    test_by_day: dict[dt.date, list[float]] = defaultdict(list)
    for p in periods:
        if p.delivery_day in test_set:
            test_by_day[p.delivery_day].append(float(p.error_mw))
    test_errors = [e for d in test_days for e in test_by_day[d]]
    if not fit_errors or not test_errors:
        raise ValueError("empty fit or test sample")

    results = []
    for target in targets:
        q = target / 100
        buffer_mw = quantile(fit_errors, q)
        rng = random.Random(seed + target)
        covered_by_day = [sum(1 for e in test_by_day[d] if e <= buffer_mw) for d in test_days]
        size_by_day = [len(test_by_day[d]) for d in test_days]
        draws = []
        for _ in range(resamples):
            sample = [rng.randrange(len(test_days)) for _ in test_days]
            draws.append(sum(covered_by_day[i] for i in sample) / sum(size_by_day[i] for i in sample))
        draws.sort()
        results.append(
            BufferResult(
                target=target,
                buffer_mw=buffer_mw,
                fit_coverage=_coverage(fit_errors, buffer_mw),
                test_coverage=_coverage(test_errors, buffer_mw),
                test_coverage_low=quantile(draws, 0.025),
                test_coverage_high=quantile(draws, 0.975),
                full_month_buffer_mw=quantile(all_errors, q),
                fit_periods=len(fit_errors),
                test_periods=len(test_errors),
            )
        )
    return results


@dataclass(frozen=True, slots=True)
class LagPoint:
    shift_minutes: int
    n: int
    mean_error_mw: float
    mae_mw: float
    rmse_mw: float
    sd_mw: float  # error spread with the mean removed
    correlation: float  # forecast vs shifted outturn


def _lag_point(shift: int, pairs: Sequence[tuple[float, float]]) -> LagPoint:
    errors = [f - a for f, a in pairs]
    m = mean(errors)
    return LagPoint(
        shift_minutes=shift,
        n=len(errors),
        mean_error_mw=m,
        mae_mw=mean(abs(e) for e in errors),
        rmse_mw=math.sqrt(mean(e * e for e in errors)),
        sd_mw=math.sqrt(mean((e - m) ** 2 for e in errors)),
        correlation=pearson([f for f, _ in pairs], [a for _, a in pairs]),
    )


def lag_scan(periods: Sequence[PeriodResult], actuals: ActualIndex, shifts: Sequence[int]) -> list[LagPoint]:
    """Error of the cutoff forecast for period t against outturn at t + shift (same periods for every shift)."""
    points = []
    for shift in shifts:
        pairs = []
        for p in periods:
            a = actuals.value(p.period_start + HALF_HOUR * (shift // 30))
            if a is None:
                raise ValueError(f"no outturn {shift} min from {p.period_start.isoformat()}")
            pairs.append((float(p.forecast_mw), float(a)))
        points.append(_lag_point(shift, pairs))
    return points


@dataclass(frozen=True, slots=True)
class VintagePair:
    period_start: dt.datetime
    publish_time: dt.datetime
    forecast_mw: int
    actual_mw: int

    @property
    def lead_hours(self) -> float:
        return (self.period_start - self.publish_time).total_seconds() / 3600

    @property
    def error_mw(self) -> int:
        return self.forecast_mw - self.actual_mw


def vintage_pairs(
    forecasts: Iterable[ForecastRow],
    actuals: ActualIndex,
    days: Sequence[dt.date],
    *,
    shift_minutes: int = 0,
) -> list[VintagePair]:
    """Every forward-looking (run, half-hour) pair for the delivery periods of ``days``, at every lead time."""
    by_source: dict[dt.datetime, list[tuple[dt.datetime, int]]] = defaultdict(list)
    for row in forecasts:
        if is_forward_looking(row):
            by_source[row.start_time].append((row.publish_time, row.generation_mw))
    pairs = []
    for day in days:
        for t in delivery_day_periods(day):
            actual = actuals.value(t)
            if actual is None:
                raise ValueError(f"no outturn for {t.isoformat()}")
            for publish, mw in by_source.get(source_hour(t, shift_minutes), []):
                if publish <= t:
                    pairs.append(VintagePair(t, publish, mw, actual))
    return pairs


@dataclass(frozen=True, slots=True)
class GridCell:
    lead_lo: int
    hour: int
    n: int
    mae_mw: float
    mean_error_mw: float


@dataclass(frozen=True, slots=True)
class VintageSummary:
    pairs: int
    runs: int
    by_lead: list[Breakdown]
    by_hour: list[Breakdown]  # UK clock hour of the period start, leads 12-36 h only
    grid: list[GridCell]  # 6-hour lead buckets x UK hour
    lead_effect_mw: float  # range of lead-bucket means of the grid (hours balanced)
    hour_effect_mw: float  # range of hour means of the grid (leads balanced)
    effect_leads_h: tuple[int, int]  # lead range of the complete grid rows used for the two effects
    short_lead_lag_scan: list[LagPoint]  # leads under 6 h, where timing errors are smallest


def _width(buckets: Sequence[tuple[int, int]]) -> int:
    return buckets[0][1] - buckets[0][0]


def _uk_hour(t: dt.datetime) -> int:
    return t.astimezone(LONDON).hour


def summarise_vintages(
    pairs: Sequence[VintagePair],
    actuals: ActualIndex,
    lead_buckets: Sequence[tuple[int, int]],
    grid_buckets: Sequence[tuple[int, int]],
    shifts: Sequence[int],
) -> VintageSummary:
    by_lead_groups: dict[int, list[float]] = defaultdict(list)
    by_hour_groups: dict[int, list[float]] = defaultdict(list)
    grid_groups: dict[tuple[int, int], list[float]] = defaultdict(list)
    for p in pairs:
        lead, err = p.lead_hours, float(p.error_mw)
        for lo, hi in lead_buckets:
            if lo <= lead < hi:
                by_lead_groups[lo].append(err)
                break
        if 12 <= lead < 36:
            by_hour_groups[_uk_hour(p.period_start)].append(err)
        for lo, hi in grid_buckets:
            if lo <= lead < hi:
                grid_groups[(lo, _uk_hour(p.period_start))].append(err)
                break

    by_lead = [
        Breakdown(
            _bucket_label(lo, hi, " h"),
            lo,
            hi,
            error_stats(by_lead_groups[lo]) if by_lead_groups[lo] else None,
        )
        for lo, hi in lead_buckets
    ]
    by_hour = [
        Breakdown(f"{h:02d}:00", h, h + 1, error_stats(by_hour_groups[h]) if by_hour_groups[h] else None)
        for h in range(24)
    ]
    grid = [GridCell(lo, h, len(v), mean(abs(e) for e in v), mean(v)) for (lo, h), v in sorted(grid_groups.items())]
    # Main effects on the cells that exist for every hour, so neither factor is confounded with the other.
    complete_leads = [lo for lo, _ in grid_buckets if all((lo, h) in grid_groups for h in range(24))]
    cell_mae = {(c.lead_lo, c.hour): c.mae_mw for c in grid}
    lead_means = [mean(cell_mae[(lo, h)] for h in range(24)) for lo in complete_leads]
    hour_means = [mean(cell_mae[(lo, h)] for lo in complete_leads) for h in range(24)] if complete_leads else []

    short = [p for p in pairs if p.lead_hours < 6]
    short_scan = []
    for shift in shifts:
        shifted = []
        for p in short:
            a = actuals.value(p.period_start + HALF_HOUR * (shift // 30))
            if a is not None:
                shifted.append((float(p.forecast_mw), float(a)))
        short_scan.append(_lag_point(shift, shifted))

    return VintageSummary(
        pairs=len(pairs),
        runs=len({p.publish_time for p in pairs}),
        by_lead=by_lead,
        by_hour=by_hour,
        grid=grid,
        lead_effect_mw=(max(lead_means) - min(lead_means)) if lead_means else math.nan,
        hour_effect_mw=(max(hour_means) - min(hour_means)) if hour_means else math.nan,
        effect_leads_h=(min(complete_leads), max(complete_leads) + _width(grid_buckets)) if complete_leads else (0, 0),
        short_lead_lag_scan=short_scan,
    )
