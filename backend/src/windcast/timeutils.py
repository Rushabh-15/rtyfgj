"""Time conventions.

* Every instant is a timezone-aware UTC ``datetime``; Elexon timestamps are ISO-8601 with a ``Z`` suffix.
* Clock times that people choose (the decision cutoff, the delivery-day boundary) are UK local time
  (Europe/London), converted to UTC with ``zoneinfo`` so clock changes are handled.
* A delivery day D runs from 23:00 UK on D-1 to 23:00 UK on D (Nord Pool's GB convention), so it has 48
  half-hours, or 46 / 50 on clock-change days.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

UTC = dt.UTC
LONDON = ZoneInfo("Europe/London")
HALF_HOUR = dt.timedelta(minutes=30)
HOUR = dt.timedelta(hours=1)
DAY = dt.timedelta(days=1)
DELIVERY_DAY_START_UK = dt.time(23, 0)
_ISO_Z = "%Y-%m-%dT%H:%M:%SZ"


def parse_utc(value: str) -> dt.datetime:
    """Parse an Elexon timestamp such as ``2026-01-05T04:30:00Z``; anything else raises ``ValueError``."""
    return dt.datetime.strptime(value, _ISO_Z).replace(tzinfo=UTC)


def iso_z(t: dt.datetime) -> str:
    """Format an aware datetime as ISO-8601 UTC with a ``Z`` suffix."""
    require_aware(t)
    return t.astimezone(UTC).strftime(_ISO_Z)


def require_aware(t: dt.datetime) -> None:
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError(f"naive datetime not allowed: {t!r}")


def require_half_hour(t: dt.datetime) -> None:
    """Settlement periods start on the hour or half-hour."""
    require_aware(t)
    if t.minute not in (0, 30) or t.second or t.microsecond:
        raise ValueError(f"not a half-hour boundary: {t.isoformat()}")


def uk_local(day: dt.date, clock: dt.time) -> dt.datetime:
    """The UTC instant of ``clock`` UK time on ``day``.

    Times inside the spring-forward gap or the autumn overlap are rejected rather than guessed; the cutoff range
    (03:00-16:00) and the 23:00 delivery-day boundary never fall in them.
    """
    local = dt.datetime.combine(day, clock, tzinfo=LONDON)
    as_utc = local.astimezone(UTC)
    round_trip = as_utc.astimezone(LONDON)
    other_fold = local.replace(fold=1).astimezone(UTC)
    if round_trip.replace(tzinfo=None) != local.replace(tzinfo=None) or other_fold != as_utc:
        raise ValueError(f"{clock.isoformat()} on {day.isoformat()} is not a unique UK local time")
    return as_utc


def delivery_day_bounds(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """UTC start (inclusive) and end (exclusive) of delivery day ``day``: 23:00 UK on D-1 to 23:00 UK on D."""
    return uk_local(day - DAY, DELIVERY_DAY_START_UK), uk_local(day, DELIVERY_DAY_START_UK)


def delivery_day_periods(day: dt.date) -> list[dt.datetime]:
    """Half-hour period starts (UTC) of delivery day ``day``, in order."""
    start, end = delivery_day_bounds(day)
    periods = []
    t = start
    while t < end:
        periods.append(t)
        t += HALF_HOUR
    return periods


def delivery_day_of(period_start: dt.datetime) -> dt.date:
    """The delivery day a half-hour belongs to (periods from 23:00 UK belong to the next date)."""
    require_aware(period_start)
    local = period_start.astimezone(LONDON)
    return local.date() + DAY if local.time() >= DELIVERY_DAY_START_UK else local.date()


def cutoff_instant(delivery_day: dt.date, cutoff: dt.time) -> dt.datetime:
    """Decision cutoff for ``delivery_day``: ``cutoff`` UK time on the day before delivery (D-1)."""
    return uk_local(delivery_day - DAY, cutoff)


def parse_hhmm(value: str) -> dt.time:
    """Parse ``HH:MM`` (24-hour) into a ``time``; seconds are not allowed."""
    if len(value) != 5 or value[2] != ":":
        raise ValueError(f"expected HH:MM, got {value!r}")
    hours, minutes = int(value[:2]), int(value[3:])
    return dt.time(hours, minutes)


def format_hhmm(t: dt.time) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def date_range(first: dt.date, last: dt.date) -> list[dt.date]:
    """Inclusive list of dates."""
    if last < first:
        raise ValueError("last date before first date")
    return [first + dt.timedelta(days=i) for i in range((last - first).days + 1)]
