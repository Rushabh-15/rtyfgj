"""Hypothesis strategies: small random WINDFOR-like datasets and selection requests.

Times are drawn on a coarse grid near a fixed origin so that collisions that matter (a run published exactly at a
cutoff, a target hour equal to its run's publish time) happen often.
"""

from __future__ import annotations

import datetime as dt

from hypothesis import strategies as st

from windcast.selection import SelectionRequest
from windcast.snapshot import ForecastRow

ORIGIN = dt.datetime(2026, 1, 10, 0, 0, tzinfo=dt.UTC)


def at(minutes: int) -> dt.datetime:
    return ORIGIN + dt.timedelta(minutes=minutes)


# Runs publish on a 5-minute grid over ~2 days; targets are whole hours over ~3 days.
publish_minutes = st.integers(min_value=0, max_value=48 * 12).map(lambda k: 5 * k)
target_hours = st.integers(min_value=0, max_value=72)


@st.composite
def forecast_rows(draw: st.DrawFn, max_rows: int = 60) -> list[ForecastRow]:
    keys = draw(st.lists(st.tuples(publish_minutes, target_hours), max_size=max_rows, unique=True))
    return [
        ForecastRow(publish_time=at(p), start_time=at(60 * h), generation_mw=draw(st.integers(0, 25_000)))
        for p, h in keys
    ]


@st.composite
def requests(draw: st.DrawFn, max_requests: int = 30) -> list[SelectionRequest]:
    periods = draw(st.lists(st.integers(min_value=0, max_value=2 * 72), min_size=1, max_size=max_requests))
    out = []
    for k in periods:
        # Cutoffs on a 5-minute grid hit run publish times exactly with useful probability.
        cutoff = at(5 * draw(st.integers(min_value=-12, max_value=50 * 12)))
        out.append(SelectionRequest(period_start=at(30 * k), cutoff=cutoff))
    return out


shifts = st.sampled_from([0, -30])
