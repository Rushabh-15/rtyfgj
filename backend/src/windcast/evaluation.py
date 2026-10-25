"""Pair the forecast selected at a cutoff with the outturn and the persistence baseline, per half-hour."""

from __future__ import annotations

import bisect
import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass

from windcast.selection import Selection, SelectionRequest, select_forecasts
from windcast.snapshot import ActualRow, ForecastRow
from windcast.timeutils import HALF_HOUR, cutoff_instant, delivery_day_periods


class CoverageError(RuntimeError):
    """A delivery period has no forecast at the cutoff or no outturn."""


@dataclass(frozen=True, slots=True)
class PeriodResult:
    delivery_day: dt.date
    period_start: dt.datetime
    cutoff: dt.datetime
    publish_time: dt.datetime
    source_start: dt.datetime
    forecast_mw: int
    actual_mw: int
    persistence_mw: int

    @property
    def error_mw(self) -> int:
        """Forecast minus actual: positive is a shortfall of wind against the forecast."""
        return self.forecast_mw - self.actual_mw

    @property
    def persistence_error_mw(self) -> int:
        return self.persistence_mw - self.actual_mw

    @property
    def lead_hours(self) -> float:
        return (self.period_start - self.publish_time).total_seconds() / 3600


@dataclass(frozen=True, slots=True)
class Persistence:
    """The last outturn published strictly before the cutoff, held flat for the whole delivery day."""

    value_mw: int
    period_start: dt.datetime
    publish_time: dt.datetime


@dataclass(frozen=True, slots=True)
class DayResult:
    delivery_day: dt.date
    cutoff: dt.datetime
    persistence: Persistence
    periods: tuple[PeriodResult, ...]

    @property
    def runs(self) -> tuple[dt.datetime, ...]:
        """Distinct runs used for this day, earliest first (normally exactly one)."""
        return tuple(sorted({p.publish_time for p in self.periods}))


class ActualIndex:
    """Outturn lookups by period start, and "what was known before t" by publish time."""

    def __init__(self, actuals: Sequence[ActualRow]) -> None:
        self.by_start: dict[dt.datetime, ActualRow] = {a.start_time: a for a in actuals}
        if len(self.by_start) != len(actuals):
            raise ValueError("duplicate FUELHH periods")
        ordered = sorted(actuals, key=lambda a: (a.publish_time, a.start_time))
        self._publish_times = [a.publish_time for a in ordered]
        # Running "latest period published so far": late publications can arrive out of order.
        self._latest_known: list[ActualRow] = []
        best: ActualRow | None = None
        for a in ordered:
            if best is None or a.start_time > best.start_time:
                best = a
            self._latest_known.append(best)

    def value(self, period_start: dt.datetime) -> int | None:
        row = self.by_start.get(period_start)
        return None if row is None else row.generation_mw

    def latest_known_before(self, instant: dt.datetime) -> ActualRow | None:
        """The most recent period whose outturn was published strictly before ``instant``."""
        i = bisect.bisect_left(self._publish_times, instant)
        return None if i == 0 else self._latest_known[i - 1]


def day_ahead_requests(days: Sequence[dt.date], cutoff: dt.time) -> list[SelectionRequest]:
    return [SelectionRequest(p, cutoff_instant(d, cutoff)) for d in days for p in delivery_day_periods(d)]


def evaluate_cutoff(
    forecasts: Sequence[ForecastRow],
    actuals: ActualIndex,
    days: Sequence[dt.date],
    cutoff: dt.time,
    *,
    shift_minutes: int = 0,
) -> list[DayResult]:
    """Forecast at the cutoff, outturn and persistence for every half-hour of ``days``.

    Raises ``CoverageError`` if any period lacks a forecast or an outturn, so incomplete tables are never served.
    """
    requests = day_ahead_requests(days, cutoff)
    selections = select_forecasts(forecasts, requests, shift_minutes=shift_minutes)
    by_day: dict[dt.date, list[Selection]] = {d: [] for d in days}
    period_day = {p: d for d in days for p in delivery_day_periods(d)}
    for request, selection in zip(requests, selections, strict=True):
        if selection is None:
            raise CoverageError(
                f"no forecast before {request.cutoff.isoformat()} for {request.period_start.isoformat()}"
            )
        by_day[period_day[selection.period_start]].append(selection)

    results = []
    for day in days:
        cut = cutoff_instant(day, cutoff)
        known = actuals.latest_known_before(cut)
        if known is None:
            raise CoverageError(f"no outturn published before {cut.isoformat()}")
        persistence = Persistence(known.generation_mw, known.start_time, known.publish_time)
        periods = []
        for s in by_day[day]:
            actual = actuals.value(s.period_start)
            if actual is None:
                raise CoverageError(f"no outturn for {s.period_start.isoformat()}")
            periods.append(
                PeriodResult(
                    delivery_day=day,
                    period_start=s.period_start,
                    cutoff=s.cutoff,
                    publish_time=s.publish_time,
                    source_start=s.source_start,
                    forecast_mw=s.generation_mw,
                    actual_mw=actual,
                    persistence_mw=persistence.value_mw,
                )
            )
        results.append(DayResult(day, cut, persistence, tuple(periods)))
    return results


def all_periods(days: Sequence[DayResult]) -> list[PeriodResult]:
    return [p for d in days for p in d.periods]


def shifted_actual(actuals: ActualIndex, period_start: dt.datetime, shift_minutes: int) -> int | None:
    """Outturn for the half-hour ``shift_minutes`` after ``period_start`` (used by the lag scan)."""
    if shift_minutes % 30:
        raise ValueError("lag shifts must be multiples of 30 minutes")
    return actuals.value(period_start + HALF_HOUR * (shift_minutes // 30))
