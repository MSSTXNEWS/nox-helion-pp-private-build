"""E06-only admission for a coherent GPU tile from existing P05 native readings.

No sampling, drivers, network calls or event bus are implemented here. This
check is deliberately stricter than individual scalar validation: a single
LIVE tile must describe one native provider and one observation window.
"""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any

_SAMPLE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,160}$")
_UTC = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$"
)
_GPU_KEYS = ("gpu.percent", "gpu.temperature.c", "gpu.vram.used_bytes",
             "gpu.vram.total_bytes")


def valid_sample_id(value: Any) -> bool:
    """Optional native sample IDs must be bounded, non-spoofable strings."""
    return type(value) is str and _SAMPLE_ID.fullmatch(value) is not None


def _utc_instant(value: Any) -> datetime | None:
    if type(value) is not str or _UTC.fullmatch(value) is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def enforce_gpu_tile_sample(
    safe: dict[str, dict], observed: dict[str, str], samples: dict[str, str | None]
) -> None:
    """Quarantine inconsistent LIVE GPU values without touching CPU or owner data.

    Input scalars and physical DeviceId have already passed the existing
    E06/P05 gates. Legacy producers may omit sample IDs entirely; if any
    metric supplies one, every displayed GPU metric must have the same ID.
    """
    live = [k for k in _GPU_KEYS if isinstance(safe.get(k), dict)
            and safe[k].get("status") == "LIVE"
            and safe[k].get("value") is not None]
    if len(live) <= 1:
        return

    sources = [safe[k].get("source") for k in live]
    times = [_utc_instant(observed.get(k)) for k in live]
    identifiers = [samples.get(k) for k in live]
    any_sample_id = any(v is not None for v in identifiers)
    valid = (
        all(type(s) is str and s and s == s.strip() for s in sources)
        and len(set(sources)) == 1
        and all(t is not None for t in times)
        and (max(times) - min(times)).total_seconds() <= 5
        and (not any_sample_id or (
            all(valid_sample_id(v) for v in identifiers)
            and len(set(identifiers)) == 1
        ))
    ) if all(t is not None for t in times) else False

    if not valid:
        for key in live:
            safe[key] = {"value": None, "status": "N_D", "source": None}

