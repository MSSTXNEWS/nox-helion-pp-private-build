"""Owner-gated read-only identity witness for one already-running model service.

The remote probe emits only Supervisor PID/start ticks and a bounded SHA-256 +
file identity for a single model file proven present in that process's maps.
It never prints paths, argv values, source bytes, or model content.
"""
from __future__ import annotations

import hashlib

from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as conn

MODEL_SERVICE = "nox-ds41-8098"
MAX_CMDLINE_BYTES = 8192
MAX_PROC_FILE_BYTES = 8 * 1024 * 1024
MAX_MODEL_PATH_CHARS = 4096
MAX_WEIGHT_BYTES = 16 * 1024 * 1024 * 1024
HASH_CHUNK_BYTES = 1024 * 1024
MAX_HASH_SECONDS = 45

REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import hashlib
import json
import os
import re
import stat
import subprocess
import time
from pathlib import Path

SERVICE = "nox-ds41-8098"
MAX_CMDLINE_BYTES = 8192
MAX_PROC_FILE_BYTES = 8 * 1024 * 1024
MAX_MODEL_PATH_CHARS = 4096
MAX_WEIGHT_BYTES = 16 * 1024 * 1024 * 1024
HASH_CHUNK_BYTES = 1024 * 1024
MAX_HASH_SECONDS = 45
MODEL_FLAGS = ("-m", "--model", "--model-path", "--model-file")
REASON_CODES = {
    "HOLD_SUPERVISOR_READ", "HOLD_MODEL_SERVICE_NOT_RUNNING",
    "HOLD_PID_IDENTITY", "HOLD_CMDLINE_READ", "HOLD_CMDLINE_PARSE",
    "HOLD_MODEL_ARG_MISSING_OR_AMBIGUOUS", "HOLD_MODEL_PATH_UNSAFE",
    "HOLD_CWD_UNAVAILABLE", "HOLD_WEIGHT_OPEN", "HOLD_WEIGHT_NOT_REGULAR",
    "HOLD_WEIGHT_SIZE_BOUNDS", "HOLD_WEIGHT_NOT_MAPPED",
    "HOLD_MAPS_READ", "HOLD_MAPS_BOUNDS", "HOLD_WEIGHT_HASH_BUDGET",
    "HOLD_WEIGHT_CHANGED", "HOLD_SUPERVISOR_PID_CHANGED",
    "HOLD_MODEL_PROCESS_REUSED", "HOLD_MODEL_ARG_CHANGED", "HOLD_WEIGHT_READ", "HOLD_WEIGHT_SHORT_READ",
}

class ProbeHold(Exception):
    def __init__(self, code):
        self.code = code if code in REASON_CODES else "HOLD_INTERNAL"
        super().__init__(self.code)

def read_small(path, limit):
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        fd = os.open(path, flags)
    except OSError:
        raise ProbeHold("HOLD_CMDLINE_READ" if path.endswith("/cmdline")
                        else "HOLD_MAPS_READ") from None
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ProbeHold("HOLD_MAPS_READ")
        raw = bytearray()
        while len(raw) <= limit:
            block = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not block:
                break
            raw.extend(block)
        after = os.fstat(fd)
        identity = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        if len(raw) > limit:
            raise ProbeHold("HOLD_MAPS_BOUNDS")
        if identity(before) != identity(after):
            raise ProbeHold("HOLD_MAPS_READ")
        if not path.startswith("/proc/") and len(raw) != before.st_size:
            raise ProbeHold("HOLD_MAPS_READ")
        return bytes(raw)
    finally:
        os.close(fd)

