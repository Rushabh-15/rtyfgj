from __future__ import annotations

import datetime as dt

import pytest

from windcast.timeutils import (
    cutoff_instant,
    delivery_day_bounds,
    delivery_day_of,
    delivery_day_periods,
    iso_z,
    parse_hhmm,
    parse_utc,
    uk_local,
)


@pytest.mark.parametrize(
    ("day", "periods", "start", "end"),
    [
        (dt.date(2026, 1, 16), 48, "2026-01-15T23:00:00Z", "2026-01-16T23:00:00Z"),
        # Clocks go forward on 29 March 2026: 23:00 GMT to 23:00 BST is 23 hours.
        (dt.date(2026, 3, 29), 46, "2026-03-28T23:00:00Z", "2026-03-29T22:00:00Z"),
        # Clocks go back on 25 October 2026: 23:00 BST to 23:00 GMT is 25 hours.
        (dt.date(2026, 10, 25), 50, "2026-10-24T22:00:00Z", "2026-10-25T23:00:00Z"),
        (dt.date(2026, 7, 1), 48, "2026-06-30T22:00:00Z", "2026-07-01T22:00:00Z"),
    ],
)
def test_delivery_day_runs_23_00_to_23_00_uk(day: dt.date, periods: int, start: str, end: str) -> None:
    first, last = delivery_day_bounds(day)
    assert (iso_z(first), iso_z(last)) == (start, end)
    assert len(delivery_day_periods(day)) == periods
    assert {delivery_day_of(p) for p in delivery_day_periods(day)} == {day}


def test_cutoff_is_uk_time_on_the_day_before() -> None:
    assert iso_z(cutoff_instant(dt.date(2026, 1, 16), dt.time(9, 0))) == "2026-01-15T09:00:00Z"
    assert iso_z(cutoff_instant(dt.date(2026, 7, 16), dt.time(9, 0))) == "2026-07-15T08:00:00Z"


def test_ambiguous_or_missing_local_times_are_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        uk_local(dt.date(2026, 3, 29), dt.time(1, 30))  # skipped by the spring-forward change
    with pytest.raises(ValueError, match="unique"):
        uk_local(dt.date(2026, 10, 25), dt.time(1, 30))  # happens twice in the autumn


def test_parsers() -> None:
    assert parse_utc("2026-01-05T04:30:00Z") == dt.datetime(2026, 1, 5, 4, 30, tzinfo=dt.UTC)
    with pytest.raises(ValueError, match="does not match format"):
        parse_utc("2026-01-05T04:30:00+00:00")
    assert parse_hhmm("09:00") == dt.time(9, 0)
    for bad in ("9:00", "09:00:00", "0900"):
        with pytest.raises(ValueError, match="HH:MM"):
            parse_hhmm(bad)


def test_settlement_period_numbering() -> None:
    from windcast.timeutils import settlement_period

    assert settlement_period(dt.datetime(2026, 1, 16, 10, 0, tzinfo=dt.UTC)) == (dt.date(2026, 1, 16), 21)
    assert settlement_period(dt.datetime(2026, 1, 15, 23, 30, tzinfo=dt.UTC)) == (dt.date(2026, 1, 15), 48)
    # 25 Oct 2026 has 50 periods: 23:30 GMT is the last one.
    assert settlement_period(dt.datetime(2026, 10, 25, 23, 30, tzinfo=dt.UTC)) == (dt.date(2026, 10, 25), 50)
    assert settlement_period(dt.datetime(2026, 7, 1, 9, 0, tzinfo=dt.UTC)) == (dt.date(2026, 7, 1), 21)
