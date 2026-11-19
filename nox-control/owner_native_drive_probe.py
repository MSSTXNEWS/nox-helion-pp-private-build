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
