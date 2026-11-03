"""ModelCenter progress and receipt tracking.

Buttons, download progress, and training start are recorded here.
Actual weight download and LoRA training stay behind existing P03/P04 gates.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .worms import WormHold


def make_progress(
    *,
    action: str,
    tag: str | None = None,
    bytes_done: int = 0,
    bytes_total: int = 0,
    status: str = "RUNNING",
) -> dict:
    """Visible progress record for ModelCenter UI."""
    if not isinstance(action, str) or not action:
        raise WormHold("MODELCENTER_ACTION_REQUIRED")
    return {
        "schema": "NOX-MODELCENTER-PROGRESS-v1",
        "action": action,
        "tag": tag,
        "bytes_done": max(0, int(bytes_done)),
        "bytes_total": max(0, int(bytes_total)),
        "percent": (
            round(100 * bytes_done / bytes_total, 1)
            if bytes_total > 0
            else None
        ),
        "status": status,
        "ts": time.time(),
    }


def make_receipt(
    *,
    action: str,
    tag: str,
    outcome: str,
    evidence: dict[str, Any] | None = None,
) -> dict:
    """Fixed receipt after a ModelCenter action finishes or is held."""
    if outcome not in ("OK", "HOLD", "FAILED", "CANCELLED"):
        raise WormHold("MODELCENTER_OUTCOME_INVALID")
    return {
        "schema": "NOX-MODELCENTER-RECEIPT-v1",
        "action": action,
        "tag": tag,
        "outcome": outcome,
        "evidence": evidence or {},
        "training_performed": False,
        "weights_updated": False,
        "ts": time.time(),
    }


def write_receipt(path: Path, receipt: dict) -> None:
    """Append one receipt as JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(receipt, ensure_ascii=False) + "\n")
