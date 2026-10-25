"""Validation checklist: ``windcast validate`` writes ``docs/validation.md`` with pass/fail and the numbers.

Automated checks are recomputed from the snapshot and the served tables every run. Checks that need the outside
world (Elexon's website, NESO's published figure, CI, the deployed URL) read evidence saved under ``validation/``
with its provenance; none of that data is used by the app.
"""

from __future__ import annotations

import datetime as dt
import filecmp
import json
import math
import tempfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from windcast import contracts, study
from windcast.config import Settings
from windcast.evaluation import ActualIndex, day_ahead_requests, evaluate_cutoff
from windcast.precompute import precompute
from windcast.selection import ALLOWED_SHIFTS_MINUTES, SelectionRequest, is_forward_looking, select_forecasts
from windcast.snapshot import Snapshot, load_snapshot
from windcast.timeutils import HALF_HOUR, format_hhmm, iso_z, parse_utc

PASS, FAIL, EXPLAINED, PENDING = "PASS", "FAIL", "EXPLAINED", "PENDING"


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    status: str
    result: str
    method: str


def _pct(x: float, digits: int = 1) -> str:
    return f"{100 * x:.{digits}f}%"


def _load(path: Path) -> Any:
    return json.loads(path.read_text())


# --------------------------------------------------------------------------------------------- automated checks
def check_contracts(snapshot: Snapshot) -> Check:
    results = contracts.run_checks(snapshot)
    failed = [r for r in results if not r.passed]
    return Check(
        "Data contracts on the raw snapshot",
        PASS if not failed else FAIL,
        f"{len(results) - len(failed)}/{len(results)} pass"
        + ("" if not failed else ": " + "; ".join(r.name for r in failed)),
        "`windcast check`: SHA-256 vs manifest, schema, unique keys, hourly runs, contiguous settlement-consistent "
        "half-hours, window coverage",
    )


def check_period_counts(derived: Path) -> Check:
    expected_days = len(study.DELIVERY_DAYS)
    problems = []
    tables = 0
    for shift in ALLOWED_SHIFTS_MINUTES:
        for cutoff in study.cutoff_grid():
            table = _load(derived / f"alignment_{shift}" / "cutoffs" / f"{study.cutoff_key(cutoff)}.json")
            tables += 1
            days = table["days"]
            sizes = Counter(len(d["forecast_mw"]) for d in days)
            if table["periods"] != 48 * expected_days or len(days) != expected_days or set(sizes) != {48}:
                problems.append(f"{shift}/{format_hhmm(cutoff)}: {table['periods']} periods, {len(days)} days")
    actuals = _load(derived / "actuals.json")["days"]
    if len(actuals) != expected_days or any(len(d["actual_mw"]) != 48 for d in actuals.values()):
        problems.append("actuals.json incomplete")
    return Check(
        "Complete period counts",
        PASS if not problems else FAIL,
        f"{tables} served tables × {expected_days} delivery days × 48 half-hours = {48 * expected_days:,} periods "
        "each, every one with a forecast and an outturn" + (f"; problems: {problems}" if problems else ""),
        "Counts in every `data/derived` table (27 cutoffs × 2 alignments); January has no clock change",
    )


def check_no_post_cutoff(snapshot: Snapshot, derived: Path) -> Check:
    late = past = checked = 0
    served_late = 0
    for shift in ALLOWED_SHIFTS_MINUTES:
        for cutoff in study.cutoff_grid():
            requests = day_ahead_requests(study.DELIVERY_DAYS, cutoff)
            selections = select_forecasts(snapshot.forecasts, requests, shift_minutes=shift)
            rows = {(f.publish_time, f.start_time): f for f in snapshot.forecasts}
            for req, sel in zip(requests, selections, strict=True):
                assert sel is not None
                checked += 1
                late += sel.publish_time >= req.cutoff
                past += not is_forward_looking(rows[(sel.publish_time, sel.source_start)])
            table = _load(derived / f"alignment_{shift}" / "cutoffs" / f"{study.cutoff_key(cutoff)}.json")
            for day in table["days"]:
                cut = parse_utc(day["cutoff_utc"])
                served_late += sum(parse_utc(r) >= cut for r in day["runs_utc"])
                served_late += parse_utc(day["persistence"]["publish_time_utc"]) >= cut
    ok = late == past == served_late == 0
    return Check(
        "Zero post-cutoff forecasts used",
        PASS if ok else FAIL,
        f"{checked:,} selections: {late} published at or after the cutoff, {past} from rows before their run; "
        f"served tables: {served_late} runs or persistence values at or after the cutoff",
        "Re-selected from the snapshot for every cutoff and alignment, and checked in the served tables",
    )


