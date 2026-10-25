"""Data contracts on the raw snapshot. ``windcast check`` and the Docker build fail if any contract fails.

Each check returns a ``CheckResult`` with the number it measured, so a failure says what was wrong, not just
that something was.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import itertools
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from windcast import study
from windcast.selection import is_forward_looking
from windcast.snapshot import Snapshot
from windcast.timeutils import HALF_HOUR, HOUR, LONDON, cutoff_instant, delivery_day_bounds

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
WINDFOR_FIELDS = frozenset({"dataset", "publishTime", "startTime", "generation"})
FUELHH_FIELDS = frozenset(
    {"dataset", "publishTime", "startTime", "settlementDate", "settlementPeriod", "fuelType", "generation"}
)
MAX_PLAUSIBLE_MW = 40_000  # well above GB metered wind capacity; catches unit or parsing errors
MIN_RUN_HORIZON_H = 46  # a run must reach at least this far ahead to cover the next delivery day


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def _result(name: str, failures: list[str], ok_detail: str) -> CheckResult:
    if failures:
        shown = "; ".join(failures[:5]) + (f"; … {len(failures) - 5} more" if len(failures) > 5 else "")
        return CheckResult(name, False, shown)
    return CheckResult(name, True, ok_detail)


def check_manifest(s: Snapshot) -> CheckResult:
    failures = []
    for entry in s.files:
        body = (s.directory / entry.file).read_bytes()
        if hashlib.sha256(body).hexdigest() != entry.sha256:
            failures.append(f"{entry.file}: SHA-256 mismatch")
        if len(body) != entry.bytes:
            failures.append(f"{entry.file}: {len(body)} bytes, manifest says {entry.bytes}")
    rows = {"windfor": len(s.raw_windfor), "fuelhh_wind": len(s.raw_fuelhh)}
    for entry in s.files:
        if rows.get(entry.name) != entry.rows:
            failures.append(f"{entry.name}: {rows.get(entry.name)} rows, manifest says {entry.rows}")
    return _result("manifest hashes and row counts", failures, f"{len(s.files)} files match SHA-256, bytes and rows")


def _schema_failures(raw: list[dict[str, Any]], fields: frozenset[str], dataset: str) -> list[str]:
    failures = []
    for i, r in enumerate(raw):
        if set(r) != fields:
            failures.append(f"row {i}: fields {sorted(r)}")
            continue
        if r["dataset"] != dataset:
            failures.append(f"row {i}: dataset {r['dataset']!r}")
        for key in ("publishTime", "startTime"):
            if not isinstance(r[key], str) or not ISO_Z.match(r[key]):
                failures.append(f"row {i}: {key} {r[key]!r} is not ISO-8601 UTC")
        g = r["generation"]
        if not isinstance(g, int) or isinstance(g, bool) or not 0 <= g <= MAX_PLAUSIBLE_MW:
            failures.append(f"row {i}: generation {g!r}")
    return failures


def check_windfor_schema(s: Snapshot) -> CheckResult:
    return _result(
        "WINDFOR schema",
        _schema_failures(s.raw_windfor, WINDFOR_FIELDS, "WINDFOR"),
        f"{len(s.raw_windfor):,} rows: 4 fields, UTC 'Z' timestamps, integer MW in 0..{MAX_PLAUSIBLE_MW:,}",
    )


def check_fuelhh_schema(s: Snapshot) -> CheckResult:
    failures = _schema_failures(s.raw_fuelhh, FUELHH_FIELDS, "FUELHH")
    for i, r in enumerate(s.raw_fuelhh):
        if r.get("fuelType") != "WIND":
            failures.append(f"row {i}: fuelType {r.get('fuelType')!r}")
        sp = r.get("settlementPeriod")
        if not isinstance(sp, int) or not 1 <= sp <= 50:
            failures.append(f"row {i}: settlementPeriod {sp!r}")
    return _result(
        "FUELHH schema",
        failures,
        f"{len(s.raw_fuelhh):,} rows: fuelType WIND, settlement periods 1..50, integer MW",
    )


def check_windfor_keys(s: Snapshot) -> CheckResult:
    counts = Counter((f.publish_time, f.start_time) for f in s.forecasts)
    dupes = [f"run {p.isoformat()} hour {t.isoformat()} x{n}" for (p, t), n in counts.items() if n > 1]
    return _result("WINDFOR unique (publishTime, startTime)", dupes, f"{len(counts):,} unique keys, no duplicates")


def check_windfor_runs(s: Snapshot) -> CheckResult:
    """Hourly, contiguous targets on the hour, reaching at least two days ahead."""
    runs: dict[dt.datetime, list[dt.datetime]] = defaultdict(list)
    for f in s.forecasts:
        runs[f.publish_time].append(f.start_time)
    failures = []
    for publish, targets in sorted(runs.items()):
        targets.sort()
        if any(t.minute or t.second for t in targets):
            failures.append(f"run {publish.isoformat()}: target not on the hour")
        if any(b - a != HOUR for a, b in itertools.pairwise(targets)):
            failures.append(f"run {publish.isoformat()}: gap or overlap in hourly targets")
        if targets[-1] - publish < dt.timedelta(hours=MIN_RUN_HORIZON_H):
            failures.append(f"run {publish.isoformat()}: horizon only {(targets[-1] - publish) / HOUR:.1f} h")
    return _result(
        "WINDFOR runs hourly and complete",
        failures,
        f"{len(runs)} runs, every one hourly and contiguous, reaching ≥{MIN_RUN_HORIZON_H} h ahead",
    )


def check_fuelhh_periods(s: Snapshot) -> CheckResult:
    """Unique, contiguous half-hours; settlement date and period consistent with startTime in UK time."""
    failures = []
    starts = sorted(a.start_time for a in s.actuals)
    if len(set(starts)) != len(starts):
        failures.append("duplicate startTime")
    keys = Counter((a.settlement_date, a.settlement_period) for a in s.actuals)
    failures += [f"duplicate settlement key {k}" for k, n in keys.items() if n > 1]
    failures += [f"gap after {a.isoformat()}" for a, b in itertools.pairwise(starts) if b - a != HALF_HOUR]
    for a in s.actuals:
        midnight = dt.datetime.combine(a.settlement_date, dt.time(0), tzinfo=LONDON).astimezone(dt.UTC)
        if midnight + (a.settlement_period - 1) * HALF_HOUR != a.start_time:
            failures.append(f"{a.start_time.isoformat()} is not SP {a.settlement_period} of {a.settlement_date}")
        if a.publish_time < a.start_time + HALF_HOUR:
            failures.append(f"{a.start_time.isoformat()} published before its period ended")
    return _result(
        "FUELHH periods contiguous and settlement-consistent",
        failures,
        f"{len(starts):,} half-hours {starts[0]:%d %b %H:%M}–{starts[-1]:%d %b %H:%M} UTC, no gaps, "
        "startTime = settlement date + (SP−1)×30 min, published after period end",
    )


def check_window_coverage(s: Snapshot) -> CheckResult:
    """The snapshot spans every run and outturn the study can ask for, with room for the ±2 h lag scan."""
    failures = []
    first_start, _ = delivery_day_bounds(study.FIRST_DELIVERY_DAY)
    _, last_end = delivery_day_bounds(study.LAST_DELIVERY_DAY)
    earliest_cutoff = cutoff_instant(study.FIRST_DELIVERY_DAY, study.CUTOFF_MIN)
    latest_cutoff = cutoff_instant(study.LAST_DELIVERY_DAY, study.CUTOFF_MAX)
    lag = dt.timedelta(minutes=max(abs(m) for m in study.LAG_SHIFTS_MINUTES))
    starts = {a.start_time for a in s.actuals}
    need_from = min(first_start - lag, earliest_cutoff - dt.timedelta(hours=6))
    t = need_from
    while t < last_end + lag:
        if t not in starts:
            failures.append(f"no outturn for {t.isoformat()}")
        t += HALF_HOUR
    publishes = sorted({f.publish_time for f in s.forecasts})
    if not any(p < earliest_cutoff for p in publishes):
        failures.append(f"no run before the earliest cutoff {earliest_cutoff.isoformat()}")
    if not any(p >= latest_cutoff - dt.timedelta(hours=1) for p in publishes):
        failures.append(f"no run near the latest cutoff {latest_cutoff.isoformat()}")
    if publishes[-1] < last_end - dt.timedelta(hours=6):
        failures.append("runs stop before the end of the delivery window, so the vintage analysis is incomplete")
    return _result(
        "snapshot covers the study window",
        failures,
        f"outturn {need_from:%d %b %H:%M}–{last_end + lag:%d %b %H:%M} UTC present; "
        f"runs {publishes[0]:%d %b %H:%M}–{publishes[-1]:%d %b %H:%M} UTC",
    )


def check_past_rows(s: Snapshot) -> CheckResult:
    """Rows targeting hours before their publish time exist and are excluded; report how many."""
    past = sum(1 for f in s.forecasts if not is_forward_looking(f))
    return CheckResult(
        "WINDFOR rows before publishTime excluded",
        True,
        f"{past:,} of {len(s.forecasts):,} rows ({past / len(s.forecasts):.1%}) target an hour before their run; "
        "never selected",
    )


CHECKS: tuple[Callable[[Snapshot], CheckResult], ...] = (
    check_manifest,
    check_windfor_schema,
    check_fuelhh_schema,
    check_windfor_keys,
    check_windfor_runs,
    check_fuelhh_periods,
    check_window_coverage,
    check_past_rows,
)


def run_checks(s: Snapshot) -> list[CheckResult]:
    return [check(s) for check in CHECKS]


@dataclass(frozen=True, slots=True)
class RunCadence:
    runs: int
    days: int
    per_day: dict[int, int]  # runs per UTC day -> number of days
    regular_slots_utc: tuple[str, ...]
    missing: tuple[str, ...]
    off_schedule: tuple[str, ...]


def run_cadence(s: Snapshot) -> RunCadence:
    """Publication pattern of WINDFOR runs (informational: deviations are expected and handled by the rule)."""
    publishes = sorted({f.publish_time for f in s.forecasts})
    by_day: dict[dt.date, set[str]] = defaultdict(set)
    for p in publishes:
        by_day[p.date()].add(f"{p:%H:%M}")
    slot_counts = Counter(slot for slots in by_day.values() for slot in slots)
    regular = tuple(sorted(slot for slot, n in slot_counts.items() if n >= len(by_day) / 2))
    missing = tuple(
        f"{d.isoformat()} {slot}" for d, slots in sorted(by_day.items()) for slot in regular if slot not in slots
    )
    extra = tuple(
        f"{d.isoformat()} {slot}"
        for d, slots in sorted(by_day.items())
        for slot in sorted(slots)
        if slot not in regular
    )
    return RunCadence(
        runs=len(publishes),
        days=len(by_day),
        per_day=dict(Counter(len(v) for v in by_day.values())),
        regular_slots_utc=regular,
        missing=missing,
        off_schedule=extra,
    )
