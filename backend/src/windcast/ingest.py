"""Re-runnable download of the snapshot window from the Elexon Insights API (standard library only).

Each response body is saved unchanged and recorded in ``manifest.json`` with its URL, parameters, download time,
HTTP status, byte size, row count and SHA-256. ``compare_manifests`` reports whether a fresh download is
byte-identical to the committed snapshot (Elexon can restate data, so a difference is a finding, not a crash).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1/datasets"
HEADERS = {"Accept": "application/json", "User-Agent": "windcast-ingest/1.0"}
RETRY_STATUSES = {429, 500, 502, 503, 504}


@dataclass(frozen=True, slots=True)
class RequestSpec:
    name: str
    dataset: str
    path: str
    params: tuple[tuple[str, str], ...]
    file: str


# Inclusive bounds on both endpoints. A superset of the study: runs from 30 Dec (the earliest run that covers the
# first delivery period is 31 Dec 02:30) and outturn from 31 Dec 00:00 to 2 Feb 23:30 (persistence and lag scan).
REQUESTS: tuple[RequestSpec, ...] = (
    RequestSpec(
        name="windfor",
        dataset="WINDFOR",
        path="WINDFOR/stream",
        params=(("publishDateTimeFrom", "2025-12-30T00:00:00Z"), ("publishDateTimeTo", "2026-02-02T00:00:00Z")),
        file="WINDFOR_stream_2025-12-30_2026-02-02.json",
    ),
    RequestSpec(
        name="fuelhh_wind",
        dataset="FUELHH",
        path="FUELHH/stream",
        params=(("settlementDateFrom", "2025-12-31"), ("settlementDateTo", "2026-02-02"), ("fuelType", "WIND")),
        file="FUELHH_WIND_stream_2025-12-31_2026-02-02.json",
    ),
)


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def url_for(spec: RequestSpec) -> str:
    return f"{BASE_URL}/{spec.path}?{urllib.parse.urlencode(spec.params, safe=':')}"


def fetch(url: str, attempts: int = 5, timeout: float = 120.0) -> tuple[int, dict[str, str], bytes, str, str]:
    """GET with exponential back-off on 429/5xx and network errors."""
    delay = 2.0
    for attempt in range(1, attempts + 1):
        started = _utc_now()
        try:
            request = urllib.request.Request(url, headers=HEADERS, method="GET")
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, dict(response.headers), response.read(), started, _utc_now()
        except urllib.error.HTTPError as err:
            if err.code not in RETRY_STATUSES or attempt == attempts:
                raise RuntimeError(f"HTTP {err.code} for {url}") from err
        except urllib.error.URLError as err:
            if attempt == attempts:
                raise RuntimeError(f"network error for {url}: {err.reason}") from err
        print(f"  retry {attempt}/{attempts - 1} in {delay:.0f}s", file=sys.stderr)
        time.sleep(delay)
        delay *= 2
    raise AssertionError("unreachable")


def pull(out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for spec in REQUESTS:
        url = url_for(spec)
        print(f"GET {url}", file=sys.stderr)
        status, headers, body, started, finished = fetch(url)
        payload = json.loads(body)
        rows = len(payload) if isinstance(payload, list) else len(payload["data"])
        (out_dir / spec.file).write_bytes(body)
        entries.append(
            {
                "name": spec.name,
                "dataset": spec.dataset,
                "file": spec.file,
                "method": "GET",
                "url": url,
                "endpoint": f"{BASE_URL}/{spec.path}",
                "params": dict(spec.params),
                "request_headers": {"Accept": HEADERS["Accept"]},
                "requested_at_utc": started,
                "completed_at_utc": finished,
                "http_status": status,
                "content_type": headers.get("Content-Type"),
                "server_date": headers.get("Date"),
                "bytes": len(body),
                "rows": rows,
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        )
    manifest = {"generated_by": "windcast ingest", "generated_at_utc": _utc_now(), "requests": entries}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def compare_manifests(new: dict[str, Any], reference: Path) -> list[str]:
    """Differences between a fresh pull and the committed manifest (empty list = byte-identical)."""
    ref = {e["name"]: e for e in json.loads(reference.read_text())["requests"]}
    differences = []
    for entry in new["requests"]:
        old = ref.get(entry["name"])
        if old is None:
            differences.append(f"{entry['name']}: not in the reference manifest")
        elif (old["sha256"], old["rows"]) != (entry["sha256"], entry["rows"]):
            differences.append(
                f"{entry['name']}: {entry['rows']} rows sha256 {entry['sha256'][:12]}… vs "
                f"{old['rows']} rows sha256 {old['sha256'][:12]}…"
            )
    return differences
