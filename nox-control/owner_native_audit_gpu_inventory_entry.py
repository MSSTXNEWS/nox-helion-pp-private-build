#!/usr/bin/env python3
"""Run pinned read-only owner audit then GPU inventory in one SSH payload."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

INSTANCE_ID = 60509551
AUDIT_SOURCE_SHA = "b1e33d60983885a7ebd1979bda4ec640b7ca7047"
AUDIT_BLOB_SHA = "e5c439c6733fcb276bec58dbf8af5193694645ac"
GPU_SOURCE_SHA = "a95c7c6e4d52a35db9199e1aa2a5ad01752efc7e"
GPU_BLOB_SHA = "3a3ff33e7709539d5ff6ab6b8614d694a9d2becb"
AUDIT_PREFIX = "NOX_MAINT_AUDIT="
AUDIT_COMPLETE = "NOX_MAINT_AUDIT_COMPLETE=true"
GPU_PREFIX = "NOX_MAINT_GPU_INVENTORY="
GPU_RESULT_PREFIX = "NOX_MAINT_GPU_INVENTORY_RESULT="
GPU_COMPLETE = "NOX_MAINT_GPU_INVENTORY_COMPLETE=true"
COMPOSITE_COMPLETE = "NOX_MAINT_AUDIT_GPU_INVENTORY_COMPLETE=true"
AUDIT_SECTIONS = (
    "hardware", "process_rows", "supervisor", "packages", "models",
    "storage", "mount_inventory",
)
MAX_HELPER_BYTES = 256 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_MARKER_CHARS = 179000
HELPER_TIMEOUT = 120
AUDIT_HELPER_B64 = __NOX_AUDIT_HELPER_B64__
GPU_HELPER_B64 = __NOX_GPU_HELPER_B64__


class Hold(RuntimeError):
    pass


def require(ok, code):
    if not ok:
        raise Hold(code)


def git_blob_sha(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def owner_context():
    source = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    request = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", source)), "HOLD_COMPOSITE_SOURCE_PIN")
    require(bool(re.fullmatch(r"[1-9][0-9]{0,19}", request)), "HOLD_COMPOSITE_REQUEST_PIN")
    return source, request


def stage_helper(root, name, payload, expected_blob):
    try:
        raw = base64.b64decode(payload, validate=True)
    except Exception:
        raise Hold("HOLD_COMPOSITE_HELPER_ENCODING") from None
    require(0 < len(raw) <= MAX_HELPER_BYTES, "HOLD_COMPOSITE_HELPER_SIZE")
    require(git_blob_sha(raw) == expected_blob, "HOLD_COMPOSITE_HELPER_BLOB_PIN")
    path = root / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o700)
    try:
        os.fchmod(fd, 0o700)
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)
    require(not path.is_symlink() and path.read_bytes() == raw,
            "HOLD_COMPOSITE_HELPER_READBACK")
    return path


def bounded_run(path, env):
    import resource

    with tempfile.TemporaryFile() as output:
        def limit_output_file():
            resource.setrlimit(resource.RLIMIT_FSIZE,
                               (MAX_OUTPUT_BYTES, MAX_OUTPUT_BYTES))

        try:
            proc = subprocess.Popen(
                [sys.executable, "-B", str(path)],
                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.DEVNULL,
                env=env, close_fds=True, start_new_session=True,
                preexec_fn=limit_output_file,
            )
        except Exception as exc:
            raise Hold("HOLD_COMPOSITE_HELPER_START_" +
                       re.sub(r"[^A-Z0-9_]", "_", type(exc).__name__.upper())[:40]) from None
        try:
            code = proc.wait(timeout=HELPER_TIMEOUT)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                raise Hold("HOLD_COMPOSITE_HELPER_TIMEOUT") from None
            raise Hold("HOLD_COMPOSITE_HELPER_TIMEOUT") from None
        size = os.fstat(output.fileno()).st_size
        require(size <= MAX_OUTPUT_BYTES, "HOLD_COMPOSITE_OUTPUT_BOUND")
        output.seek(0)
        raw = output.read(MAX_OUTPUT_BYTES + 1)
    require(len(raw) == size, "HOLD_COMPOSITE_OUTPUT_READBACK")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise Hold("HOLD_COMPOSITE_OUTPUT_ENCODING") from None
    lines = text.splitlines()
    require(all(len(line) < MAX_MARKER_CHARS for line in lines),
            "HOLD_COMPOSITE_MARKER_LINE_BOUND")
    return code, lines


def validate_audit(code, lines):
    if code != 0 or len(lines) != len(AUDIT_SECTIONS) + 1:
        return False
    if lines[-1] != AUDIT_COMPLETE:
        return False
    for expected, line in zip(AUDIT_SECTIONS, lines[:-1]):
        if not line.startswith(AUDIT_PREFIX):
            return False
        try:
            row = json.loads(line[len(AUDIT_PREFIX):])
        except (TypeError, ValueError):
            return False
        if not isinstance(row, dict) or row.get("section") != expected:
            return False
        if type(row.get("worker_pid")) is not int or row["worker_pid"] <= 1:
            return False
        if "error" in row:
            if not isinstance(row["error"], str) or not row["error"]:
                return False
        elif expected == "process_rows":
            if not isinstance(row.get("result"), list):
                return False
        elif not isinstance(row.get("result"), dict):
            return False
    return True


def validate_gpu(code, lines, request):
    if code != 0 or len(lines) != 2 or lines[1] != GPU_COMPLETE:
        return False
    if not lines[0].startswith(GPU_PREFIX):
        return False
    try:
        receipt = json.loads(lines[0][len(GPU_PREFIX):])
    except (TypeError, ValueError):
        return False
    if (
        not isinstance(receipt, dict)
        or set(receipt) != {
            "schema", "action", "instance_id", "source_sha", "request_id",
            "inventory_sha256", "inventory",
        }
        or receipt.get("schema") != "NOX_GPU_INVENTORY_V1"
        or receipt.get("action") != "gpu_inventory"
        or type(receipt.get("instance_id")) is not int
        or receipt.get("instance_id") != INSTANCE_ID
        or receipt.get("source_sha") != GPU_SOURCE_SHA
        or type(receipt.get("request_id")) is not int
        or receipt.get("request_id") != int(request)
        or not isinstance(receipt.get("inventory_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", receipt["inventory_sha256"]) is None
    ):
        return False
    inventory = receipt["inventory"]
    if (
        not isinstance(inventory, dict)
        or set(inventory) != {
            "schema", "action", "instance_id", "boot_id", "uptime_scope",
            "memory_semantics", "identity_stable", "snapshots",
        }
        or inventory.get("schema") != "NOX_GPU_INVENTORY_V1"
        or inventory.get("action") != "gpu_inventory"
        or type(inventory.get("instance_id")) is not int
        or inventory.get("instance_id") != INSTANCE_ID
        or inventory.get("uptime_scope") != "two monotonic host snapshots; point-in-time only"
        or inventory.get("memory_semantics") != "nvidia-smi MiB; 0<=total-used-free<=1024 reserved"
        or inventory.get("identity_stable") is not True
        or not isinstance(inventory.get("boot_id"), str)
        or re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", inventory["boot_id"]) is None
        or not isinstance(inventory.get("snapshots"), list)
        or len(inventory["snapshots"]) != 2
    ):
        return False
    identities = []
    uptimes = []
    prior_end = None
    for snapshot in inventory["snapshots"]:
        if (
            not isinstance(snapshot, dict)
            or set(snapshot) != {
                "boot_id", "uptime_seconds", "monotonic_started_ns",
                "monotonic_finished_ns", "nvidia_smi_rc", "rows",
            }
            or snapshot.get("boot_id") != inventory["boot_id"]
            or type(snapshot.get("nvidia_smi_rc")) is not int
            or snapshot["nvidia_smi_rc"] != 0
            or type(snapshot.get("monotonic_started_ns")) is not int
            or type(snapshot.get("monotonic_finished_ns")) is not int
            or snapshot["monotonic_started_ns"] < 0
            or snapshot["monotonic_finished_ns"] < snapshot["monotonic_started_ns"]
            or (prior_end is not None and snapshot["monotonic_started_ns"] <= prior_end)
            or not isinstance(snapshot.get("uptime_seconds"), (int, float))
            or isinstance(snapshot["uptime_seconds"], bool)
            or not 0 <= snapshot["uptime_seconds"] < 10**9
            or not isinstance(snapshot.get("rows"), list)
            or len(snapshot["rows"]) != 2
        ):
            return False
        prior_end = snapshot["monotonic_finished_ns"]
        rows = []
        seen_indices = set()
        seen_uuids = set()
        for row in snapshot["rows"]:
            fields = {
                "index", "model", "uuid", "memory_total_mib",
                "memory_used_mib", "memory_free_mib",
            }
            if (
                not isinstance(row, dict)
                or set(row) != fields
                or type(row.get("index")) is not int
                or not 0 <= row["index"] <= 31
                or row.get("model") != "Tesla V100-SXM2-32GB"
                or not isinstance(row.get("uuid"), str)
                or re.fullmatch(r"GPU-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", row["uuid"]) is None
                or row["index"] in seen_indices
                or row["uuid"] in seen_uuids
            ):
                return False
            numbers = [row.get(key) for key in (
                "memory_total_mib", "memory_used_mib", "memory_free_mib",
            )]
            if any(type(value) is not int or not 0 <= value <= 10**7 for value in numbers):
                return False
            total, used, free = numbers
            if (
                total <= 0 or used > total or free > total
                or used + free > total
                or total - used - free > min(1024, total // 10)
            ):
                return False
            seen_indices.add(row["index"])
            seen_uuids.add(row["uuid"])
            rows.append((row["index"], row["model"], row["uuid"], total))
        if rows != sorted(rows):
            return False
        identities.append(rows)
        uptimes.append(snapshot["uptime_seconds"])
    if identities[0] != identities[1] or uptimes[1] <= uptimes[0]:
        return False
    canonical = json.dumps(
        inventory, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest() == receipt["inventory_sha256"]


def emit_lines(lines):
    for line in lines:
        print(line, flush=True)


def main():
    _composite_source, request = owner_context()
    temporary_root = Path(tempfile.mkdtemp(prefix="nox-audit-gpu-"))
    audit_ok = gpu_ok = False
    try:
        audit_path = stage_helper(
            temporary_root, "owner_native_audit.py",
            AUDIT_HELPER_B64, AUDIT_BLOB_SHA)
        gpu_path = stage_helper(
            temporary_root, "owner_native_gpu_inventory.py",
            GPU_HELPER_B64, GPU_BLOB_SHA)

        clean_env = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "HOME": "/root",
            "LANG": "C",
            "LC_ALL": "C",
        }
        print("NOX_MAINT_AUDIT_SOURCE_SHA=" + AUDIT_SOURCE_SHA, flush=True)
        try:
            audit_code, audit_lines = bounded_run(audit_path, clean_env)
            audit_ok = validate_audit(audit_code, audit_lines)
            if audit_ok:
                emit_lines(audit_lines)
            else:
                print("NOX_MAINT_AUDIT_RESULT=HOLD_COMPOSITE_AUDIT_RESULT", flush=True)
        except Hold as exc:
            print("NOX_MAINT_AUDIT_RESULT=" + str(exc), flush=True)

        gpu_env = {
            **clean_env,
            "NOX_OWNER_ACTION": "gpu_inventory",
            "NOX_OWNER_INSTANCE_ID": str(INSTANCE_ID),
            "NOX_OWNER_SOURCE_SHA": GPU_SOURCE_SHA,
            "NOX_OWNER_REQUEST_ID": request,
        }
        print("NOX_MAINT_GPU_INVENTORY_SOURCE_SHA=" + GPU_SOURCE_SHA, flush=True)
        try:
            gpu_code, gpu_lines = bounded_run(gpu_path, gpu_env)
            gpu_ok = validate_gpu(gpu_code, gpu_lines, request)
            if gpu_ok:
                emit_lines(gpu_lines)
            elif (len(gpu_lines) == 1
                  and gpu_lines[0].startswith(GPU_RESULT_PREFIX)
                  and re.fullmatch(r"HOLD_[A-Z0-9_]+", gpu_lines[0][len(GPU_RESULT_PREFIX):])):
                print(gpu_lines[0], flush=True)
            else:
                print(GPU_RESULT_PREFIX + "HOLD_COMPOSITE_GPU_RESULT", flush=True)
        except Hold as exc:
            print(GPU_RESULT_PREFIX + str(exc), flush=True)

        if audit_ok and gpu_ok:
            print(COMPOSITE_COMPLETE, flush=True)
            return 0
        return 2
    finally:
        for child in (temporary_root / "owner_native_audit.py",
                      temporary_root / "owner_native_gpu_inventory.py"):
            try:
                if child.is_symlink():
                    raise Hold("HOLD_COMPOSITE_TEMP_CLEANUP")
                child.unlink(missing_ok=True)
            except OSError:
                raise Hold("HOLD_COMPOSITE_TEMP_CLEANUP") from None
        try:
            temporary_root.rmdir()
        except OSError:
            raise Hold("HOLD_COMPOSITE_TEMP_CLEANUP") from None


if __name__ == "__main__":
    raise SystemExit(main())
