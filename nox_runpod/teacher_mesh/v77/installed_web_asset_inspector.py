"""Fail-closed, read-only inspection of one installed NOX web process.

This module deliberately does not discover a web root heuristically. A fresh,
owner-authenticated receipt must bind PID/start ticks, owner/lease/STOP state,
entrypoint, static root, manifest, and the loopback serving origin.
"""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import os
import re
import stat
import time
from pathlib import Path, PurePosixPath
from typing import Callable, Any
from urllib.parse import urlsplit


MAX_RECEIPT = 16 * 1024
MAX_MANIFEST = 256 * 1024
MAX_ASSETS = 128
MAX_ASSET_BYTES = 10 * 1024 * 1024
RECEIPT_TTL_SECONDS = 300
TARGET_PID = 356735
_SHA = re.compile(r"^[0-9a-f]{64}$")


class Hold(RuntimeError):
    """Inspection must not proceed because an invariant is unproven."""


def _read_regular_nofollow(path: str, limit: int, *, expected_uid: int | None = None) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise Hold("cannot safely open required file") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            raise Hold("required file type or size is outside bounds")
        if expected_uid is not None and st.st_uid != expected_uid:
            raise Hold("receipt owner does not match process owner")
        if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise Hold("receipt is group/world writable")
        data = bytearray()
        while len(data) <= limit:
            block = os.read(fd, min(65536, limit + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        if len(data) > limit:
            raise Hold("required file exceeded its read bound")
        after = os.fstat(fd)
        if (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise Hold("required file changed while being read")
        return bytes(data)
    finally:
        os.close(fd)


def _safe_path_components(path: str, *, must_exist_dir: bool = False) -> str:
    if not os.path.isabs(path) or "\x00" in path:
        raise Hold("path must be absolute")
    current = "/"
    for part in Path(path).parts[1:]:
        if part in ("", ".", ".."):
            raise Hold("path contains unsafe component")
        current = os.path.join(current, part)
        try:
            st = os.lstat(current)
        except OSError as exc:
            raise Hold("path component is unavailable") from exc
        if stat.S_ISLNK(st.st_mode):
            raise Hold("symlink path component is forbidden")
    if must_exist_dir and not stat.S_ISDIR(os.stat(current, follow_symlinks=False).st_mode):
        raise Hold("static root is not a directory")
    return current


def _start_ticks(proc_root: str, pid: int) -> int:
    raw = _read_regular_nofollow(os.path.join(proc_root, str(pid), "stat"), 4096)
    try:
        text = raw.decode("ascii")
        tail = text[text.rfind(")") + 2 :].split()
        return int(tail[19])  # field 22; tail starts with field 3
    except (UnicodeError, ValueError, IndexError) as exc:
        raise Hold("process start time cannot be parsed") from exc


def _proc_uid(proc_root: str, pid: int) -> int:
    raw = _read_regular_nofollow(os.path.join(proc_root, str(pid), "status"), 16 * 1024)
    for line in raw.decode("ascii", "strict").splitlines():
        if line.startswith("Uid:"):
            try:
                return int(line.split()[1])
            except (ValueError, IndexError) as exc:
                raise Hold("process owner cannot be parsed") from exc
    raise Hold("process owner is unavailable")


def _argv(proc_root: str, pid: int) -> list[str]:
    raw = _read_regular_nofollow(os.path.join(proc_root, str(pid), "cmdline"), 64 * 1024)
    if not raw or not raw.endswith(b"\0"):
        raise Hold("process arguments are unavailable")
    try:
        return [x.decode("utf-8", "strict") for x in raw.rstrip(b"\0").split(b"\0")]
    except UnicodeError as exc:
        raise Hold("process arguments are not valid UTF-8") from exc


def _arg_value(argv: list[str], name: str) -> str | None:
    values = []
    for i, arg in enumerate(argv):
        if arg == name:
            if i + 1 >= len(argv):
                raise Hold("web root argument is incomplete")
            values.append(argv[i + 1])
        elif arg.startswith(name + "="):
            values.append(arg[len(name) + 1 :])
    if len(values) != 1:
        return None
    return values[0]


def _asset_path(root: str, rel: str, *, web_asset: bool = True) -> str:
    p = PurePosixPath(rel)
    if p.is_absolute() or not p.parts or any(x in ("", ".", "..") for x in p.parts):
        raise Hold("asset path is not a safe relative path")
    if web_asset and p.suffix.lower() not in (".js", ".css"):
        raise Hold("allowlist accepts only JavaScript and CSS")
    target = os.path.join(root, *p.parts)
    # Reject symlinks in every component and ensure the resolved name remains below root.
    checked = _safe_path_components(target)
    if os.path.commonpath((root, checked)) != root:
        raise Hold("asset escaped canonical static root")
    return checked


def _read_asset(path: str) -> bytes:
    # Asset files need not be owner-only, but every component is checked above.
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise Hold("allowlisted asset cannot be opened safely") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_ASSET_BYTES:
            raise Hold("asset is not a bounded regular file")
        data = bytearray()
        while len(data) <= MAX_ASSET_BYTES:
            block = os.read(fd, min(65536, MAX_ASSET_BYTES + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        if len(data) > MAX_ASSET_BYTES:
            raise Hold("asset exceeded its read bound")
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise Hold("asset changed while being read")
        return bytes(data)
    finally:
        os.close(fd)


def _parse_origin(origin: str) -> tuple[str, int, str]:
    if not isinstance(origin, str):
        raise Hold("serving origin must be a string")
    u = urlsplit(origin)
    if u.scheme != "http" or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise Hold("serving origin must be plain loopback HTTP without credentials/query")
    try:
        ip = ipaddress.ip_address(u.hostname)
    except ValueError as exc:
        raise Hold("serving origin must use a numeric loopback address") from exc
    if not ip.is_loopback:
        raise Hold("serving origin is not loopback")
    if u.path not in ("", "/"):
        raise Hold("serving origin must not include a route prefix")
    return u.hostname, u.port or 80, ""


def _fetch_loopback(origin: str, route_prefix: str, rel: str, limit: int) -> bytes:
    host, port, _ = _parse_origin(origin)
    if (not isinstance(route_prefix, str) or not route_prefix.startswith("/")
            or "?" in route_prefix or "#" in route_prefix or "%" in route_prefix
            or "\\" in route_prefix or ".." in PurePosixPath(route_prefix).parts
            or "//" in route_prefix):
        raise Hold("invalid serving route prefix")
    target = route_prefix.rstrip("/") + "/" + rel
    if "?" in target or "#" in target or "%" in target or "\\" in target:
        raise Hold("asset route contains query or fragment")
    conn = http.client.HTTPConnection(host, port, timeout=2)
    try:
        conn.request("GET", target, headers={"Connection": "close", "Accept-Encoding": "identity"})
        response = conn.getresponse()
        if response.status != 200 or response.getheader("Location") is not None:
            raise Hold("loopback asset request was not a direct HTTP 200")
        if response.getheader("Set-Cookie") is not None:
            raise Hold("loopback asset response attempted to set a cookie")
        data = response.read(limit + 1)
        if len(data) > limit:
            raise Hold("served asset exceeded its read bound")
        return data
    finally:
        conn.close()


def inspect(proc_root: str, receipt_path: str, *, now: int | None = None,
            fetcher: Callable[[str, str, str, int], bytes] = _fetch_loopback) -> dict[str, Any]:
    """Return hashes only after proving process, receipt, root, and served assets.

    `proc_root` is injectable for offline tests. Never call this on production
    unless the owner has supplied a fresh admission receipt and explicitly
    authorized the bounded loopback GETs.
    """
    now = int(time.time()) if now is None else now
    receipt_bytes = _read_regular_nofollow(receipt_path, MAX_RECEIPT)
    try:
        r = json.loads(receipt_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Hold("owner receipt is not valid JSON") from exc
    required = {"pid", "start_ticks", "uid", "issued_at", "owner_lease", "stop", "entrypoint", "static_root", "manifest_rel", "serve_origin", "route_prefix", "allowlist"}
    if not isinstance(r, dict) or not required.issubset(r):
        raise Hold("owner receipt is missing required evidence")
    pid = r["pid"]
    if pid != TARGET_PID:
        raise Hold("receipt is not for the requested web process")
    if r["owner_lease"] != "CLEAR" or r["stop"] != "CLEAR":
        raise Hold("owner lease or STOP state is not clear")
    try:
        issued = int(r["issued_at"])
        expected_ticks = int(r["start_ticks"])
        expected_uid = int(r["uid"])
    except (TypeError, ValueError) as exc:
        raise Hold("receipt identity or freshness fields are invalid") from exc
    if issued > now or now - issued > RECEIPT_TTL_SECONDS:
        raise Hold("owner receipt is stale")
    if _start_ticks(proc_root, pid) != expected_ticks:
        raise Hold("PID start time does not match owner receipt")
    uid = _proc_uid(proc_root, pid)
    if uid != expected_uid:
        raise Hold("process owner does not match owner receipt")
    receipt = json.loads(receipt_bytes)
    receipt_owner = os.stat(receipt_path, follow_symlinks=False).st_uid
    if receipt_owner != uid:
        raise Hold("receipt owner does not match process owner")

    exe_link = os.path.join(proc_root, str(pid), "exe")
    try:
        exe = os.readlink(exe_link)
    except OSError as exc:
        raise Hold("process executable identity is unavailable") from exc
    expected_entry = r["entrypoint"]
    if not isinstance(expected_entry, str) or not expected_entry.startswith("/") or exe != expected_entry:
        raise Hold("process entrypoint does not match receipt")
    argv = _argv(proc_root, pid)
    root_arg = _arg_value(argv, "--static-root") or _arg_value(argv, "--web-root")
    if not isinstance(r["static_root"], str) or root_arg is None or root_arg != r["static_root"]:
        raise Hold("process does not expose the receipt's explicit static root")
    root = _safe_path_components(r["static_root"], must_exist_dir=True)
    if not os.path.isabs(r["manifest_rel"]):
        manifest_path = _asset_path(root, r["manifest_rel"], web_asset=False)
    else:
        raise Hold("manifest must be relative to the static root")
    manifest = _read_asset_bounded(manifest_path, MAX_MANIFEST)
    try:
        m = json.loads(manifest)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Hold("asset manifest is not valid JSON") from exc
    assets = m.get("assets") if isinstance(m, dict) else None
    if (not isinstance(assets, list) or not assets or len(assets) > MAX_ASSETS
            or any(not isinstance(x, str) for x in assets) or len(set(assets)) != len(assets)):
        raise Hold("asset manifest allowlist is invalid")
    if not isinstance(r.get("allowlist"), list) or r["allowlist"] != assets:
        raise Hold("owner receipt and manifest allowlists differ")
    origin = r["serve_origin"]
    _parse_origin(origin)
    results = []
    for rel in assets:
        disk = _read_asset(_asset_path(root, rel))
        served = fetcher(origin, r["route_prefix"], rel, MAX_ASSET_BYTES)
        disk_sha = hashlib.sha256(disk).hexdigest()
        served_sha = hashlib.sha256(served).hexdigest()
        if disk_sha != served_sha:
            raise Hold("served asset hash differs from installed asset hash")
        results.append({"path": rel, "bytes": len(disk), "sha256": disk_sha, "served_sha256": served_sha})
    if _start_ticks(proc_root, pid) != expected_ticks:
        raise Hold("PID changed during inspection")
    return {"result": "PASS_READ_ONLY", "pid": pid, "start_ticks": expected_ticks,
            "uid": uid, "entrypoint_basename": os.path.basename(exe),
            "static_root": root, "manifest_bytes": len(manifest),
            "manifest_sha256": hashlib.sha256(manifest).hexdigest(), "assets": results}


def _read_asset_bounded(path: str, limit: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise Hold("manifest cannot be opened safely") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            raise Hold("manifest is not a bounded regular file")
        data = bytearray()
        while len(data) <= limit:
            block = os.read(fd, min(65536, limit + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        if len(data) > limit:
            raise Hold("manifest exceeded its read bound")
        after = os.fstat(fd)
        if (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise Hold("manifest changed while being read")
        return bytes(data)
    finally:
        os.close(fd)


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--receipt", required=True, help="owner admission receipt JSON")
    p.add_argument("--proc-root", default="/proc", help=argparse.SUPPRESS)
    args = p.parse_args()
    try:
        result = inspect(args.proc_root, args.receipt)
    except Hold as exc:
        print(json.dumps({"result": "HOLD", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
