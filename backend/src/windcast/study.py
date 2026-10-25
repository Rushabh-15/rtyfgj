"""The study design: windows, cutoff range, splits and bins. Changing a value here changes every served number."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from windcast.timeutils import date_range, format_hhmm

# Purchase decisions made in January 2026 are taken on D-1 = 1..31 January, for delivery days 2 Jan..1 Feb.
FIRST_DELIVERY_DAY = dt.date(2026, 1, 2)
LAST_DELIVERY_DAY = dt.date(2026, 2, 1)
DELIVERY_DAYS: tuple[dt.date, ...] = tuple(date_range(FIRST_DELIVERY_DAY, LAST_DELIVERY_DAY))

# Out-of-sample buffer test: fit on the first 15 delivery days, test on the remaining 16.
FIT_DAYS: tuple[dt.date, ...] = tuple(date_range(dt.date(2026, 1, 2), dt.date(2026, 1, 16)))
TEST_DAYS: tuple[dt.date, ...] = tuple(date_range(dt.date(2026, 1, 17), dt.date(2026, 2, 1)))

# Decision cutoff: UK local time on D-1. From 03:00 the selected run covers the whole delivery day.
CUTOFF_DEFAULT = dt.time(9, 0)
CUTOFF_MIN = dt.time(3, 0)
CUTOFF_MAX = dt.time(16, 0)
CUTOFF_STEP_MINUTES = 30


def cutoff_grid() -> tuple[dt.time, ...]:
    """Every selectable cutoff, 03:00 to 16:00 in 30-minute steps (27 values).

    WINDFOR runs are published at :30 past the hour (one late run at 12:25), so with the strictly-before rule
    every distinct choice of run is reachable on this grid.
    """
    start = dt.datetime.combine(dt.date(2000, 1, 1), CUTOFF_MIN)
    end = dt.datetime.combine(dt.date(2000, 1, 1), CUTOFF_MAX)
    times = []
    t = start
    while t <= end:
        times.append(t.time())
        t += dt.timedelta(minutes=CUTOFF_STEP_MINUTES)
    return tuple(times)


def cutoff_key(t: dt.time) -> str:
    """File-name form of a cutoff, e.g. ``0900``."""
    return format_hhmm(t).replace(":", "")


COVERAGE_LEVELS: tuple[int, ...] = (50, 80, 90, 95)
DEFAULT_COVERAGE = 90

# Lead time = period start minus run publish time, in hours; 6-hour buckets [lo, hi).
LEAD_BUCKETS_H: tuple[tuple[int, int], ...] = tuple((lo, lo + 6) for lo in range(0, 72, 6))
# Finer buckets for the all-vintage analysis.
VINTAGE_LEAD_BUCKETS_H: tuple[tuple[int, int], ...] = tuple((lo, lo + 3) for lo in range(0, 69, 3))

# Forecast level bands in MW, [lo, hi); conditioning on the forecast keeps the breakdown usable at decision time.
LEVEL_BANDS_MW: tuple[tuple[int, int | None], ...] = (
    (0, 6000),
    (6000, 10000),
    (10000, 14000),
    (14000, 18000),
    (18000, None),
)

# Lag scan: compare the forecast for period t with the outturn for t + shift.
LAG_SHIFTS_MINUTES: tuple[int, ...] = tuple(range(-120, 121, 30))

# Block bootstrap of buffer coverage over test days.
BOOTSTRAP_RESAMPLES = 5000
BOOTSTRAP_SEED = 20260101


@dataclass(frozen=True, slots=True)
class Marker:
    """A reference time on the D-1 timeline shown next to the cutoff control."""

    time_uk: str
    label: str
    kind: str  # "gate" (auction gate closure) or "run" (WINDFOR publication slot)
    source: str


GATE_CLOSURES: tuple[Marker, ...] = (
    Marker("09:20", "EPEX GB 60-min auction", "gate", "https://www.epexspot.com/en/tradingproducts"),
    Marker(
        "09:50",
        "Nord Pool GB hourly auction",
        "gate",
        "https://www.nordpoolgroup.com/497dea/globalassets/download-center/rules-and-regulations/product-specifications-gb-18.04.23.pdf",
    ),
    Marker(
        "14:30",
        "Nord Pool GB half-hourly auction",
        "gate",
        "https://www.nordpoolgroup.com/497dea/globalassets/download-center/rules-and-regulations/product-specifications-gb-18.04.23.pdf",
    ),
    Marker("15:30", "EPEX GB 30-min auction", "gate", "https://www.epexspot.com/en/tradingproducts"),
)
