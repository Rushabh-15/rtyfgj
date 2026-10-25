"""API contract tests: shapes, validation errors, caching, and end-to-end agreement with the snapshot."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import GOLDEN_DIR, REPO
from windcast import study
from windcast.api import Store, app, get_store
from windcast.config import Settings
from windcast.evaluation import ActualIndex, evaluate_cutoff
from windcast.fixtures import build_fixtures
from windcast.snapshot import Snapshot
from windcast.timeutils import iso_z

client = TestClient(app)
OPENAPI = REPO / "frontend" / "src" / "api" / "openapi.json"
FIXTURE_DIR = REPO / "frontend" / "src" / "test" / "fixtures"


def get(path: str, **params: Any) -> Any:
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_health_reports_the_snapshot() -> None:
    body = get("/api/health")
    assert body["status"] == "ok"
    assert body["alignment_shift_minutes"] == 0
    assert len(body["snapshot_sha256"]) == 2


def test_meta_describes_the_study() -> None:
    meta = get("/api/v1/meta")
    assert len(meta["delivery_days"]) == 31
    assert meta["delivery_days"][0] == "2026-01-02"
    assert meta["delivery_window_utc"] == ["2026-01-01T23:00:00Z", "2026-02-01T23:00:00Z"]
    assert meta["cutoffs_uk"][0] == "03:00"
    assert meta["cutoffs_uk"][-1] == "16:00"
    assert len(meta["cutoffs_uk"]) == 27
    assert meta["default_cutoff_uk"] == "09:00"
    assert {m["kind"] for m in meta["markers"]} == {"gate", "run"}
    assert meta["runs"]["missing"] == ["2026-01-15 11:30"]


def test_day_view_matches_the_golden_day() -> None:
    golden = json.loads((GOLDEN_DIR / "delivery_2026-01-16.json").read_text())
    day = get("/api/v1/days/2026-01-16", cutoff="09:00", coverage=90)
    assert day["cutoff_utc"] == "2026-01-15T09:00:00Z"
    assert day["window_utc"] == ["2026-01-15T23:00:00Z", "2026-01-16T23:00:00Z"]
    assert day["runs"] == [{"publish_time_utc": "2026-01-15T07:30:00Z", "periods": 48}]
    hourly = golden["hourly_forecast_0900_cutoff"]
    periods = day["periods"]
    assert [p["forecast_mw"] for p in periods] == [hourly[p["source_hour_utc"]] for p in periods]
    assert [p["actual_mw"] for p in periods] == golden["actual_half_hourly"]
    assert sum(abs(p["error_mw"]) for p in periods) == golden["day_metrics_0900_cutoff"]["sum_abs_error_mw"]
    assert day["persistence"]["value_mw"] == 12719
    assert day["sample"] == "fit"
    buffer = day["buffer_mw"]
    for p in periods:
        assert p["procure_for_mw"] == pytest.approx(p["forecast_mw"] - buffer)
        assert p["covered"] == (p["error_mw"] <= buffer)


def test_late_run_fallback_is_visible_in_the_day_view() -> None:
    assert get("/api/v1/days/2026-01-16", cutoff="12:00")["runs"][0]["publish_time_utc"] == "2026-01-15T09:30:00Z"
    assert get("/api/v1/days/2026-01-16", cutoff="12:30")["runs"][0]["publish_time_utc"] == "2026-01-15T12:25:00Z"


@pytest.mark.parametrize(
    ("path", "params", "status"),
    [
        ("/api/v1/days/2026-03-01", {}, 404),
        ("/api/v1/days/2026-01-16", {"cutoff": "09:15"}, 422),
        ("/api/v1/days/2026-01-16", {"cutoff": "9am"}, 422),
        ("/api/v1/days/2026-01-16", {"coverage": 85}, 422),
        ("/api/v1/days/16-01-2026", {}, 422),
        ("/api/v1/accuracy", {"cutoff": "17:00"}, 422),
        ("/api/v1/nope", {}, 404),
    ],
)
def test_invalid_requests_are_rejected(path: str, params: dict[str, Any], status: int) -> None:
    response = client.get(path, params=params)
    assert response.status_code == status
    assert "detail" in response.json()


def test_accuracy_matches_the_served_tables() -> None:
    acc = get("/api/v1/accuracy", cutoff="09:00")
    assert acc["periods"] == 1488
    assert acc["forecast"]["mae_mw"] == pytest.approx(2038.1)
    assert acc["skill_mae"] > 0
    assert [b["target_pct"] for b in acc["buffer"]] == list(study.COVERAGE_LEVELS)
    assert len(acc["days"]) == 31
    assert {d["sample"] for d in acc["days"]} == {"fit", "test"}
    assert [p["shift_minutes"] for p in acc["lag_scan"]] == list(study.LAG_SHIFTS_MINUTES)


def test_vintages() -> None:
    v = get("/api/v1/vintages")
    assert v["pairs"] > 20_000
    assert len(v["by_hour_uk"]) == 24


def test_responses_are_cacheable_and_conditional() -> None:
    first = client.get("/api/v1/meta")
    etag = first.headers["etag"]
    assert "max-age" in first.headers["cache-control"]
    second = client.get("/api/v1/meta", headers={"If-None-Match": etag})
    assert second.status_code == 304


@pytest.mark.parametrize("cutoff", ["03:00", "09:00", "12:00", "16:00"])
def test_api_reproduces_the_snapshot_end_to_end(snapshot: Snapshot, actual_index: ActualIndex, cutoff: str) -> None:
    """Snapshot -> selection rule -> served tables -> API gives the same numbers as computing directly."""
    import datetime as dt

    expected = evaluate_cutoff(snapshot.forecasts, actual_index, study.DELIVERY_DAYS, dt.time.fromisoformat(cutoff))
    for day in expected:
        served = get(f"/api/v1/days/{day.delivery_day.isoformat()}", cutoff=cutoff)
        assert [
            (p["start_utc"], p["forecast_mw"], p["actual_mw"], p["publish_time_utc"]) for p in served["periods"]
        ] == [(iso_z(p.period_start), p.forecast_mw, p.actual_mw, iso_z(p.publish_time)) for p in day.periods]


def test_committed_openapi_schema_is_current() -> None:
    """The frontend's TypeScript types are generated from this file; regenerate with `windcast openapi`."""
    assert OPENAPI.exists(), "run: cd backend && uv run windcast openapi"
    assert json.loads(OPENAPI.read_text()) == app.openapi()


