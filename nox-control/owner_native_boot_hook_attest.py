#!/usr/bin/env python3
"""Read bounded metadata for the exact NOX startup and Supervisor files.

This owner action reads only STARTUP_FILES. It emits hashes and stat metadata,
never file contents, config values, or environment values. Missing, unsafe,
changed, or unpinned files produce HOLD.
"""
from __future__ import annotations

import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

ROOT_UID = 0
STARTUP_FILES = (
    ("instance_start_hook", "/root/onstart.sh", 65_536),
    ("supervisor_main_config", "/etc/supervisor/supervisord.conf", 262_144),
    ("observer_program_config",
     "/etc/supervisor/conf.d/nox-lifeline-observer.conf", 8_192),
)
OBSERVER_PROGRAM_CONFIG_SHA256 = (
    "00f58d8a96fb9277f7e5e0f65acc4719b231608fe43e633011cc524ac04f66f4"
)
SUPERVISOR_INCLUDE_GLOB = "/etc/supervisor/conf.d/*.conf"
SHA = re.compile(r"^[0-9a-f]{40}$")


def _trusted_directory(info: os.stat_result) -> bool:
    return (stat.S_ISDIR(info.st_mode) and info.st_uid == ROOT_UID and
            not (info.st_mode & 0o022))


def safe_read(path_text: str, limit: int) -> tuple[bytes, os.stat_result]:
    """Open one exact absolute path without links; reject unsafe files/races."""
    if (not isinstance(path_text, str) or not path_text.startswith("/") or
            "\x00" in path_text):
        raise ValueError("HOLD_STARTUP_PATH_SHAPE")
    path = Path(path_text)
    if path.as_posix() != path_text or path.name in ("", ".", ".."):
        raise ValueError("HOLD_STARTUP_PATH_SHAPE")
    if type(limit) is not int or not 1 <= limit <= 262_144:
        raise ValueError("HOLD_STARTUP_SIZE_LIMIT")

    parent_fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if not _trusted_directory(os.fstat(parent_fd)):
            raise ValueError("HOLD_STARTUP_PARENT_SHAPE")
        for part in path.parts[1:-1]:
            if part in ("", ".", ".."):
                raise ValueError("HOLD_STARTUP_PATH_SHAPE")
            child_fd = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child_fd
            if not _trusted_directory(os.fstat(parent_fd)):
                raise ValueError("HOLD_STARTUP_PARENT_SHAPE")

        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=parent_fd)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != ROOT_UID or
                    before.st_nlink != 1 or before.st_mode & 0o022 or
                    before.st_size < 0 or before.st_size > limit):
                raise ValueError("HOLD_STARTUP_FILE_SHAPE")
            chunks = []
            total = 0
            while total <= limit:
                chunk = os.read(fd, min(65_536, limit + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            after = os.fstat(fd)
            named_after = os.stat(path.name, dir_fd=parent_fd,
                                  follow_symlinks=False)
            fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid",
                      "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
            raw = b"".join(chunks)
            if (total > limit or total != before.st_size or
                    any(getattr(before, key) != getattr(after, key) or
                        getattr(after, key) != getattr(named_after, key)
                        for key in fields)):
                raise ValueError("HOLD_STARTUP_FILE_CHANGED")
            return raw, after
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _stat_fields(info: os.stat_result) -> dict:
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "mode": stat.S_IMODE(info.st_mode),
        "uid": info.st_uid,
        "gid": info.st_gid,
        "nlink": info.st_nlink,
        "size_bytes": info.st_size,
        "mtime_ns": info.st_mtime_ns,
        "ctime_ns": info.st_ctime_ns,
    }


def _include_loads_observer(raw: bytes) -> bool:
    """Return only a boolean for the one allowed Supervisor include pattern."""
    try:
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.read_string(raw.decode("utf-8", "strict"))
        files = parser.get("include", "files", fallback="")
    except (UnicodeError, configparser.Error, ValueError):
        return False
    entries = [entry for entry in re.split(r"[\s,]+", files.strip()) if entry]
    return entries == [SUPERVISOR_INCLUDE_GLOB]


def attest_boot_hook() -> dict:
    """Return metadata only; any missing or unsafe required path makes HOLD."""
    rows = []
    raw_by_name = {}
    hold_reasons = []
    for name, path_text, limit in STARTUP_FILES:
        try:
            raw, info = safe_read(path_text, limit)
        except FileNotFoundError:
            rows.append({"name": name, "path": path_text, "state": "MISSING"})
            hold_reasons.append("REQUIRED_FILE_MISSING")
            continue
        except (OSError, ValueError):
            rows.append({"name": name, "path": path_text,
                         "state": "HOLD_UNSAFE_OR_CHANGED"})
            hold_reasons.append("UNSAFE_OR_CHANGED_FILE")
            continue
        digest = hashlib.sha256(raw).hexdigest()
        raw_by_name[name] = raw
        rows.append({"name": name, "path": path_text, "state": "READ_OK",
                     "sha256": digest, **_stat_fields(info)})

    include_ok = False
    if "supervisor_main_config" in raw_by_name:
        include_ok = _include_loads_observer(
            raw_by_name["supervisor_main_config"])
        if not include_ok:
            hold_reasons.append("OBSERVER_CONFIG_NOT_INCLUDED")
    else:
        hold_reasons.append("SUPERVISOR_MAIN_CONFIG_UNAVAILABLE")

    observer_config = next((row for row in rows
                            if row["name"] == "observer_program_config"), None)
    observer_pin_ok = bool(
        observer_config and observer_config.get("sha256") ==
        OBSERVER_PROGRAM_CONFIG_SHA256)
    if observer_config and observer_config.get("state") == "READ_OK" and not observer_pin_ok:
        hold_reasons.append("OBSERVER_CONFIG_PIN_MISMATCH")
    elif observer_config is None or observer_config.get("state") != "READ_OK":
        hold_reasons.append("OBSERVER_CONFIG_UNAVAILABLE")

    complete = (not hold_reasons and len(rows) == len(STARTUP_FILES) and
                all(row["state"] == "READ_OK" for row in rows) and
                include_ok and observer_pin_ok)
    return {
        "schema": "NOX_BOOT_HOOK_ATTEST_V1",
        "state": "READ_OK" if complete else "HOLD",
        "observed_at_unix": time.time(),
        "files": rows,
        "supervisor_include_loads_observer_config": include_ok,
        "observer_program_config_matches_installer_pin": observer_pin_ok,
        "hold_reasons": sorted(set(hold_reasons)),
        "file_contents_emitted": False,
        "secret_values_emitted": False,
    }


def main() -> int:
    source_sha = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    request_id = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    if (os.geteuid() != ROOT_UID or not SHA.fullmatch(source_sha) or
            not request_id.isdigit()):
        print("NOX_MAINT_BOOT_HOOK_ATTEST=" + json.dumps({
            "schema": "NOX_BOOT_HOOK_ATTEST_V1", "state": "HOLD",
            "reason": "HOLD_OWNER_CONTEXT", "file_contents_emitted": False,
            "secret_values_emitted": False,
        }, separators=(",", ":")), flush=True)
        return 2
    result = attest_boot_hook()
    result.update({"source_sha": source_sha, "request_id": request_id})
    print("NOX_MAINT_BOOT_HOOK_ATTEST=" + json.dumps(
        result, sort_keys=True, separators=(",", ":"), allow_nan=False), flush=True)
    if result["state"] != "READ_OK":
        return 2
    print("NOX_MAINT_BOOT_HOOK_ATTEST_COMPLETE=true", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
