"""Independent re-implementations of ``selection.select_forecasts`` used as test oracles.

* pandas ``merge_asof`` with ``allow_exact_matches=False`` (strictly before) and ``by`` = source hour.
* DuckDB ``ASOF LEFT JOIN`` with the inequality ``cutoff > publish_time``.

Neither is used to serve data: the app depends only on the standard-library implementation. Timestamps are passed
as integer epoch seconds so that neither engine's time-zone handling can affect the result.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence

import duckdb
import pandas as pd

from windcast.selection import Selection, SelectionRequest, source_hour
from windcast.snapshot import ForecastRow

UTC = dt.UTC


def _epoch(t: dt.datetime) -> int:
    return int(t.timestamp())


def _from_epoch(s: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(s, tz=UTC)


def _frames(
    rows: Iterable[ForecastRow], requests: Sequence[SelectionRequest], shift_minutes: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    forecasts = pd.DataFrame(
        [(_epoch(r.publish_time), _epoch(r.start_time), r.generation_mw) for r in rows],
        columns=["publish_s", "start_s", "generation_mw"],
    ).astype("int64")
    forecasts = forecasts[forecasts["start_s"] >= forecasts["publish_s"]]  # exclude rows before their run
    req = pd.DataFrame(
        [
            (i, _epoch(q.period_start), _epoch(q.cutoff), _epoch(source_hour(q.period_start, shift_minutes)))
            for i, q in enumerate(requests)
        ],
        columns=["idx", "period_s", "cutoff_s", "source_s"],
    ).astype("int64")
    return forecasts, req


def _to_selections(requests: Sequence[SelectionRequest], matched: pd.DataFrame) -> list[Selection | None]:
    out: list[Selection | None] = [None] * len(requests)
    columns = (matched[c].tolist() for c in ("idx", "source_s", "publish_s", "generation_mw"))
    for idx, source_s, publish_s, generation_mw in zip(*columns, strict=True):
        if pd.isna(publish_s):  # unmatched: NA from DuckDB, NaN from pandas
            continue
        i = int(idx)
        out[i] = Selection(
            period_start=requests[i].period_start,
            cutoff=requests[i].cutoff,
            publish_time=_from_epoch(int(publish_s)),
            source_start=_from_epoch(int(source_s)),
            generation_mw=int(generation_mw),
        )
    return out


def select_forecasts_pandas(
    rows: Iterable[ForecastRow], requests: Sequence[SelectionRequest], *, shift_minutes: int = 0
) -> list[Selection | None]:
    forecasts, req = _frames(rows, requests, shift_minutes)
    if req.empty:
        return []
    matched = pd.merge_asof(
        req.sort_values("cutoff_s", kind="stable"),
        forecasts.rename(columns={"start_s": "source_s"}).sort_values("publish_s", kind="stable"),
        left_on="cutoff_s",
        right_on="publish_s",
        by="source_s",
        direction="backward",
        allow_exact_matches=False,  # strictly before the cutoff
    )
    return _to_selections(requests, matched)


def select_forecasts_duckdb(
    rows: Iterable[ForecastRow], requests: Sequence[SelectionRequest], *, shift_minutes: int = 0
) -> list[Selection | None]:
    forecasts, req = _frames(rows, requests, shift_minutes)
    if req.empty:
        return []
    con = duckdb.connect()
    try:
        con.register("forecasts", forecasts)
        con.register("req", req)
        matched = con.execute(
            """
            SELECT r.idx, r.source_s, f.publish_s, f.generation_mw
            FROM req r
            ASOF LEFT JOIN forecasts f
              ON r.source_s = f.start_s AND r.cutoff_s > f.publish_s
            ORDER BY r.idx
            """
        ).df()
    finally:
        con.close()
    return _to_selections(requests, matched)
