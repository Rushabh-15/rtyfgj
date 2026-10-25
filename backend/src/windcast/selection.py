"""The core rule: which forecast did the desk have at its decision cutoff?

For each target half-hour we take the hourly WINDFOR value that covers it, from the latest run published
**strictly before** that period's cutoff. Rows whose target hour starts before their own ``publishTime`` are
ignored: once an hour has begun, later runs carry a frozen value for it rather than a forecast.

``select_forecasts`` is pure: it reads its arguments, mutates nothing and depends on nothing else, so the
property tests in ``tests/test_selection_properties.py`` can check it against brute force on random inputs, and
``selection_asof.py`` re-implements it with pandas ``merge_asof`` and DuckDB ``ASOF JOIN`` as cross-checks.

Alignment of hourly values to half-hours: by default the value labelled ``H`` (WINDFOR ``startTime``) covers the
half-hours starting ``H`` and ``H+30``. ``shift_minutes=-30`` moves that window 30 minutes earlier (``H-30`` and
``H``). See the decision log in the README for why the default is the field's literal meaning.
"""

from __future__ import annotations

import bisect
import datetime as dt
import itertools
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from windcast.snapshot import ForecastRow
from windcast.timeutils import require_aware, require_half_hour

ALLOWED_SHIFTS_MINUTES = (0, -30)


@dataclass(frozen=True, slots=True)
class SelectionRequest:
    """Select a forecast for the half-hour starting ``period_start`` as known strictly before ``cutoff``."""

    period_start: dt.datetime
    cutoff: dt.datetime


@dataclass(frozen=True, slots=True)
class Selection:
    period_start: dt.datetime
    cutoff: dt.datetime
    publish_time: dt.datetime
    source_start: dt.datetime
    generation_mw: int


def source_hour(period_start: dt.datetime, shift_minutes: int = 0) -> dt.datetime:
    """The hourly label whose value covers the half-hour starting ``period_start``."""
    require_half_hour(period_start)
    if shift_minutes not in ALLOWED_SHIFTS_MINUTES:
        raise ValueError(f"shift_minutes must be one of {ALLOWED_SHIFTS_MINUTES}, got {shift_minutes}")
    t = period_start - dt.timedelta(minutes=shift_minutes)
    return t.replace(minute=0, second=0, microsecond=0)


def _publish_time(run: tuple[dt.datetime, int]) -> dt.datetime:
    return run[0]


def is_forward_looking(row: ForecastRow) -> bool:
    """False for rows whose target hour starts before the run was published (these are excluded)."""
    return row.start_time >= row.publish_time


def select_forecasts(
    rows: Iterable[ForecastRow],
    requests: Sequence[SelectionRequest],
    *,
    shift_minutes: int = 0,
) -> list[Selection | None]:
    """For each request, the latest forward-looking forecast published strictly before its cutoff.

    Returns one entry per request, in request order; ``None`` where no run published before the cutoff covers
    the period. Raises ``ValueError`` on naive datetimes, periods off the half-hour grid, an unsupported shift,
    or two rows with the same run and target hour (the input contract forbids duplicates).
    """
    candidates: dict[dt.datetime, list[tuple[dt.datetime, int]]] = {}
    for row in rows:
        require_aware(row.publish_time)
        require_aware(row.start_time)
        if not is_forward_looking(row):
            continue
        candidates.setdefault(row.start_time, []).append((row.publish_time, row.generation_mw))

    for target, runs in candidates.items():
        runs.sort()
        for (earlier, _), (later, _) in itertools.pairwise(runs):
            if earlier == later:
                raise ValueError(f"duplicate forecast rows for run {earlier.isoformat()}, hour {target.isoformat()}")

    selections: list[Selection | None] = []
    for request in requests:
        require_aware(request.cutoff)
        source = source_hour(request.period_start, shift_minutes)
        runs = candidates.get(source, [])
        # Index of the first run published at or after the cutoff; the one before it is the latest earlier run.
        i = bisect.bisect_left(runs, request.cutoff, key=_publish_time)
        if i == 0:
            selections.append(None)
            continue
        publish_time, generation_mw = runs[i - 1]
        selections.append(
            Selection(
                period_start=request.period_start,
                cutoff=request.cutoff,
                publish_time=publish_time,
                source_start=source,
                generation_mw=generation_mw,
            )
        )
    return selections