def check_reproducible(snapshot: Snapshot, derived: Path) -> Check:
    with tempfile.TemporaryDirectory() as tmp:
        rebuilt = Path(tmp) / "derived"
        written = precompute(snapshot, rebuilt)
        differ = [
            p.relative_to(rebuilt)
            for p in written
            if not filecmp.cmp(p, derived / p.relative_to(rebuilt), shallow=False)
        ]
    return Check(
        "Served tables reproduce from the snapshot",
        PASS if not differ else FAIL,
        f"{len(written)} files rebuilt, {len(differ)} differ" + (f": {differ[:3]}" if differ else ""),
        "`windcast precompute` into a temporary directory, byte comparison with `data/derived` (also a CI step)",
    )


def check_implementations(snapshot: Snapshot) -> Check:
    try:
        from windcast.selection_asof import select_forecasts_duckdb, select_forecasts_pandas
    except ImportError:
        return Check("Three implementations agree", PENDING, "pandas/DuckDB not installed", "dev dependencies")
    mismatches = compared = 0
    for shift in ALLOWED_SHIFTS_MINUTES:
        for cutoff in study.cutoff_grid():
            reqs = day_ahead_requests(study.DELIVERY_DAYS, cutoff)
            expected = select_forecasts(snapshot.forecasts, reqs, shift_minutes=shift)
            for other in (select_forecasts_pandas, select_forecasts_duckdb):
                compared += 1
                mismatches += other(snapshot.forecasts, reqs, shift_minutes=shift) != expected
    return Check(
        "Pure Python, pandas merge_asof and DuckDB ASOF JOIN agree",
        PASS if mismatches == 0 else FAIL,
        f"{compared} comparisons of 1,488 selections, {mismatches} differ",
        "Every cutoff and alignment; Hypothesis also compares them on random inputs in the test suite",
    )


def check_golden(snapshot: Snapshot, golden: Path) -> Check:
    g = _load(golden)
    day = dt.date.fromisoformat(g["delivery_day"])
    (result,) = evaluate_cutoff(snapshot.forecasts, ActualIndex(snapshot.actuals), [day], dt.time(9, 0))
    hourly = g["hourly_forecast_0900_cutoff"]
    ok_f = [p.forecast_mw for p in result.periods] == [
        hourly[iso_z(p.period_start.replace(minute=0))] for p in result.periods
    ]
    ok_a = [p.actual_mw for p in result.periods] == g["actual_half_hourly"]
    total = sum(abs(p.error_mw) for p in result.periods)
    ok_m = total == g["day_metrics_0900_cutoff"]["sum_abs_error_mw"]
    return Check(
        "Golden day (16 Jan 2026) matches the hand check",
        PASS if ok_f and ok_a and ok_m else FAIL,
        f"48/48 forecasts {'match' if ok_f else 'DIFFER'}, 48/48 outturns {'match' if ok_a else 'DIFFER'}, "
        f"Σ|error| {total:,} MW vs {g['day_metrics_0900_cutoff']['sum_abs_error_mw']:,} by hand; runs at 8 cutoffs "
        "incl. the 15 Jan late-run fallback are asserted in `tests/test_selection_golden.py`",
        "Values read from the raw JSON with jq and summed by hand",
    )


