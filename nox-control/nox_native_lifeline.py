#!/usr/bin/env python3
"""NOX lifeline: independent bounded safety guard, not a second dispatcher.

Controls only explicitly named, locally approved Supervisor programs.
No shell, network commands, model promotion, training restarts or deletions.
Python 3.9+ / Linux. Install on the existing OneHost only after local acceptance.
"""
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time

SCHEMA = "NOX_LIFELINE_V2"
SERVICES = frozenset({
    "nox-dispatcher-t855u", "nox-priority-scheduler",
    "nox-selfheal", "nox-gpu-watchdog-t865u",
})
STOP_FILES = (
    "/root/nox/STOP", "/root/nox/STOP.flag", "/root/nox/stop.flag",
    "/root/nox/.stop", "/root/nox/program/STOP",
    "/workspace/NOX_STOP", "/root/nox/state/STOP", "/root/nox/state/STOP.flag",
    "/root/nox/state/OWNER_MAINTENANCE.flag",
)
STATUS = re.compile(r"^([a-zA-Z0-9_.:-]+)\s+([A-Z]+)(?:\s+pid\s+([0-9]+))?")
REPAIRABLE = frozenset(("STOPPED", "EXITED"))
MAX_EVENT_ROWS = 100
CGROUP_MEMORY_CURRENT = Path("/sys/fs/cgroup/memory.current")
CGROUP_MEMORY_MAX = Path("/sys/fs/cgroup/memory.max")
MEMORY_READ_MAX_BYTES = 64
MEMORY_FLOOR_BYTES = 2 * 1024 ** 3
MAX_CGROUP_COUNTER = (1 << 64) - 1

def policy_check(value):
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ValueError("HOLD_POLICY_SCHEMA")
    if type(value.get("enabled")) is not bool:
        raise ValueError("HOLD_POLICY_ENABLED_TYPE")
    items = value.get("services")
    if not isinstance(items, list) or not 1 <= len(items) <= len(SERVICES):
        raise ValueError("HOLD_POLICY_SERVICES")
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"name", "restart"}:
            raise ValueError("HOLD_POLICY_SERVICE_FIELDS")
        name = item["name"]
        if name not in SERVICES or name in seen or type(item["restart"]) is not bool:
            raise ValueError("HOLD_POLICY_UNAPPROVED_SERVICE")
        seen.add(name)
    for field,lo,hi in (
        ("poll_seconds",15,600),("consecutive_failures",2,10),
        ("cooldown_seconds",60,86400),("daily_limit",0,3)):
        n = value.get(field)
        if type(n) is not int or not lo <= n <= hi:
            raise ValueError("HOLD_POLICY_LIMIT_"+field.upper())
    return value

def policy_load(path):
    # A model, public repository or user-supplied URL is never a policy source.
    if path.is_symlink():
        raise ValueError("HOLD_POLICY_SYMLINK")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 32768 or info.st_nlink != 1:
            raise ValueError("HOLD_POLICY_FILE")
        if (info.st_mode & 0o022) or info.st_uid not in (0, os.geteuid()):
            raise ValueError("HOLD_POLICY_PERMISSIONS")
        # Bound the actual read, not just the pre-read size: another writer
        # can grow a file between fstat and JSON parsing.
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            raw = stream.read(32769)
        if len(raw) > 32768:
            raise ValueError("HOLD_POLICY_FILE")
    finally:
        if fd >= 0:
            os.close(fd)
    try:
        # A duplicate 'enabled'/'restart' key must not silently replace an
        # earlier owner value. JSON NaN/Infinity or fractional policy numbers
        # are not a supported admission format.
        value = json.loads(raw, object_pairs_hook=_unique_state_pairs,
                           parse_constant=_reject_state_nonfinite,
                           parse_float=_reject_state_nonfinite)
    except (ValueError, UnicodeError, TypeError) as exc:
        raise ValueError("HOLD_POLICY_CORRUPT") from exc
    return policy_check(value)

