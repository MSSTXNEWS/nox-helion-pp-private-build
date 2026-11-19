#!/usr/bin/env python3
"""Owner-only two-step emergency memory relief for one attested NOX model.

This source is inert until called by the pinned owner-maintenance workflow.
It stops only the exact Supervisor model service when fresh cgroup
headroom is below 2 GiB. This version always preserves the memfd holder and
never clears owner markers or restarts services.
"""
from __future__ import annotations

import contextlib
import configparser
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import time

ROOT = Path("/root/nox")
SUPERVISOR_CONFIG_DIR = Path("/etc/supervisor/conf.d")
SUPERVISOR_CLIENT_CONFIG = Path("/etc/supervisor/supervisord.conf")
SUPERVISORCTL_BIN = Path("/usr/bin/supervisorctl")
SUPERVISOR_CONFIG_MAX_FILES = 128
STOP = ROOT / "STOP"
MAINTENANCE = ROOT / "state/OWNER_MAINTENANCE.flag"
LOCK = ROOT / "state/owner_maintenance.lock"
CGROUP_ROOT = Path("/sys/fs/cgroup")
SUPERVISOR_SERVICE = "nox-ds41-8098"
MODEL_PID = 3266857
MODEL_START_TICKS = 172046662
MODEL_PATH = "/root/nox/models/deepseek_v41_flash_iq2xxs/DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf"
HOLDER_PID = 498569
HOLDER_START_TICKS = 168416044
HOLDER_SCRIPT = "/root/nox/engram_ram/engram_memfd_holder.py"
HOLDER_CWD = "/root/nox/engram_ram"
HOLDER_SCRIPT_PATH_SHA256 = "353c37488551c902ee42bc1826068a047195d296c3d5d83ed01d359e88ab6e6d"
HOLDER_CWD_SHA256 = "3c590f2f120bd22263af64a761d1c04ce54cbf99bbabdb83ce41122d75cc85d1"
HOLDER_CMDLINE_SHA256 = "35f379354687daac56932bc6cd415f5c83321db4b50b3ccb4766b035cf0e45d2"
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
    "LLAMA_ARG_KV_UNIFIED", "LLAMA_ARG_KV_UNIFIED_PER_SLOT", "LLAMA_ARG_N_PARALLEL",
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
MAX_PROC_PATH_BYTES = 4_096
MAX_SUPERVISOR_CONFIG_BYTES = 250_000
MAX_EXECUTABLE_BYTES = 256 * 1024 * 1024
MAX_PROCESS_TABLE_ENTRIES = 8_192
MAX_CGROUP_RUNTIME_PROCESSES = 512
MAX_ENV_BYTES = 256 * 1024
MAX_FD_ENTRIES_PER_PID = 16_384
MAX_HOLDER_FD_BYTES = 1 * 1024 * 1024
MAX_FD_LINK_BYTES = 4_096
MAX_MAPS_BYTES = 2 * 1024 * 1024
OWNER_LOCK_WAIT_SECONDS = 5.0
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
DIAGNOSTICS = {}


def fail(label: str) -> None:
    raise RuntimeError("HOLD_EMERGENCY_STOP_" + label)


def emit(payload: dict) -> None:
    print("NOX_MAINT_EMERGENCY_STOP=" + json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ), flush=True)


def root_directory(path: Path):
    try:
        st = path.lstat()
    except OSError:
        fail("REQUIRED_DIRECTORY_MISSING")
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
        fail("UNSAFE_DIRECTORY")
    return st


