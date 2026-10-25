"""Runtime settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from windcast.selection import ALLOWED_SHIFTS_MINUTES

# backend/src/windcast/config.py -> repository root (valid for editable installs and the Vercel bundle).
_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    static_dir: Path | None
    alignment_shift_minutes: int

    @property
    def snapshot_dir(self) -> Path:
        return self.data_dir / "snapshot"

    @property
    def derived_dir(self) -> Path:
        return self.data_dir / "derived"


def load_settings() -> Settings:
    data_dir = Path(os.environ.get("WINDCAST_DATA_DIR", _REPO_ROOT / "data"))
    static = os.environ.get("WINDCAST_STATIC_DIR")
    shift = int(os.environ.get("WINDCAST_ALIGNMENT_SHIFT_MINUTES", "0"))
    if shift not in ALLOWED_SHIFTS_MINUTES:
        raise ValueError(f"WINDCAST_ALIGNMENT_SHIFT_MINUTES must be one of {ALLOWED_SHIFTS_MINUTES}, got {shift}")
    return Settings(data_dir=data_dir, static_dir=Path(static) if static else None, alignment_shift_minutes=shift)
