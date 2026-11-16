#!/usr/bin/env python3
"""Stage owner's FORSAZH=6 / NORMAL=2 selection on original Vast OneHost.

This guarded owner-command writes ONLY a mode-intent record while emergency
MODEL_UPDATE STOP is active. It NEVER starts, restarts, kills or resumes a
process, changes trainer/model/S03/dispatcher config, or clears STOP.
Existing native dispatcher integration must adopt the intent under the
owner-authorized handback after Maya/DeepSeek/web acceptance.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time

ROOT = Path("/root/nox")
STATE = ROOT / "state"
MODE_PATH = STATE / "owner_autonomy_mode_v15.json"
INSTANCE = 60509551
NORMAL = 2
FORSAZH = 6
SCHEMA = "NOX_OWNER_MODE_INTENT_V15"
SHA = re.compile(r"^[0-9a-f]{40}$")
RECEIPT_PREFIX = "NOX_MAINT_REPAIR="
PROTECTED_SERVICES = ("nox-dispatcher-t855u", "nox-chat-8081",
                      "nox-priority-scheduler", "nox-selfheal")


class Hold(RuntimeError):
    pass


def check(value, code):
    if not value:
        raise Hold("HOLD_V15_" + code)


def plain(path):
    check(path.is_absolute(), "PATH_NOT_ABSOLUTE")
    for child in (path, *path.parents):
        check(not child.is_symlink(), "PATH_SYMLINK")
    return path


def checked_supervisor():
    result = {}
    for name in PROTECTED_SERVICES:
        try:
            p = subprocess.run(["supervisorctl", "status", name], capture_output=True,
                               text=True, shell=False, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Hold("HOLD_V15_SUPERVISOR_UNAVAILABLE") from exc
        parts = p.stdout.strip().split()
        check(len(parts) >= 2 and parts[0] == name, "SUPERVISOR_IDENTITY")
        state = parts[1]
        check(state in ("STOPPED", "FATAL", "EXITED"), "NOX_STILL_RUNNING_" +
              name.replace("-", "_").upper())
        result[name] = state
    return result


def required_stop():
    flags = (ROOT / "STOP", STATE / "OWNER_MAINTENANCE.flag")
    for path in flags:
        check(not path.is_symlink(), "STOP_SYMLINK")
        check(path.is_file(), "STOP_NOT_ACTIVE")
        check(path.stat().st_uid == ROOT.stat().st_uid, "STOP_OWNER")
    return True


def atomic_create(path, data):
    plain(path)
    check(not path.exists(), "MODE_INTENT_ALREADY_EXISTS")
    raw = (json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False) + "\n").encode()
    fd, temporary = tempfile.mkstemp(prefix=".owner-mode-", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(raw)
            file.flush()
            os.fsync(file.fileno())
        # Atomic no-clobber publication: an existing owner's newer request wins.
        os.link(temporary, path, follow_symlinks=False)
        os.unlink(temporary)
        dfd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return hashlib.sha256(raw).hexdigest()


def main():
    request = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    source = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    check(os.geteuid() == 0 and request.isdigit() and SHA.fullmatch(source or ""),
          "OWNER_CONTEXT")
    check(ROOT.is_dir() and STATE.is_dir(), "HOST")
    plain(MODE_PATH)
    before = checked_supervisor()
    required_stop()
    if MODE_PATH.exists():
        check(MODE_PATH.is_file(), "EXISTING_MODE_TYPE")
        item = json.loads(MODE_PATH.read_text(encoding="utf-8"))
        check(item.get("schema") == SCHEMA and item.get("selected") == "FORSAZH"
              and item.get("mode_workers") == {"NORMAL": 2, "FORSAZH": 6},
              "EXISTING_OWNER_MODE_CONFLICT")
        output = {"kind": "autonomy_mode_intent_v15", "state": "ALREADY_STAGED",
                  "selected": "FORSAZH", "target_native_workers_after_handback": 6,
                  "active_native_workers_verified": False, "stop_preserved": True,
                  "mode_sha256": hashlib.sha256(MODE_PATH.read_bytes()).hexdigest()}
    else:
        intent = {"schema": SCHEMA, "instance": INSTANCE, "selected": "FORSAZH",
                  "mode_workers": {"NORMAL": NORMAL, "FORSAZH": FORSAZH},
                  "activation": "PENDING_VERIFIED_NEW_MAYA_DEEPSEEK_WEB_HAND_BACK",
                  "created_by_owner_comment_id": request,
                  "owner_source_sha": source,
                  "production_processes_started": False,
                  "native_binding_active_verified": False,
                  "created_unix": time.time()}
        receipt = atomic_create(MODE_PATH, intent)
        output = {"kind": "autonomy_mode_intent_v15", "state": "MODE_FORSAZH_STAGED_STOP_HELD",
                  "selected": "FORSAZH", "normal": NORMAL, "forsazh": FORSAZH,
                  "target_native_workers_after_handback": 6,
                  "active_native_workers_verified": False,
                  "mode_sha256": receipt, "stop_preserved": True,
                  "supervisor_before": before}
    required_stop()
    check(checked_supervisor() == before, "SERVICES_CHANGED")
    print(RECEIPT_PREFIX + json.dumps(output, ensure_ascii=False,
                                      separators=(",", ":")), flush=True)
    print("NOX_MAINT_REPAIR_COMPLETE=true", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        state = str(exc) if isinstance(exc, Hold) else "HOLD_V15_" + type(exc).__name__.upper()
        print(RECEIPT_PREFIX + json.dumps({"kind":"autonomy_mode_intent_v15",
              "state":"HOLD", "reason":state, "active_workers_claimed":0}), flush=True)
        raise SystemExit(2)
