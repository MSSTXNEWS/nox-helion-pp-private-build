#!/usr/bin/env python3
"""NOX owner-scoped read-only Google Drive authentication probe on Vast.ai.

Does not print remotes, Drive filenames, configuration content, passwords,
OAuth tokens or service-account secrets. Does not transfer or delete data.
Only verifies that the configured remote is rooted at the approved NOX folder.
"""
from __future__ import annotations

import configparser
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

EXPECTED_ROOT = "1ewQ-R7z33fN0fKoMNNuFzv1_3rCEP96v"
REMOTE = "noxdrive"
MAX_CONFIG_BYTES = 128 * 1024
TIMEOUT = 25



# One bounded, read-only inventory of the actual installed dispatcher surface.
# No runtime imports, arbitrary source execution, private source text or secrets.
DISPATCHER = Path("/root/nox/scripts/nox_dispatcher_t855u.py")
BRIDGE = Path("/root/nox/ops/drive-auth/nox_drive_native_binding.py")
SERVICE = "nox-dispatcher-t855u"
HOST_STOP_FLAGS = (
    "/root/nox/STOP", "/root/nox/STOP.flag", "/root/nox/state/STOP",
    "/root/nox/state/OWNER_MAINTENANCE.flag", "/workspace/NOX_STOP",
)


def dispatcher_surface(source=DISPATCHER, runner=subprocess.run):
    import ast
    import hashlib
    import re

    result = {
        "schema": "NOX_DRIVE_DISPATCHER_SURFACE_V1",
        "read_only": True, "live_process_verified": False,
        "source_pinned": False, "source_sha256": None,
        "bridge_installed": False, "bridge_sha256": None,
        "native_handler_registered": "UNVERIFIED",
        "registration_interface": "UNVERIFIED",
        "candidate_functions": [], "candidate_registries": [],
        "stop_present": any(os.path.lexists(name) for name in HOST_STOP_FLAGS),
        "cgroup_raw_free_bytes": None, "cgroup_inactive_file_bytes": None,
        "transport_384m_raw_gate": False, "state": "HOLD_DISPATCHER_SOURCE",
    }
    try:
        stat_source = source.lstat()
        if not stat.S_ISREG(stat_source.st_mode) or stat_source.st_uid != os.geteuid() or (
            stat_source.st_mode & 0o022
        ) or not (0 < stat_source.st_size <= 180000) or any(
            ancestor.is_symlink() for ancestor in source.parents
        ):
            return result
        raw = source.read_bytes()
        if len(raw) != stat_source.st_size:
            return result
        tree = ast.parse(raw.decode("utf-8"), filename=source.name)
        result["source_sha256"] = hashlib.sha256(raw).hexdigest()
        result["source_pinned"] = True
        # Report names and argument labels only. Never publish AST literals,
        # code snippets, file paths, process argv or arbitrary object repr.
        prefixes = ("handler", "register", "dispatch", "queue", "claim",
                    "enqueue", "lease", "resource", "execute", "worker",
                    "stop", "foreground", "admit", "owner")
        found = set()
        registries = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name.lower()
                if any(token in name for token in prefixes):
                    args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                    safe_name = re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", node.name)
                    safe_args = [
                        arg.arg for arg in args[:9]
                        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", arg.arg)
                    ]
                    if safe_name:
                        found.add(node.name + "(" + ",".join(safe_args) + ")")
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name) and any(
                        token in target.id.lower() for token in ("handler", "registry", "dispatch")
                    ) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", target.id):
                        registries.add(target.id)
        result["candidate_functions"] = sorted(found)[:36]
        result["candidate_registries"] = sorted(registries)[:24]
        result["registration_interface"] = (
            "DECLARED_FUNCTION" if any(item.startswith("register_handler(") for item in found)
            else "NO_EXACT_REGISTER_HANDLER_FOUND"
        )
        result["state"] = "SOURCE_AST_READ"
    except (OSError, UnicodeError, SyntaxError, ValueError, TypeError):
        return result
    # Live process identity verification is separate from source AST inventory.
    try:
        observed = runner(
            ["supervisorctl", "status", SERVICE], capture_output=True,
            text=True, timeout=7, check=False
        )
        match = re.search(
            r"^nox-dispatcher-t855u\s+RUNNING\s+pid\s+(\d+),",
            observed.stdout[:512] if isinstance(observed.stdout, str) else "",
        )
        if observed.returncode == 0 and match:
            pid = int(match.group(1))
            argv = Path("/proc") / str(pid) / "cmdline"
            cmd = argv.read_bytes()[:2048].split(b"\x00")
            result["live_process_verified"] = (
                any(arg == str(source).encode() or arg.endswith(
                    b"/" + source.name.encode()
                ) for arg in cmd)
            )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    try:
        st = BRIDGE.lstat()
        if stat.S_ISREG(st.st_mode) and st.st_uid == os.geteuid() and not st.st_mode & 0o022:
            raw = BRIDGE.read_bytes()
            if 0 < len(raw) <= 65536:
                result["bridge_installed"] = True
                result["bridge_sha256"] = hashlib.sha256(raw).hexdigest()
    except OSError:
        pass
    try:
        root = Path("/sys/fs/cgroup")
        maximum = (root / "memory.max").read_text().strip()
        current = int((root / "memory.current").read_text().strip())
        if maximum.isdecimal() and int(maximum) >= current >= 0:
            raw_free = int(maximum) - current
            result["cgroup_raw_free_bytes"] = raw_free
            result["transport_384m_raw_gate"] = raw_free >= 384 * 1024**2
        for line in (root / "memory.stat").read_text().splitlines():
            if line.startswith("inactive_file "):
                n = int(line.split()[1])
                if n >= 0:
                    result["cgroup_inactive_file_bytes"] = n
                break
    except (OSError, ValueError, IndexError):
        pass
    return result


