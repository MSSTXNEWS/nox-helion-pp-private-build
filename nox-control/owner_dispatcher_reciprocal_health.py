"""NOX real supervisor identity check; callable by the EXISTING dispatcher.
No polling daemon, no service mutations, no GPU inference and no shell=True.
"""
from __future__ import annotations
import hashlib
import re
import subprocess
import time
from pathlib import Path

SERVICES = {
    "nox-dispatcher-t855u": "/root/nox/scripts/nox_dispatcher_t855u.py",
    "nox-priority-scheduler": "/root/nox/scripts/nox_priority_scheduler.py",
    "nox-selfheal": "/root/nox_selfheal.py",
}
STATUSES = {"RUNNING", "STOPPED", "EXITED", "FATAL", "BACKOFF", "STARTING", "STOPPING"}
LINE = re.compile(r"^([A-Za-z0-9_.@-]{1,80})\s+(RUNNING|STOPPED|EXITED|FATAL|BACKOFF|STARTING|STOPPING)(?:\s|$)")
PID = re.compile(r"\bpid ([1-9][0-9]{0,9})(?:,|\s|$)")

def process_identity(pid, expected, proc=Path("/proc")):
    if type(pid) is not int or not 1 <= pid < 2**31:
        return None
    base = proc / str(pid)
    try:
        a = (base / "stat").read_text()
        cmd = (base / "cmdline").read_bytes()
        b = (base / "stat").read_text()
        sa = a.rsplit(") ", 1)[1].split()
        sb = b.rsplit(") ", 1)[1].split()
        # Field 22: index 19 after the comm state begins at field 3.
        if len(sa) < 20 or len(sb) < 20 or sa[19] != sb[19] or not sa[19].isdigit():
            return None
        argv = [arg.decode("utf8", "strict") for arg in cmd.split(b"\0") if arg]
        if expected not in argv:
            return None
        return {"pid": pid, "start_ticks": int(sa[19]),
                "argv_digest": hashlib.sha256(cmd).hexdigest()}
    except (OSError, ValueError, UnicodeError, IndexError):
        return None

def inspect(names=("nox-dispatcher-t855u", "nox-priority-scheduler", "nox-selfheal"),
            *, call=subprocess.run, proc=Path("/proc")):
    if any(x not in SERVICES for x in names) or len(set(names)) != len(names):
        raise ValueError("unreviewed or duplicate service")
    out = []
    for name in names:
        try:
            p = call(["supervisorctl", "status", name], capture_output=True, text=True,
                     timeout=5, check=False)
            raw = p.stdout.strip()
            match = LINE.match(raw) if len(raw) <= 500 and "\n" not in raw else None
            valid = p.returncode == 0 and match and match.group(1) == name
            state = match.group(2) if valid else "UNKNOWN"
            found = PID.search(raw) if state == "RUNNING" else None
            process = process_identity(int(found.group(1)), SERVICES[name], proc) if found else None
            row = {"name": name, "state": state, "identity_verified": process is not None}
            if process is not None:
                row.update(process)
            if state == "RUNNING" and process is None:
                row["state"] = "HOLD_PID_OR_SCRIPT"
            out.append(row)
        except (OSError, subprocess.TimeoutExpired):
            out.append({"name": name, "state": "HOLD_SUPERVISOR_UNAVAILABLE",
                        "identity_verified": False})
    all_verified = len(out) == len(names) and all(x["identity_verified"] for x in out)
    return {"schema": "NOX_DISPATCHER_RECIPROCAL_HEALTH_V1",
            "scope": "NATIVE_SUPERVISOR_PID_STARTTICKS",
            "observed_epoch": time.time(), "verified": all_verified,
            "services": out,
            "state": "ALL_IDENTITIES_VERIFIED" if all_verified else "HOLD_PROCESS_IDENTITY"}

if __name__ == "__main__":
    import json
    print(json.dumps(inspect(), sort_keys=True))
