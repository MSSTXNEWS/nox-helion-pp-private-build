#!/usr/bin/env python3
"""Owner-fenced, demand-paged DeepSeek GGUF mount.

This is a read-only source adapter: missing model ranges stay in a bounded RAM
LRU and are never written to disk. Already present disk files are used only
after the V10 owner receipt and the full pinned SHA are revalidated. The V10
OneHost downloader remains the safe persistent-disk fallback.

The mount requires the original live OneHost owner lease. OWNER_STOP and
OWNER_MAINTENANCE are checked at startup and for every FUSE read. direct_io is
enabled to prevent kernel page-cache reads from bypassing those fences.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import os
from collections import OrderedDict
from pathlib import Path
import stat
import threading
import time
from urllib.parse import urlsplit
import urllib.request

from fuse import FUSE, FuseOSError, Operations

import deepseek_owner_range_v10 as owner

BLOCK_BYTES = 16 * 1024 * 1024
NETWORK_TIMEOUT = 60


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if (
            parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or not owner.final_url_allowed(newurl)
        ):
            raise owner.Hold("HOLD_RANGE_REDIRECT_SCOPE")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _strong_etag(value):
    return (
        bool(value)
        and not value.startswith("W/")
        and len(value) <= 256
        and all(ord(char) >= 32 for char in value)
    )


def _read_exact(response, count):
    value = bytearray()
    while len(value) < count:
        block = response.read(min(1024 * 1024, count - len(value)))
        if not block:
            raise owner.Hold("HOLD_RANGE_EARLY_EOF")
        value.extend(block)
    if response.read(1):
        raise owner.Hold("HOLD_RANGE_EXCESS_BYTES")
    return bytes(value)


def _identity(info):
    return (
        info.st_dev, info.st_ino, info.st_size, info.st_mode, info.st_uid,
        info.st_nlink, info.st_mtime_ns, info.st_ctime_ns,
    )


class DeepSeekOwnerRangeFS(Operations):
    def __init__(self, *, manifest_path, destination, owner_root, lease_path, request_id, cache_bytes):
        self.owner_root = Path(owner_root)
        self.lease_path = Path(lease_path)
        self.request_id = request_id
        self.destination = Path(destination)
        self.cache_bytes_limit = cache_bytes
        self.cache = OrderedDict()
        self.cache_size = 0
        self.cache_lock = threading.RLock()
        self.remote = {}
        self.local = {}
        self.aliases = {}
        self.started = time.time()
        self.opener = urllib.request.build_opener(PublicRedirect())

        self.guard()
        self.manifest = owner.load_manifest(Path(manifest_path).read_bytes())
        self.aliases = {}  # Set only from the V10-validated alias in the same manifest.
        raw_manifest = __import__("json").loads(Path(manifest_path).read_text())
        alias = raw_manifest["alias"]
        self.aliases[alias["path"]] = alias["target"]
        self.names = set(self.manifest) | set(self.aliases)

        for name, row in self.manifest.items():
            self.guard()
            local_path = self.destination / name
            local_stat = owner.regular(local_path, allow_missing=True)
            if local_stat is not None:
                receipt_path = self.destination / (name + ".verified.json")
                receipt_stat = owner.regular(receipt_path, allow_missing=True)
                if receipt_stat is not None:
                    owner.verify_existing_receipt(receipt_path, row)
                self._open_and_hash_local(name, row, local_path, local_stat)
            else:
                self._probe_remote(name, row)

        self.guard()

    def guard(self):
        owner.stop(self.owner_root)
        owner.lease(self.lease_path, self.request_id, time.time(), self.owner_root)

    def _open_and_hash_local(self, name, row, path, before):
        owner.require(before.st_size == row["bytes"], "HOLD_LOCAL_FALLBACK_SIZE")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            opened = os.fstat(fd)
            owner.require(stat.S_ISREG(opened.st_mode) and _identity(opened) == _identity(before),
                          "HOLD_LOCAL_FALLBACK_CHANGED")
            whole = hashlib.sha256()
            blocks = []
            offset = 0
            while offset < row["bytes"]:
                self.guard()
                count = min(BLOCK_BYTES, row["bytes"] - offset)
                data = os.pread(fd, count, offset)
                owner.require(len(data) == count, "HOLD_LOCAL_FALLBACK_SHORT_READ")
                whole.update(data)
                blocks.append(hashlib.sha256(data).hexdigest())
                offset += count
            after = os.fstat(fd)
            owner.require(_identity(opened) == _identity(after), "HOLD_LOCAL_FALLBACK_CHANGED")
            after_path = owner.regular(path)
            owner.require(after_path is not None and _identity(after_path) == _identity(after),
                          "HOLD_LOCAL_FALLBACK_PATH_CHANGED")
            owner.require(whole.hexdigest() == row["sha256"], "HOLD_LOCAL_FALLBACK_SHA")
            owner.verify_existing_receipt(self.destination / (name + ".verified.json"), row)
            self.local[name] = {"fd": fd, "identity": _identity(after), "blocks": blocks}
            fd = -1
        finally:
            if fd >= 0:
                os.close(fd)

    def _probe_remote(self, name, row):
        request = urllib.request.Request(
            row["url"], headers={"Accept-Encoding": "identity", "User-Agent": "NOX-Owner-Range-V10"},
            method="HEAD",
        )
        self.guard()
        with self.opener.open(request, timeout=NETWORK_TIMEOUT) as response:
            etag = response.headers.get("ETag", "")
            owner.require(response.status == 200, "HOLD_RANGE_HEAD_STATUS")
            owner.require(response.headers.get("Content-Length") == str(row["bytes"]),
                          "HOLD_RANGE_HEAD_LENGTH")
            owner.require(response.headers.get("Content-Encoding", "identity").lower() == "identity",
                          "HOLD_RANGE_HEAD_ENCODING")
            owner.require(_strong_etag(etag), "HOLD_RANGE_STRONG_ETAG_REQUIRED")
        self.guard()
        self.remote[name] = dict(row, etag=etag)

    def _resolve(self, name):
        return self.aliases.get(name, name)

    def getattr(self, path, fh=None):
        now = time.time()
        if path == "/":
            return {
                "st_mode": stat.S_IFDIR | 0o555, "st_nlink": 2,
                "st_uid": os.getuid(), "st_gid": os.getgid(), "st_size": 0,
                "st_atime": now, "st_mtime": self.started, "st_ctime": self.started,
            }
        name = path.lstrip("/")
        if "/" in name or name not in self.names:
            raise FuseOSError(errno.ENOENT)
        target = self._resolve(name)
        row = self.manifest[target]
        return {
            "st_mode": stat.S_IFREG | 0o444, "st_nlink": 1,
            "st_uid": os.getuid(), "st_gid": os.getgid(), "st_size": row["bytes"],
            "st_blksize": 4096, "st_blocks": (row["bytes"] + 511) // 512,
            "st_atime": self.started, "st_mtime": self.started, "st_ctime": self.started,
        }

    def readdir(self, path, fh):
        if path != "/":
            raise FuseOSError(errno.ENOENT)
        yield "."
        yield ".."
        yield from sorted(self.names)

    def open(self, path, flags):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise FuseOSError(errno.EROFS)
        name = path.lstrip("/")
        if "/" in name or name not in self.names:
            raise FuseOSError(errno.ENOENT)
        self.guard()
        return 0

    def read(self, path, size, offset, fh):
        if size < 0 or offset < 0:
            raise FuseOSError(errno.EINVAL)
        name = path.lstrip("/")
        if "/" in name or name not in self.names:
            raise FuseOSError(errno.ENOENT)
        target = self._resolve(name)
        row = self.manifest[target]
        self.guard()
        if offset >= row["bytes"] or size == 0:
            return b""
        end = min(row["bytes"], offset + size)
        output = bytearray()
        cursor = offset
        while cursor < end:
            index = cursor // BLOCK_BYTES
            block = self._block(target, index)
            start = index * BLOCK_BYTES
            within = cursor - start
            take = min(end - cursor, len(block) - within)
            if take <= 0:
                raise FuseOSError(errno.EIO)
            output.extend(block[within:within + take])
            cursor += take
        self.guard()
        return bytes(output)

    def _block(self, name, index):
        self.guard()
        key = (name, index)
        with self.cache_lock:
            cached = self.cache.get(key)
            if cached is not None:
                self.cache.move_to_end(key)
                return cached

        row = self.manifest[name]
        start = index * BLOCK_BYTES
        length = min(BLOCK_BYTES, row["bytes"] - start)
        if length <= 0:
            raise FuseOSError(errno.EIO)

        local = self.local.get(name)
        if local is not None:
            try:
                if _identity(os.fstat(local["fd"])) != local["identity"]:
                    raise owner.Hold("HOLD_LOCAL_FALLBACK_CHANGED")
                block = os.pread(local["fd"], length, start)
                owner.require(len(block) == length, "HOLD_LOCAL_FALLBACK_SHORT_READ")
                owner.require(hashlib.sha256(block).hexdigest() == local["blocks"][index],
                              "HOLD_LOCAL_FALLBACK_BLOCK_SHA")
            except Exception as exc:
                raise FuseOSError(errno.EIO) from exc
        else:
            headers = {
                "Range": "bytes=%d-%d" % (start, start + length - 1),
                "Accept-Encoding": "identity",
                "If-Range": self.remote[name]["etag"],
                "User-Agent": "NOX-Owner-Range-V10",
            }
            request = urllib.request.Request(row["url"], headers=headers)
            self.guard()
            try:
                with self.opener.open(request, timeout=NETWORK_TIMEOUT) as response:
                    owner.require(response.status == 206, "HOLD_RANGE_STATUS")
                    owner.require(owner.final_url_allowed(response.geturl()), "HOLD_RANGE_REDIRECT_SCOPE")
                    owner.content_range(response.headers.get("Content-Range"), start,
                                        start + length - 1, row["bytes"])
                    owner.require(response.headers.get("Content-Length") == str(length),
                                  "HOLD_RANGE_LENGTH")
                    owner.require(response.headers.get("Content-Encoding", "identity").lower() == "identity",
                                  "HOLD_RANGE_ENCODING")
                    owner.require(response.headers.get("ETag") == self.remote[name]["etag"],
                                  "HOLD_RANGE_ETAG_CHANGED")
                    block = _read_exact(response, length)
                self.guard()
            except Exception as exc:
                raise FuseOSError(errno.EIO) from exc

        with self.cache_lock:
            existing = self.cache.get(key)
            if existing is not None:
                self.cache.move_to_end(key)
                return existing
            self.cache[key] = block
            self.cache_size += len(block)
            while self.cache_size > self.cache_bytes_limit and self.cache:
                _, evicted = self.cache.popitem(last=False)
                self.cache_size -= len(evicted)
        return block

    def destroy(self, path):
        for item in self.local.values():
            try:
                os.close(item["fd"])
            except OSError:
                pass
        self.local.clear()
        self.cache.clear()
        self.cache_size = 0


def main():
    parser = argparse.ArgumentParser(description="Owner-fenced DeepSeek demand-range mount")
    parser.add_argument("--mountpoint", required=True, help="existing empty absolute directory")
    parser.add_argument("--manifest", default=str(Path(__file__).with_name("deepseek_v41_download_manifest.json")))
    parser.add_argument("--destination", required=True, help="existing owner-protected model directory")
    parser.add_argument("--lease", required=True, help="current OneHost-issued owner lease")
    parser.add_argument("--request", required=True, help="request ID matching the original lease")
    parser.add_argument("--cache-gib", type=float, default=4.0)
    args = parser.parse_args()

    if not args.request.isdigit() or not (0.25 <= args.cache_gib <= 32):
        parser.error("request must be numeric and cache-gib must be between 0.25 and 32")
    mountpoint = Path(args.mountpoint).expanduser()
    if not mountpoint.is_absolute() or any(part.is_symlink() for part in (mountpoint, *mountpoint.parents)):
        parser.error("mountpoint must be absolute and contain no symlinked components")
    if not mountpoint.is_dir() or any(mountpoint.iterdir()):
        parser.error("mountpoint must be an existing empty directory")
    if os.path.ismount(mountpoint):
        parser.error("mountpoint is already mounted")

    fs = DeepSeekOwnerRangeFS(
        manifest_path=args.manifest,
        destination=args.destination,
        owner_root="/root/nox",
        lease_path=args.lease,
        request_id=args.request,
        cache_bytes=int(args.cache_gib * 1024**3),
    )
    # Direct I/O makes each read pass through the live owner STOP/lease guard.
    # Model writes are never allowed; missing bytes remain in this bounded RAM cache.
    FUSE(fs, str(mountpoint), foreground=True, ro=True, allow_other=False,
         direct_io=True, nothreads=False)


if __name__ == "__main__":
    try:
        main()
    except owner.Hold as exc:
        import json
        print(json.dumps({"state": "HOLD", "reason": str(exc)}))
        raise SystemExit(2)