def lag_checks(derived: Path) -> list[Check]:
    table = _load(derived / "alignment_0" / "cutoffs" / f"{study.cutoff_key(study.CUTOFF_DEFAULT)}.json")
    scan = table["accuracy"]["lag_scan"]
    short = _load(derived / "alignment_0" / "vintages.json")["short_lead_lag_scan"]
    zero = next(p for p in scan if p["shift_minutes"] == 0)
    by_mae = min(scan, key=lambda p: p["mae_mw"])
    by_rmse = min(scan, key=lambda p: p["rmse_mw"])
    by_sd = min(scan, key=lambda p: p["sd_mw"])
    short_zero = next(p for p in short if p["shift_minutes"] == 0)
    short_sd = min(short, key=lambda p: p["sd_mw"])
    gain = (zero["sd_mw"] - by_sd["sd_mw"]) / zero["sd_mw"]
    short_gain = (short_zero["sd_mw"] - short_sd["sd_mw"]) / short_zero["sd_mw"]
    as_specified = Check(
        "Lag-scan minimum at zero (as specified)",
        PASS if by_mae["shift_minutes"] == by_rmse["shift_minutes"] == by_sd["shift_minutes"] == 0 else FAIL,
        f"At the {format_hhmm(study.CUTOFF_DEFAULT)} cutoff the minimum is at {by_mae['shift_minutes']:+d} min for MAE "
        f"({by_mae['mae_mw']:,.0f} vs {zero['mae_mw']:,.0f} MW at 0), {by_rmse['shift_minutes']:+d} min for RMSE and "
        f"{by_sd['shift_minutes']:+d} min for the bias-removed spread ({by_sd['sd_mw']:,.0f} vs {zero['sd_mw']:,.0f} "
        f"MW); short-lead runs: {short_sd['shift_minutes']:+d} min",
        "Forecast for t vs outturn for t + shift, −120..+120 min in 30-minute steps (`docs/analysis.md`)",
    )
    tolerance = Check(
        "No gross misalignment (proposed criterion)",
        PASS
        if abs(by_sd["shift_minutes"]) <= 60 and abs(short_sd["shift_minutes"]) <= 60 and max(gain, short_gain) < 0.02
        else FAIL,
        f"Bias-removed optimum {by_sd['shift_minutes']:+d} min day-ahead and {short_sd['shift_minutes']:+d} min at short "
        f"lead, within ±60 min of zero, and shifting improves the spread by at most {max(gain, short_gain):.1%} "
        f"({gain:.1%}, {short_gain:.1%}). Timestamps themselves are confirmed by Elexon's settlement-period labels "
        "(check 10)",
        "Proposed replacement for check 7: the curve is nearly flat between −90 and −30 min, so the scan cannot "
        "resolve shifts under an hour; see the flagged problem in the README",
    )
    return [as_specified, tolerance]


def check_persistence(derived: Path) -> Check:
    skills = {}
    for cutoff in study.cutoff_grid():
        t = _load(derived / "alignment_0" / "cutoffs" / f"{study.cutoff_key(cutoff)}.json")
        skills[format_hhmm(cutoff)] = t["accuracy"]["skill_mae"]
    default = skills[format_hhmm(study.CUTOFF_DEFAULT)]
    worst = min(skills, key=lambda k: skills[k])
    t = _load(derived / "alignment_0" / "cutoffs" / f"{study.cutoff_key(study.CUTOFF_DEFAULT)}.json")["accuracy"]
    return Check(
        "Forecast beats persistence",
        PASS if min(skills.values()) > 0 else FAIL,
        f"MAE {t['forecast']['mae_mw']:,.0f} vs {t['persistence']['mae_mw']:,.0f} MW at {format_hhmm(study.CUTOFF_DEFAULT)} "
        f"(skill {_pct(default)}); lowest skill over all 27 cutoffs {_pct(skills[worst])} at {worst}",
        "Persistence = last outturn published strictly before the cutoff, held for the delivery day",
    )


