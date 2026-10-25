from __future__ import annotations

from pathlib import Path

import pytest

from windcast.evaluation import ActualIndex
from windcast.snapshot import Snapshot, load_snapshot

REPO = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = REPO / "data" / "snapshot"
DERIVED_DIR = REPO / "data" / "derived"
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


@pytest.fixture(scope="session")
def snapshot() -> Snapshot:
    return load_snapshot(SNAPSHOT_DIR)


@pytest.fixture(scope="session")
def actual_index(snapshot: Snapshot) -> ActualIndex:
    return ActualIndex(snapshot.actuals)
