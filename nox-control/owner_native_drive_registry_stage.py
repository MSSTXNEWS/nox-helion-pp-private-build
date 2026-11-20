#!/usr/bin/env python3
"""Owner-pinned NOX Drive static registry staging on Vast #60509551.

This changes only the dormant dispatcher SOURCE, and never imports/runs the
dispatcher or reloads an active process. No OAuth, queue, model, S03, GPU,
checkpoint, handler invocation, or supervisor mutation. A future separately
admitted controlled dispatcher restart is required for live registration.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

SCHEMA = "NOX_OWNER_DRIVE_REGISTRY_STAGE_V1"
INSTANCE = 60509551
EXPECTED_DISPATCHER_SHA = "c9d08cbcd6afe91259129a154b31038ebacd50f648e027eac9fa89a2094f5649"
EXPECTED_BRIDGE_SHA = "9916a1ff5be7c8182fdef71d2477ecb50fa7aa1ef6f6d0c79a39b436f4dc22f6"
SOURCE = Path("/root/nox/scripts/nox_dispatcher_t855u.py")
BRIDGE = Path("/root/nox/ops/drive-auth/nox_drive_native_binding.py")
BACKUPS = Path("/root/nox/ops/drive-auth/private/dispatcher-backups")
STOP = ("/root/nox/STOP", "/root/nox/STOP.flag", "/root/nox/state/STOP",
        "/root/nox/state/OWNER_MAINTENANCE.flag", "/workspace/NOX_STOP")
HANDLER = "nox.drive.first.native.v1"
START = "# NOX_DRIVE_FIRST_STATIC_V1_START"
END = "# NOX_DRIVE_FIRST_STATIC_V1_END"

# This is registered into the SAME in-process HANDLERS dict. It accepts
# only a native claimed task, reuses existing host priority callbacks, and
# returns a success only after full remote or SSD SHA readback.
SHIM = '''# NOX_DRIVE_FIRST_STATIC_V1_START
def _nox_drive_first_native_handler(task):
    import os as _os
    import shutil as _shutil
    import sys as _sys
    from pathlib import Path as _Path
    from types import SimpleNamespace as _SimpleNamespace
    if (not isinstance(task, dict)
            or task.get("handler") != "nox.drive.first.native.v1"
            or task.get("status") != "running"
            or not isinstance(task.get("params"), dict)
            or not isinstance(task.get("claim"), dict)
            or not isinstance(task["claim"].get("nonce"), str)
            or len(task["claim"]["nonce"]) < 12):
        raise RuntimeError("HOLD_DRIVE_NATIVE_OWNER_CLAIM")
    _flags = ("/root/nox/STOP", "/root/nox/STOP.flag", "/root/nox/state/STOP",
              "/root/nox/state/OWNER_MAINTENANCE.flag", "/workspace/NOX_STOP",
              "/root/nox/state/DRIVE_STOP.flag")
    def _stopped():
        return any(_os.path.lexists(p) for p in _flags)
    def _lease_current():
        return (task.get("status") == "running"
                and isinstance(task.get("claim"), dict)
                and isinstance(task["claim"].get("nonce"), str)
                and len(task["claim"]["nonce"]) >= 12
                and not _stopped())
    def _foreground_active():
        try:
            return _nox_owner_boost_active() is not False
        except Exception:
            return True
    def _admission(kind):
        if kind != "IO_LIGHT" or _stopped() or not _lease_current():
            return False
        if _foreground_active():
            return False
        try:
            cg = _Path("/sys/fs/cgroup")
            maximum = (cg / "memory.max").read_text().strip()
            current = int((cg / "memory.current").read_text().strip())
            if not maximum.isdecimal() or int(maximum) - current < 384 * 1024**2:
                return False
            if _shutil.disk_usage("/var/lib/nox-drive-reconnect").free < 2 * 1024**3:
                return False
            return True
        except (OSError, ValueError):
            return False
    if _stopped() or _foreground_active() or not _admission("IO_LIGHT"):
        raise RuntimeError("HOLD_DRIVE_NATIVE_STOP_CHAT_OR_RESOURCES")
    _directory = "/root/nox/ops/drive-auth"
    if _directory not in _sys.path:
        _sys.path.insert(0, _directory)
    from nox_drive_native_binding import NativeDriveBridge as _Bridge
    _callbacks = {
        "stop_active": _stopped,
        "lease_current": _lease_current,
        "foreground_active": _foreground_active,
        "resource_admission": _admission,
    }
    _bridge = _Bridge(_callbacks)
    _cancel = _SimpleNamespace(cancelled=lambda: _stopped() or not _lease_current())
    _receipt = _bridge.worker(task["params"], cancel=_cancel)
    if (not isinstance(_receipt, dict)
            or _receipt.get("remote_verified") is not True
            or _receipt.get("original_task_accepted") is not False
            or _receipt.get("state") not in (
                "VERIFIED_DRIVE_TRANSFER", "VERIFIED_SSD_STAGE_NOT_GPU_LOADED")):
        raise RuntimeError("HOLD_DRIVE_NATIVE_NO_VERIFIED_RECEIPT")
    return _receipt

HANDLERS["nox.drive.first.native.v1"] = _nox_drive_first_native_handler
# NOX_DRIVE_FIRST_STATIC_V1_END
'''


class Hold(RuntimeError):
    pass


def require(ok, code):
    if not ok:
        raise Hold("HOLD_DRIVE_REGISTRY_" + code)


def digest(b):
    return hashlib.sha256(b).hexdigest()


def private_regular(path, limit):
    require(path.is_absolute() and not path.is_symlink()
            and not any(p.is_symlink() for p in path.parents), "LINK")
    st = path.stat()
    require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1
            and st.st_uid == os.geteuid()
            and not (st.st_mode & 0o022)
            and 0 < st.st_size <= limit, "FILE_SCOPE")
    raw = path.read_bytes()
    require(len(raw) == st.st_size, "FILE_CHANGED")
    return raw, st


def assert_dispatcher_source(raw):
    tree = ast.parse(raw.decode("utf-8"))
    registry = [n for n in tree.body
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "HANDLERS" for t in n.targets)]
    require(len(registry) == 1 and isinstance(registry[0].value, ast.Dict), "REGISTRY_SHAPE")
    require(len(registry[0].value.keys) == 21, "REGISTRY_COUNT")
    names = [k.value for k in registry[0].value.keys if isinstance(k, ast.Constant)
             and isinstance(k.value, str)]
    require(len(names) == 21 and len(set(names)) == 21, "REGISTRY_KEYS")
    require(not any(isinstance(k, ast.Constant) and k.value == HANDLER
                    for k in registry[0].value.keys), "REGISTRY_CONFLICT")
    run_one = [n for n in tree.body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == "run_one"]
    require(len(run_one) == 1 and any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "handler"
        for n in ast.walk(run_one[0])), "RUN_ONE_CONTRACT")
    require(any(isinstance(n, ast.FunctionDef) and n.name == "_nox_owner_boost_active"
                for n in tree.body), "CHAT_PRIORITY_CALLBACK")
    return registry[0].end_lineno


def make_patched(raw):
    require(START.encode() not in raw and END.encode() not in raw, "ALREADY_PATCHED")
    insertion = assert_dispatcher_source(raw)
    lines = raw.decode("utf-8").splitlines(keepends=True)
    require(0 < insertion < len(lines), "REGISTRY_POSITION")
    prefix = "".join(lines[:insertion])
    suffix = "".join(lines[insertion:])
    require(prefix.endswith("\n"), "LINE_ENDING")
    changed = (prefix + "\n" + SHIM + "\n" + suffix).encode("utf-8")
    compile(changed, "nox_dispatcher_t855u.py", "exec")
    require(changed.count(START.encode()) == 1 and changed.count(END.encode()) == 1,
            "MARKER_COUNT")
    return changed


def owner_context():
    source_sha = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    request_id = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    require(re.fullmatch(r"[0-9a-f]{40}", source_sha) is not None
            and re.fullmatch(r"[1-9][0-9]{0,23}", request_id) is not None,
            "OWNER_COMMAND")
    require(os.geteuid() == 0, "UID")
    require(not any(os.path.lexists(path) for path in STOP), "STOP")
    return source_sha, request_id


def secure_backup(path, raw):
    parent = path.parent
    require(parent.exists() and parent.is_dir() and parent.stat().st_uid == os.geteuid()
            and not parent.stat().st_mode & 0o077, "BACKUP_PARENT")
    if not path.exists():
        path.mkdir(mode=0o700)
    require(path.is_dir() and not path.is_symlink()
            and path.stat().st_uid == os.geteuid()
            and not path.stat().st_mode & 0o077, "BACKUP_DIR")
    filename = path / ("nox-dispatcher-before-drive-" + digest(raw)[:20] + ".py")
    if filename.exists():
        prior, _ = private_regular(filename, 180000)
        require(prior == raw, "BACKUP_CONFLICT")
        return digest(prior), False
    fd = os.open(filename, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    require(filename.read_bytes() == raw, "BACKUP_READBACK")
    return digest(raw), True


def stage(*, source=SOURCE, bridge=BRIDGE, backups=BACKUPS,
          expected_dispatcher=EXPECTED_DISPATCHER_SHA,
          expected_bridge=EXPECTED_BRIDGE_SHA, service_check=True):
    original, st = private_regular(source, 180000)
    current_hash = digest(original)
    if START.encode() in original or END.encode() in original:
        require(START.encode() in original and END.encode() in original
                and original.count(START.encode()) == 1
                and original.count(END.encode()) == 1, "PARTIAL_PATCH")
        return {"state": "ALREADY_STAGED_NOT_LIVE", "new_sha256": current_hash,
                "native_handler_registered": False, "restarted": False}
    require(current_hash == expected_dispatcher, "DISPATCHER_SHA_DRIFT")
    payload, _ = private_regular(bridge, 100000)
    require(digest(payload) == expected_bridge, "BRIDGE_SHA_DRIFT")
    if service_check:
        try:
            run = subprocess.run(["supervisorctl", "status", "nox-dispatcher-t855u"],
                                 capture_output=True, timeout=8, check=False)
            require(run.returncode == 0 and b"RUNNING" in run.stdout,
                    "SERVICE_NOT_RUNNING")
        except (OSError, subprocess.TimeoutExpired):
            raise Hold("HOLD_DRIVE_REGISTRY_SERVICE_UNVERIFIED") from None
    changed = make_patched(original)
    backup_sha, backup_created = secure_backup(backups, original)
    require(backup_sha == current_hash, "BACKUP_MISMATCH")
    require(not any(os.path.lexists(path) for path in STOP), "STOP_CHANGED")
    # Exact preimage compare immediately before replace. Do not alter a newer source.
    reread, _ = private_regular(source, 180000)
    require(reread == original, "PREIMAGE_CHANGED")
    temp = source.with_name("." + source.name + ".drive-stage")
    require(not os.path.lexists(temp), "TEMP_EXISTS")
    try:
        fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(changed)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, stat.S_IMODE(st.st_mode))
        require(temp.read_bytes() == changed, "TEMP_READBACK")
        require(not any(os.path.lexists(path) for path in STOP), "STOP_CHANGED")
        require(source.read_bytes() == original, "PREIMAGE_RACE")
        os.replace(temp, source)
        require(source.read_bytes() == changed, "FINAL_READBACK")
    finally:
        temp.unlink(missing_ok=True)
    return {
        "state": "SOURCE_STAGED_NOT_LIVE",
        "previous_sha256": current_hash,
        "new_sha256": digest(changed),
        "backup_sha256": backup_sha,
        "backup_created": backup_created,
        "native_handler_registered": False,
        "restarted": False,
        "google_oauth_updated": False,
        "model_or_s03_modified": False,
        "weights_modified": False,
    }


def main():
    source_sha, request_id = "", ""
    try:
        source_sha, request_id = owner_context()
        result = stage()
    except Hold as exc:
        result = {"state": str(exc), "native_handler_registered": False,
                  "restarted": False, "google_oauth_updated": False}
        print("NOX_MAINT_DRIVE_REGISTRY_STAGE=" + json.dumps(result, sort_keys=True),
              flush=True)
        return 2
    except Exception as exc:
        result = {"state": "HOLD_DRIVE_REGISTRY_" + type(exc).__name__.upper(),
                  "native_handler_registered": False,
                  "restarted": False, "google_oauth_updated": False}
        print("NOX_MAINT_DRIVE_REGISTRY_STAGE=" + json.dumps(result, sort_keys=True),
              flush=True)
        return 2
    result.update(schema=SCHEMA, instance_id=INSTANCE, source_sha=source_sha,
                  request_id=request_id)
    print("NOX_MAINT_DRIVE_REGISTRY_STAGE=" + json.dumps(result, sort_keys=True),
          flush=True)
    print("NOX_MAINT_DRIVE_REGISTRY_STAGE_COMPLETE=true", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
