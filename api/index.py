"""Vercel entry point: the same FastAPI app as the Docker image, serving the committed ``data/derived`` tables.

Vercel builds this function from source (``requirements.txt``), so it is not the CI-tested container image; the
Playwright smoke test runs against the deployed URL to cover that gap.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))
os.environ.setdefault("WINDCAST_DATA_DIR", str(ROOT / "data"))

from windcast.api import app  # noqa: E402

__all__ = ["app"]