def test_committed_frontend_fixtures_are_current() -> None:
    """The React tests run against these responses; regenerate with `windcast fixtures`."""
    store = Store(Settings(data_dir=REPO / "data", static_dir=None, alignment_shift_minutes=0))
    expected = build_fixtures(store)
    committed = {p.name: json.loads(p.read_text()) for p in sorted(FIXTURE_DIR.glob("*.json"))}
    assert sorted(committed) == sorted(expected), "run: cd backend && uv run windcast fixtures"
    for name, data in expected.items():
        assert committed[name] == data, f"{name} is stale; run: cd backend && uv run windcast fixtures"


def test_chart_scale_covers_every_day_and_cutoff() -> None:
    """The Day view uses one fixed y-scale; no forecast or outturn at any cutoff may exceed it."""
    store = get_store()
    top = store.meta().chart_max_mw
    highest = 0
    for cutoff in store.meta().cutoffs_uk:
        for day in store.meta().delivery_days:
            view = store.day(day, cutoff, study.DEFAULT_COVERAGE)
            highest = max(highest, *(max(p.forecast_mw, p.actual_mw) for p in view.periods))
    assert highest <= top
    assert top - highest < 2_000, "scale is far above anything shown"


def test_store_is_cached() -> None:
    assert get_store() is get_store()
