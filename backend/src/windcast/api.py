"""FastAPI app: a read-only view over the precomputed tables in ``data/derived``.

Nothing here calls Elexon or recomputes the analysis: the served numbers are exactly the ones CI checks against
the snapshot. Every response under ``/api/v1`` is cacheable and carries an ETag derived from the snapshot hashes,
the app version and the alignment, so a new snapshot or build invalidates caches automatically.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Awaitable, Callable
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi import Path as PathParam
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from windcast import __version__, study
from windcast import schemas as s
from windcast.config import Settings, load_settings
from windcast.selection import source_hour
from windcast.study import cutoff_key
from windcast.timeutils import HALF_HOUR, delivery_day_bounds, iso_z, parse_utc, settlement_period

API_PREFIX = "/api/v1"


class Store:
    """The derived tables for one alignment, loaded once per process."""

    def __init__(self, settings: Settings) -> None:
        derived = settings.derived_dir
        self.shift = settings.alignment_shift_minutes
        self._meta: dict[str, Any] = json.loads((derived / "meta.json").read_text())
        self._actuals: dict[str, Any] = json.loads((derived / "actuals.json").read_text())["days"]
        base = derived / f"alignment_{self.shift}"
        self._cutoffs: dict[str, dict[str, Any]] = {}
        for t in study.cutoff_grid():
            key = f"{t.hour:02d}:{t.minute:02d}"
            self._cutoffs[key] = json.loads((base / "cutoffs" / f"{cutoff_key(t)}.json").read_text())
        self._vintages: dict[str, Any] = json.loads((base / "vintages.json").read_text())
        hashes = [f["sha256"] for f in self._meta["snapshot"]]
        self.snapshot_sha256 = hashes
        self.etag = (
            '"' + hashlib.sha256(f"{__version__}|{self.shift}|{'|'.join(hashes)}".encode()).hexdigest()[:20] + '"'
        )
        self._fit = {d.isoformat() for d in study.FIT_DAYS}

    # ------------------------------------------------------------------ lookups with validation
    def table(self, cutoff: str) -> dict[str, Any]:
        try:
            return self._cutoffs[cutoff]
        except KeyError:
            allowed = ", ".join(self._cutoffs)
            raise HTTPException(422, f"cutoff must be one of {allowed} (UK time on D-1), got {cutoff!r}") from None

    def sample(self, day: str) -> str:
        return "fit" if day in self._fit else "test"

    # ------------------------------------------------------------------ views
    def meta(self) -> s.Meta:
        return s.Meta.model_validate(
            {k: v for k, v in self._meta.items() if k not in ("schema_version", "alignments_available")}
            | {"alignment_shift_minutes": self.shift}
        )

    def day(self, delivery_day: str, cutoff: str, coverage: int) -> s.DayView:
        table = self.table(cutoff)
        day = next((d for d in table["days"] if d["delivery_day"] == delivery_day), None)
        if day is None:
            first, last = self._meta["delivery_days"][0], self._meta["delivery_days"][-1]
            raise HTTPException(404, f"delivery day must be between {first} and {last}, got {delivery_day!r}")
        buffer = self._buffer(table, coverage)
        actual = self._actuals[delivery_day]
        start = parse_utc(actual["start_utc"])
        runs = [parse_utc(r) for r in day["runs_utc"]]
        periods = []
        for i, (forecast, measured) in enumerate(zip(day["forecast_mw"], actual["actual_mw"], strict=True)):
            t = start + i * HALF_HOUR
            run = runs[day["run_index"][i]]
            error = forecast - measured
            sp_date, sp = settlement_period(t)
            periods.append(
                s.Period(
                    start_utc=iso_z(t),
                    settlement_date=sp_date.isoformat(),
                    settlement_period=sp,
                    forecast_mw=forecast,
                    actual_mw=measured,
                    error_mw=error,
                    publish_time_utc=iso_z(run),
                    source_hour_utc=iso_z(source_hour(t, self.shift)),
                    lead_hours=round((t - run).total_seconds() / 3600, 2),
                    procure_for_mw=round(forecast - buffer, 1),
                    covered=error <= buffer,
                )
            )
        first, last = delivery_day_bounds(dt.date.fromisoformat(delivery_day))
        return s.DayView(
            delivery_day=delivery_day,
            sample=self.sample(delivery_day),
            cutoff_uk=cutoff,
            cutoff_utc=day["cutoff_utc"],
            window_utc=[iso_z(first), iso_z(last)],
            coverage_pct=coverage,
            buffer_mw=buffer,
            runs=[
                s.RunUsed(publish_time_utc=iso_z(r), periods=sum(1 for p in periods if p.publish_time_utc == iso_z(r)))
                for r in runs
            ],
            persistence=s.Persistence(**day["persistence"]),
            stats=s.ErrorStats(**day["stats"]),
            max_shortfall_mw=max(p.error_mw for p in periods),
            covered_share=round(sum(p.covered for p in periods) / len(periods), 4),
            periods=periods,
        )

    def _buffer(self, table: dict[str, Any], coverage: int) -> float:
        for row in table["accuracy"]["buffer"]:
            if row["target_pct"] == coverage:
                return float(row["buffer_mw"])
        allowed = ", ".join(str(r["target_pct"]) for r in table["accuracy"]["buffer"])
        raise HTTPException(422, f"coverage must be one of {allowed}, got {coverage}")

    def accuracy(self, cutoff: str) -> s.Accuracy:
        table = self.table(cutoff)
        a = table["accuracy"]
        return s.Accuracy(
            cutoff_uk=table["cutoff_uk"],
            alignment_shift_minutes=table["alignment_shift_minutes"],
            periods=table["periods"],
            lead_hours=table["lead_hours"],
            runs_used_utc=table["runs_used_utc"],
            forecast=s.ErrorStats(**a["forecast"]),
            persistence=s.ErrorStats(**a["persistence"]),
            skill_mae=a["skill_mae"],
            skill_rmse=a["skill_rmse"],
            by_lead=[s.Breakdown.model_validate(b) for b in a["by_lead"]],
            by_level=[s.Breakdown.model_validate(b) for b in a["by_level"]],
            buffer=[s.BufferRow(**b) for b in a["buffer"]],
            lag_scan=[s.LagPoint(**p) for p in a["lag_scan"]],
            days=[
                s.DaySummary(
                    delivery_day=d["delivery_day"],
                    sample=self.sample(d["delivery_day"]),
                    runs_utc=d["runs_utc"],
                    stats=s.ErrorStats(**d["stats"]),
                )
                for d in table["days"]
            ],
        )

    def vintages(self) -> s.Vintages:
        return s.Vintages.model_validate({k: v for k, v in self._vintages.items() if k != "schema_version"})


@lru_cache(maxsize=1)
def get_store() -> Store:
    return Store(load_settings())


StoreDep = Annotated[Store, Depends(get_store)]
CutoffQuery = Annotated[
    str,
    Query(
        pattern=r"^\d{2}:\d{2}$",
        description="Decision cutoff, UK clock time on the day before delivery (03:00-16:00, 30-minute steps)",
    ),
]
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": s.Problem, "description": "Unknown delivery day"}}
BAD_PARAM: dict[int | str, dict[str, Any]] = {422: {"description": "Cutoff or coverage outside the allowed values"}}

app = FastAPI(
    title="Wind at cutoff",
    version=__version__,
    summary="GB wind forecast at the day-ahead decision cutoff vs outturn, January 2026 (Elexon WINDFOR, FUELHH)",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def cache_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Conditional GET and caching for the read-only API."""
    if not request.url.path.startswith(API_PREFIX) or request.method != "GET":
        return await call_next(request)
    etag = get_store().etag
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    response = await call_next(request)
    if response.status_code == 200:
        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = "public, max-age=300, s-maxage=86400, stale-while-revalidate=86400"
    return response


