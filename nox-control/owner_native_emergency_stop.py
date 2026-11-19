#!/usr/bin/env python3
"""Owner-only two-step emergency memory relief for one attested NOX model.

This source is inert until called by the pinned owner-maintenance workflow.
It stops only the exact Supervisor model service when fresh cgroup
headroom is below 2 GiB. This version always preserves the memfd holder and
never clears owner markers or restarts services.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

ROOT = Path("/root/nox")
STOP = ROOT / "STOP"
MAINTENANCE = ROOT / "state/OWNER_MAINTENANCE.flag"
LOCK = ROOT / "state/owner_maintenance.lock"
CGROUP_ROOT = Path("/sys/fs/cgroup")
SUPERVISOR_SERVICE = "nox-ds41-8098"
MODEL_PID = 3266857
MODEL_START_TICKS = 172046662
MODEL_PATH = "/root/nox/models/deepseek_v41_flash_iq2xxs/DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf"
HOLDER_PID = 498569
HOLDER_SCRIPT_NAME = "engram_memfd_holder.py"
HOLDER_CWD = "/root/nox/engram_ram"
HOLDER_START_TICKS = 168416044
HOLDER_SCRIPT = "/root/nox/engram_ram/engram_memfd_holder.py"
MEMFD_INODE = 131095
MEMFD_SIZE = 75_266_239_716
MIN_HEADROOM = 2_147_483_648
MEMFD_LABEL = "memfd:engram_iq3xxs (deleted)"
MODEL_SOURCE_ENV_KEYS = {
    "LLAMA_ARG_MODEL_URL", "LLAMA_ARG_DOCKER_REPO", "LLAMA_ARG_HF_REPO",
    "LLAMA_ARG_HF_FILE", "LLAMA_ARG_SHARD", "LLAMA_ARG_MMPROJ",
    "LLAMA_ARG_MMPROJ_URL", "LLAMA_ARG_MMPROJ_AUTO",
    "LLAMA_ARG_SPEC_DRAFT_MODEL", "LLAMA_ARG_SPEC_DRAFT_HF_REPO",
    "LLAMA_ARG_MODELS_DIR", "LLAMA_ARG_MODELS_PRESET",
    "LLAMA_ARG_MODELS_MAX", "LLAMA_ARG_MODELS_MEMORY_MARGIN",
    "LLAMA_ARG_MODELS_AUTOLOAD",
}
MODEL_CONTEXT_ENV_KEYS = {
    "LLAMA_ARG_KV_UNIFIED_PER_SLOT", "LLAMA_ARG_N_PARALLEL",
    "LLAMA_ARG_CTX_CHECKPOINTS", "LLAMA_ARG_ROPE_SCALING_TYPE",
    "LLAMA_ARG_ROPE_SCALE", "LLAMA_ARG_ROPE_FREQ_BASE",
    "LLAMA_ARG_ROPE_FREQ_SCALE", "LLAMA_ARG_YARN_ORIG_CTX",
    "LLAMA_ARG_YARN_EXT_FACTOR", "LLAMA_ARG_YARN_ATTN_FACTOR",
    "LLAMA_ARG_YARN_BETA_SLOW", "LLAMA_ARG_YARN_BETA_FAST",
    "LLAMA_ARG_FIT", "LLAMA_ARG_FIT_CTX", "LLAMA_ARG_SWA_FULL",
}
MODEL_ENV_KEYS = MODEL_SOURCE_ENV_KEYS | MODEL_CONTEXT_ENV_KEYS | {
    "LLAMA_ARG_MODEL", "LLAMA_ARG_CTX_SIZE",
}
MAX_STAT_BYTES = 8_192
MAX_CMDLINE_BYTES = 16 * 1024
MAX_ENV_BYTES = 256 * 1024
MAX_FD_ENTRIES_PER_PID = 16_384
MAX_HOLDER_FD_BYTES = 1 * 1024 * 1024
MAX_FD_LINK_BYTES = 4_096
MAX_MAPS_BYTES = 2 * 1024 * 1024
SHA40 = re.compile(r"^[0-9a-f]{40}$")
STATUS_LINE = re.compile(r"^([A-Za-z0-9_.:-]+)\s+(RUNNING|STOPPED|EXITED)(?:\s+pid\s+([0-9]+))?(?:,.*)?$")

PHASE = {
    "owner_lock": False,
    "stop_marker": False,
    "maintenance_marker": False,
    "model_stop_requested": False,
    "model_stopped": False,
}
MARKERS = {}


def fail(label: str) -> None:
    raise RuntimeError("HOLD_EMERGENCY_STOP_" + label)


def emit(payload: dict) -> None:
    print("NOX_MAINT_EMERGENCY_STOP=" + json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ), flush=True)


def root_directory(path: Path) -> None:
    try:
        st = path.lstat()
    except OSError:
        fail("REQUIRED_DIRECTORY_MISSING")
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
        fail("UNSAFE_DIRECTORY")


def acquire_lock() -> int:
    root_directory(ROOT)
    root_directory(ROOT / "state")
    try:
        fd = os.open(LOCK, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                     getattr(os, "O_CLOEXEC", 0))
    except OSError:
        fail("OWNER_LOCK_UNAVAILABLE")
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or
                st.st_nlink != 1 or st.st_mode & 0o022):
            fail("OWNER_LOCK_UNSAFE")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("OWNER_LOCK_BUSY")
        PHASE["owner_lock"] = True
        return fd
    except BaseException:
        os.close(fd)
        raise


def check_marker(path: Path, label: str, new_bytes: bytes) -> dict:
    created = False
    try:
        st = path.lstat()
    except FileNotFoundError:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), 0o600)
        except FileExistsError:
            return check_marker(path, label, new_bytes)
        except OSError:
            fail(label + "_CREATE_FAILED")
        created = True
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb", closefd=False) as out:
                out.write(new_bytes)
                out.flush()
                os.fsync(fd)
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or
                    st.st_nlink != 1 or stat.S_IMODE(st.st_mode) != 0o600):
                fail(label + "_READBACK_UNSAFE")
        finally:
            os.close(fd)
        try:
            dfd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            fail(label + "_DIRECTORY_SYNC_FAILED")
        st = path.lstat()
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_nlink != 1 or
            st.st_mode & 0o022):
        fail(label + "_UNSAFE")
    try:
        raw = path.read_bytes()
    except OSError:
        fail(label + "_READ_FAILED")
    if len(raw) > 4096:
        fail(label + "_TOO_LARGE")
    if raw != new_bytes:
        fail(label + "_REQUEST_BINDING_MISMATCH")
    result = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
              "created": created, "mode": oct(stat.S_IMODE(st.st_mode))}
    if label == "STOP":
        PHASE["stop_marker"] = True
    else:
        PHASE["maintenance_marker"] = True
    MARKERS[label] = result
    return result


def ensure_owner_fence(request_id: int, source_sha: str) -> dict:
    payload = (f"NOX_OWNER_EMERGENCY_STOP_V1\nrequest_id={request_id}\n"
               f"source_sha={source_sha}\n").encode("ascii")
    # No overwrite: existing flags are accepted only as safe root-owned files.
    return {
        "stop": check_marker(STOP, "STOP", payload),
        "maintenance": check_marker(MAINTENANCE, "MAINTENANCE", payload),
    }


def command(argv: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, shell=False, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        fail("COMMAND_UNAVAILABLE")


def supervisor_status() -> dict:
    p = command(["supervisorctl", "status", SUPERVISOR_SERVICE])
    lines = p.stdout.strip().splitlines()
    m = STATUS_LINE.fullmatch(lines[0]) if len(lines) == 1 else None
    if m is None or m.group(1) != SUPERVISOR_SERVICE or p.returncode not in (0, 3):
        fail("SUPERVISOR_STATUS_UNTRUSTED")
    return {"state": m.group(2), "pid": int(m.group(3)) if m.group(3) else None,
            "rc": p.returncode}


def cgroup_path(pid: int) -> Path:
    try:
        lines = (Path("/proc") / str(pid) / "cgroup").read_text().splitlines()
    except OSError:
        fail("CGROUP_IDENTITY_UNAVAILABLE")
    rows = [line.split(":", 2)[2] for line in lines if line.startswith("0::")]
    if len(rows) != 1:
        fail("CGROUP_V2_IDENTITY_UNAVAILABLE")
    try:
        base = CGROUP_ROOT.resolve(strict=True)
        result = (base / rows[0].lstrip("/")).resolve(strict=True)
        if os.path.commonpath((str(base), str(result))) != str(base):
            fail("CGROUP_PATH_ESCAPE")
    except (OSError, ValueError):
        fail("CGROUP_PATH_UNSAFE")
    return result


def proc_start_ticks(pid: int, missing_ok: bool = False):
    path = Path("/proc") / str(pid) / "stat"
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_STAT_BYTES + 1)
    except FileNotFoundError:
        if missing_ok:
            return None
        fail("PROC_STAT_MISSING")
    except OSError:
        fail("PROC_STAT_UNREADABLE")
    if len(raw) > MAX_STAT_BYTES:
        fail("PROC_STAT_TOO_LARGE")
    text = raw.decode("ascii", "replace")
    match = re.match(r"^([0-9]+) \(", text)
    if match is None or int(match.group(1)) != pid:
        fail("PROC_STAT_PID_MISMATCH")
    try:
        fields = text.rsplit(")", 1)[1].split()
        if len(fields) <= 19:
            fail("PROC_STAT_FIELDS_INCOMPLETE")
        return int(fields[19])
    except (ValueError, IndexError):
        fail("PROC_STAT_PARSE_FAILED")


def stable_start_ticks(pid: int, expected_ticks: int = None, missing_ok: bool = False):
    first = proc_start_ticks(pid, missing_ok=missing_ok)
    if first is None:
        return None
    time.sleep(0.05)
    second = proc_start_ticks(pid, missing_ok=missing_ok)
    if second is None:
        return None
    if first != second:
        fail("PROC_STARTTIME_UNSTABLE")
    if expected_ticks is not None and second != expected_ticks:
        fail("PROC_STARTTIME_MISMATCH")
    return second


def read_maps_bounded(pid: int):
    path = Path("/proc") / str(pid) / "maps"
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_MAPS_BYTES + 1)
    except FileNotFoundError:
        return None
    except OSError:
        return None
    if len(raw) > MAX_MAPS_BYTES:
        return None
    return raw.decode("ascii", "replace")


def mapped_inode(rows: str, device: int, inode: int) -> bool:
    for row in rows.splitlines():
        fields = row.split(maxsplit=5)
        if len(fields) < 5 or not fields[4].isdigit() or int(fields[4]) != inode:
            continue
        try:
            major, minor = (int(x, 16) for x in fields[3].split(":", 1))
        except (ValueError, IndexError):
            fail("MAPS_DEVICE_UNPARSEABLE")
        if os.makedev(major, minor) == device:
            return True
    return False


def reject_model_context_selectors(args: list[str]) -> None:
    """Reject alternate model and context selectors from llama.cpp server CLI.

    The option families are based on ggml-org/llama.cpp tools/server/README.md
    and common/arg.cpp; unlisted non-selector options remain permitted.
    """
    short_selectors = {
        "-mu", "-dr", "-hf", "-hfr", "-hff", "-mm", "-mmu",
        "-md", "-hfd", "-hfrd", "-np", "-ns", "-ctxcp", "-fit", "-fitc",
    }
    long_prefixes = (
        "--model", "--hf", "--mmproj", "--models-", "--spec-draft-",
        "--ctx-size", "--rope-", "--yarn-",
    )
    long_exact = {
        "--docker-repo", "--shard", "--ple", "--kv-unified-per-slot",
        "--mtp", "--dflash", "--eagle3", "--spec-type", "--parallel",
        "--sequences", "--ctx-checkpoints", "--swa-checkpoints",
        "--swa-full", "--fit", "--fit-ctx",
    }
    preset_prefixes = (
        "--embd-", "--fim-", "--gpt-oss-", "--vision-gemma-",
    )
    for token in args:
        option = token.split("=", 1)[0]
        if (token.startswith("-c=") or option in short_selectors or
                option in long_exact or option.startswith(long_prefixes) or
                option.startswith(preset_prefixes)):
            fail("MODEL_OR_CONTEXT_SELECTOR_ALIAS")


def model_environment_identity(pid: int, expected_ticks: int) -> dict:
    """Read bounded relevant env keys; never put their values in a receipt."""
    proc = Path("/proc") / str(pid)
    try:
        with (proc / "environ").open("rb") as stream:
            raw = stream.read(MAX_ENV_BYTES + 1)
    except OSError:
        fail("MODEL_ENVIRONMENT_UNAVAILABLE")
    if len(raw) > MAX_ENV_BYTES or (raw and not raw.endswith(b"\0")):
        fail("MODEL_ENVIRONMENT_INVALID_OR_OVER_LIMIT")
    env = {}
    for row in raw.split(b"\0"):
        if not row:
            continue
        key, separator, value = row.partition(b"=")
        if not separator:
            fail("MODEL_ENVIRONMENT_ENTRY_INVALID")
        try:
            name = key.decode("ascii", "strict")
        except UnicodeDecodeError:
            fail("MODEL_ENVIRONMENT_KEY_INVALID")
        if name in MODEL_ENV_KEYS:
            if name in env:
                fail("MODEL_ENVIRONMENT_DUPLICATE_KEY")
            env[name] = value
    if stable_start_ticks(pid, expected_ticks) != expected_ticks:
        fail("MODEL_ENVIRONMENT_PROCESS_CHANGED")

    expected = {
        "LLAMA_ARG_MODEL": MODEL_PATH.encode("ascii"),
        "LLAMA_ARG_CTX_SIZE": b"8192",
    }
    for name, value in expected.items():
        if name in env and env[name] != value:
            fail("MODEL_ENVIRONMENT_OVERRIDE_MISMATCH")
    if any(env.get(name, b"") for name in MODEL_SOURCE_ENV_KEYS):
        fail("MODEL_ENVIRONMENT_SOURCE_OVERRIDE")
    if any(env.get(name, b"") for name in MODEL_CONTEXT_ENV_KEYS):
        fail("MODEL_ENVIRONMENT_CONTEXT_OVERRIDE")
    return {
        "model_env_present": "LLAMA_ARG_MODEL" in env,
        "ctx_env_present": "LLAMA_ARG_CTX_SIZE" in env,
        "model_source_env_present": any(name in env for name in MODEL_SOURCE_ENV_KEYS),
        "context_pool_env_present": any(name in env for name in MODEL_CONTEXT_ENV_KEYS),
    }


def process_identity(pid: int, expected_ticks: int, role: str) -> dict:
    ticks = stable_start_ticks(pid, expected_ticks)
    proc = Path("/proc") / str(pid)
    try:
        exe = os.readlink(proc / "exe")
        with (proc / "cmdline").open("rb") as stream:
            raw_cmdline = stream.read(MAX_CMDLINE_BYTES + 1)
    except OSError:
        fail(role + "_IDENTITY_UNAVAILABLE")
    if len(raw_cmdline) > MAX_CMDLINE_BYTES or not raw_cmdline.endswith(b"\0"):
        fail(role + "_CMDLINE_INVALID_OR_OVER_LIMIT")
    raw_argv = raw_cmdline[:-1].split(b"\0")
    if not raw_argv or any(not token for token in raw_argv):
        fail(role + "_CMDLINE_INVALID")
    try:
        argv = [token.decode("utf-8", "strict") for token in raw_argv]
    except UnicodeDecodeError:
        fail(role + "_CMDLINE_ENCODING_INVALID")
    exe_name = Path(exe.removesuffix(" (deleted)")).name
    argv0_name = Path(argv[0].removesuffix(" (deleted)")).name
    if role == "MODEL":
        model_args = argv[1:]
        model_positions = [i for i, token in enumerate(model_args) if token == "-m"]
        context_positions = [i for i, token in enumerate(model_args) if token == "-c"]
        if (exe_name != "llama-server" or argv0_name != "llama-server" or
                len(model_positions) != 1 or len(context_positions) != 1):
            fail("MODEL_EXECUTABLE_OR_ARGV_MISMATCH")
        model_index = model_positions[0]
        context_index = context_positions[0]
        if (model_index + 1 >= len(model_args) or
                model_args[model_index + 1] != MODEL_PATH or
                context_index + 1 >= len(model_args) or
                model_args[context_index + 1] != "8192"):
            fail("MODEL_EXECUTABLE_OR_ARGV_MISMATCH")
        reject_model_context_selectors(model_args)
        environment_overrides = model_environment_identity(pid, expected_ticks)
    elif role == "HOLDER":
        if HOLDER_SCRIPT not in argv:
            try:
                cwd = os.readlink(proc / "cwd")
            except OSError:
                fail("HOLDER_CWD_UNAVAILABLE")
            if HOLDER_SCRIPT_NAME not in argv or cwd != HOLDER_CWD:
                fail("HOLDER_ARGV_OR_CWD_MISMATCH")
    else:
        fail("UNKNOWN_PROCESS_ROLE")
    group = cgroup_path(pid)
    if stable_start_ticks(pid, expected_ticks) != ticks:
        fail(role + "_IDENTITY_CHANGED_DURING_READ")
    return {"pid": pid, "start_ticks": ticks, "exe": exe_name,
            "argv_sha256": hashlib.sha256(b"\0".join(raw_argv)).hexdigest(),
            "environment_overrides": environment_overrides if role == "MODEL" else None,
            "cgroup": str(group)}


def fd_memfd_identity(pid: int, expected_ticks: int = HOLDER_START_TICKS) -> dict:
    fd_dir = Path("/proc") / str(pid) / "fd"
    matches = []
    entries_scanned = 0
    link_bytes = 0
    before = stable_start_ticks(pid, expected_ticks)
    try:
        with os.scandir(fd_dir) as entries:
            for entry in entries:
                entries_scanned += 1
                if entries_scanned > MAX_FD_ENTRIES_PER_PID:
                    fail("HOLDER_FD_ENTRY_LIMIT")
                try:
                    link = os.readlink(entry.path)
                    link_size = len(os.fsencode(link))
                    if link_size > MAX_FD_LINK_BYTES:
                        fail("HOLDER_FD_LINK_OVER_LIMIT")
                    link_bytes += link_size
                    if link_bytes > MAX_HOLDER_FD_BYTES:
                        fail("HOLDER_FD_BYTE_LIMIT")
                    st = os.stat(entry.path)
                except OSError:
                    fail("HOLDER_FD_IDENTITY_UNAVAILABLE")
                label = link.rsplit("/", 1)[-1]
                candidate = (st.st_ino == MEMFD_INODE or label == MEMFD_LABEL)
                if candidate and (st.st_ino != MEMFD_INODE or
                                  st.st_size != MEMFD_SIZE or label != MEMFD_LABEL):
                    fail("HOLDER_MEMFD_IDENTITY_MISMATCH")
                if candidate:
                    matches.append({"fd": entry.name, "device": st.st_dev,
                                    "inode": st.st_ino, "size": st.st_size,
                                    "label": label})
    except OSError:
        fail("HOLDER_FD_CENSUS_UNAVAILABLE")
    if stable_start_ticks(pid, expected_ticks) != before:
        fail("HOLDER_FD_PROCESS_CHANGED")
    if not matches:
        fail("HOLDER_MEMFD_NOT_PRESENT")
    devices = {x["device"] for x in matches}
    if len(devices) != 1:
        fail("HOLDER_MEMFD_DEVICE_AMBIGUOUS")
    return {"device": next(iter(devices)), "inode": MEMFD_INODE,
            "size": MEMFD_SIZE, "label": MEMFD_LABEL,
            "fd_count": len(matches), "entries_scanned": entries_scanned}


def model_maps_memfd(pid: int, memfd_device: int) -> bool:
    rows = read_maps_bounded(pid)
    if rows is None:
        fail("MODEL_MAPS_UNAVAILABLE_OR_OVER_LIMIT")
    if not mapped_inode(rows, memfd_device, MEMFD_INODE):
        fail("MODEL_MEMFD_MAPPING_NOT_PRESENT")
    return True


def memory_headroom(group: Path) -> dict:
    try:
        raw_max = (group / "memory.max").read_text().strip()
        raw_current = (group / "memory.current").read_text().strip()
        if not raw_max.isdigit() or not raw_current.isdigit():
            fail("CGROUP_MEMORY_LIMIT_UNBOUNDED_OR_INVALID")
        maximum, current = int(raw_max), int(raw_current)
    except OSError:
        fail("CGROUP_MEMORY_UNAVAILABLE")
    if maximum < current:
        fail("CGROUP_MEMORY_COUNTER_CONTRADICTION")
    return {"current": current, "max": maximum, "headroom": maximum - current}


def require_model_running() -> dict:
    status = supervisor_status()
    if status["state"] != "RUNNING" or status["pid"] != MODEL_PID:
        fail("MODEL_SUPERVISOR_IDENTITY_MISMATCH")
    return status


def require_model_identity_gone() -> str:
    first = proc_start_ticks(MODEL_PID, missing_ok=True)
    if first == MODEL_START_TICKS:
        fail("MODEL_PROCESS_STILL_PRESENT")
    if first is None:
        second = proc_start_ticks(MODEL_PID, missing_ok=True)
        if second is None:
            return "absent"
        if second == MODEL_START_TICKS:
            fail("MODEL_PROCESS_REAPPEARED")
        return "pid-reused"
    second = stable_start_ticks(MODEL_PID)
    if second == MODEL_START_TICKS:
        fail("MODEL_PROCESS_REAPPEARED")
    if second != first:
        fail("MODEL_PID_REUSE_UNSTABLE")
    return "pid-reused"


def wait_model_stopped() -> dict:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        status = supervisor_status()
        if status["state"] in ("STOPPED", "EXITED") and status["pid"] is None:
            ticks = proc_start_ticks(MODEL_PID, missing_ok=True)
            if ticks is None or ticks != MODEL_START_TICKS:
                PHASE["model_stopped"] = True
                return status
        time.sleep(0.5)
    fail("MODEL_GRACEFUL_STOP_NOT_VERIFIED")


def run_action(request_id: int, source_sha: str) -> dict:
    # Fresh read-only identity and memory preflight happens before any marker.
    status = require_model_running()
    model = process_identity(MODEL_PID, MODEL_START_TICKS, "MODEL")
    holder = process_identity(HOLDER_PID, HOLDER_START_TICKS, "HOLDER")
    if model["cgroup"] != holder["cgroup"]:
        fail("TARGETS_NOT_IN_SAME_CGROUP")
    memfd = fd_memfd_identity(HOLDER_PID)
    model_maps_memfd(MODEL_PID, memfd["device"])
    before = memory_headroom(Path(model["cgroup"]))
    if before["headroom"] >= MIN_HEADROOM:
        fail("HEADROOM_ALREADY_SAFE")

    # Create the owner fence only after a fresh low-headroom preflight.
    fence = ensure_owner_fence(request_id, source_sha)

    # Revalidate exact identities and headroom immediately before stopping.
    status = require_model_running()
    process_identity(MODEL_PID, MODEL_START_TICKS, "MODEL")
    latest_holder = process_identity(HOLDER_PID, HOLDER_START_TICKS, "HOLDER")
    if latest_holder["cgroup"] != holder["cgroup"]:
        fail("HOLDER_CGROUP_CHANGED_BEFORE_STOP")
    latest_memfd = fd_memfd_identity(HOLDER_PID)
    if (latest_memfd["device"] != memfd["device"] or
            latest_memfd["inode"] != memfd["inode"] or
            latest_memfd["size"] != memfd["size"] or
            latest_memfd["label"] != MEMFD_LABEL):
        fail("HOLDER_MEMFD_CHANGED_BEFORE_STOP")
    pre_stop = memory_headroom(Path(model["cgroup"]))
    if pre_stop["headroom"] >= MIN_HEADROOM:
        fail("HEADROOM_RECOVERED_BEFORE_STOP")

    PHASE["model_stop_requested"] = True
    stopped = command(["supervisorctl", "stop", SUPERVISOR_SERVICE], timeout=35)
    if stopped.returncode != 0:
        fail("SUPERVISOR_STOP_COMMAND_FAILED")
    after_status = wait_model_stopped()
    model_pid_state = require_model_identity_gone()

    # This version always preserves the memfd holder. A later owner action
    # must gather fresh evidence before considering any holder signal.
    latest_holder = process_identity(HOLDER_PID, HOLDER_START_TICKS, "HOLDER")
    latest_memfd = fd_memfd_identity(HOLDER_PID)
    if (latest_holder["cgroup"] != holder["cgroup"] or
            latest_memfd["device"] != memfd["device"] or
            latest_memfd["inode"] != memfd["inode"] or
            latest_memfd["size"] != memfd["size"] or
            latest_memfd["label"] != MEMFD_LABEL):
        fail("HOLDER_IDENTITY_CHANGED_AFTER_MODEL_STOP")
    after_model = memory_headroom(Path(holder["cgroup"]))
    return {"state": ("MODEL_STOPPED_HOLDER_PRESERVED_HEADROOM_MET" if
                      after_model["headroom"] >= MIN_HEADROOM else
                      "MODEL_STOPPED_HOLDER_PRESERVED_HEADROOM_STILL_SHORT"),
            "model": model, "holder": holder, "memfd": memfd,
            "before": before, "pre_stop": pre_stop,
            "after_model": after_model, "minimum_headroom": MIN_HEADROOM,
            "model_pid_state": model_pid_state, "markers": fence,
            "supervisor_after": after_status, "holder_signal": "NONE"}


def main() -> int:
    source_sha = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    request = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    if not SHA40.fullmatch(source_sha) or not request.isdigit():
        fail("OWNER_CONTEXT")
    if os.geteuid() != 0:
        fail("ROOT_REQUIRED")
    lock_fd = acquire_lock()
    try:
        receipt = run_action(int(request), source_sha)
        emit({"source_sha": source_sha, "request_id": int(request),
              "owner_fence_retained": True, **receipt})
        print("NOX_MAINT_EMERGENCY_STOP_COMPLETE=true", flush=True)
        return 0
    finally:
        with contextlib.suppress(Exception):
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        label = str(exc)
        if not re.fullmatch(r"HOLD_EMERGENCY_STOP_[A-Z0-9_]+", label):
            label = "HOLD_EMERGENCY_STOP_" + type(exc).__name__.upper()
        emit({"state": label, "phase": PHASE, "markers": MARKERS,
              "owner_fence_retained": bool(PHASE["stop_marker"] or PHASE["maintenance_marker"]),
              "no_rollback_or_restart": True})
        print("NOX_MAINT_EMERGENCY_STOP_RESULT=" + label, flush=True)
        raise SystemExit(2)
