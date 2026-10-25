"""Load the raw Elexon snapshot into typed rows.

The snapshot directory holds the API responses exactly as downloaded plus ``manifest.json``. Loading verifies the
SHA-256 of every file against the manifest before parsing, so the served numbers can always be traced back to
specific bytes.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from windcast.timeutils import parse_utc

MANIFEST = "manifest.json"


@dataclass(frozen=True, slots=True)
class ForecastRow:
    """One WINDFOR value: run ``publish_time`` forecasts ``generation_mw`` for the hour labelled ``start_time``."""

    publish_time: dt.datetime
    start_time: dt.datetime
    generation_mw: int


@dataclass(frozen=True, slots=True)
class ActualRow:
    """One FUELHH WIND value: average MW over the half-hour starting ``start_time``."""

    start_time: dt.datetime
    settlement_date: dt.date
    settlement_period: int
    publish_time: dt.datetime
    generation_mw: int


@dataclass(frozen=True, slots=True)
class FileEntry:
    name: str
    dataset: str
    file: str
    url: str
    sha256: str
    rows: int
    bytes: int
    requested_at_utc: str


@dataclass(frozen=True)
class Snapshot:
    directory: Path
    files: tuple[FileEntry, ...]
    raw_windfor: list[dict[str, Any]]
    raw_fuelhh: list[dict[str, Any]]
    forecasts: tuple[ForecastRow, ...]
    actuals: tuple[ActualRow, ...]

    def file(self, name: str) -> FileEntry:
        for entry in self.files:
            if entry.name == name:
                return entry
        raise KeyError(name)


class SnapshotError(RuntimeError):
    """The snapshot on disk does not match its manifest."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_manifest(directory: Path) -> tuple[FileEntry, ...]:
    manifest = json.loads((directory / MANIFEST).read_text())
    return tuple(
        FileEntry(
            name=e["name"],
            dataset=e["dataset"],
            file=e["file"],
            url=e["url"],
            sha256=e["sha256"],
            rows=e["rows"],
            bytes=e["bytes"],
            requested_at_utc=e["requested_at_utc"],
        )
        for e in manifest["requests"]
    )


def _load_verified(directory: Path, entry: FileEntry) -> list[dict[str, Any]]:
    body = (directory / entry.file).read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    if digest != entry.sha256 or len(body) != entry.bytes:
        raise SnapshotError(f"{entry.file}: SHA-256 {digest[:12]}… does not match the manifest")
    payload = json.loads(body)
    if not isinstance(payload, list) or len(payload) != entry.rows:
        raise SnapshotError(f"{entry.file}: expected a list of {entry.rows} rows")
    return payload


def parse_forecasts(raw: list[dict[str, Any]]) -> tuple[ForecastRow, ...]:
    return tuple(
        ForecastRow(
            publish_time=parse_utc(r["publishTime"]),
            start_time=parse_utc(r["startTime"]),
            generation_mw=int(r["generation"]),
        )
        for r in raw
    )


def parse_actuals(raw: list[dict[str, Any]]) -> tuple[ActualRow, ...]:
    return tuple(
        ActualRow(
            start_time=parse_utc(r["startTime"]),
            settlement_date=dt.date.fromisoformat(r["settlementDate"]),
            settlement_period=int(r["settlementPeriod"]),
            publish_time=parse_utc(r["publishTime"]),
            generation_mw=int(r["generation"]),
        )
        for r in raw
    )


def load_snapshot(directory: Path) -> Snapshot:
    """Read and hash-check the snapshot. Raises ``SnapshotError`` if any file differs from the manifest."""
    files = read_manifest(directory)
    by_name = {f.name: f for f in files}
    try:
        windfor, fuelhh = by_name["windfor"], by_name["fuelhh_wind"]
    except KeyError as missing:
        raise SnapshotError(f"manifest has no entry {missing}") from None
    raw_windfor = _load_verified(directory, windfor)
    raw_fuelhh = _load_verified(directory, fuelhh)
    return Snapshot(
        directory=directory,
        files=files,
        raw_windfor=raw_windfor,
        raw_fuelhh=raw_fuelhh,
        forecasts=parse_forecasts(raw_windfor),
        actuals=parse_actuals(raw_fuelhh),
    )
