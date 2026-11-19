#!/usr/bin/env python3
"""Bounded, owner-routed, read-only Supervisor endpoint configuration preflight.

This route reports only normalized endpoint paths, fixed predicate results and
configuration hashes. It never contacts Supervisor, signals a process, acquires
locks, or writes to the host.
"""
from __future__ import annotations

import configparser
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from urllib.parse import urlsplit

SUPERVISOR_CLIENT_CONFIG = Path("/etc/supervisor/supervisord.conf")
SUPERVISOR_CONFIG_DIR = Path("/etc/supervisor/conf.d")
MAX_CONFIG_BYTES = 250_000
MAX_CONFIG_FILES = 128
MAX_TOTAL_CONFIG_BYTES = MAX_CONFIG_BYTES * (MAX_CONFIG_FILES + 1)
ROOT_UID = 0
EXPECTED_FACTORY = "supervisor.rpcinterface:make_main_rpcinterface"
SAFE_PATH = re.compile(r"/[A-Za-z0-9_./-]{0,4095}\Z")
MODE_TEXT = re.compile(r"0?[0-7]{3,4}\Z")
DIR_STABILITY_FIELDS = ("st_dev", "st_ino", "st_mtime_ns", "st_ctime_ns")
FILE_STABILITY_FIELDS = (
    "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns",
    "st_mode", "st_uid", "st_gid", "st_nlink",
)


def _hold(code: str) -> None:
    raise RuntimeError("HOLD_ENDPOINT_PREFLIGHT_" + code)


def _root_directory(path: Path):
    try:
        result = path.lstat()
    except OSError:
        _hold("DIRECTORY_UNAVAILABLE")
    if (not stat.S_ISDIR(result.st_mode) or result.st_uid != ROOT_UID or
            result.st_mode & 0o022):
        _hold("DIRECTORY_UNSAFE")
    return result


