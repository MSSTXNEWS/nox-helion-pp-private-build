"""Read-only native V100 topology receipt for Maya's advisory profile.

This module owns the nvidia-smi invocation. Callers cannot inject a GPU
inventory, source label, UUID, timestamp, or memory reading into the profile.
The receipt proves only a fresh native observation; it never authorizes launch
or substitutes for the runtime memory/STOP/lease verifier.
"""
from __future__ import annotations

import csv
import math
import re
import subprocess
import time
from datetime import datetime, timezone

NVIDIA_SMI = "/usr/bin/nvidia-smi"
MIN_GPU_TOTAL_BYTES = 30 * 1024 ** 3
MAX_QUERY_SECONDS = 10.0
UUID_PATTERN = re.compile(r"GPU-[0-9A-Fa-f-]{8,}\Z")
QUERY = (
    "--query-gpu=index,uuid,name,compute_cap,memory.total,memory.free",
    "--format=csv,noheader,nounits",
)


def _hold(state: str, **details) -> dict:
    return {
        **details,
        "state": state,
        "native_gpu_readback_verified": False,
        "launchable": False,
    }


def collect_two_v100_topology() -> dict:
    """Collect and validate exactly two fresh V100 observations internally.

    No inventory, clock, command runner, or current-time input is accepted.
    A missing/unsupported nvidia-smi field, malformed row, stale query, or
    nonmatching topology fails closed.
    """
    started_ns = time.monotonic_ns()
    try:
        result = subprocess.run(
            [NVIDIA_SMI, *QUERY],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _hold("HOLD_NATIVE_GPU_COLLECTOR_UNAVAILABLE",
                     error_type=type(exc).__name__)

    finished_ns = time.monotonic_ns()
    elapsed_ns = finished_ns - started_ns
    if elapsed_ns < 0 or elapsed_ns > MAX_QUERY_SECONDS * 1_000_000_000:
        return _hold("HOLD_NATIVE_GPU_READBACK_STALE",
                     query_elapsed_ns=elapsed_ns)
    if result.returncode != 0:
        return _hold("HOLD_NATIVE_GPU_QUERY_FAILED",
                     returncode=result.returncode)

    try:
        rows = [tuple(cell.strip() for cell in row)
                for row in csv.reader(result.stdout.splitlines(), skipinitialspace=True)
                if row and any(cell.strip() for cell in row)]
    except (TypeError, csv.Error):
        return _hold("HOLD_NATIVE_GPU_INVENTORY_MALFORMED")
    if len(rows) != 2 or any(len(row) != 6 for row in rows):
        return _hold("HOLD_NATIVE_GPU_INVENTORY",
                     observed_rows=len(rows))

    devices = []
    try:
        for visible_id, row in enumerate(rows):
            index_text, uuid, name, cc_text, total_text, free_text = row
            if not index_text.isdigit():
                return _hold("HOLD_NATIVE_GPU_INVENTORY_MALFORMED")
            index = int(index_text)
            if not UUID_PATTERN.fullmatch(uuid):
                return _hold("HOLD_NATIVE_GPU_UUID", gpu_index=index)
            if not name.startswith("Tesla V100"):
                return _hold("HOLD_NATIVE_GPU_NAME", gpu_index=index, gpu_name=name)
            cc = float(cc_text)
            total_mib = int(total_text)
            free_mib = int(free_text)
            if not math.isfinite(cc) or cc != 7.0:
                return _hold("HOLD_NATIVE_GPU_SM", gpu_index=index,
                             compute_capability=cc_text)
            total_bytes = total_mib * 1024 ** 2
            free_bytes = free_mib * 1024 ** 2
            if (total_bytes < MIN_GPU_TOTAL_BYTES or free_bytes <= 0
                    or free_bytes > total_bytes):
                return _hold("HOLD_NATIVE_GPU_VRAM", gpu_index=index)
            devices.append({
                "visible_id": visible_id,
                "nvidia_smi_index": index,
                "uuid": uuid,
                "name": name,
                "compute_capability": cc_text,
                "total_bytes": total_bytes,
                "free_bytes": free_bytes,
            })
    except (TypeError, ValueError, OverflowError):
        return _hold("HOLD_NATIVE_GPU_INVENTORY_MALFORMED")

    ids = tuple(row["visible_id"] for row in devices)
    host_indices = tuple(row["nvidia_smi_index"] for row in devices)
    uuids = tuple(row["uuid"] for row in devices)
    if ids != (0, 1) or len(set(host_indices)) != 2 or len(set(uuids)) != 2:
        return _hold("HOLD_NATIVE_GPU_TOPOLOGY",
                     visible_ids=list(ids),
                     nvidia_smi_indices=list(host_indices),
                     unique_uuid_count=len(set(uuids)))
    if devices[0]["total_bytes"] != devices[1]["total_bytes"]:
        return _hold("HOLD_NATIVE_GPU_MEMORY_ASYMMETRY",
                     total_bytes=[row["total_bytes"] for row in devices])

    return {
        "state": "NATIVE_GPU_TOPOLOGY_VERIFIED",
        "source": "direct:/usr/bin/nvidia-smi",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "query_elapsed_ns": elapsed_ns,
        "fresh": True,
        "visible_ids": list(ids),
        "nvidia_smi_indices": list(host_indices),
        "device_uuids": list(uuids),
        "visibility_binding": "CUDA_VISIBLE_DEVICES is pinned to this ordered UUID list; Maya --gpus uses visible ordinals",
        "devices": devices,
        "native_gpu_readback_verified": True,
        "launchable": False,
    }
