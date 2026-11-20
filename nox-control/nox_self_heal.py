#!/usr/bin/env python3
"""NOX local self-repair observer. Python 3.9+, systemd; no third-party modules.
Local file policy only. Remote manifests and LLM messages cannot authorize repairs.
"""
import argparse
import datetime as datetime
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request
from urllib.parse import urlsplit

UNIT_PATTERN = re.compile(r"^nox-[a-z0-9][a-z0-9_.@-]{0,79}\.service$")

def load(path):
    try:
        value = json.loads(path.read_text(encoding="utf8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temp, path)

def policy_validate(p):
    if p.get("schema_version") != 1 or not isinstance(p.get("services"), list):
        raise ValueError("invalid local policy")
    if len(p["services"]) > 16:
        raise ValueError("too many services")
    units = []
    for svc in p["services"]:
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


def repair_cycle(policy, state_path, dry_run=False):
    state = load(state_path)
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
            if stop.exists():
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
            elif stop.exists():
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