def atomic(path, obj):
    if path.is_symlink():
        raise ValueError("HOLD_STATE_SYMLINK")
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".lifeline-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as writer:
            json.dump(obj, writer, sort_keys=True, ensure_ascii=False, allow_nan=False)
            writer.write("\n")
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def _unique_state_pairs(pairs):
    """A duplicate persisted key can erase a previous repair attempt."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("HOLD_STATE_DUPLICATE_KEY")
        result[key] = value
    return result


def _reject_state_nonfinite(value):
    raise ValueError("HOLD_STATE_NONFINITE")


def _read_cgroup_counter(path, *, allow_unlimited=False):
    """Read one small cgroup-v2 scalar without following symlinks or unbounded I/O."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                     getattr(os, "O_CLOEXEC", 0))
    except OSError:
        return None
    try:
        raw = os.read(fd, MEMORY_READ_MAX_BYTES + 1)
    except OSError:
        return None
    finally:
        os.close(fd)
    if not raw or len(raw) > MEMORY_READ_MAX_BYTES:
        return None
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if not raw or b"\n" in raw or b"\r" in raw:
        return None
    if allow_unlimited and raw == b"max":
        return "max"
    if not re.fullmatch(rb"(?:0|[1-9][0-9]{0,19})", raw):
        return None
    value = int(raw)
    return value if value <= MAX_CGROUP_COUNTER else None


def cgroup_memory_snapshot():
    """Report raw cgroup-v2 RAM headroom; missing evidence fails closed in the flag."""
    current = _read_cgroup_counter(CGROUP_MEMORY_CURRENT)
    maximum = _read_cgroup_counter(CGROUP_MEMORY_MAX, allow_unlimited=True)
    if type(current) is int and type(maximum) is int:
        headroom = maximum - current
        status = "OK" if headroom >= 0 else "INCONSISTENT"
        below_floor = headroom < MEMORY_FLOOR_BYTES
    else:
        headroom = None
        status = "UNKNOWN"
        # An unavailable or unlimited limit does not prove the 2 GiB floor.
        below_floor = True
    return {"memory.current": current,
            "memory.max": maximum,
            "raw_headroom_bytes": headroom,
            "below_2GiB": below_floor,
            "status": status}


def read_state(path):
    # Missing state is a first-install bootstrap. Existing unreadable state must
    # HOLD; resetting its retry history could silently reopen the start budget.
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise ValueError("HOLD_STATE_ACCESS") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 262144 or info.st_nlink != 1:
            raise ValueError("HOLD_STATE_FILE")
        # Repair attempts are a security boundary: a mutable or foreign-owned
        # history file could erase hourly/daily limits and authorize extra starts.
        if (info.st_mode & 0o022) or info.st_uid not in (0, os.geteuid()):
            raise ValueError("HOLD_STATE_PERMISSIONS")
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = -1
            try:
                obj = json.load(stream, object_pairs_hook=_unique_state_pairs,
                                parse_constant=_reject_state_nonfinite)
            except (ValueError, UnicodeError) as exc:
                raise ValueError("HOLD_STATE_CORRUPT") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("HOLD_STATE_CORRUPT") from exc
    finally:
        if fd >= 0:
            os.close(fd)
    if not isinstance(obj, dict) or ("services" in obj and not isinstance(obj["services"], dict)):
        raise ValueError("HOLD_STATE_STRUCTURE")
    services = obj.get("services", {})
    # Preserve persisted restart history: never reset a malformed service row.
    if any(not isinstance(name, str) or not isinstance(row, dict)
           for name, row in services.items()):
        raise ValueError("HOLD_STATE_SERVICE_ROW")
    return obj

