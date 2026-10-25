"""API responses saved as fixtures for the frontend tests.

The React tests run against these files instead of a live server, so they must be exactly what the API returns
for the committed snapshot. ``windcast fixtures`` writes them and a backend test fails when they drift.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from windcast.api import Store

# File name -> response. Names encode the request so the frontend's fake fetch can find them:
#   accuracy_<HH-MM>.json for /api/v1/accuracy?cutoff=HH:MM
#   day_<date>_<HH-MM>_<coverage>.json for /api/v1/days/<date>?cutoff=HH:MM&coverage=<coverage>
FIXTURES: dict[str, Callable[[Store], BaseModel]] = {
    "meta.json": lambda s: s.meta(),
    "vintages.json": lambda s: s.vintages(),
    "accuracy_09-00.json": lambda s: s.accuracy("09:00"),
    "accuracy_09-30.json": lambda s: s.accuracy("09:30"),
    "accuracy_12-00.json": lambda s: s.accuracy("12:00"),
    "accuracy_12-30.json": lambda s: s.accuracy("12:30"),
    "day_2026-01-02_09-00_90.json": lambda s: s.day("2026-01-02", "09:00", 90),
    "day_2026-01-02_09-00_95.json": lambda s: s.day("2026-01-02", "09:00", 95),
    "day_2026-01-02_09-30_90.json": lambda s: s.day("2026-01-02", "09:30", 90),
    "day_2026-01-02_12-00_90.json": lambda s: s.day("2026-01-02", "12:00", 90),
    "day_2026-01-16_09-00_90.json": lambda s: s.day("2026-01-16", "09:00", 90),
    "day_2026-01-16_12-00_90.json": lambda s: s.day("2026-01-16", "12:00", 90),
    "day_2026-01-16_12-30_90.json": lambda s: s.day("2026-01-16", "12:30", 90),
}


def build_fixtures(store: Store) -> dict[str, Any]:
    """Every fixture as JSON-compatible data, keyed by file name."""
    return {name: make(store).model_dump(mode="json") for name, make in FIXTURES.items()}


def write_fixtures(store: Store, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.json"):
        if stale.name not in FIXTURES:
            stale.unlink()
    written = []
    for name, data in build_fixtures(store).items():
        path = out / name
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
        written.append(path)
    return written
