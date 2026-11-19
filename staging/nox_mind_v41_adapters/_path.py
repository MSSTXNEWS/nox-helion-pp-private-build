"""Put the unpacked mind package on sys.path without installing it."""
from __future__ import annotations

import sys
from pathlib import Path


def ensure_mind_package_on_path() -> Path:
    root = Path(__file__).resolve().parents[1] / "nox_mind_v41"
    entry = str(root)
    if entry not in sys.path:
        sys.path.insert(0, entry)
    return root