def stopped():
    # The owner inspector accepts /state/STOP and /state/STOP.flag; lifeline
    # must honor the same manual fences. lstat also fails CLOSED on EACCES
    # (Path.exists/is_symlink may otherwise report both false).
    for name in STOP_FILES:
        try:
            os.lstat(name)
        except FileNotFoundError:
            continue
        except OSError:
            return True
        else:
            return True
    # The original owner's maintenance lease also inhibits repair, even if
    # the legacy flag is absent during an interrupted maintenance operation.
    lease = Path("/root/nox/state/owner_maintenance.lock")
    try:
        fd = os.open(lease, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return False
    except OSError:
        return True
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True
    finally:
        os.close(fd)

def supervise(name, command="status"):
    if name not in SERVICES or command not in ("status", "start"):
        raise ValueError("HOLD_UNAPPROVED_OPERATION")
    try:
        p = subprocess.run(["supervisorctl", command, name], capture_output=True,
                           text=True, shell=False, timeout=12, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"state": "UNKNOWN", "pid": None, "rc": 124}
    if command == "start":
        return {"rc": p.returncode}
    # supervisorctl may include stale status-like stdout on a failed command.
    # Never infer a repairable or healthy state from a nonzero status exit code.
    if p.returncode not in (0, 3):
        return {"state": "UNKNOWN", "pid": None, "rc": p.returncode}
    # Treat unknown output, group names, errors, and missing pid as UNKNOWN.
    first = p.stdout.strip().splitlines()
    match = STATUS.match(first[0]) if len(first) == 1 else None
    if not match or match[1] != name:
        return {"state": "UNKNOWN", "pid": None, "rc": p.returncode}
    # rc=3 is a Supervisor STOPPED/EXITED state, never RUNNING/FATAL proof.
    if p.returncode == 3 and match[2] not in REPAIRABLE:
        return {"state": "UNKNOWN", "pid": None, "rc": p.returncode}
    # Malformed PID evidence may not become a repairable STOPPED/EXITED row.
    # Keep legitimate Supervisor "Not started" and ", uptime" text intact.
    if match[3] is None and re.search(r"\bpid\b", first[0][match.end():], re.IGNORECASE):
        return {"state": "UNKNOWN", "pid": None, "rc": p.returncode}
    state = match[2]
    pid = int(match[3]) if match[3] else None
    if state == "RUNNING" and not pid:
        state = "UNKNOWN"
    # STOPPED/EXITED with an attached PID is contradictory evidence; a live
    # detached listener must not be started over by this health guard.
    if state in REPAIRABLE and pid is not None:
        state, pid = "UNKNOWN", None
    return {"state": state, "pid": pid, "rc": p.returncode}

def _check_all_repair_histories(records, now):
    """Fail before touching ANY service if even a later service ledger is corrupt."""
    if not isinstance(records, dict):
        raise ValueError("HOLD_REPAIR_HISTORY_CORRUPT")
    for name, row in records.items():
        if not isinstance(name, str) or not isinstance(row, dict):
            raise ValueError("HOLD_REPAIR_HISTORY_CORRUPT")
        attempts = row.get("attempts", [])
        failures = row.get("failures", 0)
        if (not isinstance(attempts, list) or
            any(type(x) not in (int, float) or not 0 <= x <= now for x in attempts) or
            attempts != sorted(attempts) or
            type(failures) is not int or not 0 <= failures <= 1000):
            raise ValueError("HOLD_REPAIR_HISTORY_CORRUPT")


def tick(policy, state, *, dry_run=False, now=None, status_fn=supervise, stop_fn=stopped):
    now = time.time() if now is None else now
    observed = []
    records = state.setdefault("services", {})
    _check_all_repair_histories(records, now)
    for spec in policy["services"]:
        name = spec["name"]
        current = status_fn(name, "status")
        row = records.setdefault(name, {})
        if not isinstance(row, dict):
            raise ValueError("HOLD_REPAIR_HISTORY_CORRUPT")
        attempts = row.get("attempts", [])
        if not isinstance(attempts, list) or any(
            type(x) not in (int, float) or not 0 <= x <= now for x in attempts
        ) or attempts != sorted(attempts):
            raise ValueError("HOLD_REPAIR_HISTORY_CORRUPT")
        attempts = [x for x in attempts if now - x < 86400]
        row["attempts"] = attempts
        previous = row.get("failures", 0)
        bad = current.get("state") in REPAIRABLE
        row["failures"] = min(previous + 1, 1000) if bad else 0
        action = "observed_healthy" if current.get("state") == "RUNNING" else "observation_only"
        if current.get("state") in ("UNKNOWN", "FATAL", "BACKOFF", "STARTING", "STOPPING"):
            action = "owner_investigation_required"
        elif bad and row["failures"] >= policy["consecutive_failures"]:
            if stop_fn():
                action = "stop_or_maintenance_lock"
            elif not policy["enabled"] or spec["restart"] is not True:
                action = "owner_authorization_required"
            elif len(attempts) >= policy["daily_limit"]:
                action = "daily_repair_budget_exhausted"
            elif sum(now - x < 3600 for x in attempts) >= 2:
                action = "hourly_repair_budget_exhausted"
            elif attempts and now - attempts[-1] < policy["cooldown_seconds"]:
                action = "repair_cooldown"
            elif dry_run:
                action = "would_start"
            elif stop_fn():
                action = "stop_or_maintenance_lock"
            else:
                # The first STOPPED sample is not a lease on service state.
                # Recheck immediately before admitting any original Supervisor start.
                fresh = status_fn(name, "status")
                if fresh.get("state") not in REPAIRABLE or fresh.get("pid"):
                    action = "service_changed_before_start_hold"
                elif stop_fn():
                    action = "stop_or_maintenance_lock"
                else:
                    # Persist attempt BEFORE action; a crash must not replay it.
                    attempts.append(now)
                    row["attempts"] = attempts
                    atomic(state["_path"], {k:v for k,v in state.items() if k!="_path"})
                    outcome = status_fn(name, "start")
                    verified = status_fn(name, "status")
                    if outcome.get("rc") == 0 and verified.get("state") == "RUNNING" and verified.get("pid"):
                        row["failures"] = 0
                        action = "started_verified"
                    else:
                        action = "start_failed_hold"
        event = {"name": name, "service_state": current.get("state", "UNKNOWN"),
                 "action": action, "attempts_24h": len(row["attempts"])}
        if action in ("owner_investigation_required", "owner_authorization_required",
                      "daily_repair_budget_exhausted", "hourly_repair_budget_exhausted",
                      "service_changed_before_start_hold", "start_failed_hold"):
            event["question"] = ("Check trusted supervisor journal / exact service command and "
                                 "approve a bounded recovery after preserving STOP and checkpoints.")
        observed.append(event)
    report = {"schema": SCHEMA, "at": dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(),
              "observer_only": not policy["enabled"], "results": observed[:MAX_EVENT_ROWS],
              "cgroup_memory": cgroup_memory_snapshot()}
    state["last_report"] = report
    state["at"] = now
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", default="/etc/nox/lifeline.json")
    parser.add_argument("--state", default="/root/nox/state/lifeline/state.json")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    a = parser.parse_args()
    policy_path = Path(a.policy)
    state_path = Path(a.state)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lockpath = state_path.parent / "lifeline.lock"
    lockfd = os.open(lockpath, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("NOX_LIFELINE_ALREADY_RUNNING", flush=True)
        os.close(lockfd)
        return 2
    try:
        while True:
            interval = 60
            try:
                policy = policy_load(policy_path)
                interval = policy["poll_seconds"]
                state = read_state(state_path)
                state["_path"] = state_path
                report = tick(policy, state, dry_run=a.dry_run)
                if not a.dry_run:
                    atomic(state_path, {k:v for k,v in state.items() if k!="_path"})
                print("NOX_LIFELINE_RESULT=" + json.dumps(report, sort_keys=True), flush=True)
            except Exception as exc:
                # Fail closed, do not mutate services. Log code only; no secret details.
                print("NOX_LIFELINE_HOLD=" + type(exc).__name__, flush=True)
                if a.once:
                    return 2
            if a.once:
                break
            time.sleep(interval)  # local bounded poll; never untrusted remote
    finally:
        os.close(lockfd)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
