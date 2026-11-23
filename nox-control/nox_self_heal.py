#!/usr/bin/env python3
"""NOX local self-repair observer. Python 3.9+, systemd; no third-party modules.
Local file policy only. Remote manifests and LLM messages cannot authorize repairs.
"""
import argparse
import datetime as datetime
import fcntl
import json
import math
import os
from pathlib import Path
import re
import subprocess
import stat
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit

UNIT_PATTERN = re.compile(r"^nox-[a-z0-9][a-z0-9_.@-]{0,79}\.service$")
MAX_REPAIR_STATE_BYTES = 1 << 20  # 1 MiB; well above 16 scoped units.

def load(path):
    try:
        value = json.loads(path.read_text(encoding="utf8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}

def write(path, value):
    """Atomically persist a private state snapshot without following a fixed .tmp.

    A predictable temporary filename could collide with another repair cycle
    or point at an unrelated file. mkstemp creates a private O_EXCL file in the
    same directory so os.replace remains atomic.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp",
                                   dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf8") as fh:
            json.dump(value, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
        tmp_name = None
        # Persist the directory entry as well as the JSON bytes.
        dir_fd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if tmp_name is not None:
            os.unlink(tmp_name)

def policy_validate(p):
    if p.get("schema_version") != 1 or not isinstance(p.get("services"), list):
        raise ValueError("invalid local policy")
    if len(p["services"]) > 16:
        raise ValueError("too many services")
    # A string such as "false" is truthy in Python and could silently turn
    # on a repair route. Only literal JSON booleans may authorize restarts.
    if "enabled" in p and type(p["enabled"]) is not bool:
        raise ValueError("invalid repair policy enabled flag")
    units = []
    for svc in p["services"]:
        if not isinstance(svc, dict):
            raise ValueError("invalid repair service entry")
        if "restart_enabled" in svc and type(svc["restart_enabled"]) is not bool:
            raise ValueError("invalid service restart flag")
        name = svc.get("unit", "")
        if not isinstance(name, str) or not UNIT_PATTERN.fullmatch(name) or name in units:
            raise ValueError("invalid or duplicate NOX unit")
        units.append(name)
        url = svc.get("health_url")
        if url is not None and not _is_loopback_probe(url):
            raise ValueError("health probes must be unauthenticated loopback HTTP")
    return p

class _DenyProbeRedirect(urllib.request.HTTPRedirectHandler):
    """A redirected health response cannot prove the pinned local service is healthy."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _is_loopback_probe(url):
    if not isinstance(url, str) or not url:
        return False
    try:
        parsed = urlsplit(url)
        _ = parsed.port  # Reject malformed ports before opening the URL.
    except ValueError:
        return False
    return (parsed.scheme == "http" and
            parsed.hostname in ("localhost", "127.0.0.1", "::1") and
            parsed.username is None and parsed.password is None and
            not parsed.fragment)


def alive(service, health_url=None):
    try:
        p = subprocess.run(["systemctl", "is-active", "--quiet", service],
                           shell=False, timeout=8, check=False)
        if p.returncode:
            return False
        if health_url:
            if not _is_loopback_probe(health_url):
                return False
            # Never inherit HTTP proxy settings or follow an endpoint redirect
            # to an unrelated service (or an external host).
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}), _DenyProbeRedirect())
            with opener.open(health_url, timeout=4) as res:
                return 200 <= res.status < 300
        return True
    except (OSError, ValueError, TimeoutError):
        return False

def _unit_confirmed_inactive(service):
    """Fail closed unless systemd confirms failure and no current MainPID.

    A nonzero `is-active` status (including exit 3) is ambiguous: it can
    describe intentionally inactive units as well as failed ones. HTTP probe
    failure is likewise not owner permission to restart healthy processes.
    This is only a conservative additional source guard, not a native
    owner/PID-startticks/lease/STOP authorization for an emergency restart.
    """
    try:
        failed = subprocess.run(["systemctl", "is-failed", service],
                                shell=False, timeout=8, check=False,
                                capture_output=True, text=True)
        if failed.returncode != 0 or failed.stdout.strip() != "failed":
            return False
        pid = subprocess.run(["systemctl", "show", service, "--property=MainPID", "--value"],
                             shell=False, timeout=8, check=False,
                             capture_output=True, text=True)
        return pid.returncode == 0 and pid.stdout.strip() == "0"
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False


