#!/usr/bin/env python3
"""NOX Drive native task adapter; the existing dispatcher alone owns the queue.

A model may propose a Drive-first action, never approve/execute it itself.
Host must bind callbacks from its existing owner-authenticated queue, STOP,
CAS lease, resource gate and foreground-chat priority. Not a second daemon.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace

import nox_drive_first as drive
import nox_drive_prefetch as cache

SCHEMA = "NOX_DRIVE_NATIVE_TASK_V1"
HANDLER_KIND = "nox.drive.first.native.v1"
MANIFEST_DIR = Path("/root/nox/ops/drive-auth/private/drive-tasks")
SSD_ROOT = Path("/var/lib/nox-drive-reconnect/cache/warm-ssd")
SHA = re.compile(r"[0-9a-f]{64}\Z")
TASK = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")
OPERATIONS = ("offload", "ingest", "restore_ssd")
CALLBACKS = ("is_owner", "stop_active", "lease_current",
             "foreground_active", "resource_admission", "enqueue")
WORKER_CALLBACKS = ("stop_active", "lease_current",
                    "foreground_active", "resource_admission")


class Hold(Exception):
    pass


def require(value, reason):
    if not value:
        raise Hold("HOLD_DRIVE_NATIVE_" + reason)


def capability_descriptor():
    """Instruction/tool binding for the existing NOX planner; no live claim."""
    return {
        "schema": "NOX_DRIVE_FIRST_TOOL_DESCRIPTOR_V1",
        "name": "nox_drive_first",
        "handler_kind": HANDLER_KIND,
        "operations": {
            "offload": "Existing owner-approved inactive .gguf/.safetensors from the model directory to Google Drive WARM with SHA readback; never delete source.",
            "ingest": "Owner-reviewed HTTPS source directly to Google Drive DOWNLOADS, transparently chunked; never spool whole weight to SSD.",
            "restore_ssd": "Verified Google Drive WARM weight through existing NOX prefetch into private SSD cache; RAM/GPU loading is separate.",
        },
        "selection": {
            "download_new_weight": "ingest",
            "archive_inactive_weight": "offload",
            "need_warm_weight_for_model": "restore_ssd",
        },
        "requirements": [
            "Exact owner-approved private manifest path+SHA256",
            "Existing authenticated owner and valid existing CAS lease",
            "Actual Google Drive OAuth in NOX and approved root",
            "STOP clear; foreground chat idle; fresh resource admission",
            "Actual remote full SHA readback, owner-private result receipt",
        ],
        "submits_to_existing_queue": True,
        "creates_extra_service_or_gpu_model": False,
        "personal_s03_or_checkpoint_transfer": False,
        "may_delete_original": False,
        "can_claim_live_without_native_receipt": False,
    }


def private_manifest(path, sha, root=MANIFEST_DIR):
    """Do not let model-chosen paths point outside the private owner queue."""
    require(isinstance(path, str) and isinstance(sha, str)
            and SHA.fullmatch(sha) is not None, "MANIFEST_INPUT")
    p = Path(os.path.abspath(path))
    require(p.parent == root and not p.is_symlink() and
            not any(part.is_symlink() for part in p.parents),
            "MANIFEST_SCOPE")
    require(p.is_file(), "MANIFEST_MISSING")
    st = p.stat()
    require(st.st_uid == os.geteuid() and st.st_nlink == 1
            and not st.st_mode & 0o077 and 0 < st.st_size <= 65536,
            "MANIFEST_PERMISSIONS")
    raw = p.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == sha, "MANIFEST_CHANGED")
    return p


def validated_task(operation, task_id, path, sha, *, root=MANIFEST_DIR):
    require(operation in OPERATIONS and isinstance(task_id, str)
            and TASK.fullmatch(task_id) is not None, "REQUEST")
    path = private_manifest(path, sha, root=root)
    if operation in ("offload", "ingest"):
        m = drive.load_manifest(path, sha)
        require(m["task_id"] == task_id and m["action"] == operation,
                "MANIFEST_BINDING")
    else:
        m = cache.read_manifest(path, sha)
        require(m["remote"] == "noxchunks:WARM", "RESTORE_SOURCE")
        require(len(m["assets"]) == 1, "RESTORE_ASSET_COUNT")
    return m


def oauth_present(config=drive.CONFIG):
    """Configuration presence, NOT claim of a successful Google read/write."""
    try:
        import configparser
        p = drive.private_file(config, max_bytes=131072)
        cp = configparser.RawConfigParser(interpolation=None)
        cp.read_string(p.read_text(encoding="utf-8"))
        return (cp.has_section("noxdrive") and cp.get("noxdrive","type",fallback="")=="drive"
                and cp.get("noxdrive","root_folder_id",fallback="")==drive.ROOT_ID
                and any(cp.get("noxdrive",name,fallback="").strip() for name in
                        ("token","service_account_file","service_account_credentials")))
    except (OSError, ValueError, UnicodeError, drive.Hold):
        return False


class NativeDriveBridge:
    def __init__(self, bindings, *, config=drive.CONFIG, state=drive.STATE,
                 manifest_root=MANIFEST_DIR, ssd=SSD_ROOT):
        require(isinstance(bindings, dict)
                and set(bindings) in (set(CALLBACKS), set(WORKER_CALLBACKS))
                and all(callable(v) for v in bindings.values()),
                "HOST_CALLBACKS")
        self.cb = bindings
        self.config = config
        self.state = state
        self.manifest_root = manifest_root
        self.ssd = ssd

    def owner_gate(self, actor):
        if "is_owner" not in self.cb:
            return False  # A worker-only binding can never authorize proposals.
        try:
            return (self.cb["is_owner"](actor) is True
                    and self.cb["lease_current"]() is True
                    and self.cb["stop_active"]() is False)
        except Exception:
            return False

    def worker_gate(self):
        try:
            return (self.cb["lease_current"]() is True
                    and self.cb["stop_active"]() is False
                    and self.cb["foreground_active"]() is False
                    and self.cb["resource_admission"]("IO_LIGHT") is True)
        except Exception:
            return False

    def propose(self, *, actor, task_id, operation, manifest, manifest_sha,
                remote_opt_in=False):
        """Owner intent becomes one native queue item, never an inline transfer."""
        if remote_opt_in is not True or not self.owner_gate(actor):
            return {"state": "HOLD_OWNER_AUTH_OR_LEASE", "native_job_started": False}
        try:
            validated_task(operation, task_id, manifest, manifest_sha,
                           root=self.manifest_root)
        except (Hold, drive.Hold, cache.Hold, ValueError, OSError):
            return {"state": "HOLD_OWNER_MANIFEST", "native_job_started": False}
        if not oauth_present(self.config):
            return {"state": "HOLD_GOOGLE_OAUTH_REQUIRED", "native_job_started": False}
        payload = {
            "schema": SCHEMA, "task_id": task_id, "operation": operation,
            "manifest": manifest, "manifest_sha": manifest_sha,
        }
        payload["idempotency_key"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if "enqueue" not in self.cb:
            return {"state": "HOLD_EXISTING_QUEUE", "native_job_started": False}
        try:
            receipt = self.cb["enqueue"](HANDLER_KIND, payload,
                                         payload["idempotency_key"])
        except Exception:
            return {"state": "HOLD_EXISTING_QUEUE", "native_job_started": False}
        if not isinstance(receipt, dict) or not isinstance(receipt.get("job_id"), str):
            return {"state": "HOLD_QUEUE_RECEIPT", "native_job_started": False}
        return {
            "state": "QUEUED_NOT_EXECUTED",
            "task_id": task_id, "job_id": receipt["job_id"],
            "existing_native_queue": True,
            "remote_verified": False, "original_task_accepted": False,
        }

    def worker(self, payload, *, cancel):
        """Host's existing leased native worker invokes this, never model text."""
        if (not isinstance(payload, dict)
                or set(payload) != {"schema","task_id","operation","manifest","manifest_sha","idempotency_key"}
                or payload.get("schema") != SCHEMA):
            return {"state": "HOLD_NATIVE_JOB_SCHEMA", "remote_verified": False}
        value = {k: payload[k] for k in
                 ("schema","task_id","operation","manifest","manifest_sha")}
        if (not isinstance(payload["idempotency_key"], str)
                or hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()
                                  ).hexdigest() != payload["idempotency_key"]):
            return {"state": "HOLD_NATIVE_JOB_PIN", "remote_verified": False}
        if cancel is None or not callable(getattr(cancel,"cancelled",None)) and not hasattr(cancel,"cancelled"):
            return {"state": "HOLD_NATIVE_CANCEL", "remote_verified": False}

        def cancelled():
            val = getattr(cancel,"cancelled")
            return val() is True if callable(val) else val is True

        if cancelled() or not self.worker_gate():
            return {"state": "DEFERRED_OWNER_OR_CHAT", "remote_verified": False}
        if not oauth_present(self.config):
            return {"state": "HOLD_GOOGLE_OAUTH_REQUIRED", "remote_verified": False}
        try:
            m = validated_task(payload["operation"],payload["task_id"],
                               payload["manifest"],payload["manifest_sha"],
                               root=self.manifest_root)
        except (Hold, drive.Hold, cache.Hold, ValueError, OSError):
            return {"state": "HOLD_NATIVE_MANIFEST_DRIFT", "remote_verified": False}
        if cancelled() or not self.worker_gate():
            return {"state": "DEFERRED_OWNER_OR_CHAT", "remote_verified": False}
        try:
            if payload["operation"] in ("ingest","offload"):
                result = drive.execute(m, self.config, self.state)
                require(result.get("state")=="VERIFIED_IN_DRIVE"
                        and result.get("readback_verified") is True
                        and result.get("source_deleted") is False, "NO_REMOTE_RECEIPT")
                return {"state":"VERIFIED_DRIVE_TRANSFER",
                        "task_id":payload["task_id"],
                        "remote_verified":True,"weights_modified":False,
                        "original_task_accepted":False}
            # Existing reviewed prefetch, NOT inference or RAM allocation.
            result = cache.run(SimpleNamespace(
                manifest=payload["manifest"], manifest_sha=payload["manifest_sha"],
                destination=str(self.ssd), ssd=None, mode="disk", execute=True
            ))
            require(result.get("state")=="VERIFIED_STAGE_NOT_LOADED"
                    and all(row.get("result") in ("CACHE_HIT","VERIFIED_NEW")
                            for row in result.get("assets",[])), "RESTORE_READBACK")
            return {"state":"VERIFIED_SSD_STAGE_NOT_GPU_LOADED",
                    "task_id":payload["task_id"],
                    "remote_verified":True,"weights_modified":False,
                    "original_task_accepted":False}
        except (Hold, drive.Hold, cache.Hold, ValueError, OSError):
            return {"state":"HOLD_NATIVE_DRIVE_EXECUTION",
                    "remote_verified":False,"original_task_accepted":False}

    def register_to_existing_dispatcher(self, register_handler, *, actor):
        """Requires the real owner's reviewed host registrar; no shadow queue."""
        if not callable(register_handler) or not self.owner_gate(actor):
            return {"state":"HOLD_NATIVE_REGISTRATION"}
        result=register_handler(HANDLER_KIND, self.worker)
        return {"state": "HOST_REGISTRATION_REQUESTED" if result is True
                 else "HOLD_NATIVE_REGISTRATION",
                "native_execution_verified": False}


