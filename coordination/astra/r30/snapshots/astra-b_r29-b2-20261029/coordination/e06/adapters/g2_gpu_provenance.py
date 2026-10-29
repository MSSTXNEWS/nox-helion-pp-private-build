"""E06/P05 one-GPU-tile admission; never creates a sensor or polling service.

Only normalizes device identity from an already-approved E05 native snapshot.
Ambiguous GPU provenance is quarantined as N_D (never invented as zero).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

_DEVICE = re.compile(r"^[A-Za-z0-9:._/-]{1,120}$")
GPU_KEYS = frozenset(("gpu.percent", "gpu.temperature.c",
                      "gpu.vram.used_bytes", "gpu.vram.total_bytes"))


def valid_source(value: Any) -> bool:
    """Preserve meaningful Unicode provider names, forbid spoofing controls."""
    return (type(value) is str and 0 < len(value) <= 120
            and value == value.strip()
            and all(unicodedata.category(ch) not in {"Cc", "Cf", "Cs"}
                    for ch in value))


def valid_device(value: Any) -> bool:
    """Match existing P05 device_id lexical contract; absence means N_D."""
    return type(value) is str and _DEVICE.fullmatch(value) is not None


def reconcile_gpu_tile(safe: dict, observed: dict, devices: dict) -> None:
    """Mutate only E06's freshly assembled projection, never E05 owner data.

    The one-GPU UI tile cannot mix two native devices. VRAM used and total
    must share device, provider and observation instant to be shown LIVE.
    """
    def quarantine(key: str) -> None:
        safe[key] = {"value": None, "status": "N_D", "source": None}

    used_key, total_key = "gpu.vram.used_bytes", "gpu.vram.total_bytes"
    used, total = safe.get(used_key), safe.get(total_key)
    if used is not None or total is not None:
        paired = (
            isinstance(used, dict) and isinstance(total, dict)
            and type(used.get("value")) is int and type(total.get("value")) is int
            and total["value"] > 0 and 0 <= used["value"] <= total["value"]
            and valid_source(used.get("source"))
            and used["source"] == total.get("source")
            and valid_device(devices.get(used_key))
            and devices.get(used_key) == devices.get(total_key)
            and observed.get(used_key) is not None
            and observed.get(used_key) == observed.get(total_key)
        )
        if not paired:
            quarantine(used_key)
            quarantine(total_key)

    live = [k for k in GPU_KEYS if isinstance(safe.get(k), dict)
            and safe[k].get("status") == "LIVE"
            and safe[k].get("value") is not None]
    if any(not valid_device(devices.get(k)) for k in live) or len(
            {devices[k] for k in live}) > 1:
        for key in live:
            quarantine(key)