def _reject_repair_state_duplicate_keys(pairs):
    """A later JSON key may not erase prior restart attempts or failure counts."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate repair state JSON key")
        result[key] = value
    return result


def _stop_marker_present_or_unknown(path):
    """STOP is clear only when lstat proves the path itself is absent.

    Path.exists() follows a symlink: a dangling STOP link was treated as
    missing and could authorize a restart. Permission/IO errors likewise
    must not turn an unknown STOP into permission to mutate a service.
    This local fence does not substitute for native owner STOP/lease/CAS.
    """
    # The parent directory is part of the STOP fence. If it is missing,
    # replaced by a symlink, or unreadable, treating an absent STOP filename
    # as permission to restart would fail open. Check the final directory
    # component without following its symlink before inspecting the marker.
    try:
        parent = os.stat(Path(path).parent, follow_symlinks=False)
        if not stat.S_ISDIR(parent.st_mode):
            return True
    except OSError:
        return True
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def _read_repair_state_checked(path):
    """An invalid EXISTING state must not silently reset restart safety budgets.

    A missing state is valid for first boot. A corrupt one requires an owner
    repair; preserve its original bytes, do not probe or restart anything.
    """
    # Open once, refuse symlinks/special devices, and bound the total bytes.
    # An attacker-supplied FIFO or huge file must never hang or exhaust the
    # single-writer restart observer before it can fail safely.
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW |
                     os.O_CLOEXEC | os.O_NONBLOCK)
    except FileNotFoundError:
        if path.is_symlink():  # Broken link is not an absent trusted state.
            raise ValueError("invalid repair state symlink") from None
        return {}
    except OSError:
        raise ValueError("unreadable repair state") from None
    try:
        with os.fdopen(fd, "rb") as fh:
            info = os.fstat(fh.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_REPAIR_STATE_BYTES:
                raise ValueError("invalid repair state file")
            raw_bytes = fh.read(MAX_REPAIR_STATE_BYTES + 1)
            if len(raw_bytes) > MAX_REPAIR_STATE_BYTES:
                raise ValueError("oversized repair state")
            raw = raw_bytes.decode("utf-8")
    except (OSError, UnicodeError):
        raise ValueError("unreadable repair state") from None
    try:
        state = json.loads(raw, object_pairs_hook=_reject_repair_state_duplicate_keys)
    except (ValueError, TypeError):
        raise ValueError("invalid repair state JSON") from None
    if not isinstance(state, dict):
        raise ValueError("invalid repair state object")
    # A wall-clock rollback must not quietly erase restart attempts from the
    # rolling 24-hour budget. A future attempt requires owner inspection.
    now = time.time()
    services = state.get("services", {})
    if not isinstance(services, dict):
        raise ValueError("invalid repair service records")
    for unit, entry in services.items():
        if not isinstance(unit, str) or not isinstance(entry, dict):
            raise ValueError("invalid repair service entry")
        failures = entry.get("failures")
        attempts = entry.get("attempts")
        if type(failures) is not int or not 0 <= failures <= 1000000000:
            raise ValueError("invalid repair failure counter")
        if not isinstance(attempts, list) or len(attempts) > 10000:
            raise ValueError("invalid repair attempt list")
        for timestamp in attempts:
            if type(timestamp) not in (int, float):
                raise ValueError("invalid repair attempt timestamp")
            try:
                valid = math.isfinite(timestamp) and 0 <= timestamp <= 1e12
            except (OverflowError, ValueError):
                valid = False
            if not valid or timestamp > now:
                raise ValueError("invalid repair attempt timestamp")
    return state


def repair_cycle(policy, state_path, dry_run=False):
    """Run one repair observation under an exclusive, nonblocking state lease.

    Atomic replace alone does not prevent two observers from reading the same
    failures/attempt counter and then overwriting each other's snapshots.
    Keep a persistent sidecar inode so a concurrent process cannot race the
    check -> recorded attempt -> optional action sequence. A busy owner fails
    closed; it never causes a second systemctl restart or false receipt.
    """
    state_path = Path(state_path)
    # Dry-run is an observation, not a writer. It cannot persist state or
    # restart units, and must not create a lock file or missing directory.
    # Atomic state replacement also gives it a complete snapshot if a writer
    # happens to be active in parallel.
    if dry_run:
        return _repair_cycle_locked(policy, state_path, dry_run=True)
    lock_path = state_path.with_name(state_path.name + ".writer.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # A pre-existing FIFO, directory, shared-mode or foreign-owned sidecar
    # cannot serve as a trustworthy single-writer lock. NONBLOCK also prevents
    # a hostile FIFO from hanging the observer before its safety checks.
    fd = os.open(str(lock_path),
                 os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW |
                 os.O_CLOEXEC | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                info.st_uid != os.geteuid() or info.st_mode & 0o077):
            raise ValueError("unsafe repair writer lock")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Reject a sidecar replaced between open and lease acquisition.
        # This is an additional local inode fence, not native owner CAS.
        current = os.stat(lock_path, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError("repair writer lock changed")
        return _repair_cycle_locked(policy, state_path, dry_run)
    finally:
        os.close(fd)


def _repair_cycle_locked(policy, state_path, dry_run=False):
    try:
        state = _read_repair_state_checked(state_path)
    except ValueError:
        # Preserve bad state for owner recovery. Never reset counters or
        # restart from a fabricated empty state; no file write on this path.
        return [{"unit": service["unit"], "healthy_before": None,
                 "action": "state_invalid_hold",
                 "question": "Restore reviewed repair-state bytes before retry."}
                for service in policy["services"]]
    services = state.setdefault("services", {})
    if not isinstance(services, dict):
        services = state["services"] = {}
    stop = Path(policy.get("stop_file", "/var/lib/nox/STOP"))
    now = time.time()
    result = []
    for config in policy["services"]:
        unit = config["unit"]
        entry = services.setdefault(unit, {"failures": 0, "attempts": []})
        healthy = alive(unit, config.get("health_url"))
        entry["failures"] = 0 if healthy else int(entry.get("failures", 0)) + 1
        entry["attempts"] = [x for x in entry.get("attempts", []) if
                             isinstance(x, (int, float)) and 0 <= now - x < 86400]
        action = "healthy" if healthy else "observe"
        if not healthy and entry["failures"] >= max(2, int(config.get("failures_before_restart", 3))):
            if _stop_marker_present_or_unknown(stop):
                action = "stop_lock"
            elif not policy.get("enabled") or not config.get("restart_enabled"):
                action = "needs_owner_approval"
            elif len(entry["attempts"]) >= min(3, max(0, int(policy.get("daily_restart_limit", 2)))):
                action = "needs_owner_investigation"
            elif entry["attempts"] and now - entry["attempts"][-1] < max(60, int(policy.get("cooldown_seconds", 900))):
                action = "cooldown"
            elif not _unit_confirmed_inactive(unit):
                action = "needs_owner_investigation"
            elif dry_run:
                action = "would_restart"
            elif _stop_marker_present_or_unknown(stop):
                action = "stop_lock"
            else:
                entry["attempts"].append(now)
                write(state_path, state)  # record attempt before mutation
                try:
                    p = subprocess.run(["systemctl", "restart", unit], shell=False,
                                       timeout=40, capture_output=True, check=False)
                    time.sleep(2)
                    action = "restart_verified" if p.returncode == 0 and alive(unit, config.get("health_url")) else "restart_failed"
                    if action == "restart_verified":
                        entry["failures"] = 0
                except (OSError, subprocess.TimeoutExpired):
                    action = "restart_failed"
        row = {"unit": unit, "healthy_before": healthy, "action": action}
        if action in ("needs_owner_approval", "needs_owner_investigation", "restart_failed"):
            row["question"] = "Inspect journalctl and authorize further local repair if needed."
        result.append(row)
    state["checked_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state["last_results"] = result
    if not dry_run:
        write(state_path, state)
    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", required=True)
    ap.add_argument("--state", default="/var/lib/nox/repair-state.json")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    policy = policy_validate(load(Path(args.policy)))
    while True:
        try:
            rows = repair_cycle(policy, Path(args.state), args.dry_run)
            print(json.dumps({"event": "NOX_REPAIR", "results": rows}), flush=True)
        except Exception as exc:
            print(json.dumps({"event": "NOX_REPAIR_ERROR", "type": type(exc).__name__}), flush=True)
        if args.once:
            break
        time.sleep(min(600, max(30, int(policy.get("poll_seconds", 60)))))

if __name__ == "__main__":
    main()
