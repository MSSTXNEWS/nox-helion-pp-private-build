#!/usr/bin/env python3
"""Read-only owner incident census after an ambiguous chat-policy source exchange.

Does not run model requests, stop processes, change files, acquire writer lease,
or disclose credentials, chat bodies, peer IPs, or source content.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

ROOT = Path("/root/nox")
PINS = {
    "slim_chat_t885u.py": {
        "before": "8e1a83a68b336fc0c12f350d754ea47e5b5b72688584670aacc0de4079b1d37b",
        "candidate": "82412dcfb1868c1ce8cfc9f4a0df22054dec16784e9e43d349901fec7ef1f227",
    },
    "common.py": {
        "before": "618b2b24ffdf780e64a5d09955438dec5a9b6b8b04b3346b29c57fc750403167",
        "candidate": "177fbe5df042ba75a94cf9b7c03c8ffe58bde99f12599193db0cf383cc1305dd",
    },
    "chat_proxy.py": {
        "before": "1b468ebda8cdae0dce3fd1b9df4f7def64c56d708796b05e5bd7f88fbc76af62",
        "candidate": "cc1437ce8c3bfbbc4259ffdbe299bf3b8721d4b1bb09c88565ccb6cb9fdb95eb",
    },
    "chat_state.json": {
        "before": "a3a4bb542d6c95a2de769e427c393e4d1412d6d452b90ac07fe8c8b312b1f1cc",
        "candidate": "5898f7990868c7465f4d28d6bf8164ebe7e7ee7270d867ee14261c73b5adda19",
    },
    "nox-v24-chat.js": {
        "current": "55e4445443cd0d4cfa4d2a8775dcd8c7689890daad492b58e01c298691ac7e20",
    },
}
EXPECTED = {
    "director": (106058, 181620214),
    "runtime": (106174, 181621423),
    "memory": (106175, 181621423),
    "weights": (106176, 181621423),
    "model": (3266857, 172046662),
    "old_proxy": (3703386, 175609570),
    "replacement_proxy": (242298, 183262723),
    "web": (3505392, 173653097),
}
FILES = {
    "slim_chat_t885u.py": ROOT / "scripts/slim_chat_t885u.py",
    "common.py": ROOT / "scripts/common.py",
    "chat_proxy.py": ROOT / "scripts/chat_proxy.py",
    "chat_state.json": ROOT / "status/chat_state.json",
    "nox-v24-chat.js": ROOT / "incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/pc/v24/nox-v24-chat.js",
}
SERVICES = (
    "nox-dispatcher-t855u", "nox-ds41-8098", "nox-web29-18775", "nox-proxy"
)

def snapshot(path: Path, limit=262144):
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
            return {"state": "FILE_SCOPE_HOLD"}
        raw = os.read(fd, limit + 1)
        after = os.fstat(fd)
        if len(raw) != before.st_size or before.st_ino != after.st_ino or before.st_mtime_ns != after.st_mtime_ns:
            return {"state": "FILE_CHANGED"}
        value = hashlib.sha256(raw).hexdigest()
        pins = {tag for tag, sha in PINS[path.name].items() if sha == value}
        row = {"state": "KNOWN" if pins else "UNRECOGNIZED",
               "version": next(iter(pins)) if pins else None,
               "sha256": value, "bytes": len(raw), "mtime_ns": before.st_mtime_ns}
        if path.name == "chat_state.json":
            try:
                item = json.loads(raw)
                if isinstance(item, dict) and type(item.get("inflight")) is int:
                    row["inflight"] = item["inflight"]
                    last_ts = item.get("last_ts")
                    if type(last_ts) in (int, float):
                        row["last_event_age_s"] = round(time.time() - last_ts, 1)
            except (ValueError, UnicodeError):
                row["counter_state"] = "INVALID"
        return row
    finally:
        os.close(fd)

def process(pid, ticks):
    try:
        raw = Path("/proc/%d/stat" % pid).read_bytes()[:8193]
        if len(raw) > 8192:
            return {"state": "OUT_OF_BOUND"}
        fields = raw.rsplit(b") ", 1)[1].split()
        observed = {"pid": pid, "state": fields[0].decode(),
                    "ppid": int(fields[1]), "pgrp": int(fields[2]),
                    "start_ticks": int(fields[19])}
        observed["same_identity"] = observed["start_ticks"] == ticks
        return observed
    except (OSError, ValueError, IndexError):
        return {"pid": pid, "state": "NOT_OBSERVED", "same_identity": False}

def service(name):
    try:
        x = subprocess.run(["supervisorctl", "status", name], capture_output=True,
                           timeout=6, text=True)
        summary = x.stdout.strip()
        state = summary.split()[1] if x.returncode == 0 and len(summary.split()) >= 2 else "UNKNOWN"
        if state not in ("RUNNING","STOPPED","STARTING","BACKOFF","FATAL","EXITED","UNKNOWN"):
            state="UNKNOWN"
        return {"state": state, "rc": x.returncode}
    except (OSError, subprocess.TimeoutExpired):
        return {"state": "UNAVAILABLE"}

def current_service_identity(name):
    """Read only the supervisor-owned current PID, never use historical PID as liveness."""
    if name not in SERVICES:
        return {"state": "UNSUPPORTED_SERVICE"}
    try:
        cmd = subprocess.run(["supervisorctl", "status", name], capture_output=True,
                             timeout=6, text=True)
        if cmd.returncode or len(cmd.stdout) > 2048:
            return {"state": "STATUS_UNAVAILABLE"}
        match = re.fullmatch(re.escape(name) + r"\s+RUNNING\s+pid\s+(\d+),[^\n]*\n?", cmd.stdout)
        if not match:
            return {"state": "NOT_RUNNING"}
        pid = int(match[1])
        if pid < 2 or pid >= 2**31:
            return {"state": "PID_OUT_OF_RANGE"}
        raw = Path("/proc/%d/stat" % pid).read_bytes()
        if len(raw) > 8192:
            return {"state": "STAT_TOO_LARGE"}
        fields = raw.rsplit(b") ", 1)[1].split()
        start = int(fields[19])
        status = fields[0].decode("ascii")
        if status in ("Z", "X"):
            return {"state": "NOT_LIVE"}
        return {"state": "RUNNING", "pid": pid, "start_ticks": start,
                "ppid": int(fields[1]), "pgrp": int(fields[2])}
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return {"state": "IDENTITY_UNAVAILABLE"}


def startup_order_evidence(data):
    """Evidence of source-file presence before proxy startup, not behavioral acceptance."""
    current = data.get("current_services", {}).get("nox-proxy", {})
    if current.get("state") != "RUNNING":
        return {"state": "PROXY_UNKNOWN"}
    try:
        boot_raw = Path("/proc/stat").read_bytes()
        if len(boot_raw) > 1024 * 1024:
            return {"state": "BOOT_FILE_BOUND"}
        lines = [row for row in boot_raw.splitlines() if row.startswith(b"btime ")]
        if len(lines) != 1:
            return {"state": "BOOT_TIME_UNAVAILABLE"}
        boot = int(lines[0].split()[1])
        ticks = int(os.sysconf("SC_CLK_TCK"))
        if ticks <= 0:
            return {"state": "TICK_RATE_UNAVAILABLE"}
        started_ns = boot * 1_000_000_000 + current["start_ticks"] * 1_000_000_000 // ticks
        names = ("slim_chat_t885u.py", "common.py", "chat_proxy.py")
        files = [data["files"][name] for name in names]
        if any(row.get("version") != "candidate" or type(row.get("mtime_ns")) is not int for row in files):
            return {"state": "SOURCE_CANDIDATE_MISSING"}
        latest_ns = max(row["mtime_ns"] for row in files)
        # Be conservative about tick rounding; no inference if margin < 2 seconds.
        return {"state": "SOURCE_BEFORE_PROXY_START" if started_ns >= latest_ns + 2_000_000_000
                else "TIMELINE_UNRESOLVED",
                "source_before_proxy": started_ns >= latest_ns + 2_000_000_000,
                "proxy_pid": current["pid"], "proxy_start_ticks": current["start_ticks"]}
    except (OSError, ValueError, KeyError, IndexError):
        return {"state": "TIMELINE_UNAVAILABLE"}


def main():
    result = {"schema": "NOX_OWNER_CHAT_RECOVERY_INCIDENT_INSPECT_V1",
              "read_only": True, "writes": 0, "service_restarts": 0,
              "collected_at": time.time(), "files": {}, "processes": {}, "services": {}}
    for name, path in FILES.items():
        try:
            result["files"][name] = snapshot(path)
        except (OSError, ValueError) as exc:
            result["files"][name] = {"state": type(exc).__name__}
    for name, (pid, ticks) in EXPECTED.items():
        result["processes"][name] = process(pid, ticks)
    for name in SERVICES:
        result["services"][name] = service(name)
    result["current_services"] = {name: current_service_identity(name) for name in SERVICES}
    result["source_startup_order"] = startup_order_evidence(result)
    try:
        import http.client
        connection = http.client.HTTPConnection("127.0.0.1", 8080, timeout=3)
        try:
            connection.request("GET", "/health", headers={"Connection": "close"})
            response = connection.getresponse()
            response.read(4097)
            result["proxy_health"] = {"code": response.status}
        finally:
            connection.close()
    except OSError:
        result["proxy_health"] = {"code": None}
    print("NOX_MAINT_COUNTER_POLICY_INCIDENT="+json.dumps(result,sort_keys=True,separators=(",",":"),
                                                       allow_nan=False), flush=True)
    print("NOX_MAINT_INSPECT_COMPLETE=true",flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
