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