def read_root_regular(path: Path, limit: int, label: str,
                      include_ctime: bool = False):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                     getattr(os, "O_CLOEXEC", 0))
    except OSError:
        fail(label + "_UNAVAILABLE")
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or
                before.st_nlink != 1 or before.st_mode & 0o022 or
                before.st_size > limit):
            fail(label + "_UNSAFE")
        chunks = []
        total = 0
        while total <= limit:
            chunk = os.read(fd, min(65_536, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        after = os.fstat(fd)
        if (total > limit or any(getattr(before, key) != getattr(after, key) for key in
                ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"))):
            fail(label + "_CHANGED_OR_OVERSIZED")
        content = b"".join(chunks)
        return (content, after.st_ctime_ns) if include_ctime else content
    finally:
        os.close(fd)


def linux_boot_time_ns() -> int:
    """Read the kernel boot epoch used to translate proc start ticks."""
    try:
        fd = os.open("/proc/stat", os.O_RDONLY | os.O_NOFOLLOW |
                     os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
    except OSError:
        fail("LINUX_BOOT_TIME_UNAVAILABLE")
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != 0:
            fail("LINUX_BOOT_TIME_UNSAFE")
        raw = os.read(fd, 1_048_577)
        after = os.fstat(fd)
        if (len(raw) > 1_048_576 or before.st_dev != after.st_dev or
                before.st_ino != after.st_ino):
            fail("LINUX_BOOT_TIME_UNSTABLE_OR_OVERSIZED")
    finally:
        os.close(fd)
    try:
        lines = [line for line in raw.splitlines()
                 if line.startswith(b"btime ")]
        if len(lines) != 1:
            fail("LINUX_BOOT_TIME_INVALID")
        value = lines[0].split()
        if len(value) != 2 or not value[1].isdigit():
            fail("LINUX_BOOT_TIME_INVALID")
        return int(value[1]) * 1_000_000_000
    except (ValueError, IndexError):
        fail("LINUX_BOOT_TIME_INVALID")


def verify_root_executable_path(path_text: str, label: str) -> dict:
    path = Path(path_text)
    if not path.is_absolute() or ".." in path.parts:
        fail(label + "_PATH_INVALID")
    for parent in reversed(path.parents):
        try:
            st = parent.lstat()
        except OSError:
            fail(label + "_PARENT_UNAVAILABLE")
        if (not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or
                st.st_mode & 0o022):
            fail(label + "_PARENT_UNSAFE")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                     getattr(os, "O_CLOEXEC", 0))
    except OSError:
        fail(label + "_UNAVAILABLE")
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or
                before.st_nlink != 1 or before.st_mode & 0o022 or
                not before.st_mode & 0o111 or
                before.st_size > MAX_EXECUTABLE_BYTES):
            fail(label + "_UNSAFE")
        digest = hashlib.sha256()
        total = 0
        while total <= MAX_EXECUTABLE_BYTES:
            chunk = os.read(fd, min(65_536, MAX_EXECUTABLE_BYTES + 1 - total))
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
        after = os.fstat(fd)
        if (total > MAX_EXECUTABLE_BYTES or any(
                getattr(before, key) != getattr(after, key) for key in
                ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"))):
            fail(label + "_CHANGED_OR_OVERSIZED")
        try:
            entry = path.lstat()
        except OSError:
            fail(label + "_PATH_CHANGED")
        if (not stat.S_ISREG(entry.st_mode) or entry.st_dev != after.st_dev or
                entry.st_ino != after.st_ino):
            fail(label + "_PATH_CHANGED")
        file_stat = {key: getattr(after, key) for key in (
            "st_dev", "st_ino", "st_uid", "st_gid", "st_mode", "st_nlink",
            "st_size", "st_mtime_ns", "st_ctime_ns")}
        return {"path": path_text,
                "path_sha256": hashlib.sha256(os.fsencode(path_text)).hexdigest(),
                "sha256": digest.hexdigest(), "stat": file_stat}
    finally:
        os.close(fd)


def read_supervisor_stop_settings() -> dict:
    """Read the active daemon config and its one supported include directory."""
    DIAGNOSTICS["supervisor_stanza"] = {"state": "READ_ONLY_CONFIG_READ_STARTED"}
    supervisor_dir = root_directory(Path("/etc/supervisor"))
    include_dir = root_directory(SUPERVISOR_CONFIG_DIR)
    # Every supervisorctl client call pins this same config path. The daemon's
    # own argv is checked below against this exact path before its stanza is
    # treated as the active stop policy.
    pid_result = command(["supervisorctl", "-c", str(SUPERVISOR_CLIENT_CONFIG), "pid"])
    pid_lines = pid_result.stdout.strip().splitlines()
    if pid_result.returncode != 0 or len(pid_lines) != 1 or not pid_lines[0].isdecimal():
        DIAGNOSTICS["supervisor_stanza"] = {"state": "SUPERVISOR_PID_UNAVAILABLE"}
        fail("SUPERVISOR_PID_UNAVAILABLE")
    client_identity = dict(DIAGNOSTICS.get("supervisorctl_client", {}))
    if (client_identity.get("path") != str(SUPERVISORCTL_BIN) or
            not re.fullmatch(r"[0-9a-f]{64}", client_identity.get("sha256", ""))):
        fail("SUPERVISORCTL_CLIENT_IDENTITY_MISSING")
    daemon_pid = int(pid_lines[0])
    daemon_before = proc_stat_identity(daemon_pid)
    boot_time_ns = linux_boot_time_ns()
    try:
        ticks_per_second = int(os.sysconf("SC_CLK_TCK"))
    except (ValueError, OSError):
        fail("SUPERVISOR_START_TIME_UNAVAILABLE")
    if ticks_per_second <= 0:
        fail("SUPERVISOR_START_TIME_UNAVAILABLE")
    # btime is second-resolution and start_ticks is tick-resolution. Subtract
    # both rounding bounds so this is an earliest-possible start epoch, not an
    # optimistic point estimate for the ctime comparison.
    daemon_start_lower_bound_ns = (
        boot_time_ns +
        daemon_before["start_ticks"] * 1_000_000_000 // ticks_per_second -
        1_000_000_000 -
        (1_000_000_000 + ticks_per_second - 1) // ticks_per_second)
    try:
        daemon_exe = os.readlink(Path("/proc") / str(daemon_pid) / "exe")
        with (Path("/proc") / str(daemon_pid) / "cmdline").open("rb") as stream:
            daemon_cmdline = stream.read(MAX_CMDLINE_BYTES + 1)
    except OSError:
        fail("SUPERVISOR_CMDLINE_UNAVAILABLE")
    if len(daemon_cmdline) > MAX_CMDLINE_BYTES or not daemon_cmdline.endswith(b"\0"):
        fail("SUPERVISOR_CMDLINE_INVALID")
    try:
        daemon_argv = [part.decode("utf-8", "strict")
                       for part in daemon_cmdline[:-1].split(b"\0")]
    except UnicodeDecodeError:
        fail("SUPERVISOR_CMDLINE_ENCODING_INVALID")
    if len(daemon_argv) < 2 or any(not part for part in daemon_argv):
        fail("SUPERVISOR_ARGV_INVALID")
    exe_name = Path(daemon_exe.removesuffix(" (deleted)")).name
    argv_names = [Path(part.removesuffix(" (deleted)")).name
                  for part in daemon_argv]
    if exe_name == "supervisord":
        supervisor_positions = [i for i, name in enumerate(argv_names)
                                if name == "supervisord"]
    elif re.fullmatch(r"python3(?:\.[0-9]+)?", exe_name):
        supervisor_positions = [i for i, name in enumerate(argv_names)
                                if name == "supervisord"]
    else:
        fail("SUPERVISOR_PROCESS_EXECUTABLE_MISMATCH")
    if len(supervisor_positions) != 1:
        fail("SUPERVISOR_PROCESS_ARGV_MISMATCH")
    supervisor_script = daemon_argv[supervisor_positions[0]]
    if not Path(supervisor_script).is_absolute():
        fail("SUPERVISOR_SCRIPT_PATH_NOT_ABSOLUTE")
    daemon_exe_identity = verify_root_executable_path(
        daemon_exe.removesuffix(" (deleted)"), "SUPERVISOR_DAEMON_EXECUTABLE")
    daemon_script_identity = verify_root_executable_path(
        supervisor_script, "SUPERVISOR_DAEMON_SCRIPT")
    config_paths = []
    index = 1
    while index < len(daemon_argv):
        token = daemon_argv[index]
        if token in ("-c", "--configuration"):
            if index + 1 >= len(daemon_argv):
                fail("SUPERVISOR_CONFIG_PATH_MISSING")
            config_paths.append(daemon_argv[index + 1])
            index += 2
            continue
        if token.startswith("--configuration="):
            config_paths.append(token.partition("=")[2])
        index += 1
    if len(config_paths) != 1:
        fail("SUPERVISOR_CONFIG_PATH_AMBIGUOUS")
    main_path = Path(config_paths[0])
    if (not main_path.is_absolute() or ".." in main_path.parts or
            main_path != SUPERVISOR_CLIENT_CONFIG):
        fail("SUPERVISOR_CONFIG_PATH_OUT_OF_SCOPE")
    main_raw, main_ctime_ns = read_root_regular(
        main_path, MAX_SUPERVISOR_CONFIG_BYTES, "SUPERVISOR_MAIN_CONFIG",
        include_ctime=True)
    try:
        main_config = configparser.ConfigParser(interpolation=None, strict=True)
        main_config.read_string(main_raw.decode("utf-8", "strict"))
        include_text = main_config.get("include", "files", fallback="").strip()
        include_parts = shlex.split(include_text)
    except (configparser.Error, UnicodeError, ValueError):
        fail("SUPERVISOR_MAIN_CONFIG_PARSE_FAILED")
    allowed_globs = {str(SUPERVISOR_CONFIG_DIR / "*.conf"), "conf.d/*.conf"}
    if len(include_parts) != 1 or include_parts[0] not in allowed_globs:
        DIAGNOSTICS["supervisor_stanza"] = {
            "state": "SUPERVISOR_INCLUDE_UNSUPPORTED",
            "main_config_path": str(main_path),
            "main_config_sha256": hashlib.sha256(main_raw).hexdigest(),
        }
        fail("SUPERVISOR_INCLUDE_UNSUPPORTED")

    names = []
    try:
        with os.scandir(SUPERVISOR_CONFIG_DIR) as entries:
            for entry in entries:
                if entry.name.endswith(".conf"):
                    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}\.conf", entry.name):
                        fail("SUPERVISOR_CONFIG_FILENAME_UNSAFE")
                    names.append(entry.name)
                    if len(names) > SUPERVISOR_CONFIG_MAX_FILES:
                        fail("SUPERVISOR_CONFIG_FILE_LIMIT")
    except OSError:
        fail("SUPERVISOR_CONFIG_DIRECTORY_UNAVAILABLE")
    inputs = [{"name": main_path.name,
               "sha256": hashlib.sha256(main_raw).hexdigest(),
               "ctime_ns": main_ctime_ns}]
    matches = []
    for name in sorted(names):
        path = SUPERVISOR_CONFIG_DIR / name
        raw, config_ctime_ns = read_root_regular(
            path, MAX_SUPERVISOR_CONFIG_BYTES, "SUPERVISOR_INCLUDED_CONFIG",
            include_ctime=True)
        digest = hashlib.sha256(raw).hexdigest()
        inputs.append({"name": name, "sha256": digest,
                       "ctime_ns": config_ctime_ns})
        try:
            parser = configparser.ConfigParser(interpolation=None, strict=True)
            parser.read_string(raw.decode("utf-8", "strict"))
        except (configparser.Error, UnicodeError):
            fail("SUPERVISOR_INCLUDED_CONFIG_PARSE_FAILED")
        section = "program:" + SUPERVISOR_SERVICE
        if parser.has_section(section):
            command_text = parser.get(section, "command", fallback="")
            stopasgroup = parser.get(section, "stopasgroup", fallback="").strip().lower()
            killasgroup = parser.get(section, "killasgroup", fallback="").strip().lower()
            stopsignal = parser.get(section, "stopsignal", fallback="").strip().upper()
            stopwaitsecs = parser.get(section, "stopwaitsecs", fallback="").strip()
            matches.append({
                "path": str(path), "config_sha256": digest,
                "command_sha256": hashlib.sha256(command_text.encode()).hexdigest(),
                "stopasgroup": stopasgroup if stopasgroup in ("true", "false") else None,
                "killasgroup": killasgroup if killasgroup in ("true", "false") else None,
                "stopsignal": stopsignal if re.fullmatch(r"[A-Z0-9]+", stopsignal) else None,
                "stopwaitsecs": int(stopwaitsecs) if stopwaitsecs.isdecimal() else None,
            })
    supervisor_dir_after = root_directory(Path("/etc/supervisor"))
    include_dir_after = root_directory(SUPERVISOR_CONFIG_DIR)
    directory_metadata = ("st_dev", "st_ino", "st_mtime_ns", "st_ctime_ns")
    if (any(getattr(supervisor_dir, key) != getattr(supervisor_dir_after, key)
            for key in directory_metadata) or
            any(getattr(include_dir, key) != getattr(include_dir_after, key)
                for key in directory_metadata)):
        fail("SUPERVISOR_CONFIG_DIRECTORY_CHANGED_DURING_READ")
    if (supervisor_dir.st_ctime_ns > daemon_start_lower_bound_ns or
            include_dir.st_ctime_ns > daemon_start_lower_bound_ns or
            any(item["ctime_ns"] > daemon_start_lower_bound_ns for item in inputs)):
        DIAGNOSTICS["supervisor_stanza"] = {
            "state": "SUPERVISOR_CONFIG_NEWER_THAN_DAEMON_START",
            "supervisor_start_lower_bound_ns": daemon_start_lower_bound_ns,
            "config_inputs": inputs,
            "supervisor_dir_ctime_ns": supervisor_dir.st_ctime_ns,
            "include_dir_ctime_ns": include_dir.st_ctime_ns,
        }
        fail("SUPERVISOR_CONFIG_NEWER_THAN_DAEMON_START")
    try:
        exe_after = os.readlink(Path("/proc") / str(daemon_pid) / "exe")
        with (Path("/proc") / str(daemon_pid) / "cmdline").open("rb") as stream:
            cmdline_after = stream.read(MAX_CMDLINE_BYTES + 1)
    except OSError:
        fail("SUPERVISOR_IDENTITY_REREAD_UNAVAILABLE")
    daemon_after = proc_stat_identity(daemon_pid)
    if (len(cmdline_after) > MAX_CMDLINE_BYTES or daemon_before != daemon_after or
            daemon_cmdline != cmdline_after or exe_after != daemon_exe):
        fail("SUPERVISOR_IDENTITY_CHANGED_DURING_CONFIG_READ")
    exe_identity_after = verify_root_executable_path(
        exe_after.removesuffix(" (deleted)"), "SUPERVISOR_DAEMON_EXECUTABLE_REREAD")
    script_identity_after = verify_root_executable_path(
        supervisor_script, "SUPERVISOR_DAEMON_SCRIPT_REREAD")
    if (exe_identity_after != daemon_exe_identity or
            script_identity_after != daemon_script_identity):
        fail("SUPERVISOR_EXECUTABLE_CONTENT_CHANGED_DURING_CONFIG_READ")
    daemon_identity = {
        "pid": daemon_pid,
        "start_ticks": daemon_before["start_ticks"],
        "exe": daemon_exe_identity,
        "script": daemon_script_identity,
        "argv_sha256": hashlib.sha256(daemon_cmdline).hexdigest(),
        "config_path": str(main_path),
        "start_lower_bound_ns": daemon_start_lower_bound_ns,
    }

    effective_sha = hashlib.sha256(json.dumps(
        inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    DIAGNOSTICS["supervisor_stanza"] = {
        "matches": matches,
        "source": "active_daemon_cmdline_and_all_root_owned_conf_d_inputs",
        "supervisor_pid": daemon_pid,
        "supervisor_start_ticks": daemon_before["start_ticks"],
        "supervisor_start_lower_bound_ns": daemon_start_lower_bound_ns,
        "supervisor_cmdline_sha256": hashlib.sha256(daemon_cmdline).hexdigest(),
        "supervisor_argv_sha256": hashlib.sha256(daemon_cmdline).hexdigest(),
        "supervisor_exe": daemon_exe_identity,
        "supervisor_script": daemon_script_identity,
        "supervisorctl_client": client_identity,
        "main_config_path": str(main_path),
        "main_config_sha256": hashlib.sha256(main_raw).hexdigest(),
        "include_glob": include_parts[0], "config_inputs": inputs,
        "effective_config_sha256": effective_sha,
    }
    if len(matches) != 1:
        fail("SUPERVISOR_STANZA_NOT_UNIQUE")
    settings = {**matches[0], "effective_config_sha256": effective_sha,
                "supervisor_pid": daemon_pid,
                "supervisor_start_ticks": daemon_before["start_ticks"],
                "daemon_identity": daemon_identity,
                "supervisorctl_client": client_identity}
    if (settings["stopasgroup"] not in ("true", "false") or
            settings["killasgroup"] not in ("true", "false") or
            settings["stopwaitsecs"] is None or not 1 <= settings["stopwaitsecs"] <= 30 or
            settings["stopsignal"] != "TERM"):
        fail("SUPERVISOR_STOP_SEMANTICS_UNKNOWN_OR_UNBOUNDED")
    if settings["stopasgroup"] != "false" or settings["killasgroup"] != "false":
        fail("SUPERVISOR_STOP_NOT_DIRECT_PID_ONLY")
    return settings


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
        deadline = time.monotonic() + OWNER_LOCK_WAIT_SECONDS
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    fail("OWNER_LOCK_BUSY_TIMEOUT")
                time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
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


def verify_supervisorctl_executable() -> str:
    path = SUPERVISORCTL_BIN
    if path != Path("/usr/bin/supervisorctl"):
        fail("SUPERVISORCTL_PATH_NOT_PINNED")
    identity = verify_root_executable_path(str(path), "SUPERVISORCTL_EXECUTABLE")
    identity["root_owned_nonwritable"] = True
    DIAGNOSTICS["supervisorctl_client"] = identity
    return identity["sha256"]


def command(argv: list[str], timeout: int = 15,
            verified_client_sha256: str | None = None) -> subprocess.CompletedProcess:
    if not argv or argv[0] != "supervisorctl":
        fail("COMMAND_OUTSIDE_SUPERVISORCTL_SCOPE")
    if verified_client_sha256 is None:
        verify_supervisorctl_executable()
    elif (not re.fullmatch(r"[0-9a-f]{64}", verified_client_sha256) or
          DIAGNOSTICS.get("supervisorctl_client", {}).get("sha256") !=
          verified_client_sha256):
        fail("SUPERVISORCTL_VERIFICATION_TOKEN_INVALID")
    try:
        return subprocess.run(
            [str(SUPERVISORCTL_BIN), *argv[1:]], shell=False,
            capture_output=True, text=True, timeout=timeout, check=False,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C",
                 "LC_ALL": "C", "HOME": "/root"})
    except (OSError, subprocess.TimeoutExpired):
        fail("COMMAND_UNAVAILABLE")


def supervisor_status() -> dict:
    p = command(["supervisorctl", "-c", str(SUPERVISOR_CLIENT_CONFIG),
                 "status", SUPERVISOR_SERVICE])
    lines = p.stdout.strip().splitlines()
    m = STATUS_LINE.fullmatch(lines[0]) if len(lines) == 1 else None
    if m is None or m.group(1) != SUPERVISOR_SERVICE:
        fail("SUPERVISOR_STATUS_UNTRUSTED")
    state = m.group(2)
    pid = int(m.group(3)) if m.group(3) else None
    if ((state == "RUNNING" and (p.returncode != 0 or pid is None)) or
            (state in ("STOPPED", "EXITED") and
             (p.returncode != 3 or pid is not None))):
        fail("SUPERVISOR_RC_STATE_PID_CONTRADICTION")
    return {"state": state, "pid": pid, "rc": p.returncode}


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


def proc_stat_identity(pid: int, missing_ok: bool = False):
    path = Path("/proc") / str(pid) / "stat"
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                     getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
        try:
            raw = os.read(fd, MAX_STAT_BYTES + 1)
        finally:
            os.close(fd)
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
        if not fields[1].isdigit() or not fields[2].isdigit() or not fields[19].isdigit():
            fail("PROC_STAT_FIELDS_INVALID")
        return {"pid": pid, "ppid": int(fields[1]), "pgrp": int(fields[2]),
                "start_ticks": int(fields[19])}
    except (ValueError, IndexError):
        fail("PROC_STAT_PARSE_FAILED")


def proc_start_ticks(pid: int, missing_ok: bool = False):
    identity = proc_stat_identity(pid, missing_ok=missing_ok)
    return identity["start_ticks"] if identity is not None else None


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


def _selector_option(token: str) -> str:
    return token.split("=", 1)[0]


def _canonical_long_option(option: str) -> str:
    return option.replace("_", "-") if option.startswith("--") else option


def _selector_preflight_hold(reason: str, options: list[str]) -> None:
    # Values are deliberately absent; only validated option spellings leave the host.
    safe = sorted({option for option in options
                   if re.fullmatch(r"-{1,2}[A-Za-z0-9][A-Za-z0-9_-]*", option)})
    emit({"phase": "preflight_rejected", "reason": reason,
          "matched_selector_options": safe})
    fail(reason)


def _reject_selector_like_operand(option: str, operand: str, allow_parallel_auto: bool = False) -> None:
    if operand == "":
        _selector_preflight_hold("MODEL_OPTION_OPERAND_EMPTY", [option])
    if operand.startswith("-") and not (allow_parallel_auto and operand == "-1"):
        _selector_preflight_hold("MODEL_OPTION_OPERAND_AMBIGUOUS",
                                 [option, _selector_option(operand)])


def reject_model_context_selectors(args: list[str]) -> None:
    """Reject direct model/context overrides; shard/parallel operands stay opaque."""
    short_selectors = {
        "-mu", "-dr", "-hf", "-hfr", "-hff", "-mm", "-mmu",
        "-md", "-hfd", "-hfrd", "-ns", "-ctx", "-ctxcp",
        "-kvu", "-no-kvu", "-fit", "-fitc",
    }
    long_prefixes = (
        "--model", "--base-model", "--student", "--draft-model", "--hf",
        "--mmproj", "--models-", "--spec-draft-",
        "--config", "--ctx-size", "--kv-unified", "--rope-", "--yarn-", "--parallel-",
        "--lora-", "--control-vector-", "--override-kv-",
    )
    long_exact = {
        "--docker-repo", "--shard", "--ple", "--kv-unified-per-slot",
        "--no-kv-unified", "--mtp", "--dflash", "--eagle3", "--spec-type",
        "--parallel", "--np", "--n-parallel", "--sequences",
        "--ctx-checkpoints", "--swa-checkpoints",
        "--swa-full", "--fit", "--fit-ctx", "--spec-draft",
        "--override-kv", "--lora",
        "--control-vector", "--control-vector-scaled", "--control-vector-layer-range",
    }
    preset_prefixes = ("--embd-", "--fim-", "--gpt-oss-", "--vision-gemma-")
    value_options = {
        "--alias", "--host", "--port", "--path", "--api-key", "--api-key-file",
        "--threads", "--threads-http", "--threads-batch", "--n-gpu-layers",
        "--gpu-layers", "--device", "--devices", "--split-mode", "--tensor-split",
        "--main-gpu", "--cache-type-k", "--cache-type-v", "--batch-size",
        "--ubatch-size", "--timeout", "--log-file", "--log-format",
        "--chat-template", "--chat-template-file", "--chat-template-kwargs",
        "--reasoning-format", "--hf-token", "--rpc", "--cpu-mask",
    }
    boolean_options = {
        "--no-webui", "--metrics", "--embedding", "--reranking", "--jinja",
        "--no-mmap", "--mlock", "--no-context-shift", "--no-perf",
        "--cont-batching", "--no-cont-batching", "--no-flash-attn",
        "--verbose", "--log-disable", "--cache-prompt",
        "--no-cache-prompt", "--swa-full",
    }
    opaque_options = {"--shard", "--ple", "-np", "--parallel"}
    opaque_families = {"--shard": "shard", "--ple": "shard",
                       "-np": "parallel", "--parallel": "parallel"}
    opaque_seen = {"shard": [], "parallel": []}
    for token in args:
        option = _canonical_long_option(_selector_option(token))
        family = opaque_families.get(option)
        if family is not None:
            opaque_seen[family].append(_selector_option(token))
    for options in opaque_seen.values():
        if len(options) > 1:
            _selector_preflight_hold("MODEL_OPAQUE_SELECTOR_DUPLICATE", options)

    index = 0
    while index < len(args):
        token = args[index]
        raw_option = _selector_option(token)
        option = _canonical_long_option(raw_option)
        inline_value = token.partition("=")[2] if "=" in token else None
        selector_like = (option in opaque_options or
                         token.startswith("-c=") or token.startswith("-m=") or
                         option in short_selectors or option in long_exact or
                         option.startswith(long_prefixes) or
                         option.startswith(preset_prefixes))
        if selector_like and index > 0 and "=" not in args[index - 1]:
            previous = args[index - 1]
            previous_option = _canonical_long_option(_selector_option(previous))
            if (previous.startswith("-") and previous_option not in boolean_options and
                    previous_option not in value_options and previous_option not in ("-m", "-c")):
                _selector_preflight_hold("MODEL_ARGUMENT_ARITY_AMBIGUOUS",
                                         [_selector_option(previous), raw_option])
        if option in opaque_options:
            if inline_value is not None:
                _reject_selector_like_operand(
                    raw_option, inline_value,
                    allow_parallel_auto=option in ("-np", "--parallel"))
                index += 1
            elif index + 1 < len(args):
                operand = args[index + 1]
                _reject_selector_like_operand(
                    raw_option, operand,
                    allow_parallel_auto=option in ("-np", "--parallel"))
                index += 2
            else:
                _selector_preflight_hold("MODEL_OPTION_VALUE_MISSING", [raw_option])
            continue
        if option in ("-m", "-c") and inline_value is None:
            if index + 1 >= len(args):
                _selector_preflight_hold("MODEL_BASE_SELECTOR_VALUE_MISSING", [raw_option])
            index += 2
            continue
        blocked = (token.startswith("-c=") or token.startswith("-m=") or
                   option in short_selectors or
                   (option in long_exact and option not in ("--parallel",)) or
                   option.startswith(long_prefixes) or option.startswith(preset_prefixes))
        if blocked:
            _selector_preflight_hold("MODEL_OR_CONTEXT_SELECTOR_ALIAS", [raw_option])
        if option in value_options:
            if inline_value is not None:
                _reject_selector_like_operand(raw_option, inline_value)
                index += 1
                continue
            if index + 1 >= len(args):
                _selector_preflight_hold("MODEL_OPTION_VALUE_MISSING", [raw_option])
            _reject_selector_like_operand(raw_option, args[index + 1])
            index += 2
            continue
        index += 1

    return None


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
    relevant_map = b"".join(
        name.encode("ascii") + b"=" + env[name] + b"\0"
        for name in sorted(env)
    )
    return {
        "model_env_present": "LLAMA_ARG_MODEL" in env,
        "ctx_env_present": "LLAMA_ARG_CTX_SIZE" in env,
        "model_source_env_present": any(name in env for name in MODEL_SOURCE_ENV_KEYS),
        "context_pool_env_present": any(name in env for name in MODEL_CONTEXT_ENV_KEYS),
        # Hash only: relevant environment values are never included in receipts.
        "environment_map_sha256": hashlib.sha256(relevant_map).hexdigest(),
    }


def process_identity(pid: int, expected_ticks: int, role: str) -> dict:
    stat_before = proc_stat_identity(pid)
    ticks = stable_start_ticks(pid, expected_ticks)
    if stat_before["start_ticks"] != ticks:
        fail(role + "_IDENTITY_CHANGED_DURING_READ")
    proc = Path("/proc") / str(pid)
    try:
        exe = os.readlink(proc / "exe")
        with (proc / "cmdline").open("rb") as stream:
            raw_cmdline = stream.read(MAX_CMDLINE_BYTES + 1)
    except OSError:
        fail(role + "_IDENTITY_UNAVAILABLE")
    if (len(os.fsencode(exe)) > MAX_PROC_PATH_BYTES or
            len(raw_cmdline) > MAX_CMDLINE_BYTES or not raw_cmdline.endswith(b"\0")):
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
        try:
            cwd = os.readlink(proc / "cwd")
        except OSError:
            fail("HOLDER_CWD_UNAVAILABLE")
        if len(os.fsencode(cwd)) > MAX_PROC_PATH_BYTES:
            fail("HOLDER_CWD_OVER_LIMIT")
        if (exe_name not in ("python3", "python3.11", "python3.12", "python3.13") or
                argv.count(HOLDER_SCRIPT) != 1 or cwd != HOLDER_CWD or
                hashlib.sha256(os.fsencode(HOLDER_SCRIPT)).hexdigest() !=
                HOLDER_SCRIPT_PATH_SHA256 or
                hashlib.sha256(os.fsencode(HOLDER_CWD)).hexdigest() != HOLDER_CWD_SHA256 or
                hashlib.sha256(raw_cmdline).hexdigest() != HOLDER_CMDLINE_SHA256):
            fail("HOLDER_EXPECTED_ENGRAM_PROCESS_MISMATCH")
    else:
        fail("UNKNOWN_PROCESS_ROLE")
    group = cgroup_path(pid)
    if role == "MODEL":
        environment_after_cgroup = model_environment_identity(pid, expected_ticks)
        if (environment_after_cgroup["environment_map_sha256"] !=
                environment_overrides["environment_map_sha256"]):
            fail("MODEL_ENVIRONMENT_CHANGED_DURING_READ")
        environment_overrides = environment_after_cgroup
    try:
        exe_after = os.readlink(proc / "exe")
        with (proc / "cmdline").open("rb") as stream:
            raw_cmdline_after = stream.read(MAX_CMDLINE_BYTES + 1)
        cwd_after = os.readlink(proc / "cwd") if role == "HOLDER" else None
    except OSError:
        fail(role + "_IDENTITY_REREAD_UNAVAILABLE")
    stat_after = proc_stat_identity(pid)
    if (len(raw_cmdline_after) > MAX_CMDLINE_BYTES or
            len(os.fsencode(exe_after)) > MAX_PROC_PATH_BYTES or
            (role == "HOLDER" and len(os.fsencode(cwd_after)) > MAX_PROC_PATH_BYTES) or
            not raw_cmdline_after.endswith(b"\0") or
            exe_after != exe or
            (role == "HOLDER" and cwd_after != cwd) or
            hashlib.sha256(raw_cmdline_after).digest() !=
            hashlib.sha256(raw_cmdline).digest() or
            stat_after != stat_before):
        fail(role + "_EXEC_IDENTITY_CHANGED_DURING_READ")
    if stable_start_ticks(pid, expected_ticks) != ticks:
        fail(role + "_IDENTITY_CHANGED_DURING_READ")
    if role == "MODEL":
        environment_final = model_environment_identity(pid, expected_ticks)
        if (environment_final["environment_map_sha256"] !=
                environment_overrides["environment_map_sha256"]):
            fail("MODEL_ENVIRONMENT_CHANGED_DURING_IDENTITY_READ")
        environment_overrides = environment_final
        stat_final = proc_stat_identity(pid)
        if stat_final != stat_before:
            fail("MODEL_PROCESS_GROUP_CHANGED_DURING_ENVIRONMENT_READ")
    return {"pid": pid, "start_ticks": ticks,
            "exe": (exe_name if role == "MODEL" else None),
            "exe_path_sha256": hashlib.sha256(os.fsencode(exe)).hexdigest(),
            "exe_basename": exe_name,
            "cwd_sha256": (hashlib.sha256(os.fsencode(cwd)).hexdigest()
                           if role == "HOLDER" else None),
            "cmdline_sha256": hashlib.sha256(raw_cmdline).hexdigest(),
            "ppid": stat_before["ppid"], "pgrp": stat_before["pgrp"],
            "argv_sha256": hashlib.sha256(b"\0".join(raw_argv)).hexdigest(),
            "environment_overrides": environment_overrides if role == "MODEL" else None,
            "cgroup": str(group)}


def target_model_argv_fingerprint(args: list[str]) -> tuple[str, str] | None:
    """Parse only known llama-server option arities; unknown syntax is HOLD."""
    value_options = {
        "--alias", "--host", "--port", "--path", "--api-key", "--api-key-file",
        "--threads", "--threads-http", "--threads-batch", "--n-gpu-layers",
        "--gpu-layers", "--device", "--devices", "--split-mode", "--tensor-split",
        "--main-gpu", "--cache-type-k", "--cache-type-v", "--batch-size",
        "--ubatch-size", "--timeout", "--log-file", "--log-format",
        "--chat-template", "--chat-template-file", "--chat-template-kwargs",
        "--reasoning-format", "--hf-token", "--rpc", "--cpu-mask",
        "--shard", "--ple", "-np", "--parallel",
    }
    boolean_options = {
        "--no-webui", "--metrics", "--embedding", "--reranking", "--jinja",
        "--no-mmap", "--mlock", "--no-context-shift", "--no-perf",
        "--cont-batching", "--no-cont-batching", "--no-flash-attn",
        "--verbose", "--log-disable", "--cache-prompt", "--no-cache-prompt",
        "--swa-full",
    }
    model_values = []
    context_values = []
    index = 0
    while index < len(args):
        token = args[index]
        option = _canonical_long_option(_selector_option(token))
        inline = token.partition("=")[2] if "=" in token else None
        if option in ("-m", "--model", "-c", "--ctx-size"):
            if inline is None:
                if index + 1 >= len(args) or args[index + 1].startswith("-"):
                    return None
                value = args[index + 1]
                index += 2
            else:
                if inline == "":
                    return None
                value = inline
                index += 1
            if option in ("-m", "--model"):
                model_values.append(value)
            else:
                context_values.append(value)
            continue
        if option in value_options:
            if inline is not None:
                if inline == "":
                    return None
                index += 1
                continue
            if index + 1 >= len(args):
                return None
            operand = args[index + 1]
            allow_negative_one = option in ("-np", "--parallel") and operand == "-1"
            if operand.startswith("-") and not allow_negative_one:
                return None
            index += 2
            continue
        if option in boolean_options:
            index += 1
            continue
        if option in ("--flash-attn", "--log-colors"):
            if (index + 1 < len(args) and not args[index + 1].startswith("-") and
                    _selector_option(args[index + 1]) == args[index + 1]):
                index += 2
            else:
                index += 1
            continue
        if token.startswith("-") or not token:
            return None
        # Positional values are ambiguous unless consumed by a known option.
        return None
    if len(model_values) != 1 or len(context_values) != 1:
        return None
    return model_values[0], context_values[0]


def cgroup_model_runtime_census(group: Path, model: dict) -> list[dict]:
    """Classify bounded cgroup members against the pinned model runtime fingerprint."""
    cgroup_before = cgroup_processes(group)
    if len(cgroup_before) > MAX_CGROUP_RUNTIME_PROCESSES:
        fail("CGROUP_RUNTIME_PROCESS_LIMIT")
    table_before = process_table_snapshot()
    rows = []
    for pid in cgroup_before:
        before = table_before.get(pid)
        if before is None:
            fail("CGROUP_RUNTIME_PID_IDENTITY_UNAVAILABLE")
        if before["state"] == "Z":
            rows.append({"pid": pid, "start_ticks": before["start_ticks"],
                         "exe_path_sha256": None, "argv_sha256": None,
                         "classification": "ZOMBIE"})
            continue
        proc = Path("/proc") / str(pid)
        try:
            exe = os.readlink(proc / "exe")
            with (proc / "cmdline").open("rb") as stream:
                raw_cmdline = stream.read(MAX_CMDLINE_BYTES + 1)
        except OSError:
            fail("CGROUP_RUNTIME_EXEC_IDENTITY_UNAVAILABLE")
        if (len(os.fsencode(exe)) > MAX_PROC_PATH_BYTES or
                len(raw_cmdline) > MAX_CMDLINE_BYTES or
                not raw_cmdline.endswith(b"\0")):
            fail("CGROUP_RUNTIME_EXEC_IDENTITY_INVALID")
        try:
            argv = [token.decode("utf-8", "strict")
                    for token in raw_cmdline[:-1].split(b"\0")]
        except UnicodeDecodeError:
            fail("CGROUP_RUNTIME_ARGV_ENCODING_INVALID")
        if not argv or any(not token for token in argv):
            fail("CGROUP_RUNTIME_ARGV_INVALID")
        exe_after = os.readlink(proc / "exe")
        with (proc / "cmdline").open("rb") as stream:
            raw_cmdline_after = stream.read(MAX_CMDLINE_BYTES + 1)
        after = process_table_row(pid, missing_ok=True)
        if (after is None or after["pid"] != pid or
                any(before[key] != after[key] for key in
                    ("pid", "start_ticks", "ppid", "pgrp", "state")) or
                exe_after != exe or raw_cmdline_after != raw_cmdline):
            fail("CGROUP_RUNTIME_EXEC_IDENTITY_CHANGED")
        exe_hash = hashlib.sha256(os.fsencode(exe)).hexdigest()
        argv_hash = hashlib.sha256(b"\0".join(token.encode() for token in argv)).hexdigest()
        if pid == MODEL_PID:
            if (before["start_ticks"] != MODEL_START_TICKS or
                    exe_hash != model["exe_path_sha256"] or
                    argv_hash != model["argv_sha256"]):
                fail("CGROUP_RUNTIME_PINNED_MODEL_MISMATCH")
            classification = "PINNED_TARGET_MODEL_RUNTIME"
        elif exe_hash != model["exe_path_sha256"]:
            classification = "OTHER_EXECUTABLE"
        else:
            fingerprint = target_model_argv_fingerprint(argv[1:])
            if fingerprint is None:
                classification = "SAME_EXECUTABLE_UNCLASSIFIED"
            elif fingerprint[0] == MODEL_PATH:
                classification = ("SAME_MODEL_PATH_AND_SERVING_FINGERPRINT"
                                  if fingerprint[1] == "8192" else
                                  "SAME_MODEL_PATH_OTHER_SERVING_CONTEXT")
            else:
                classification = "SAME_EXECUTABLE_OTHER_MODEL"
        rows.append({"pid": pid, "start_ticks": before["start_ticks"],
                     "exe_path_sha256": exe_hash, "argv_sha256": argv_hash,
                     "classification": classification})
    cgroup_after = cgroup_processes(group)
    table_after = process_table_snapshot()
    if cgroup_after != cgroup_before:
        fail("CGROUP_RUNTIME_MEMBERSHIP_CHANGED")
    for pid in cgroup_after:
        prior, current = table_before.get(pid), table_after.get(pid)
        if (prior is None or current is None or
                prior["start_ticks"] != current["start_ticks"] or
                prior["ppid"] != current["ppid"] or
                prior["pgrp"] != current["pgrp"] or
                (prior["state"] == "Z") != (current["state"] == "Z")):
            fail("CGROUP_RUNTIME_PROCESS_CENSUS_UNSTABLE")
    matches = [row for row in rows if row["classification"] in (
        "SAME_MODEL_PATH_AND_SERVING_FINGERPRINT",
        "SAME_MODEL_PATH_OTHER_SERVING_CONTEXT") and row["pid"] != MODEL_PID]
    unknown_same_exe = [row for row in rows
                        if row["classification"] == "SAME_EXECUTABLE_UNCLASSIFIED"]
    DIAGNOSTICS["model_runtime_cgroup"] = {
        "members": rows,
        "member_count": len(rows),
        "pinned_model_pid": MODEL_PID,
        "pinned_model_start_ticks": MODEL_START_TICKS,
        "target_model_exe_path_sha256": model["exe_path_sha256"],
        "target_model_argv_sha256": model["argv_sha256"],
        "scope": "PID_START_TICKS_EXE_PATH_AND_ARGV_HASH_CLASSIFICATION_ONLY",
    }
    if matches:
        fail("OTHER_PINNED_MODEL_RUNTIME_IN_CGROUP")
    if unknown_same_exe:
        fail("CGROUP_MODEL_RUNTIME_CLASSIFICATION_UNKNOWN")
    return rows


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


def model_maps_memfd(
    pid: int, memfd_device: int, expected_ticks: int = MODEL_START_TICKS
) -> bool:
    before = proc_stat_identity(pid)
    if before["start_ticks"] != expected_ticks:
        fail("MODEL_MAPS_PROCESS_CHANGED")
    rows = read_maps_bounded(pid)
    if rows is None:
        fail("MODEL_MAPS_UNAVAILABLE_OR_OVER_LIMIT")
    if not mapped_inode(rows, memfd_device, MEMFD_INODE):
        fail("MODEL_MEMFD_MAPPING_NOT_PRESENT")
    after = proc_stat_identity(pid)
    if after != before:
        fail("MODEL_MAPS_PROCESS_CHANGED")
    return True


def require_holder_outside_model_group(model: dict, holder: dict) -> None:
    if (type(model.get("pgrp")) is not int or type(holder.get("pgrp")) is not int or
            model["pgrp"] == holder["pgrp"]):
        fail("HOLDER_IN_MODEL_PROCESS_GROUP")


def require_same_process_identity(before: dict, after: dict, role: str) -> None:
    if before != after:
        fail(role + "_FULL_IDENTITY_CHANGED")


def process_table_row(pid: int, missing_ok: bool = True) -> dict | None:
    path = Path("/proc") / str(pid) / "stat"
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                     getattr(os, "O_CLOEXEC", 0))
        try:
            raw = os.read(fd, MAX_STAT_BYTES + 1)
        finally:
            os.close(fd)
    except FileNotFoundError:
        if missing_ok:
            return None
        fail("PROCESS_TABLE_PID_MISSING")
    except OSError:
        fail("PROCESS_TABLE_PID_UNREADABLE")
    if len(raw) > MAX_STAT_BYTES:
        fail("PROCESS_TABLE_STAT_TOO_LARGE")
    text = raw.decode("ascii", "replace")
    match = re.match(r"^([0-9]+) [(]", text)
    fields = text.rsplit(")", 1)[1].split()
    if match is None or int(match.group(1)) != pid or len(fields) <= 19:
        fail("PROCESS_TABLE_STAT_INVALID")
    try:
        if (not re.fullmatch(r"[A-Z]", fields[0]) or
                not fields[1].isdigit() or not fields[2].isdigit() or
                not fields[19].isdigit()):
            fail("PROCESS_TABLE_STAT_FIELDS_INVALID")
        return {"pid": pid, "state": fields[0], "ppid": int(fields[1]),
                "pgrp": int(fields[2]), "start_ticks": int(fields[19])}
    except (ValueError, IndexError):
        fail("PROCESS_TABLE_STAT_PARSE_FAILED")


def process_table_snapshot() -> dict[int, dict]:
    rows = {}
    scanned = 0
    try:
        with os.scandir("/proc") as entries:
            for entry in entries:
                if not entry.name.isdecimal():
                    continue
                scanned += 1
                if scanned > MAX_PROCESS_TABLE_ENTRIES:
                    fail("PROCESS_TABLE_ENTRY_LIMIT")
                pid = int(entry.name)
                row = process_table_row(pid, missing_ok=True)
                if row is not None:
                    rows[pid] = row
    except OSError:
        fail("PROCESS_TABLE_CENSUS_UNAVAILABLE")
    return rows


def target_descendants(table: dict[int, dict]) -> list[dict]:
    root = table.get(MODEL_PID)
    if root is None or root["start_ticks"] != MODEL_START_TICKS:
        fail("MODEL_MISSING_FROM_PROCESS_TABLE")
    descendants = []
    for pid, row in table.items():
        if pid == MODEL_PID:
            continue
        parent = row["ppid"]
        seen = {pid}
        depth = 0
        while parent and parent not in seen and depth < 128:
            if parent == MODEL_PID:
                descendants.append(row)
                break
            seen.add(parent)
            parent_row = table.get(parent)
            if parent_row is None:
                break
            parent = parent_row["ppid"]
            depth += 1
        if depth >= 128:
            fail("PROCESS_TREE_DEPTH_LIMIT")
    return sorted(descendants, key=lambda row: row["pid"])


def cgroup_processes(group: Path) -> list[int]:
    path = group / "cgroup.procs"
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                     getattr(os, "O_CLOEXEC", 0))
    except OSError:
        fail("CGROUP_PROCS_UNAVAILABLE")
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
            fail("CGROUP_PROCS_UNSAFE")
        chunks = []
        total = 0
        while total <= 512 * 1024:
            chunk = os.read(fd, min(65_536, 512 * 1024 + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
    finally:
        os.close(fd)
    if total > 512 * 1024:
        fail("CGROUP_PROCS_OVER_LIMIT")
    raw = b"".join(chunks)
    rows = raw.splitlines()
    if len(rows) > MAX_PROCESS_TABLE_ENTRIES or any(
            not row.isdigit() for row in rows):
        fail("CGROUP_PROCS_INVALID")
    values = [int(row) for row in rows]
    if len(values) != len(set(values)):
        fail("CGROUP_PROCS_DUPLICATE_PID")
    return sorted(values)


def require_exclusive_model_process_group(model: dict,
                                          settings: dict | None = None) -> dict:
    """Prove bounded Supervisor signal scope from stable config/procfs snapshots."""
    group = model.get("pgrp")
    if type(group) is not int or model.get("pid") != MODEL_PID:
        fail("MODEL_PROCESS_GROUP_IDENTITY_UNKNOWN")
    settings_error = None
    if settings is None:
        try:
            settings = read_supervisor_stop_settings()
        except RuntimeError as exc:
            settings_error = str(exc)
    cgroup = Path(model["cgroup"])
    cgroup_before = cgroup_processes(cgroup)
    if cgroup_processes(cgroup) != cgroup_before:
        fail("CGROUP_PROCS_CHANGED_DURING_PREFLIGHT")

    table_first = process_table_snapshot()
    descendants_first = target_descendants(table_first)
    table_second = process_table_snapshot()
    descendants = target_descendants(table_second)
    descendant_signature = lambda rows: [
        (row["pid"], row["start_ticks"], row["ppid"], row["pgrp"])
        for row in rows
    ]
    if descendant_signature(descendants_first) != descendant_signature(descendants):
        fail("MODEL_DESCENDANT_CENSUS_UNSTABLE")
    descendant_ids = {row["pid"] for row in descendants}
    if any(row["pid"] not in cgroup_before for row in descendants):
        fail("MODEL_DESCENDANT_OUTSIDE_CGROUP")
    cgroup_identities = []
    for pid in cgroup_before:
        row = table_second.get(pid)
        if row is None:
            fail("CGROUP_PID_IDENTITY_UNAVAILABLE")
        cgroup_identities.append({"pid": pid, "start_ticks": row["start_ticks"]})
    cgroup_identities.sort(key=lambda row: row["pid"])
    if {row["pid"]: row["start_ticks"] for row in cgroup_identities}.get(MODEL_PID) != MODEL_START_TICKS:
        fail("MODEL_MISSING_FROM_CGROUP_PROCS")

    def census():
        members = []
        scanned = 0
        try:
            with os.scandir("/proc") as entries:
                for entry in entries:
                    if not entry.name.isdecimal():
                        continue
                    scanned += 1
                    if scanned > MAX_PROCESS_TABLE_ENTRIES:
                        fail("PROCESS_GROUP_CENSUS_LIMIT")
                    pid = int(entry.name)
                    before = process_table_row(pid, missing_ok=True)
                    if before is None or before["pgrp"] != group:
                        continue
                    proc = Path("/proc") / str(pid)
                    try:
                        exe = os.readlink(proc / "exe")
                        with (proc / "cmdline").open("rb") as stream:
                            raw_cmdline = stream.read(MAX_CMDLINE_BYTES + 1)
                        exe_after = os.readlink(proc / "exe")
                        with (proc / "cmdline").open("rb") as stream:
                            raw_cmdline_after = stream.read(MAX_CMDLINE_BYTES + 1)
                        after = process_table_row(pid, missing_ok=True)
                    except FileNotFoundError:
                        continue
                    except OSError:
                        fail("PROCESS_GROUP_MEMBER_IDENTITY_UNAVAILABLE")
                    if (after is None or
                            any(before[key] != after[key] for key in
                                ("pid", "ppid", "pgrp", "start_ticks")) or
                            exe_after != exe or
                            raw_cmdline_after != raw_cmdline or
                            len(os.fsencode(exe)) > MAX_PROC_PATH_BYTES or
                            len(raw_cmdline) > MAX_CMDLINE_BYTES or
                            not raw_cmdline.endswith(bytes((0,)))):
                        fail("PROCESS_GROUP_MEMBER_IDENTITY_CHANGED")
                    members.append({
                        "pid": pid, "start_ticks": before["start_ticks"],
                        "ppid": before["ppid"], "state": before["state"],
                        "is_zombie": before["state"] == "Z",
                        "pgrp": before["pgrp"],
                        "same_model_cgroup": pid in cgroup_before,
                        "is_target_descendant": pid in descendant_ids,
                        "exe_basename": Path(exe.removesuffix(" (deleted)")).name,
                        "exe_path_sha256": hashlib.sha256(os.fsencode(exe)).hexdigest(),
                        "cmdline_sha256": hashlib.sha256(raw_cmdline).hexdigest(),
                    })
        except OSError:
            fail("PROCESS_GROUP_CENSUS_UNAVAILABLE")
        return sorted(members, key=lambda row: row["pid"])

    DIAGNOSTICS["model_pgrp_census"] = {"pgrp": group, "state": "CENSUS_STARTED"}
    first = census()
    DIAGNOSTICS["model_pgrp_census"]["members_first"] = first
    second = census()
    signature = lambda rows: [{key: row[key] for key in (
        "pid", "start_ticks", "ppid", "is_zombie", "pgrp", "same_model_cgroup",
        "is_target_descendant", "exe_basename", "exe_path_sha256", "cmdline_sha256")}
        for row in rows]
    DIAGNOSTICS["model_pgrp_census"] = {
        "pgrp": group, "stable_two_passes": signature(first) == signature(second),
        "members_first": first, "members_second": second,
        "cgroup_procs_before": cgroup_before,
        "cgroup_identities_before": cgroup_identities,
        "target_descendants_before": descendants,
        "scope": "READ_ONLY_HASHED_CMDLINE_AND_EXE_PATH_NO_RAW_ARGV",
    }
    if settings_error is not None:
        raise RuntimeError(settings_error)
    if signature(first) != signature(second):
        fail("MODEL_PROCESS_GROUP_CENSUS_UNSTABLE")
    model_rows = [row for row in second if row["pid"] == MODEL_PID]
    if (len(model_rows) != 1 or model_rows[0]["start_ticks"] != MODEL_START_TICKS or
            model_rows[0]["same_model_cgroup"] is not True):
        fail("MODEL_PROCESS_GROUP_IDENTITY_MISMATCH")

    live_descendants = [row for row in descendants if row["state"] != "Z"]
    if settings["stopasgroup"] != "false" or settings["killasgroup"] != "false":
        fail("SUPERVISOR_STOP_NOT_DIRECT_PID_ONLY")
    if live_descendants:
        fail("DIRECT_PID_STOP_HAS_LIVE_TARGET_DESCENDANTS")
    live_group_members = [row for row in second if row["state"] != "Z"]
    zombie_group_members = [row for row in second if row["state"] == "Z"]
    if ([row["pid"] for row in live_group_members] != [MODEL_PID] or
            live_group_members[0]["start_ticks"] != MODEL_START_TICKS):
        fail("DIRECT_PID_STOP_HAS_OTHER_LIVE_PGRP_MEMBER")
    stop_scope = "PINNED_SUPERVISOR_PROGRAM_PID_ONLY_EXCLUSIVE_LIVE_PGRP"
    model_runtime_members = cgroup_model_runtime_census(cgroup, model)
    runtime_identities = {row["pid"]: row["start_ticks"]
                          for row in model_runtime_members}
    if runtime_identities != {row["pid"]: row["start_ticks"]
                              for row in cgroup_identities}:
        fail("CGROUP_RUNTIME_MEMBERSHIP_CHANGED_DURING_CENSUS")
    return {"settings": settings, "members": second,
            "cgroup_procs": cgroup_before,
            "cgroup_identities": cgroup_identities,
            "descendants": descendants,
            "model_runtime_members": model_runtime_members,
            "live_pgrp_member_pids": [row["pid"] for row in live_group_members],
            "zombie_pgrp_member_pids": [row["pid"] for row in zombie_group_members],
            "live_pgrp_member_count": len(live_group_members),
            "zombie_pgrp_member_count": len(zombie_group_members),
            "stop_scope": stop_scope}

def require_same_stop_preflight(before: dict, after: dict, label: str) -> None:
    if (before["settings"]["effective_config_sha256"] !=
            after["settings"]["effective_config_sha256"] or
            before["settings"].get("daemon_identity") !=
            after["settings"].get("daemon_identity") or
            before["settings"].get("supervisorctl_client") !=
            after["settings"].get("supervisorctl_client") or
            before.get("model_runtime_members") !=
            after.get("model_runtime_members") or
            before["settings"]["path"] != after["settings"]["path"] or
            before["stop_scope"] != after["stop_scope"]):
        fail(label + "_SUPERVISOR_CONFIG_CHANGED")
    before_members = {row["pid"]: row for row in before["members"]}
    for row in after["members"]:
        prior = before_members.get(row["pid"])
        if (prior is None or prior["start_ticks"] != row["start_ticks"] or
                any(prior[key] != row[key] for key in (
                    "ppid", "is_zombie", "pgrp", "same_model_cgroup", "is_target_descendant",
                    "exe_basename", "exe_path_sha256", "cmdline_sha256"))):
            fail(label + "_NEW_OR_REUSED_PGRP_PID")
    if set(after["cgroup_procs"]) - set(before["cgroup_procs"]):
        fail(label + "_NEW_CGROUP_PID")
    before_cgroup = {row["pid"]: row["start_ticks"]
                     for row in before["cgroup_identities"]}
    after_cgroup = {row["pid"]: row["start_ticks"]
                    for row in after["cgroup_identities"]}
    if any(pid not in before_cgroup or before_cgroup[pid] != ticks
           for pid, ticks in after_cgroup.items()):
        fail(label + "_NEW_OR_REUSED_CGROUP_PID")
    before_descendants = {row["pid"]: row for row in before["descendants"]}
    for row in after["descendants"]:
        prior = before_descendants.get(row["pid"])
        if prior is None or prior["start_ticks"] != row["start_ticks"]:
            fail(label + "_NEW_TARGET_DESCENDANT")


def process_group_after_stop(group: int, cgroup: Path, before: dict) -> dict:
    table_first = process_table_snapshot()
    cgroup_first = cgroup_processes(cgroup)
    table = process_table_snapshot()
    cgroup_after = cgroup_processes(cgroup)
    if cgroup_first != cgroup_after:
        fail("POST_STOP_CGROUP_PROCS_UNSTABLE")
    group_first = sorted((row for row in table_first.values()
                          if row["pgrp"] == group), key=lambda row: row["pid"])
    group_after = sorted((row for row in table.values() if row["pgrp"] == group),
                         key=lambda row: row["pid"])
    group_signature = lambda rows: [(row["pid"], row["start_ticks"], row["ppid"],
                                     row["pgrp"], row["state"] == "Z")
                                    for row in rows]
    if group_signature(group_first) != group_signature(group_after):
        fail("POST_STOP_PGRP_CENSUS_UNSTABLE")
    live_members_after = [row for row in group_after if row["state"] != "Z"]
    zombie_members_after = [row for row in group_after if row["state"] == "Z"]
    prior_group = {row["pid"]: row for row in before["members"]}
    unclassified = [row for row in group_after
                    if row["pid"] not in prior_group or
                    prior_group[row["pid"]]["start_ticks"] != row["start_ticks"]]
    prior_descendants = {row["pid"]: row for row in before["descendants"]}
    remaining_descendants = []
    for pid, prior in prior_descendants.items():
        current = table.get(pid)
        if (current is not None and current["start_ticks"] == prior["start_ticks"] and
                current["state"] != "Z"):
            remaining_descendants.append(current)
    new_cgroup_pids = sorted(set(cgroup_after) - set(before["cgroup_procs"]))
    before_cgroup = {row["pid"]: row["start_ticks"]
                     for row in before["cgroup_identities"]}
    after_cgroup = {pid: table[pid]["start_ticks"] for pid in cgroup_after
                    if pid in table}
    reused_cgroup_pids = sorted(pid for pid, ticks in after_cgroup.items()
                                if pid in before_cgroup and before_cgroup[pid] != ticks)
    missing_cgroup_identities = sorted(set(cgroup_after) - set(after_cgroup))
    pinned_runtime = next((row for row in before["model_runtime_members"]
                           if row["pid"] == MODEL_PID and
                           row["start_ticks"] == MODEL_START_TICKS), None)
    if pinned_runtime is None:
        fail("POST_STOP_PINNED_MODEL_RUNTIME_EVIDENCE_MISSING")
    model_runtime_members_after = cgroup_model_runtime_census(cgroup, {
        "exe_path_sha256": pinned_runtime["exe_path_sha256"],
        "argv_sha256": pinned_runtime["argv_sha256"],
    })
    runtime_after_ids = {row["pid"]: row["start_ticks"]
                         for row in model_runtime_members_after}
    if runtime_after_ids != after_cgroup:
        fail("POST_STOP_CGROUP_RUNTIME_CENSUS_MISMATCH")
    result = {
        "pgrp": group, "members_after": group_after,
        "stable_two_passes": True,
        "live_pgrp_member_pids_after": [row["pid"] for row in live_members_after],
        "zombie_pgrp_member_pids_after": [row["pid"] for row in zombie_members_after],
        "live_pgrp_member_count_after": len(live_members_after),
        "zombie_pgrp_member_count_after": len(zombie_members_after),
        "cgroup_procs_after": cgroup_after,
        "new_cgroup_pids": new_cgroup_pids,
        "reused_cgroup_pids": reused_cgroup_pids,
        "missing_cgroup_identities": missing_cgroup_identities,
        "unclassified_pgrp_members": unclassified,
        "remaining_target_descendants": remaining_descendants,
        "model_runtime_members_after": model_runtime_members_after,
    }
    DIAGNOSTICS["model_process_group_after_stop"] = result
    if (new_cgroup_pids or reused_cgroup_pids or missing_cgroup_identities or
            unclassified or remaining_descendants or live_members_after):
        fail("POST_STOP_PROCESS_SCOPE_NOT_CLOSED")
    return result


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
    require_holder_outside_model_group(model, holder)
    stop_safety_before = require_exclusive_model_process_group(model)
    if model["cgroup"] != holder["cgroup"]:
        fail("TARGETS_NOT_IN_SAME_CGROUP")
    memfd = fd_memfd_identity(HOLDER_PID)
    model_maps_memfd(MODEL_PID, memfd["device"])
    model_after_maps = process_identity(MODEL_PID, MODEL_START_TICKS, "MODEL")
    holder_after_maps = process_identity(HOLDER_PID, HOLDER_START_TICKS, "HOLDER")
    require_same_process_identity(model, model_after_maps, "MODEL_AFTER_MAPS")
    require_same_process_identity(holder, holder_after_maps, "HOLDER_AFTER_MAPS")
    require_holder_outside_model_group(model_after_maps, holder_after_maps)
    stop_safety_after_maps = require_exclusive_model_process_group(model_after_maps)
    require_same_stop_preflight(stop_safety_before, stop_safety_after_maps,
                                "MODEL_AFTER_MAPS")
    before = memory_headroom(Path(model["cgroup"]))
    if before["headroom"] >= MIN_HEADROOM:
        fail("HEADROOM_ALREADY_SAFE")

    # Create the owner fence only after a fresh low-headroom preflight.
    fence = ensure_owner_fence(request_id, source_sha)

    # Revalidate exact identities and headroom immediately before stopping.
    status = require_model_running()
    latest_model = process_identity(MODEL_PID, MODEL_START_TICKS, "MODEL")
    if (latest_model["cgroup"] != model["cgroup"] or
            latest_model["environment_overrides"]["environment_map_sha256"] !=
            model["environment_overrides"]["environment_map_sha256"]):
        fail("MODEL_IDENTITY_OR_ENVIRONMENT_CHANGED_BEFORE_STOP")
    latest_holder = process_identity(HOLDER_PID, HOLDER_START_TICKS, "HOLDER")
    require_holder_outside_model_group(latest_model, latest_holder)
    if latest_holder["cgroup"] != holder["cgroup"]:
        fail("HOLDER_CGROUP_CHANGED_BEFORE_STOP")
    require_same_process_identity(model, latest_model, "MODEL_PRE_STOP")
    require_same_process_identity(holder, latest_holder, "HOLDER_PRE_STOP")
    latest_memfd = fd_memfd_identity(HOLDER_PID)
    if (latest_memfd["device"] != memfd["device"] or
            latest_memfd["inode"] != memfd["inode"] or
            latest_memfd["size"] != memfd["size"] or
            latest_memfd["label"] != MEMFD_LABEL):
        fail("HOLDER_MEMFD_CHANGED_BEFORE_STOP")
    pre_stop = memory_headroom(Path(model["cgroup"]))
    if pre_stop["headroom"] >= MIN_HEADROOM:
        fail("HEADROOM_RECOVERED_BEFORE_STOP")
    # Re-read relevant environment after the cgroup check; only a digest is retained.
    final_model = process_identity(MODEL_PID, MODEL_START_TICKS, "MODEL")
    final_holder = process_identity(HOLDER_PID, HOLDER_START_TICKS, "HOLDER")
    require_holder_outside_model_group(final_model, final_holder)
    if (final_model["cgroup"] != model["cgroup"] or
            final_model["environment_overrides"]["environment_map_sha256"] !=
            model["environment_overrides"]["environment_map_sha256"]):
        fail("MODEL_IDENTITY_OR_ENVIRONMENT_CHANGED_IMMEDIATELY_BEFORE_STOP")
    require_same_process_identity(model, final_model, "MODEL_IMMEDIATELY_BEFORE_STOP")
    require_same_process_identity(holder, final_holder, "HOLDER_IMMEDIATELY_BEFORE_STOP")
    # Recheck mapping, then reread both full identities at the final admission point.
    model_maps_memfd(MODEL_PID, memfd["device"], MODEL_START_TICKS)
    last_model = process_identity(MODEL_PID, MODEL_START_TICKS, "MODEL")
    last_holder = process_identity(HOLDER_PID, HOLDER_START_TICKS, "HOLDER")
    require_same_process_identity(model, last_model, "MODEL_AFTER_FINAL_MAPS")
    require_same_process_identity(holder, last_holder, "HOLDER_AFTER_FINAL_MAPS")
    require_holder_outside_model_group(last_model, last_holder)
    stop_settings_final = read_supervisor_stop_settings()
    if (stop_settings_final["effective_config_sha256"] !=
            stop_safety_before["settings"]["effective_config_sha256"]):
        fail("SUPERVISOR_CONFIG_CHANGED_LAST_PRE_STOP")
    # Close the config-read window with fresh service, process, holder and memory checks.
    final_status = require_model_running()
    final_model = process_identity(MODEL_PID, MODEL_START_TICKS, "MODEL")
    final_holder = process_identity(HOLDER_PID, HOLDER_START_TICKS, "HOLDER")
    require_same_process_identity(model, final_model, "MODEL_LAST_PRE_STOP")
    require_same_process_identity(holder, final_holder, "HOLDER_LAST_PRE_STOP")
    require_holder_outside_model_group(final_model, final_holder)
    final_memfd = fd_memfd_identity(HOLDER_PID)
    if (final_memfd["device"] != memfd["device"] or
            final_memfd["inode"] != memfd["inode"] or
            final_memfd["size"] != memfd["size"] or
            final_memfd["label"] != MEMFD_LABEL):
        fail("HOLDER_MEMFD_CHANGED_LAST_PRE_STOP")
    final_headroom = memory_headroom(Path(model["cgroup"]))
    if final_headroom["headroom"] >= MIN_HEADROOM:
        fail("HEADROOM_RECOVERED_LAST_PRE_STOP")

    # Verify the fixed client before the process census. Then make the stable
    # PGRP/cgroup closure scan the last proc/cgroup read before the stop RPC.
    stop_client_sha256 = verify_supervisorctl_executable()
    if DIAGNOSTICS.get("supervisorctl_client") != stop_settings_final.get(
            "supervisorctl_client"):
        fail("SUPERVISORCTL_CLIENT_CHANGED_LAST_PRE_STOP")
    stop_safety_immediate = require_exclusive_model_process_group(
        final_model, settings=stop_settings_final)
    require_same_stop_preflight(stop_safety_before, stop_safety_immediate,
                                "MODEL_IMMEDIATELY_BEFORE_STOP")

    PHASE["model_stop_requested"] = True
    stopped = command(["supervisorctl", "-c", str(SUPERVISOR_CLIENT_CONFIG),
                       "stop", SUPERVISOR_SERVICE], timeout=35,
                      verified_client_sha256=stop_client_sha256)
    if stopped.returncode != 0:
        fail("SUPERVISOR_STOP_COMMAND_FAILED")
    after_status = wait_model_stopped()
    model_pid_state = require_model_identity_gone()

    # This version always preserves the memfd holder. A later owner action
    # must gather fresh evidence before considering any holder signal.
    latest_holder = process_identity(HOLDER_PID, HOLDER_START_TICKS, "HOLDER")
    latest_memfd = fd_memfd_identity(HOLDER_PID)
    require_same_process_identity(holder, latest_holder, "HOLDER_AFTER_MODEL_STOP")
    require_holder_outside_model_group(model, latest_holder)
    if (latest_holder["cgroup"] != holder["cgroup"] or
            latest_memfd["device"] != memfd["device"] or
            latest_memfd["inode"] != memfd["inode"] or
            latest_memfd["size"] != memfd["size"] or
            latest_memfd["label"] != MEMFD_LABEL):
        fail("HOLDER_IDENTITY_CHANGED_AFTER_MODEL_STOP")
    DIAGNOSTICS["holder_after"] = latest_holder
    DIAGNOSTICS["memfd_after"] = latest_memfd
    DIAGNOSTICS["holder_signal"] = "NONE"
    process_scope_after = process_group_after_stop(
        model["pgrp"], Path(model["cgroup"]), stop_safety_immediate)
    after_model = memory_headroom(Path(holder["cgroup"]))
    DIAGNOSTICS["model_after"] = {"supervisor": after_status,
                                  "pinned_pid_state": model_pid_state,
                                  "headroom": after_model}
    if after_model["headroom"] < MIN_HEADROOM:
        fail("MODEL_STOPPED_HEADROOM_FLOOR_NOT_MET")
    unattributed_before = [row for row in
                           stop_safety_immediate["model_runtime_members"]
                           if row["classification"] == "OTHER_EXECUTABLE"]
    unattributed_after = [row for row in
                          process_scope_after["model_runtime_members_after"]
                          if row["classification"] == "OTHER_EXECUTABLE"]
    return {"state": "PINNED_MODEL_SERVICE_STOPPED_HOLDER_PRESERVED_HEADROOM_MET",
            "complete": True,
            "completion_scope":
                "PINNED_SUPERVISOR_SERVICE_PID_STOPPED_HEADROOM_MET_STABLE_POST_CENSUS",
            "model": model, "holder": holder, "memfd": memfd,
            "process_groups": {"model": model["pgrp"], "holder": holder["pgrp"],
                               "holder_separate_from_model": True,
                               "model_stop_scope": stop_safety_immediate["stop_scope"],
                               "model_pgrp_live_member_pids_before":
                                   stop_safety_immediate["live_pgrp_member_pids"],
                               "model_pgrp_live_member_count_before":
                                   stop_safety_immediate["live_pgrp_member_count"],
                               "model_pgrp_zombie_member_pids_before":
                                   stop_safety_immediate["zombie_pgrp_member_pids"],
                               "model_pgrp_zombie_member_count_before":
                                   stop_safety_immediate["zombie_pgrp_member_count"],
                               "model_pgrp_live_member_pids_after":
                                   process_scope_after["live_pgrp_member_pids_after"],
                               "model_pgrp_live_member_count_after":
                                   process_scope_after["live_pgrp_member_count_after"],
                               "model_pgrp_zombie_member_pids_after":
                                   process_scope_after["zombie_pgrp_member_pids_after"],
                               "model_pgrp_zombie_member_count_after":
                                   process_scope_after["zombie_pgrp_member_count_after"],
                               "stop_target_pid": MODEL_PID,
                               "stop_target_start_ticks": MODEL_START_TICKS,
                               "supervisor_group_flags": {
                                   "stopasgroup": "false", "killasgroup": "false"}},
            "process_scope_before": stop_safety_immediate,
            "process_scope_after": process_scope_after,
            "before": before, "pre_stop": pre_stop, "final_headroom": final_headroom,
            "after_model": after_model,
            "pinned_service_pid_gone": True,
            "pinned_target_model_signature_gone": True,
            "model_runtime_members_before":
                stop_safety_immediate["model_runtime_members"],
            "model_runtime_members_after":
                process_scope_after["model_runtime_members_after"],
            "unattributed_other_executable_pids_before": unattributed_before,
            "unattributed_other_executable_pids_after": unattributed_after,
            "unattributed_other_executable_pids": unattributed_after,
            "model_cgroup_runtime_attribution_complete":
                not bool(unattributed_before or unattributed_after),
            "model_runtime_attribution_scope":
                "TARGET_CGROUP_ANCESTRY_AND_PGRP_ONLY_NOT_GLOBAL",
            "model_after": {"supervisor": after_status,
                            "pinned_pid_state": model_pid_state,
                            "headroom": after_model},
            "holder_after": latest_holder, "memfd_after": latest_memfd,
            "holder_identity_basis": [
                "pinned_pid_and_start_ticks", "stable_pgrp_and_cgroup",
                "expected_holder_script_path_sha256",
                "expected_holder_cmdline_sha256", "expected_holder_cwd_sha256",
                "stable_executable_path_sha256", "stable_full_argv_sha256",
                "stable_cwd_sha256", "exact_memfd_device_inode_size_label",
            ],
            "minimum_headroom": MIN_HEADROOM,
            "model_pid_state": model_pid_state,
            "supervisor_immediately_before_stop": final_status,
            "markers": fence,
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
              "owner_fence_retained": True,
              "diagnostics": DIAGNOSTICS, **receipt})
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
              "diagnostics": DIAGNOSTICS,
              "complete": False, "holder_signal": "NONE",
              "owner_fence_retained": bool(PHASE["stop_marker"] or PHASE["maintenance_marker"]),
              "no_rollback_or_restart": True})
        print("NOX_MAINT_EMERGENCY_STOP_RESULT=" + label, flush=True)
        raise SystemExit(2)
