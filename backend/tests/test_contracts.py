"""Data contracts: they pass on the committed snapshot and catch the corruptions they are meant to catch."""

from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path

import pytest

from tests.conftest import SNAPSHOT_DIR
from windcast import contracts
from windcast.snapshot import Snapshot, SnapshotError, load_snapshot, parse_actuals, parse_forecasts


def test_every_contract_passes_on_the_snapshot(snapshot: Snapshot) -> None:
    results = contracts.run_checks(snapshot)
    failed = [f"{r.name}: {r.detail}" for r in results if not r.passed]
    assert not failed, failed


def test_snapshot_profile_is_as_documented(snapshot: Snapshot) -> None:
    assert len(snapshot.forecasts) == 19_856
    assert len(snapshot.actuals) == 1_632
    cadence = contracts.run_cadence(snapshot)
    assert cadence.runs == 272
    assert cadence.regular_slots_utc == (
        "02:30",
        "04:30",
        "07:30",
        "09:30",
        "11:30",
        "15:30",
        "18:30",
        "22:30",
    )
    assert cadence.missing == ("2026-01-15 11:30",)
    assert cadence.off_schedule == ("2026-01-15 12:25",)


def test_tampered_file_fails_the_hash_check(tmp_path: Path) -> None:
    shutil.copytree(SNAPSHOT_DIR, tmp_path / "snap")
    target = tmp_path / "snap" / "FUELHH_WIND_stream_2025-12-31_2026-02-02.json"
    target.write_bytes(target.read_bytes().replace(b'"generation":15213', b'"generation":15214', 1))
    with pytest.raises(SnapshotError, match="SHA-256"):
        load_snapshot(tmp_path / "snap")


def _with(
    snapshot: Snapshot,
    *,
    windfor: list[dict[str, object]] | None = None,
    fuelhh: list[dict[str, object]] | None = None,
) -> Snapshot:
    w = snapshot.raw_windfor if windfor is None else windfor
    f = snapshot.raw_fuelhh if fuelhh is None else fuelhh
    return dataclasses.replace(
        snapshot, raw_windfor=w, raw_fuelhh=f, forecasts=parse_forecasts(w), actuals=parse_actuals(f)
    )


def test_duplicate_forecast_row_is_caught(snapshot: Snapshot) -> None:
    corrupted = _with(snapshot, windfor=[*snapshot.raw_windfor, dict(snapshot.raw_windfor[0])])
    assert not contracts.check_windfor_keys(corrupted).passed


def test_gap_in_outturn_is_caught(snapshot: Snapshot) -> None:
    rows = [r for r in snapshot.raw_fuelhh if r["startTime"] != "2026-01-20T12:00:00Z"]
    corrupted = _with(snapshot, fuelhh=rows)
    assert not contracts.check_fuelhh_periods(corrupted).passed
    assert not contracts.check_window_coverage(corrupted).passed


def test_wrong_settlement_period_is_caught(snapshot: Snapshot) -> None:
    rows = json.loads(json.dumps(snapshot.raw_fuelhh))
    rows[100]["settlementPeriod"] = rows[100]["settlementPeriod"] % 48 + 1
    assert not contracts.check_fuelhh_periods(_with(snapshot, fuelhh=rows)).passed


def test_bad_schema_values_are_caught(snapshot: Snapshot) -> None:
    rows = json.loads(json.dumps(snapshot.raw_windfor))
    rows[5]["generation"] = -1
    rows[6]["startTime"] = "2026-01-01 00:00"
    failures = contracts._schema_failures(rows, contracts.WINDFOR_FIELDS, "WINDFOR")
    assert len(failures) == 2


def test_truncated_run_is_caught(snapshot: Snapshot) -> None:
    run = snapshot.raw_windfor[0]["publishTime"]
    rows = [r for r in snapshot.raw_windfor if not (r["publishTime"] == run and r["startTime"] > run[:10] + "T23")]
    assert not contracts.check_windfor_runs(_with(snapshot, windfor=rows)).passed