def bind_static_native_handlers(handlers, worker_bindings, *,
                                owner_authorized, cancel_for_task,
                                config=drive.CONFIG, state=drive.STATE,
                                manifest_root=MANIFEST_DIR, ssd=SSD_ROOT):
    """Add one handler to the EXISTING in-process registry at reviewed startup.

    Never executes an owner command, creates a queue or claims a live process.
    Production host must supply its actual auth, lease, chat, resource and
    cancellation callbacks; mere source installation never calls this helper.
    """
    if not isinstance(handlers, dict) or not callable(owner_authorized) or \
            not callable(cancel_for_task):
        return {"state": "HOLD_STATIC_REGISTRY_CONTRACT", "native_execution_verified": False}
    try:
        if owner_authorized() is not True:
            return {"state": "HOLD_STATIC_REGISTRY_OWNER", "native_execution_verified": False}
        bridge = NativeDriveBridge(worker_bindings, config=config, state=state,
                                   manifest_root=manifest_root, ssd=ssd)
    except Exception:
        return {"state": "HOLD_STATIC_REGISTRY_GATES", "native_execution_verified": False}
    if HANDLER_KIND in handlers:
        return {"state": "HOLD_STATIC_REGISTRY_CONFLICT", "native_execution_verified": False}

    def drive_handler(native_task):
        if (not isinstance(native_task, dict)
                or native_task.get("handler") != HANDLER_KIND
                or native_task.get("status") not in ("running", "claimed")
                or not isinstance(native_task.get("params"), dict)):
            return {"state": "HOLD_NATIVE_TASK_SHAPE", "remote_verified": False}
        try:
            cancel = cancel_for_task(native_task)
        except Exception:
            return {"state": "HOLD_NATIVE_CANCEL", "remote_verified": False}
        return bridge.worker(native_task["params"], cancel=cancel)

    handlers[HANDLER_KIND] = drive_handler
    if handlers.get(HANDLER_KIND) is not drive_handler:
        return {"state": "HOLD_STATIC_REGISTRY_READBACK", "native_execution_verified": False}
    return {
        "state": "STATIC_REGISTRY_BOUND_IN_PROCESS",
        "handler_kind": HANDLER_KIND,
        "registered_callback_verified": True,
        "native_execution_verified": False,
        "google_connected": False,
        "original_task_accepted": False,
    }