def supervisor_pid():
    try:
        result = subprocess.run(
            ["supervisorctl", "status", SERVICE],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=7, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ProbeHold("HOLD_SUPERVISOR_READ") from None
    if result.returncode != 0:
        raise ProbeHold("HOLD_SUPERVISOR_READ")
    match = re.fullmatch(
        re.escape(SERVICE) + r"\s+RUNNING\s+pid\s+([0-9]{1,10}),\s+uptime .+\s*",
        result.stdout.strip(),
    )
    if not match:
        raise ProbeHold("HOLD_MODEL_SERVICE_NOT_RUNNING")
    return int(match.group(1))

def process_start_ticks(pid, proc_root=Path("/proc")):
    try:
        raw = read_small(str(proc_root / str(pid) / "stat"), 4096)
        head, tail = raw.rsplit(b")", 1)
        actual = int(head.split(b"(", 1)[0].split()[-1])
        fields = tail.split()
        if actual != pid or len(fields) <= 19:
            raise ValueError()
        return int(fields[19])
    except ProbeHold:
        raise ProbeHold("HOLD_PID_IDENTITY") from None
    except (ValueError, IndexError):
        raise ProbeHold("HOLD_PID_IDENTITY") from None

def model_arg(pid, proc_root=Path("/proc")):
    try:
        raw = read_small(str(proc_root / str(pid) / "cmdline"), MAX_CMDLINE_BYTES)
        if not raw.endswith(b"\0"):
            raise ValueError()
        argv = [part.decode("utf-8", "strict") for part in raw[:-1].split(b"\0") if part]
    except ProbeHold:
        raise
    except (UnicodeDecodeError, ValueError):
        raise ProbeHold("HOLD_CMDLINE_PARSE") from None
    found = []
    index = 0
    while index < len(argv):
        item = argv[index]
        if item in MODEL_FLAGS:
            if index + 1 >= len(argv) or not argv[index + 1]:
                raise ProbeHold("HOLD_MODEL_ARG_MISSING_OR_AMBIGUOUS")
            found.append(argv[index + 1])
            index += 2
            continue
        if item.startswith("--model=") or item.startswith("--model-path=") or item.startswith("--model-file="):
            value = item.split("=", 1)[1]
            if not value:
                raise ProbeHold("HOLD_MODEL_ARG_MISSING_OR_AMBIGUOUS")
            found.append(value)
        index += 1
    if len(found) != 1 or len(found[0]) > MAX_MODEL_PATH_CHARS:
        raise ProbeHold("HOLD_MODEL_ARG_MISSING_OR_AMBIGUOUS")
    candidate = found[0]
    if "\0" in candidate or candidate.endswith(" (deleted)"):
        raise ProbeHold("HOLD_MODEL_PATH_UNSAFE")
    return candidate

def absolute_model_path(pid, candidate, proc_root=Path("/proc")):
    if os.path.isabs(candidate):
        path = os.path.normpath(candidate)
    else:
        try:
            cwd = os.readlink(str(proc_root / str(pid) / "cwd"))
        except OSError:
            raise ProbeHold("HOLD_CWD_UNAVAILABLE") from None
        if not cwd.startswith("/") or cwd.endswith(" (deleted)"):
            raise ProbeHold("HOLD_CWD_UNAVAILABLE")
        path = os.path.normpath(os.path.join(cwd, candidate))
    if (not path.startswith("/") or len(path) > MAX_MODEL_PATH_CHARS
            or any(part in ("", ".", "..") for part in path.split("/")[1:-1])):
        raise ProbeHold("HOLD_MODEL_PATH_UNSAFE")
    return path

def open_regular_nofollow(path):
    # Walk every component with O_NOFOLLOW; no parent or final symlink is accepted.
    parts = path.split("/")[1:]
    if not parts or not parts[-1] or any(x in ("", ".", "..") for x in parts):
        raise ProbeHold("HOLD_MODEL_PATH_UNSAFE")
    flags_dir = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        current = os.open("/", flags_dir)
        for component in parts[:-1]:
            next_fd = os.open(component, flags_dir, dir_fd=current)
            os.close(current)
            current = next_fd
        flags_file = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        fd = os.open(parts[-1], flags_file, dir_fd=current)
        os.close(current)
    except OSError:
        try:
            os.close(current)
        except (OSError, UnboundLocalError):
            pass
        raise ProbeHold("HOLD_WEIGHT_OPEN") from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ProbeHold("HOLD_WEIGHT_NOT_REGULAR")
        if st.st_size <= 0 or st.st_size > MAX_WEIGHT_BYTES:
            raise ProbeHold("HOLD_WEIGHT_SIZE_BOUNDS")
        return fd, st
    except Exception:
        os.close(fd)
        raise

def file_identity(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)

def mapped_inode(pid, st, proc_root=Path("/proc")):
    try:
        raw = read_small(str(proc_root / str(pid) / "maps"), MAX_PROC_FILE_BYTES)
    except ProbeHold as exc:
        if exc.code == "HOLD_MAPS_BOUNDS":
            raise
        raise ProbeHold("HOLD_MAPS_READ") from None
    wanted = (os.major(st.st_dev), os.minor(st.st_dev), st.st_ino)
    for line in raw.splitlines():
        fields = line.split(None, 5)
        if len(fields) < 5:
            continue
        try:
            major_s, minor_s = fields[3].decode("ascii").split(":", 1)
            found = (int(major_s, 16), int(minor_s, 16), int(fields[4]))
        except (ValueError, UnicodeError):
            continue
        if found == wanted and st.st_ino > 0:
            return True
    return False

def sha256_fd(fd, expected_size, hash_seconds=MAX_HASH_SECONDS):
    digest = hashlib.sha256()
    total = 0
    deadline = time.monotonic() + hash_seconds
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        while total < expected_size:
            if time.monotonic() > deadline:
                raise ProbeHold("HOLD_WEIGHT_HASH_BUDGET")
            block = os.read(fd, min(HASH_CHUNK_BYTES, expected_size - total))
            if not block:
                raise ProbeHold("HOLD_WEIGHT_SHORT_READ")
            total += len(block)
            digest.update(block)
        if os.read(fd, 1):
            raise ProbeHold("HOLD_WEIGHT_CHANGED")
        return digest.hexdigest(), total
    except ProbeHold:
        raise
    except OSError:
        raise ProbeHold("HOLD_WEIGHT_READ") from None

def unknown(reason, pid=None, start_ticks=None):
    return {
        "schema": "NOX_V77_LOADED_WEIGHT_IDENTITY_V1",
        "state": "UNKNOWN",
        "model_identity": {"state": "UNKNOWN", "reason": "MODEL_COMPOSITE_NOT_PROVEN"},
        "manifest_relation": {"state": "UNKNOWN", "reason": "PINNED_MANIFEST_NOT_READ_OR_USED"},
        "reason": reason if reason in REASON_CODES else "HOLD_INTERNAL",
        "service": SERVICE,
        "pid": pid,
        "start_ticks": start_ticks,
        "weight_sha256": None,
        "weight_size_bytes": None,
        "weight_identity": None,
        "callback_registry": {
            "state": "UNKNOWN",
            "reason": "EXACT_LOADED_BRIDGE_SOURCE_NOT_PROVEN",
        },
    }

def inspect_loaded_weight(supervisor_reader=supervisor_pid, proc_root=Path("/proc"),
                          hash_seconds=MAX_HASH_SECONDS, after_hash=None):
    pid = None
    start = None
    fd = None
    try:
        pid = supervisor_reader()
        start = process_start_ticks(pid, proc_root)
        candidate = model_arg(pid, proc_root)
        path = absolute_model_path(pid, candidate, proc_root)
        if process_start_ticks(pid, proc_root) != start:
            raise ProbeHold("HOLD_MODEL_PROCESS_REUSED")
        fd, st = open_regular_nofollow(path)
        identity_before = file_identity(st)
        if not mapped_inode(pid, st, proc_root):
            raise ProbeHold("HOLD_WEIGHT_NOT_MAPPED")
        digest, total = sha256_fd(fd, st.st_size, hash_seconds)
        if after_hash is not None:
            after_hash()
        st_after = os.fstat(fd)
        if file_identity(st_after) != identity_before or total != st.st_size:
            raise ProbeHold("HOLD_WEIGHT_CHANGED")
        check_fd, path_st_after = open_regular_nofollow(path)
        os.close(check_fd)
        if file_identity(path_st_after) != identity_before:
            raise ProbeHold("HOLD_WEIGHT_CHANGED")
        if not mapped_inode(pid, st_after, proc_root):
            raise ProbeHold("HOLD_WEIGHT_NOT_MAPPED")
        if model_arg(pid, proc_root) != candidate:
            raise ProbeHold("HOLD_MODEL_ARG_CHANGED")
        if absolute_model_path(pid, model_arg(pid, proc_root), proc_root) != path:
            raise ProbeHold("HOLD_MODEL_ARG_CHANGED")
        if process_start_ticks(pid, proc_root) != start:
            raise ProbeHold("HOLD_MODEL_PROCESS_REUSED")
        if supervisor_reader() != pid:
            raise ProbeHold("HOLD_SUPERVISOR_PID_CHANGED")
        return {
            "schema": "NOX_V77_LOADED_WEIGHT_IDENTITY_V1",
            "state": "VERIFIED_MAPPED_WEIGHT_FILE_SHA256",
            "reason": None,
            "model_identity": {"state": "UNKNOWN", "reason": "MODEL_COMPOSITE_NOT_PROVEN"},
            "manifest_relation": {"state": "UNKNOWN", "reason": "PINNED_MANIFEST_NOT_READ_OR_USED"},
            "service": SERVICE,
            "pid": pid,
            "start_ticks": start,
            "weight_sha256": digest,
            "weight_size_bytes": total,
            "weight_identity": {
                "device": st_after.st_dev,
                "inode": st_after.st_ino,
                "size_bytes": st_after.st_size,
                "mtime_ns": st_after.st_mtime_ns,
                "ctime_ns": st_after.st_ctime_ns,
            },
            "callback_registry": {
                "state": "UNKNOWN",
                "reason": "EXACT_LOADED_BRIDGE_SOURCE_NOT_PROVEN",
            },
        }
    except ProbeHold as exc:
        return unknown(exc.code, pid, start)
    except Exception:
        return unknown("HOLD_INTERNAL", pid, start)
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass

def main():
    result = inspect_loaded_weight()
    print("NATIVE_V77_MODEL_WEIGHT_RECEIPT=" + json.dumps(result, separators=(",", ":"), sort_keys=True))
    print("NATIVE_V77_PATHS_EXPORTED=false")
    print("NATIVE_V77_ARGV_EXPORTED=false")
    print("NATIVE_V77_CALLBACKS_PROVEN=false")
    print("NATIVE_V77_SERVICES_CHANGED=false")

if __name__ == "__main__":
    main()
PYREMOTE
"""

def probe_source_hash():
    import hashlib
    return hashlib.sha256(REMOTE.encode("utf-8")).hexdigest()

if __name__ == "__main__":
    ok = False
    conn.REMOTE = REMOTE
    print("NOX_V77_REMOTE_SHA256=" + probe_source_hash(), flush=True)
    try:
        ok = conn.probe()
    except Exception as exc:
        code = str(exc)
        print("NOX_V77_INSPECT=" + (code if code.startswith("HOLD_") else "HOLD_TRANSPORT"))
    finally:
        try:
            if not conn.cleanup():
                ok = False
        except Exception:
            ok = False
    raise SystemExit(0 if ok else 2)