# --------------------------------------------------------------------------------------------- external evidence
def check_elexon_readback(derived: Path, validation_dir: Path) -> tuple[Check, list[dict[str, Any]]]:
    folder = validation_dir / "elexon_readback"
    sample = _load(folder / "sample.json")
    readback = {r["period"]: r for r in _load(folder / "readback.json")}
    actuals = _load(derived / "actuals.json")["days"]
    table = _load(derived / f"alignment_{sample['alignment_shift_minutes']}" / "cutoffs" / "0900.json")
    days = {d["delivery_day"]: d for d in table["days"]}
    rows = []
    for p in sample["periods"]:
        day = days[p["delivery_day"]]
        start = parse_utc(actuals[p["delivery_day"]]["start_utc"])
        i = int((parse_utc(p["period_start_utc"]) - start) / HALF_HOUR)
        app_forecast, app_actual = day["forecast_mw"][i], actuals[p["delivery_day"]]["actual_mw"][i]
        app_run = day["runs_utc"][day["run_index"][i]]
        rb = readback[p["period_start_utc"]]
        el_forecast = rb["forecast"][0]["generation"] if len(rb["forecast"]) == 1 else None
        el_actual = rb["fuelhh"][0]["generation"] if len(rb["fuelhh"]) == 1 else None
        hour = parse_utc(p["hour_label_utc"])
        sp_expected = int((hour - parse_utc(p["period_start_utc"]).replace(hour=0, minute=0)) / HALF_HOUR) + 1
        sp_ok = bool(rb["forecast"]) and rb["forecast"][0]["settlementPeriod"] == sp_expected
        rows.append(
            {
                "period": p["period_start_utc"],
                "run": app_run,
                "app_forecast": app_forecast,
                "elexon_forecast": el_forecast,
                "app_actual": app_actual,
                "elexon_actual": el_actual,
                "forecast_sp": rb["forecast"][0]["settlementPeriod"] if rb["forecast"] else None,
                "match": app_forecast == el_forecast and app_actual == el_actual and app_run == rb["run"] and sp_ok,
            }
        )
    matched = sum(r["match"] for r in rows)
    check = Check(
        "20 random periods match Elexon",
        PASS if matched == len(rows) == 20 else FAIL,
        f"{matched}/{len(rows)} periods: forecast (run in use), outturn and Elexon's settlement-period label all match",
        "Seeded random sample (seed 20261025) at the 09:00 cutoff, read back from bmrs.elexon.co.uk's data "
        "endpoints (forecast history for the run; FUELHH as its 30-minute export returns it); see table below",
    )
    return check, rows


@dataclass(frozen=True, slots=True)
class NesoComparison:
    periods: int
    capacity_min: float
    capacity_max: float
    capacity_mean: float
    runs: dict[str, int]
    windfor_ape: float
    neso_ape: float
    windfor_minus_neso_mw: float
    windfor_minus_neso_pct: float
    windfor_bias_mw: float
    neso_bias_mw: float
    windfor_ape_debiased: float
    neso_ape_debiased: float
    reloaded_days: int
    off_window_days: list[str]
    windfor_ape_original_days: float
    neso_ape_original_days: float
    published_pct: float
    published_alt_pct: float


def neso_comparison(snapshot: Snapshot, validation_dir: Path) -> NesoComparison:
    folder = validation_dir / "neso"
    manifest = _load(folder / "manifest.json")
    records = _load(folder / manifest["responses"][0]["file"])["result"]["records"]
    jan = [r for r in records if r["Date"].startswith("2026-01")]
    actuals = ActualIndex(snapshot.actuals)

    def utc(s: str) -> dt.datetime:
        return dt.datetime.fromisoformat(s).replace(tzinfo=dt.UTC)

    requests = []
    for r in jan:
        day = dt.date.fromisoformat(r["Date"])
        # NESO scores the day-ahead forecast published between 09:00 and 10:00 (UK = UTC in January) on D-1.
        requests.append(
            SelectionRequest(
                utc(r["Datetime_GMT"]), dt.datetime.combine(day - dt.timedelta(days=1), dt.time(10, 0), tzinfo=dt.UTC)
            )
        )
    selections = select_forecasts(snapshot.forecasts, requests)
    windfor_err, neso_err, caps, diffs, original = [], [], [], [], []
    runs: Counter[str] = Counter()
    for r, sel in zip(jan, selections, strict=True):
        assert sel is not None
        if not dt.time(9, 0) <= sel.publish_time.time() < dt.time(10, 0):
            raise ValueError(f"run {sel.publish_time} is outside 09:00-10:00")
        runs[f"{sel.publish_time:%H:%M}"] += 1
        a = actuals.value(sel.period_start)
        assert a is not None
        cap, neso = float(r["Capacity"]), float(r["Incentive_forecast"])
        windfor_err.append(sel.generation_mw - a)
        neso_err.append(neso - a)
        caps.append(cap)
        diffs.append(sel.generation_mw - neso)
        stamp = utc(r["Forecast_Timestamp"])
        original.append(stamp.date() == dt.date.fromisoformat(r["Date"]) - dt.timedelta(days=1))
    by_day_stamp = {r["Date"]: utc(r["Forecast_Timestamp"]) for r in jan}
    off_window = sorted(
        d
        for d, s in by_day_stamp.items()
        if s.date() == dt.date.fromisoformat(d) - dt.timedelta(days=1)
        and not dt.time(9, 0) <= s.time() < dt.time(10, 0)
    )

    def ape(errors: Sequence[float], mask: Sequence[bool] | None = None) -> float:
        pairs = [(e, c) for i, (e, c) in enumerate(zip(errors, caps, strict=True)) if mask is None or mask[i]]
        return math.fsum(abs(e) / c for e, c in pairs) / len(pairs)

    wb = math.fsum(windfor_err) / len(windfor_err)
    nb = math.fsum(neso_err) / len(neso_err)
    neso_mean = math.fsum(float(r["Incentive_forecast"]) for r in jan) / len(jan)
    published = manifest["published_metric"]
    return NesoComparison(
        periods=len(jan),
        capacity_min=min(caps),
        capacity_max=max(caps),
        capacity_mean=math.fsum(caps) / len(caps),
        runs=dict(runs),
        windfor_ape=ape(windfor_err),
        neso_ape=ape(neso_err),
        windfor_minus_neso_mw=math.fsum(diffs) / len(diffs),
        windfor_minus_neso_pct=math.fsum(diffs) / len(diffs) / neso_mean,
        windfor_bias_mw=wb,
        neso_bias_mw=nb,
        windfor_ape_debiased=ape([e - wb for e in windfor_err]),
        neso_ape_debiased=ape([e - nb for e in neso_err]),
        reloaded_days=sum(
            1 for d, s in by_day_stamp.items() if s.date() != dt.date.fromisoformat(d) - dt.timedelta(days=1)
        ),
        off_window_days=off_window,
        windfor_ape_original_days=ape(windfor_err, original),
        neso_ape_original_days=ape(neso_err, original),
        published_pct=float(published[0]["value_pct"]) / 100,
        published_alt_pct=float(published[1]["value_pct"]) / 100,
    )


