"""API response models (the OpenAPI schema the frontend's TypeScript types are generated from).

All times are ISO-8601 UTC strings ending in ``Z`` unless the field name ends in ``_uk`` (UK clock time HH:MM).
Power is MW. Errors are forecast minus outturn: positive means wind came in below forecast (a shortfall).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ErrorStats(Model):
    n: int = Field(description="Number of half-hours")
    mean_error_mw: float = Field(description="Mean of forecast minus outturn (bias)")
    mae_mw: float
    rmse_mw: float
    p10_mw: float
    p50_mw: float
    p90_mw: float
    shortfall_share: float = Field(description="Share of half-hours where outturn was below forecast")


class Breakdown(Model):
    label: str
    lo: float
    hi: float | None
    stats: ErrorStats | None


class BufferRow(Model):
    target_pct: int = Field(description="Share of half-hours the buffer should cover")
    buffer_mw: float = Field(description="Fitted on the fit days: buy this much beyond the forecast-implied volume")
    fit_coverage: float
    test_coverage: float = Field(description="Realised coverage on the test days (out of sample)")
    test_coverage_low: float = Field(description="95% day-block bootstrap interval, lower bound")
    test_coverage_high: float
    full_month_buffer_mw: float = Field(description="Refitted on all delivery days")
    fit_periods: int
    test_periods: int


class LagPoint(Model):
    shift_minutes: int
    n: int
    mean_error_mw: float
    mae_mw: float
    rmse_mw: float
    sd_mw: float = Field(description="Error spread with the mean removed")
    correlation: float


class Marker(Model):
    time_uk: str
    label: str
    kind: str = Field(description='"gate" (auction gate closure) or "run" (WINDFOR publication slot, UTC)')
    source: str


class SnapshotFile(Model):
    name: str
    dataset: str
    file: str
    sha256: str
    rows: int
    url: str
    downloaded_utc: str


class RunsInfo(Model):
    total: int
    regular_slots_utc: list[str]
    missing: list[str]
    off_schedule: list[str]


class Meta(Model):
    app_version: str
    timezone: str
    delivery_day_convention: str
    delivery_days: list[str]
    delivery_window_utc: list[str]
    cutoffs_uk: list[str]
    default_cutoff_uk: str
    coverage_levels_pct: list[int]
    default_coverage_pct: int
    fit_days: list[str]
    test_days: list[str]
    alignment_shift_minutes: int
    chart_max_mw: int = Field(description="Highest outturn or forecast (any run) in the delivery window")
    markers: list[Marker]
    runs: RunsInfo
    snapshot: list[SnapshotFile]


class Persistence(Model):
    value_mw: int
    period_start_utc: str
    publish_time_utc: str


class RunUsed(Model):
    publish_time_utc: str
    periods: int


class Period(Model):
    start_utc: str
    settlement_date: str = Field(description="Settlement date (UK) of the half-hour")
    settlement_period: int = Field(description="Settlement period, 1-based (46-50 on clock-change days)")
    forecast_mw: int
    actual_mw: int
    error_mw: int
    publish_time_utc: str = Field(description="Run whose value is used for this half-hour")
    source_hour_utc: str = Field(description="WINDFOR startTime of the hourly value applied to this half-hour")
    lead_hours: float
    procure_for_mw: float = Field(description="Forecast minus the buffer: the wind volume the buffer plans on")
    covered: bool = Field(description="Shortfall within the buffer")


class DaySummary(Model):
    delivery_day: str
    sample: str = Field(description='"fit" or "test" for the buffer back-test')
    runs_utc: list[str]
    stats: ErrorStats


class DayView(Model):
    delivery_day: str
    sample: str
    cutoff_uk: str
    cutoff_utc: str
    window_utc: list[str]
    coverage_pct: int
    buffer_mw: float
    runs: list[RunUsed]
    persistence: Persistence
    stats: ErrorStats
    max_shortfall_mw: int
    covered_share: float
    periods: list[Period]


class Accuracy(Model):
    cutoff_uk: str
    alignment_shift_minutes: int
    periods: int
    lead_hours: list[float]
    runs_used_utc: list[str]
    forecast: ErrorStats
    persistence: ErrorStats
    skill_mae: float = Field(description="1 - MAE(forecast) / MAE(persistence)")
    skill_rmse: float
    by_lead: list[Breakdown]
    by_level: list[Breakdown]
    buffer: list[BufferRow]
    lag_scan: list[LagPoint]
    days: list[DaySummary]


class GridCell(Model):
    lead_lo: int
    hour_uk: int
    n: int
    mae_mw: float
    mean_error_mw: float


class Vintages(Model):
    alignment_shift_minutes: int
    pairs: int
    runs: int
    by_lead: list[Breakdown]
    by_hour_uk: list[Breakdown]
    by_hour_lead_range_h: list[int]
    grid: list[GridCell]
    grid_lead_bucket_h: int
    lead_effect_mw: float
    hour_effect_mw: float
    effect_leads_h: list[int]
    short_lead_lag_scan: list[LagPoint]


class Health(Model):
    status: str
    version: str
    alignment_shift_minutes: int
    snapshot_sha256: list[str]


class Problem(Model):
    detail: str