def _read_root_regular(path: Path, limit: int) -> tuple[bytes, int]:
    """Read one stable root-owned, non-writable regular file without following links."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                     getattr(os, "O_CLOEXEC", 0))
    except OSError:
        _hold("CONFIG_FILE_UNAVAILABLE")
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != ROOT_UID or
                before.st_nlink != 1 or before.st_mode & 0o022 or
                before.st_size > limit):
            _hold("CONFIG_FILE_UNSAFE")
        chunks: list[bytes] = []
        total = 0
        while total <= limit:
            chunk = os.read(fd, min(65_536, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        after = os.fstat(fd)
        try:
            current = path.lstat()
        except OSError:
            _hold("CONFIG_FILE_CHANGED")
        if (total > limit or
                any(getattr(before, key) != getattr(after, key)
                    for key in FILE_STABILITY_FIELDS) or
                any(getattr(before, key) != getattr(current, key)
                    for key in FILE_STABILITY_FIELDS)):
            _hold("CONFIG_FILE_CHANGED_OR_OVERSIZED")
        return b"".join(chunks), before.st_ctime_ns
    finally:
        os.close(fd)


def _safe_path(value: str, *, allow_here: bool = False) -> str | None:
    normalized = value
    if allow_here and normalized.startswith("%(here)s"):
        normalized = str(SUPERVISOR_CLIENT_CONFIG.parent) + normalized[len("%(here)s"):]
    if (not SAFE_PATH.fullmatch(normalized) or
            ".." in PurePosixPath(normalized).parts or
            not PurePosixPath(normalized).is_absolute()):
        return None
    return normalized


def inspect_configuration() -> dict:
    """Return fixed, sanitized facts from a stable bounded config snapshot."""
    supervisor_dir = _root_directory(SUPERVISOR_CLIENT_CONFIG.parent)
    include_dir = _root_directory(SUPERVISOR_CONFIG_DIR)
    main_bytes, _ = _read_root_regular(SUPERVISOR_CLIENT_CONFIG, MAX_CONFIG_BYTES)
    try:
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.read_string(main_bytes.decode("utf-8", "strict"))
        sections = set(parser.sections())
        allowed_sections = {
            "supervisord", "unix_http_server", "rpcinterface:supervisor",
            "supervisorctl", "include",
        }
        required_sections = {
            "unix_http_server", "rpcinterface:supervisor", "supervisorctl", "include",
        }
        shape_ok = (
            required_sections.issubset(sections) and sections.issubset(allowed_sections)
            and set(parser["unix_http_server"]) <= {"file", "chmod", "chown"}
            and set(parser["supervisorctl"]) == {"serverurl"}
            and set(parser["rpcinterface:supervisor"]) ==
            {"supervisor.rpcinterface_factory"}
            and set(parser["include"]) == {"files"}
        )
        if not shape_ok:
            _hold("CONFIG_SHAPE_UNSUPPORTED")
        socket_raw = parser.get("unix_http_server", "file")
        serverurl_raw = parser.get("supervisorctl", "serverurl")
        factory_raw = parser.get("rpcinterface:supervisor",
                                 "supervisor.rpcinterface_factory")
        mode_raw = parser.get("unix_http_server", "chmod", fallback="0700")
        owner_raw = parser.get("unix_http_server", "chown", fallback="root:root")
        include_raw = parser.get("include", "files")
    except (configparser.Error, UnicodeError, ValueError, KeyError):
        _hold("CONFIG_PARSE_FAILED")

    include_glob_ok = include_raw == str(SUPERVISOR_CONFIG_DIR / "*.conf")
    names: list[str] = []
    try:
        with os.scandir(SUPERVISOR_CONFIG_DIR) as entries:
            for entry in entries:
                if entry.name.endswith(".conf"):
                    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}\.conf", entry.name):
                        _hold("INCLUDE_NAME_UNSAFE")
                    names.append(entry.name)
                    if len(names) > MAX_CONFIG_FILES:
                        _hold("INCLUDE_FILE_LIMIT")
    except OSError:
        _hold("INCLUDE_DIRECTORY_UNAVAILABLE")

    include_rows = []
    total_bytes = len(main_bytes)
    for name in sorted(names):
        raw, ctime_ns = _read_root_regular(SUPERVISOR_CONFIG_DIR / name,
                                           MAX_CONFIG_BYTES)
        total_bytes += len(raw)
        if total_bytes > MAX_TOTAL_CONFIG_BYTES:
            _hold("TOTAL_CONFIG_LIMIT")
        include_rows.append({"name": name, "sha256": hashlib.sha256(raw).hexdigest(),
                             "ctime_ns": ctime_ns})

    supervisor_dir_after = _root_directory(SUPERVISOR_CLIENT_CONFIG.parent)
    include_dir_after = _root_directory(SUPERVISOR_CONFIG_DIR)
    dirs_stable = (
        all(getattr(supervisor_dir, key) == getattr(supervisor_dir_after, key)
            for key in DIR_STABILITY_FIELDS) and
        all(getattr(include_dir, key) == getattr(include_dir_after, key)
            for key in DIR_STABILITY_FIELDS)
    )
    if not dirs_stable:
        _hold("CONFIG_DIRECTORY_CHANGED")

    socket_path = _safe_path(socket_raw, allow_here=True)
    try:
        parsed_url = urlsplit(serverurl_raw)
        unix_scheme = parsed_url.scheme == "unix"
        no_authority_query_fragment = (
            not parsed_url.netloc and not parsed_url.query and not parsed_url.fragment
        )
        serverurl_path = (_safe_path(parsed_url.path)
                          if unix_scheme and no_authority_query_fragment else None)
    except ValueError:
        unix_scheme = False
        no_authority_query_fragment = False
        serverurl_path = None

    try:
        mode_int = int(mode_raw, 8) if MODE_TEXT.fullmatch(mode_raw) else None
    except ValueError:
        mode_int = None
    endpoint = {
        "normalized_socket_path": socket_path,
        "serverurl_path": serverurl_path,
        "socket_path_absolute_no_traversal": socket_path is not None,
        "serverurl_unix_scheme": unix_scheme,
        "serverurl_has_no_authority_query_fragment": no_authority_query_fragment,
        "socket_serverurl_paths_equal": bool(
            socket_path is not None and serverurl_path is not None and
            socket_path == serverurl_path),
        "rpc_factory_matches_fixed_allowlist": factory_raw == EXPECTED_FACTORY,
        "configured_owner_is_root_root": owner_raw == "root:root",
        "configured_mode_octal": mode_raw if mode_int is not None else None,
        "configured_mode_format_allowed": mode_int is not None,
        "configured_mode_private": bool(mode_int is not None and not mode_int & 0o022),
        "configured_mode_owner_write_set": bool(mode_int is not None and mode_int & 0o200),
        "endpoint_config_predicates_all_pass": bool(
            socket_path is not None and unix_scheme and no_authority_query_fragment and
            serverurl_path is not None and socket_path == serverurl_path and
            factory_raw == EXPECTED_FACTORY and owner_raw == "root:root" and
            mode_int is not None and not mode_int & 0o022 and mode_int & 0o200),
    }
    main_sha = hashlib.sha256(main_bytes).hexdigest()
    includes_sha = hashlib.sha256(json.dumps(
        [{"name": row["name"], "sha256": row["sha256"]} for row in include_rows],
        sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    effective_sha = hashlib.sha256(json.dumps(
        {"main_sha256": main_sha,
         "includes": [{"name": row["name"], "sha256": row["sha256"]}
                      for row in include_rows]},
        sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "state": "ENDPOINT_PREFLIGHT_READ_ONLY",
        "read_only": True,
        "config_snapshot_stable": True,
        "config_shape_supported": shape_ok,
        "include_glob_matches_fixed_scope": include_glob_ok,
        "endpoint": endpoint,
        "config": {
            "main_sha256": main_sha,
            "include_set_sha256": includes_sha,
            "effective_config_sha256": effective_sha,
            "include_file_count": len(include_rows),
            "total_config_bytes": total_bytes,
        },
        "raw_config_values_included": False,
        "credentials_included": False,
        "argv_included": False,
        "supervisor_rpc_calls": 0,
        "process_signals": 0,
        "host_writes": 0,
    }


def main() -> int:
    source_sha = os.environ.get("NOX_OWNER_SOURCE_SHA", "")
    request_id = os.environ.get("NOX_OWNER_REQUEST_ID", "")
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha) or not request_id.isdecimal():
        _hold("OWNER_CONTEXT")
    if os.geteuid() != 0:
        _hold("ROOT_REQUIRED")
    try:
        receipt = inspect_configuration()
        receipt.update({"source_sha": source_sha, "request_id": int(request_id)})
        print("NOX_MAINT_ENDPOINT_PREFLIGHT=" + json.dumps(
            receipt, sort_keys=True, separators=(",", ":"), allow_nan=False), flush=True)
        print("NOX_MAINT_EMERGENCY_STOP_PREFLIGHT_COMPLETE=true", flush=True)
        return 0
    except Exception as exc:
        label = str(exc)
        if not re.fullmatch(r"HOLD_ENDPOINT_PREFLIGHT_[A-Z0-9_]+", label):
            label = "HOLD_ENDPOINT_PREFLIGHT_" + type(exc).__name__.upper()
        print("NOX_MAINT_ENDPOINT_PREFLIGHT_RESULT=" + label, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