# This is intentionally invoked ONLY by the existing authenticated, SHA-pinned
# drive_reconnect_install transaction. It never restarts a running service.
def stage_native_dispatcher_source(*, expected_bridge_sha, hook_syntax_only=False):
    """Stage an exact dispatcher registry patch on disk; never claim live activation."""
    if not isinstance(expected_bridge_sha, str) or not SHA.fullmatch(expected_bridge_sha):
        raise Hold("HOLD_DRIVE_NATIVE_STAGE_BUNDLE_SHA")
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
    EXPECTED_DISPATCHER_SHA = "9ae0c67523967756206a0da31d1a1cab65281dc2f4f28989f2156cd27da43a21"
    EXPECTED_BRIDGE_SHA = None  # pass exact bundled SHA from owner installer
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
    
    
    # SHIM is embedded in a nested scope; remove only indentation from this literal.
    _parts = SHIM.splitlines()
    # First marker shares its line with the opening quote and is already at
    # column zero; strip the wrapper indentation only from subsequent lines.
    SHIM = _parts[0] + "\n" + __import__("textwrap").dedent("\n".join(_parts[1:])) + "\n"
    
    
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
    
    
    # Pure syntax validation for focused CI; never reads or modifies Vast.
    if hook_syntax_only is True:
        compile("HANDLERS = {}\\n".replace("\\n", "\n") + SHIM,
                "<NOX_DRIVE_STATIC_HOOK>", "exec")
        return {"state": "HOOK_SYNTAX_VALIDATED_ONLY", "native_handler_registered": False}
    # Existing owner install has authenticated this event and pinned the Git SHA.
    owner_context()
    return stage(expected_bridge=expected_bridge_sha)