def config_candidates():
    specified = os.environ.get("RCLONE_CONFIG", "")
    if specified:
        return [Path(specified)]
    return [Path("/root/.config/rclone/rclone.conf"), Path("/root/nox/rclone.conf")]


def safe_config():
    for path in config_candidates():
        if not path.is_absolute() or path.is_symlink() or any(p.is_symlink() for p in path.parents):
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
            return None, None, "CONFIG_PERMISSIONS"
        if not 0 < st.st_size < MAX_CONFIG_BYTES:
            return None, None, "CONFIG_SIZE"
        cfg = configparser.RawConfigParser(interpolation=None)
        try:
            cfg.read_string(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, configparser.Error):
            return None, None, "CONFIG_UNREADABLE"
        if not cfg.has_section(REMOTE):
            return None, None, "REMOTE_MISSING"
        return path, cfg, "CONFIG_OK"
    return None, None, "CONFIG_MISSING"


def inspect_config(cfg):
    get = lambda k: cfg.get(REMOTE, k, fallback="").strip()
    if get("type") != "drive":
        return "BACKEND_NOT_DRIVE"
    if get("root_folder_id") != EXPECTED_ROOT:
        return "ROOT_NOT_PINNED"
    if not (get("token") or get("service_account_file") or get("service_account_credentials")):
        return "CREDENTIALS_NOT_CONFIGURED"
    return "CONFIG_READY"


def check_access(config_path, runner=subprocess.run, which=shutil.which):
    if not which("rclone"):
        return "RCLONE_MISSING"
    # Use only the pinned root and a known absolute private config path.
    cmd = ["rclone", "--config", str(config_path), "lsf", REMOTE + ":",
           "--max-depth", "1", "--retries", "1", "--low-level-retries", "1",
           "--contimeout", "5s", "--timeout", "10s", "--log-level", "ERROR"]
    try:
        proc = runner(cmd, stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL, timeout=TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        return "LIST_TIMEOUT"
    except (OSError, subprocess.SubprocessError):
        return "LIST_ERROR"
    return "READ_CONNECTED" if proc.returncode == 0 else "READ_UNAVAILABLE"


def probe():
    path, cfg, config_state = safe_config()
    result = {"schema": "NOX_DRIVE_AUTH_OWNER_PROBE_V1", "instance_id": 60509551,
              "approved_root_id": EXPECTED_ROOT, "config_state": config_state,
              "root_pinned": False, "read_access": False, "write_access": "NOT_TESTED"}
    result["dispatcher_surface"] = dispatcher_surface()
    if cfg is None:
        result["state"] = "NOT_CONNECTED"
        return result
    state = inspect_config(cfg)
    result["root_pinned"] = cfg.get(REMOTE, "root_folder_id", fallback="").strip() == EXPECTED_ROOT
    if state != "CONFIG_READY":
        result["state"] = state
        return result
    state = check_access(path)
    result["state"] = state
    result["read_access"] = state == "READ_CONNECTED"
    return result


def main():
    try:
        result = probe()
    except Exception as exc:
        result = {"schema": "NOX_DRIVE_AUTH_OWNER_PROBE_V1",
                  "instance_id": 60509551,
                  "state": "PROBE_ERROR_" + type(exc).__name__.upper(),
                  "read_access": False, "write_access": "NOT_TESTED"}
    print("NOX_MAINT_DRIVE_PROBE=" + json.dumps(result, ensure_ascii=True, sort_keys=True), flush=True)
    print("NOX_MAINT_DRIVE_PROBE_COMPLETE=true", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
