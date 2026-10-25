"""Build ``data/derived``: every table the API serves, computed from the raw snapshot.

Layout (one directory per alignment so the 30-minute shift is a runtime switch, not a rebuild)::

    derived/
      meta.json                      study design, provenance, markers (alignment-independent)
      actuals.json                   outturn per delivery day (alignment-independent)
      alignment_0/cutoffs/0900.json  per-cutoff day series and accuracy, 03:00..16:00
      alignment_0/vintages.json      all-vintage analysis (cutoff-independent)
      alignment_-30/...

Output is deterministic (fixed bootstrap seed, fixed rounding), so CI can rebuild it and fail on any difference.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from windcast import __version__, analysis, contracts, study
from windcast.evaluation import ActualIndex, DayResult, all_periods, evaluate_cutoff
from windcast.metrics import ErrorStats, error_stats
from windcast.selection import ALLOWED_SHIFTS_MINUTES
from windcast.snapshot import Snapshot
from windcast.timeutils import delivery_day_bounds, delivery_day_periods, format_hhmm, iso_z

SCHEMA_VERSION = 1


def _r(x: float, digits: int = 1) -> float:
    return round(float(x), digits)


def stats_json(s: ErrorStats | None) -> dict[str, Any] | None:
    if s is None:
        return None
    return {
        "n": s.n,
        "mean_error_mw": _r(s.mean_error_mw),
        "mae_mw": _r(s.mae_mw),
        "rmse_mw": _r(s.rmse_mw),
        "p10_mw": _r(s.p10_mw),
        "p50_mw": _r(s.p50_mw),
        "p90_mw": _r(s.p90_mw),
        "shortfall_share": _r(s.shortfall_share, 4),
    }


def _breakdown_json(rows: Sequence[analysis.Breakdown]) -> list[dict[str, Any]]:
    return [{"label": b.label, "lo": b.lo, "hi": b.hi, "stats": stats_json(b.stats)} for b in rows]


def _lag_json(points: Sequence[analysis.LagPoint]) -> list[dict[str, Any]]:
    return [
        {
            "shift_minutes": p.shift_minutes,
            "n": p.n,
            "mean_error_mw": _r(p.mean_error_mw),
            "mae_mw": _r(p.mae_mw),
            "rmse_mw": _r(p.rmse_mw),
            "sd_mw": _r(p.sd_mw),
            "correlation": _r(p.correlation, 5),
        }
        for p in points
    ]


def _day_json(day: DayResult) -> dict[str, Any]:
    runs = list(day.runs)
    run_index = {r: i for i, r in enumerate(runs)}
    return {
        "delivery_day": day.delivery_day.isoformat(),
        "cutoff_utc": iso_z(day.cutoff),
        "runs_utc": [iso_z(r) for r in runs],
        "run_index": [run_index[p.publish_time] for p in day.periods],
        "forecast_mw": [p.forecast_mw for p in day.periods],
        "persistence": {
            "value_mw": day.persistence.value_mw,
            "period_start_utc": iso_z(day.persistence.period_start),
            "publish_time_utc": iso_z(day.persistence.publish_time),
        },
        "stats": stats_json(error_stats(p.error_mw for p in day.periods)),
    }


def cutoff_table(
    snapshot: Snapshot, actuals: ActualIndex, cutoff: dt.time, shift_minutes: int
) -> tuple[dict[str, Any], list[DayResult]]:
    days = evaluate_cutoff(snapshot.forecasts, actuals, study.DELIVERY_DAYS, cutoff, shift_minutes=shift_minutes)
    periods = all_periods(days)
    skill = analysis.persistence_skill(periods)
    buffers = analysis.buffer_backtest(
        periods,
        study.FIT_DAYS,
        study.TEST_DAYS,
        study.COVERAGE_LEVELS,
        resamples=study.BOOTSTRAP_RESAMPLES,
        seed=study.BOOTSTRAP_SEED,
    )
    leads = [p.lead_hours for p in periods]
    table = {
        "schema_version": SCHEMA_VERSION,
        "cutoff_uk": format_hhmm(cutoff),
        "alignment_shift_minutes": shift_minutes,
        "periods": len(periods),
        "lead_hours": [_r(min(leads), 2), _r(max(leads), 2)],
        "runs_used_utc": sorted({iso_z(r) for d in days for r in d.runs}),
        "accuracy": {
            "forecast": stats_json(skill.forecast),
            "persistence": stats_json(skill.persistence),
            "skill_mae": _r(skill.mae_skill, 4),
            "skill_rmse": _r(skill.rmse_skill, 4),
            "by_lead": _breakdown_json(
                [b for b in analysis.breakdown(periods, "lead", study.LEAD_BUCKETS_H, "h") if b.stats]
            ),
            "by_level": _breakdown_json(analysis.breakdown(periods, "level", study.LEVEL_BANDS_MW, "GW")),
            "buffer": [
                {
                    "target_pct": b.target,
                    "buffer_mw": _r(b.buffer_mw),
                    "fit_coverage": _r(b.fit_coverage, 4),
                    "test_coverage": _r(b.test_coverage, 4),
                    "test_coverage_low": _r(b.test_coverage_low, 4),
                    "test_coverage_high": _r(b.test_coverage_high, 4),
                    "full_month_buffer_mw": _r(b.full_month_buffer_mw),
                    "fit_periods": b.fit_periods,
                    "test_periods": b.test_periods,
                }
                for b in buffers
            ],
            "lag_scan": _lag_json(analysis.lag_scan(periods, actuals, study.LAG_SHIFTS_MINUTES)),
        },
        "days": [_day_json(d) for d in days],
    }
    return table, days


def vintages_table(snapshot: Snapshot, actuals: ActualIndex, shift_minutes: int) -> dict[str, Any]:
    pairs = analysis.vintage_pairs(snapshot.forecasts, actuals, study.DELIVERY_DAYS, shift_minutes=shift_minutes)
    v = analysis.summarise_vintages(
        pairs, actuals, study.VINTAGE_LEAD_BUCKETS_H, study.LEAD_BUCKETS_H, study.LAG_SHIFTS_MINUTES
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "alignment_shift_minutes": shift_minutes,
        "pairs": v.pairs,
        "runs": v.runs,
        "by_lead": _breakdown_json([b for b in v.by_lead if b.stats]),
        "by_hour_uk": _breakdown_json(v.by_hour),
        "by_hour_lead_range_h": [12, 36],
        "grid": [
            {
                "lead_lo": c.lead_lo,
                "hour_uk": c.hour,
                "n": c.n,
                "mae_mw": _r(c.mae_mw),
                "mean_error_mw": _r(c.mean_error_mw),
            }
            for c in v.grid
        ],
        "grid_lead_bucket_h": 6,
        "lead_effect_mw": _r(v.lead_effect_mw),
        "hour_effect_mw": _r(v.hour_effect_mw),
        "effect_leads_h": list(v.effect_leads_h),
        "short_lead_lag_scan": _lag_json(v.short_lead_lag_scan),
    }


def actuals_table(actuals: ActualIndex) -> dict[str, Any]:
    days = {}
    for d in study.DELIVERY_DAYS:
        periods = delivery_day_periods(d)
        values = [actuals.value(p) for p in periods]
        if any(v is None for v in values):
            raise ValueError(f"missing outturn on delivery day {d}")
        days[d.isoformat()] = {"start_utc": iso_z(periods[0]), "actual_mw": values}
    return {"schema_version": SCHEMA_VERSION, "days": days}


def meta_table(snapshot: Snapshot) -> dict[str, Any]:
    cadence = contracts.run_cadence(snapshot)
    first, _ = delivery_day_bounds(study.FIRST_DELIVERY_DAY)
    _, last = delivery_day_bounds(study.LAST_DELIVERY_DAY)
    markers = [
        {"time_uk": m.time_uk, "label": m.label, "kind": m.kind, "source": m.source} for m in study.GATE_CLOSURES
    ]
    markers += [
        {"time_uk": slot, "label": f"WINDFOR run {slot} UTC", "kind": "run", "source": "data"}
        for slot in cadence.regular_slots_utc
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "app_version": __version__,
        "timezone": "Europe/London",
        "delivery_day_convention": "23:00-23:00 UK (Nord Pool GB)",
        "delivery_days": [d.isoformat() for d in study.DELIVERY_DAYS],
        "delivery_window_utc": [iso_z(first), iso_z(last)],
        "cutoffs_uk": [format_hhmm(t) for t in study.cutoff_grid()],
        "default_cutoff_uk": format_hhmm(study.CUTOFF_DEFAULT),
        "coverage_levels_pct": list(study.COVERAGE_LEVELS),
        "default_coverage_pct": study.DEFAULT_COVERAGE,
        "fit_days": [study.FIT_DAYS[0].isoformat(), study.FIT_DAYS[-1].isoformat()],
        "test_days": [study.TEST_DAYS[0].isoformat(), study.TEST_DAYS[-1].isoformat()],
        "alignments_available": list(ALLOWED_SHIFTS_MINUTES),
        "markers": sorted(markers, key=lambda m: m["time_uk"]),
        "runs": {
            "total": cadence.runs,
            "regular_slots_utc": list(cadence.regular_slots_utc),
            "missing": list(cadence.missing),
            "off_schedule": list(cadence.off_schedule),
        },
        "snapshot": [
            {
                "name": f.name,
                "dataset": f.dataset,
                "file": f.file,
                "sha256": f.sha256,
                "rows": f.rows,
                "url": f.url,
                "downloaded_utc": f.requested_at_utc,
            }
            for f in snapshot.files
        ],
    }


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")


def precompute(snapshot: Snapshot, out: Path) -> list[Path]:
    """Write every derived table under ``out`` (replacing it) and return the files written."""
    failed = [c for c in contracts.run_checks(snapshot) if not c.passed]
    if failed:
        raise RuntimeError("data contracts failed: " + "; ".join(f"{c.name}: {c.detail}" for c in failed))
    if out.exists():
        shutil.rmtree(out)
    actuals = ActualIndex(snapshot.actuals)
    written = []
    for name, obj in (("meta.json", meta_table(snapshot)), ("actuals.json", actuals_table(actuals))):
        _write(out / name, obj)
        written.append(out / name)
    for shift in ALLOWED_SHIFTS_MINUTES:
        base = out / f"alignment_{shift}"
        for cutoff in study.cutoff_grid():
            table, _ = cutoff_table(snapshot, actuals, cutoff, shift)
            path = base / "cutoffs" / f"{study.cutoff_key(cutoff)}.json"
            _write(path, table)
            written.append(path)
        _write(base / "vintages.json", vintages_table(snapshot, actuals, shift))
        written.append(base / "vintages.json")
    return written