def check_neso(c: NesoComparison) -> Check:
    gap = c.windfor_ape - c.published_pct
    product = c.windfor_ape - c.neso_ape
    rest = c.neso_ape - c.published_pct
    return Check(
        "January error on NESO's definition vs NESO's published 4.99% (4.9% in later reports)",
        EXPLAINED,
        f"WINDFOR run published 09:00–10:00 on D−1 ({', '.join(c.runs)} UTC), per half-hour, % of capacity "
        f"({c.capacity_min:,.0f}–{c.capacity_max:,.0f} MW, NESO): **{_pct(c.windfor_ape, 2)}**, {100 * gap:.2f} pp above "
        f"NESO. {100 * product:.2f} pp is the forecast product: NESO's own incentive forecast scores "
        f"{_pct(c.neso_ape, 2)} against the same FUELHH outturn. The remaining {100 * rest:.2f} pp matches what NESO's "
        "metric removes and these datasets cannot: sites with a bid-offer acceptance (curtailment) or withdrawn "
        "availability, and settlement-metered outturn (unverified)",
        "`validation/neso` (NESO Data Portal archive + incentive reports); details below. Not used by the app",
    )


def check_manual(validation_dir: Path) -> list[Check]:
    path = validation_dir / "manual_checks.json"
    if not path.exists():
        return []
    return [Check(m["name"], m["status"], m["result"], m["method"]) for m in _load(path)["checks"]]


