#!/usr/bin/env python3
"""Bounded read-only two-snapshot NVIDIA V100 inventory for owner action.

Only fixed GPU identity and memory counters are emitted. No process arguments,
environment, files, credentials, or configuration are read.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ACTION = "gpu_inventory"
INSTANCE_ID = 60509551
SCHEMA = "NOX_GPU_INVENTORY_V1"
NVIDIA_SMI = "/usr/bin/nvidia-smi"
QUERY = (
    "--query-gpu=index,name,uuid,memory.total,memory.used,memory.free",
    "--format=csv,noheader,nounits",
)
MAX_OUTPUT_BYTES = 4096
MAX_ROW_BYTES = 512
MAX_GPUS = 2
UUID_RE = re.compile(r"GPU-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
SOURCE_RE = re.compile(r"[0-9a-f]{40}\Z")
BOOT_RE = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")


def _hold(code: str) -> RuntimeError:
    return RuntimeError(code if re.fullmatch(r"HOLD_[A-Z0-9_]+", code) else "HOLD_GPU_INVENTORY_INVALID")


def _read_host_clock(read_text):
    boot_id = read_text("/proc/sys/kernel/random/boot_id", 128).strip().lower()
    uptime_text = read_text("/proc/uptime", 128).split()
    if not BOOT_RE.fullmatch(boot_id) or not uptime_text:
        raise _hold("HOLD_GPU_INVENTORY_HOST_CLOCK")
    try:
        uptime = float(uptime_text[0])
    except (TypeError, ValueError, OverflowError) as exc:
        raise _hold("HOLD_GPU_INVENTORY_HOST_CLOCK") from exc
    if not (uptime >= 0 and uptime < 10**9):
        raise _hold("HOLD_GPU_INVENTORY_HOST_CLOCK")
    return boot_id, uptime


def parse_gpu_rows(output: str):
    if not isinstance(output, str) or len(output.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise _hold("HOLD_GPU_INVENTORY_OUTPUT_BOUND")
    rows = []
    try:
        parsed = list(csv.reader(io.StringIO(output, newline=""), strict=True))
    except (csv.Error, TypeError, ValueError) as exc:
        raise _hold("HOLD_GPU_INVENTORY_CSV") from exc
    for fields in parsed:
        if not fields or not any(field.strip() for field in fields):
            continue
        if len(",".join(fields).encode("utf-8")) > MAX_ROW_BYTES or len(fields) != 6:
            raise _hold("HOLD_GPU_INVENTORY_ROW_SHAPE")
        index_text, name, uuid, total_text, used_text, free_text = (v.strip() for v in fields)
        if not re.fullmatch(r"[0-9]{1,2}", index_text):
            raise _hold("HOLD_GPU_INVENTORY_INDEX")
        index = int(index_text)
        name = " ".join(name.split())
        if not name or len(name) > 96 or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise _hold("HOLD_GPU_INVENTORY_MODEL")
        if name != "Tesla V100-SXM2-32GB" or not UUID_RE.fullmatch(uuid):
            raise _hold("HOLD_GPU_INVENTORY_IDENTITY")
        numbers = (total_text, used_text, free_text)
        if any(not re.fullmatch(r"[0-9]{1,7}", value) for value in numbers):
            raise _hold("HOLD_GPU_INVENTORY_MEMORY")
        total, used, free = (int(value) for value in numbers)
        if total <= 0 or used < 0 or free < 0 or used > total or free > total or used + free != total:
            raise _hold("HOLD_GPU_INVENTORY_MEMORY")
        rows.append({
            "index": index,
            "model": name,
            "uuid": uuid,
            "memory_total_mib": total,
            "memory_used_mib": used,
            "memory_free_mib": free,
        })
    if len(rows) != MAX_GPUS:
        raise _hold("HOLD_GPU_INVENTORY_GPU_COUNT")
    if len({row["index"] for row in rows}) != MAX_GPUS:
        raise _hold("HOLD_GPU_INVENTORY_DUPLICATE_INDEX")
    if len({row["uuid"] for row in rows}) != MAX_GPUS:
        raise _hold("HOLD_GPU_INVENTORY_DUPLICATE_UUID")
    return sorted(rows, key=lambda row: row["index"])


def capture_snapshot(run=subprocess.run, read_text=None, monotonic_ns=time.monotonic_ns):
    if read_text is None:
        def read_text(path, limit):
            value = Path(path).read_text(encoding="ascii")
            if len(value) > limit:
                raise _hold("HOLD_GPU_INVENTORY_HOST_CLOCK")
            return value
    before_boot, before_uptime = _read_host_clock(read_text)
    started = monotonic_ns()
    try:
        result = run(
            [NVIDIA_SMI, *QUERY],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise _hold("HOLD_GPU_INVENTORY_NVIDIA_SMI") from exc
    finished = monotonic_ns()
    if type(result.returncode) is not int or result.returncode != 0:
        raise _hold("HOLD_GPU_INVENTORY_NVIDIA_SMI_RC")
    output = result.stdout
    if not isinstance(output, str) or len(output.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise _hold("HOLD_GPU_INVENTORY_OUTPUT_BOUND")
    rows = parse_gpu_rows(output)
    after_boot, after_uptime = _read_host_clock(read_text)
    if before_boot != after_boot or after_uptime < before_uptime or finished < started:
        raise _hold("HOLD_GPU_INVENTORY_CLOCK_DRIFT")
    return {
        "boot_id": after_boot,
        "uptime_seconds": after_uptime,
        "monotonic_started_ns": started,
        "monotonic_finished_ns": finished,
        "nvidia_smi_rc": result.returncode,
        "rows": rows,
    }


def _identity_rows(rows):
    return [
        (row["index"], row["model"], row["uuid"], row["memory_total_mib"])
        for row in rows
    ]


def build_inventory(run=subprocess.run, read_text=None, monotonic_ns=time.monotonic_ns, sleep=time.sleep):
    before = capture_snapshot(run=run, read_text=read_text, monotonic_ns=monotonic_ns)
    sleep(0.5)
    after = capture_snapshot(run=run, read_text=read_text, monotonic_ns=monotonic_ns)
    if before["boot_id"] != after["boot_id"] or after["uptime_seconds"] <= before["uptime_seconds"]:
        raise _hold("HOLD_GPU_INVENTORY_BOOT_OR_UPTIME")
    if _identity_rows(before["rows"]) != _identity_rows(after["rows"]):
        raise _hold("HOLD_GPU_INVENTORY_DEVICE_DRIFT")
    return {
        "schema": SCHEMA,
        "action": ACTION,
        "instance_id": INSTANCE_ID,
        "boot_id": before["boot_id"],
        "uptime_scope": "two monotonic host snapshots; point-in-time only",
        "memory_semantics": "nvidia-smi MiB counters; memory.total=memory.used+memory.free",
        "identity_stable": True,
        "snapshots": [before, after],
    }


def inventory_digest(inventory):
    payload = json.dumps(inventory, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def run_action(env=None, run=subprocess.run, read_text=None, monotonic_ns=time.monotonic_ns, sleep=time.sleep):
    env = os.environ if env is None else env
    source_sha = env.get("NOX_OWNER_SOURCE_SHA", "")
    request_text = env.get("NOX_OWNER_REQUEST_ID", "")
    action = env.get("NOX_OWNER_ACTION", "")
    instance_id = env.get("NOX_OWNER_INSTANCE_ID", "")
    if action != ACTION:
        raise _hold("HOLD_GPU_INVENTORY_ACTION_PIN")
    if instance_id != str(INSTANCE_ID):
        raise _hold("HOLD_GPU_INVENTORY_INSTANCE_PIN")
    if not SOURCE_RE.fullmatch(source_sha):
        raise _hold("HOLD_GPU_INVENTORY_SOURCE_PIN")
    if not re.fullmatch(r"[1-9][0-9]{0,19}", request_text):
        raise _hold("HOLD_GPU_INVENTORY_REQUEST_PIN")
    request_id = int(request_text)
    inventory = build_inventory(run=run, read_text=read_text, monotonic_ns=monotonic_ns, sleep=sleep)
    receipt = {
        "schema": SCHEMA,
        "action": ACTION,
        "instance_id": INSTANCE_ID,
        "source_sha": source_sha,
        "request_id": request_id,
        "inventory_sha256": inventory_digest(inventory),
        "inventory": inventory,
    }
    return receipt


def main():
    try:
        receipt = run_action()
    except Exception as exc:
        code = str(exc)
        if not re.fullmatch(r"HOLD_[A-Z0-9_]+", code):
            code = "HOLD_GPU_INVENTORY_" + type(exc).__name__.upper()
        print("NOX_MAINT_GPU_INVENTORY_RESULT=" + code, flush=True)
        return 2
    print("NOX_MAINT_GPU_INVENTORY=" + json.dumps(receipt, sort_keys=True, separators=(",", ":")), flush=True)
    print("NOX_MAINT_GPU_INVENTORY_COMPLETE=true", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