@app.get("/api/health", response_model=s.Health, tags=["ops"])
def health(store: StoreDep) -> s.Health:
    return s.Health(
        status="ok", version=__version__, alignment_shift_minutes=store.shift, snapshot_sha256=store.snapshot_sha256
    )


@app.get(f"{API_PREFIX}/meta", response_model=s.Meta, tags=["data"])
def meta(store: StoreDep) -> s.Meta:
    """Study design: delivery days, selectable cutoffs, markers for the decision timeline, data provenance."""
    return store.meta()


@app.get(
    f"{API_PREFIX}/days/{{delivery_day}}", response_model=s.DayView, responses=NOT_FOUND | BAD_PARAM, tags=["data"]
)
def day_view(
    store: StoreDep,
    delivery_day: Annotated[str, PathParam(pattern=r"^\d{4}-\d{2}-\d{2}$", description="Delivery date (YYYY-MM-DD)")],
    cutoff: CutoffQuery = "09:00",
    coverage: Annotated[int, Query(description="Buffer target, % of half-hours")] = study.DEFAULT_COVERAGE,
) -> s.DayView:
    """Forecast at the cutoff vs outturn for each half-hour of one delivery day (23:00-23:00 UK)."""
    return store.day(delivery_day, cutoff, coverage)


@app.get(f"{API_PREFIX}/accuracy", response_model=s.Accuracy, responses=BAD_PARAM, tags=["data"])
def accuracy(store: StoreDep, cutoff: CutoffQuery = "09:00") -> s.Accuracy:
    """Error statistics, breakdowns, persistence skill, buffer back-test and lag scan at one cutoff."""
    return store.accuracy(cutoff)


@app.get(f"{API_PREFIX}/vintages", response_model=s.Vintages, tags=["data"])
def vintages(store: StoreDep) -> s.Vintages:
    """Errors across every forecast run, separating lead time from hour of day (cutoff-independent)."""
    return store.vintages()


def _mount_frontend(application: FastAPI, static_dir: Path | None) -> None:
    """Serve the built React app from the same origin when a build directory is configured."""
    if static_dir is None or not (static_dir / "index.html").exists():
        return
    index = static_dir / "index.html"
    application.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @application.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = (static_dir / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(static_dir.resolve()):
            return FileResponse(candidate)
        if path.startswith("api/"):
            raise HTTPException(404, "not found")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


_mount_frontend(app, load_settings().static_dir)