# --------------------------------------------------------------------------------------------- document
def build(settings: Settings, validation_dir: Path) -> tuple[str, bool]:
    snapshot = load_snapshot(settings.snapshot_dir)
    derived = settings.derived_dir
    golden = Path(__file__).resolve().parents[2] / "tests" / "golden" / "delivery_2026-01-16.json"
    readback_check, readback_rows = check_elexon_readback(derived, validation_dir)
    neso = neso_comparison(snapshot, validation_dir)
    checks = [
        check_contracts(snapshot),
        check_period_counts(derived),
        check_no_post_cutoff(snapshot, derived),
        check_reproducible(snapshot, derived),
        check_implementations(snapshot),
        *([check_golden(snapshot, golden)] if golden.exists() else []),
        *lag_checks(derived),
        check_persistence(derived),
        readback_check,
        check_neso(neso),
        *check_manual(validation_dir),
    ]
    automated_ok = all(c.status != FAIL for c in checks if c.name != "Lag-scan minimum at zero (as specified)")

    out: list[str] = []
    w = out.append
    w("# Validation checklist")
    w("")
    counts = Counter(c.status for c in checks)
    w(
        f"_Generated by `windcast validate`. {counts[PASS]} pass, {counts[FAIL]} fail, {counts[EXPLAINED]} explained, "
        f"{counts[PENDING]} pending. External evidence lives in `validation/` with its provenance and is never read by "
        "the app._"
    )
    w("")
    w("| # | Check | Status | Result | How |")
    w("| ---: | --- | --- | --- | --- |")
    for i, c in enumerate(checks, 1):
        w(f"| {i} | {c.name} | **{c.status}** | {c.result} | {c.method} |")
    w("")
    w("## 20 random periods vs Elexon")
    w("")
    w(
        "| Period (UTC) | Run used (UTC) | App forecast | Elexon forecast | SP label | App outturn | Elexon outturn | Match |"
    )
    w("| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |")
    for r in readback_rows:
        w(
            f"| {r['period']} | {r['run']} | {r['app_forecast']:,} | {r['elexon_forecast']:,} | {r['forecast_sp']} | "
            f"{r['app_actual']:,} | {r['elexon_actual']:,} | {'yes' if r['match'] else '**no**'} |"
        )
    w("")
    w(
        "SP label is the settlement period Elexon's forecast-history endpoint assigns to the hourly value used: always "
        "the period starting at the value's startTime, which the hour-start alignment follows (for a :30 period the "
        "label is one period earlier)."
    )
    w("")
    w("## NESO comparison")
    w("")
    w(
        "[NESO's metric](https://www.neso.energy/document/377601/download): average absolute error between the "
        "day-ahead forecast published between 09:00 and 10:00 and post-event settlement-metered outturn, per "
        "half-hour, as a percentage of capacity for BM wind units, excluding sites with a bid-offer acceptance or that "
        "withdrew availability. January 2026: **4.99%** in NESO's January 2026 report; the previous-year row of the "
        "[2026-27 reports](https://www.neso.energy/document/382306/download) shows 4.9%."
    )
    w("")
    w("| Quantity | Value |")
    w("| --- | ---: |")
    w(f"| Half-hours (settlement days 1–31 Jan) | {neso.periods:,} |")
    w(
        f"| Capacity, BM wind (NESO `Capacity` column) | {neso.capacity_min:,.0f}–{neso.capacity_max:,.0f} MW "
        f"(mean {neso.capacity_mean:,.0f}) |"
    )
    w(f"| WINDFOR 09:30 run vs FUELHH, % of capacity | {_pct(neso.windfor_ape, 2)} |")
    w(f"| NESO incentive forecast vs FUELHH, % of capacity | {_pct(neso.neso_ape, 2)} |")
    w(f"| NESO published (exclusions applied, settlement metering) | {_pct(neso.published_pct, 2)} |")
    w(
        f"| WINDFOR minus NESO incentive forecast, mean | {neso.windfor_minus_neso_mw:+,.0f} MW "
        f"({_pct(neso.windfor_minus_neso_pct)} of NESO's mean) |"
    )
    w(
        f"| Mean error vs FUELHH: WINDFOR / NESO incentive | {neso.windfor_bias_mw:+,.0f} / {neso.neso_bias_mw:+,.0f} MW |"
    )
    w(
        f"| Diagnostic only: % of capacity after removing each forecast's January mean error | "
        f"{_pct(neso.windfor_ape_debiased, 2)} / {_pct(neso.neso_ape_debiased, 2)} |"
    )
    w("")
    w(
        f"Caveats. {neso.reloaded_days} of 31 January days in NESO's archive carry a forecast timestamp of 4 June 2026 "
        "(the rows were reloaded), so they cannot be confirmed as the 09:00–10:00 forecast; on the other days the "
        f"comparison gives {_pct(neso.windfor_ape_original_days, 2)} (WINDFOR) and {_pct(neso.neso_ape_original_days, 2)} "
        f"(NESO). NESO's forecast for {', '.join(neso.off_window_days) or 'no day'} was timestamped outside 09:00–10:00, "
        "matching the IT issue NESO reports for 27–28 January. FUELHH is operational metering; NESO uses settlement "
        "metering after the initial settlement run."
    )
    w("")
    return "\n".join(out) + "\n", automated_ok


def write_validation(settings: Settings, validation_dir: Path, out: Path) -> bool:
    text, ok = build(settings, validation_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return ok
