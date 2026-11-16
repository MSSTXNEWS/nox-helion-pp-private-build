#!/usr/bin/env python3
"""Owner-fenced DeepSeek demand-range mount for Maya.

First use streams every pinned source file through SHA-256 in bounded RAM,
without writing model bytes to disk. A tiny receipt is cached by source+ETag.
Maya's immutable GGUF files are read-only; only virtual /maya-ds4 maps to a
separate owner-private writable directory for Maya's local model pack.

The original V10 OneHost downloader remains the safe full-file disk fallback.
Every mount and file operation is fenced by its current OneHost lease and
OWNER_STOP. Direct I/O prevents cached kernel pages from bypassing those gates.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
from collections import OrderedDict
from pathlib import Path, PurePosixPath
import stat
import threading
import time
from urllib.parse import urlsplit
import urllib.request

from fuse import FUSE, FuseOSError, Operations

import deepseek_owner_range_v10 as owner

BLOCK_BYTES = 16 * 1024 * 1024
STREAM_VERIFY_BYTES = 128 * 1024 * 1024
NETWORK_TIMEOUT = 60
PACK_VIRTUAL = "/maya-ds4"
PACK_RESERVE_BYTES = 1024**3
RECEIPT_SCHEMA = "NOX_DEEPSEEK_RANGE_SHA_RECEIPT_V1"


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


def _private_directory(path, create=False, private=True):
    path = Path(path).expanduser()
    if not path.is_absolute() or ".." in path.parts:
        raise owner.Hold("HOLD_RANGE_DIRECTORY_PATH")
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise owner.Hold("HOLD_RANGE_DIRECTORY_SYMLINK")
    if not path.exists() and create:
        if not path.parent.is_dir():
            raise owner.Hold("HOLD_RANGE_DIRECTORY_PARENT")
        path.mkdir(mode=0o700)
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise owner.Hold("HOLD_RANGE_DIRECTORY_UNREADABLE") from exc
    owner.require(stat.S_ISDIR(info.st_mode), "HOLD_RANGE_DIRECTORY_TYPE")
    owner.require(info.st_uid == os.geteuid() and not (info.st_mode & 0o022),
                  "HOLD_RANGE_DIRECTORY_PERMISSIONS")
    if private:
        owner.require(not (info.st_mode & 0o077), "HOLD_RANGE_DIRECTORY_PRIVATE")
    return path


class DeepSeekOwnerRangeFS(Operations):
    def __init__(
        self, *, manifest_path, destination, pack_root, receipt_dir,
        owner_root, lease_path, request_id, cache_bytes,
    ):
        self.owner_root = Path(owner_root)
        self.lease_path = Path(lease_path)
        self.request_id = request_id
        self.destination = Path(destination)
        self.cache_bytes_limit = cache_bytes
        self.cache = OrderedDict()
        self.cache_size = 0
        self.cache_lock = threading.RLock()
        self.handle_lock = threading.RLock()
        self.pack_handles = {}
        self.remote = {}
        self.local = {}
        self.aliases = {}
        self.started = time.time()
        self.opener = urllib.request.build_opener(PublicRedirect())

        self.guard()
        self.destination = _private_directory(self.destination, private=False)
        self.pack_root = _private_directory(pack_root, create=True)
        self.receipt_dir = _private_directory(receipt_dir, create=True)
        owner.require(
            self.destination.parts[:len(self.owner_root.parts)] == self.owner_root.parts
            and self.pack_root.parts[:len(self.owner_root.parts)] == self.owner_root.parts
            and self.receipt_dir.parts[:len(self.owner_root.parts)] == self.owner_root.parts,
            "HOLD_RANGE_PATH_OUTSIDE_OWNER_ROOT",
        )
        capacity = os.statvfs(self.pack_root)
        owner.require(
            capacity.f_bavail * capacity.f_frsize >= 3 * 1024**3,
            "HOLD_MAYA_PACK_DISK_RESERVE",
        )

        manifest_raw = Path(manifest_path).read_bytes()
        self.manifest = owner.load_manifest(manifest_raw)
        raw_manifest = json.loads(manifest_raw)
        alias = raw_manifest["alias"]
        self.aliases = {alias["path"]: alias["target"]}
        self.names = set(self.manifest) | set(self.aliases)
        self.sha_verified = set()

        for name, row in self.manifest.items():
            self.guard()
            etag = self._probe_remote(name, row)
            local_path = self.destination / name
            local_stat = owner.regular(local_path, allow_missing=True)
            if local_stat is not None:
                self._verify_local_source(name, row, local_path, local_stat, etag)
            else:
                self._verify_remote_source(name, row, etag)
        self.guard()

    def guard(self):
        owner.stop(self.owner_root)
        owner.lease(self.lease_path, self.request_id, time.time(), self.owner_root)

    def runtime_guard(self):
        try:
            self.guard()
        except Exception as exc:
            raise FuseOSError(errno.EIO) from exc

    def _receipt_path(self, row, etag):
        identity = "\0".join((
            owner.REPO, owner.REVISION, row["path"], str(row["bytes"]),
            row["sha256"], row["url"], etag,
        )).encode()
        key = hashlib.sha256(identity).hexdigest()
        return self.receipt_dir / (key + ".json")

    def _receipt_matches(self, path, row, etag):
        st = owner.regular(path, allow_missing=True)
        if st is None:
            return False
        owner.require(st.st_size <= 8192 and not (st.st_mode & 0o077),
                      "HOLD_RANGE_SHA_RECEIPT_PERMISSIONS")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            opened = os.fstat(fd)
            owner.require(stat.S_ISREG(opened.st_mode) and _identity(opened) == _identity(st),
                          "HOLD_RANGE_SHA_RECEIPT_CHANGED")
            raw = os.read(fd, 8193)
            owner.require(len(raw) == opened.st_size and _identity(os.fstat(fd)) == _identity(opened),
                          "HOLD_RANGE_SHA_RECEIPT_CHANGED")
        finally:
            os.close(fd)
        try:
            doc = json.loads(raw, object_pairs_hook=owner._strict_lease_pairs,
                             parse_constant=owner._reject_lease_nonfinite)
        except (ValueError, UnicodeError, TypeError) as exc:
            raise owner.Hold("HOLD_RANGE_SHA_RECEIPT_JSON") from exc
        expected = {
            "schema": RECEIPT_SCHEMA,
            "repository": owner.REPO,
            "revision": owner.REVISION,
            "source_path": row["path"],
            "bytes": row["bytes"],
            "sha256": row["sha256"],
            "verified_sha256": row["sha256"],
            "url": row["url"],
            "etag": etag,
        }
        owner.require(isinstance(doc, dict) and
                      all(doc.get(key) == value for key, value in expected.items()),
                      "HOLD_RANGE_SHA_RECEIPT_IDENTITY")
        return True

    def _save_receipt(self, row, etag, method):
        path = self._receipt_path(row, etag)
        owner.atomic_receipt(path, {
            "schema": RECEIPT_SCHEMA,
            "repository": owner.REPO,
            "revision": owner.REVISION,
            "source_path": row["path"],
            "bytes": row["bytes"],
            "sha256": row["sha256"],
            "verified_sha256": row["sha256"],
            "url": row["url"],
            "etag": etag,
            "method": method,
            "verified_at_unix": time.time(),
        })

    def _probe_remote(self, name, row):
        self.guard()
        request = urllib.request.Request(
            row["url"],
            headers={"Accept-Encoding": "identity", "User-Agent": "NOX-Owner-Range-V10"},
            method="HEAD",
        )
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
        return etag

    def _request_block(self, name, row, etag, start, max_bytes=BLOCK_BYTES):
        count = min(max_bytes, row["bytes"] - start)
        if count <= 0:
            raise owner.Hold("HOLD_RANGE_OFFSET")
        end = start + count - 1
        headers = {
            "Range": "bytes=%d-%d" % (start, end),
            "Accept-Encoding": "identity",
            "If-Range": etag,
            "User-Agent": "NOX-Owner-Range-V10",
        }
        request = urllib.request.Request(row["url"], headers=headers)
        self.guard()
        with self.opener.open(request, timeout=NETWORK_TIMEOUT) as response:
            owner.require(response.status == 206, "HOLD_RANGE_STATUS")
            owner.require(owner.final_url_allowed(response.geturl()), "HOLD_RANGE_REDIRECT_SCOPE")
            owner.content_range(response.headers.get("Content-Range"), start, end, row["bytes"])
            owner.require(response.headers.get("Content-Length") == str(count), "HOLD_RANGE_LENGTH")
            owner.require(response.headers.get("Content-Encoding", "identity").lower() == "identity",
                          "HOLD_RANGE_ENCODING")
            owner.require(response.headers.get("ETag") == etag, "HOLD_RANGE_ETAG_CHANGED")
            block = _read_exact(response, count)
        self.guard()
        return block

    def _verify_remote_source(self, name, row, etag):
        receipt = self._receipt_path(row, etag)
        if self._receipt_matches(receipt, row, etag):
            self.sha_verified.add(name)
            return
        whole = hashlib.sha256()
        offset = 0
        while offset < row["bytes"]:
            self.guard()
            block = self._request_block(name, row, etag, offset, STREAM_VERIFY_BYTES)
            whole.update(block)
            offset += len(block)
        self.guard()
        owner.require(whole.hexdigest() == row["sha256"], "HOLD_RANGE_FULL_SOURCE_SHA")
        try:
            self._save_receipt(row, etag, "FULL_PUBLIC_RANGE_STREAM")
        except owner.Hold:
            if not self._receipt_matches(receipt, row, etag):
                raise
        self.sha_verified.add(name)

    def _verify_local_source(self, name, row, path, before, etag):
        owner.require(before.st_size == row["bytes"], "HOLD_LOCAL_FALLBACK_SIZE")
        receipt_path = self.destination / (name + ".verified.json")
        existing_receipt = owner.regular(receipt_path, allow_missing=True)
        if existing_receipt is not None:
            owner.verify_existing_receipt(receipt_path, row)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        keep_fd = False
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
            after_path = owner.regular(path)
            owner.require(_identity(opened) == _identity(after) == _identity(after_path),
                          "HOLD_LOCAL_FALLBACK_PATH_CHANGED")
            owner.require(whole.hexdigest() == row["sha256"], "HOLD_LOCAL_FALLBACK_SHA")
            receipt = self._receipt_path(row, etag)
            if not self._receipt_matches(receipt, row, etag):
                try:
                    self._save_receipt(row, etag, "LOCAL_FULL_SHA")
                except owner.Hold:
                    if not self._receipt_matches(receipt, row, etag):
                        raise
            self.local[name] = {"fd": fd, "identity": _identity(after), "blocks": blocks}
            keep_fd = True
            self.sha_verified.add(name)
        finally:
            if not keep_fd:
                os.close(fd)

    def _resolve(self, name):
        return self.aliases.get(name, name)

    def _pack_path(self, path, allow_missing=False):
        value = path.rstrip("/") or "/"
        if value == PACK_VIRTUAL:
            return self.pack_root
        if not value.startswith(PACK_VIRTUAL + "/"):
            raise FuseOSError(errno.EROFS)
        relative = value[len(PACK_VIRTUAL) + 1:]
        parts = PurePosixPath(relative).parts
        if not parts or any(part in ("", ".", "..") for part in parts):
            raise FuseOSError(errno.EACCES)
        current = self.pack_root
        for index, part in enumerate(parts):
            current = current / part
            try:
                info = os.lstat(current)
            except FileNotFoundError:
                if allow_missing and index == len(parts) - 1:
                    return current
                raise FuseOSError(errno.ENOENT)
            except OSError as exc:
                raise FuseOSError(errno.EIO) from exc
            if stat.S_ISLNK(info.st_mode):
                raise FuseOSError(errno.ELOOP)
            if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
                raise FuseOSError(errno.ENOTDIR)
        return current

    def _pack_capacity(self, incoming=0):
        try:
            vfs = os.statvfs(self.pack_root)
        except OSError as exc:
            raise FuseOSError(errno.EIO) from exc
        available = vfs.f_bavail * vfs.f_frsize
        if available < PACK_RESERVE_BYTES + incoming:
            raise FuseOSError(errno.ENOSPC)

    def _pack_handle(self, path, fh):
        with self.handle_lock:
            handle = self.pack_handles.get(fh)
        if handle is None or handle["path"] != path:
            raise FuseOSError(errno.EBADF)
        try:
            current = os.fstat(fh)
            if _identity(current) != handle["identity"]:
                raise FuseOSError(errno.EIO)
        except OSError as exc:
            raise FuseOSError(errno.EIO) from exc
        return handle

    def getattr(self, path, fh=None):
        now = time.time()
        if path == "/":
            return {
                "st_mode": stat.S_IFDIR | 0o555, "st_nlink": 2,
                "st_uid": os.getuid(), "st_gid": os.getgid(), "st_size": 0,
                "st_atime": now, "st_mtime": self.started, "st_ctime": self.started,
            }
        if path == PACK_VIRTUAL or path.startswith(PACK_VIRTUAL + "/"):
            target = self._pack_path(path)
            try:
                info = os.lstat(target)
            except OSError as exc:
                raise FuseOSError(errno.ENOENT) from exc
            if stat.S_ISLNK(info.st_mode):
                raise FuseOSError(errno.ELOOP)
            return {
                "st_mode": info.st_mode, "st_nlink": info.st_nlink,
                "st_uid": info.st_uid, "st_gid": info.st_gid, "st_size": info.st_size,
                "st_blksize": info.st_blksize, "st_blocks": info.st_blocks,
                "st_atime": info.st_atime, "st_mtime": info.st_mtime, "st_ctime": info.st_ctime,
            }
        name = path.lstrip("/")
        if "/" in name or name not in self.names:
            raise FuseOSError(errno.ENOENT)
        row = self.manifest[self._resolve(name)]
        return {
            "st_mode": stat.S_IFREG | 0o444, "st_nlink": 1,
            "st_uid": os.getuid(), "st_gid": os.getgid(), "st_size": row["bytes"],
            "st_blksize": 4096, "st_blocks": (row["bytes"] + 511) // 512,
            "st_atime": self.started, "st_mtime": self.started, "st_ctime": self.started,
        }

    def readdir(self, path, fh):
        if path == "/":
            yield "."
            yield ".."
            yield from sorted(self.names | {"maya-ds4"})
            return
        if path == PACK_VIRTUAL or path == PACK_VIRTUAL + "/":
            root = self._pack_path(PACK_VIRTUAL)
            yield "."
            yield ".."
            try:
                children = sorted(root.iterdir(), key=lambda child: child.name)
            except OSError as exc:
                raise FuseOSError(errno.EIO) from exc
            for child in children:
                if child.is_symlink():
                    raise FuseOSError(errno.ELOOP)
                yield child.name
            return
        if path.startswith(PACK_VIRTUAL + "/"):
            root = self._pack_path(path)
            try:
                if not root.is_dir():
                    raise FuseOSError(errno.ENOTDIR)
                yield "."
                yield ".."
                for child in sorted(root.iterdir(), key=lambda item: item.name):
                    if child.is_symlink():
                        raise FuseOSError(errno.ELOOP)
                    yield child.name
            except OSError as exc:
                raise FuseOSError(errno.EIO) from exc
            return
        raise FuseOSError(errno.ENOENT)

    def open(self, path, flags):
        if path == PACK_VIRTUAL or path.startswith(PACK_VIRTUAL + "/"):
            self.runtime_guard()
            target = self._pack_path(path)
            try:
                fd = os.open(target, flags | os.O_NOFOLLOW | os.O_CLOEXEC)
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode):
                    os.close(fd)
                    raise FuseOSError(errno.EISDIR)
            except OSError as exc:
                raise FuseOSError(exc.errno or errno.EIO) from exc
            with self.handle_lock:
                self.pack_handles[fd] = {"path": path, "identity": _identity(info)}
            return fd

        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise FuseOSError(errno.EROFS)
        name = path.lstrip("/")
        if "/" in name or name not in self.names:
            raise FuseOSError(errno.ENOENT)
        self.runtime_guard()
        return 0

    def create(self, path, mode, fi=None):
        self.runtime_guard()
        target = self._pack_path(path, allow_missing=True)
        self._pack_capacity(1)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            fd = os.open(target, flags, mode & 0o600 or 0o600)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                os.close(fd)
                raise FuseOSError(errno.EIO)
        except OSError as exc:
            raise FuseOSError(exc.errno or errno.EIO) from exc
        with self.handle_lock:
            self.pack_handles[fd] = {"path": path, "identity": _identity(info)}
        return fd

    def read(self, path, size, offset, fh):
        if size < 0 or offset < 0:
            raise FuseOSError(errno.EINVAL)
        if path == PACK_VIRTUAL or path.startswith(PACK_VIRTUAL + "/"):
            self.runtime_guard()
            self._pack_path(path)
            handle = self._pack_handle(path, fh)
            try:
                return os.pread(fh, size, offset)
            except OSError as exc:
                raise FuseOSError(errno.EIO) from exc

        name = path.lstrip("/")
        if "/" in name or name not in self.names:
            raise FuseOSError(errno.ENOENT)
        target = self._resolve(name)
        row = self.manifest[target]
        self.runtime_guard()
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
        self.runtime_guard()
        return bytes(output)

    def _block(self, name, index):
        self.runtime_guard()
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
        try:
            if local is not None:
                if _identity(os.fstat(local["fd"])) != local["identity"]:
                    raise owner.Hold("HOLD_LOCAL_FALLBACK_CHANGED")
                block = os.pread(local["fd"], length, start)
                owner.require(len(block) == length, "HOLD_LOCAL_FALLBACK_SHORT_READ")
                owner.require(hashlib.sha256(block).hexdigest() == local["blocks"][index],
                              "HOLD_LOCAL_FALLBACK_BLOCK_SHA")
            else:
                remote = self.remote[name]
                block = self._request_block(name, row, remote["etag"], start)
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
                _, removed = self.cache.popitem(last=False)
                self.cache_size -= len(removed)
        return block

    def write(self, path, data, offset, fh):
        self.runtime_guard()
        self._pack_path(path)
        self._pack_handle(path, fh)
        self._pack_capacity(len(data))
        try:
            return os.pwrite(fh, data, offset)
        except OSError as exc:
            raise FuseOSError(errno.EIO) from exc

    def truncate(self, path, length, fh=None):
        self.runtime_guard()
        target = self._pack_path(path)
        if fh is not None:
            self._pack_handle(path, fh)
            fd = fh
            close = False
        else:
            try:
                fd = os.open(target, os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
                close = True
            except OSError as exc:
                raise FuseOSError(errno.EIO) from exc
        try:
            self._pack_capacity(max(0, length - os.fstat(fd).st_size))
            os.ftruncate(fd, length)
        except OSError as exc:
            raise FuseOSError(errno.EIO) from exc
        finally:
            if close:
                os.close(fd)

    def mkdir(self, path, mode):
        self.runtime_guard()
        if path == PACK_VIRTUAL or path == PACK_VIRTUAL + "/":
            raise FuseOSError(errno.EEXIST)
        target = self._pack_path(path, allow_missing=True)
        self._pack_capacity(1)
        try:
            os.mkdir(target, mode & 0o700 or 0o700)
        except OSError as exc:
            raise FuseOSError(exc.errno or errno.EIO) from exc

    def unlink(self, path):
        self.runtime_guard()
        target = self._pack_path(path)
        try:
            if not stat.S_ISREG(os.lstat(target).st_mode):
                raise FuseOSError(errno.EPERM)
            os.unlink(target)
        except OSError as exc:
            raise FuseOSError(exc.errno or errno.EIO) from exc

    def rmdir(self, path):
        self.runtime_guard()
        target = self._pack_path(path)
        if target == self.pack_root:
            raise FuseOSError(errno.EPERM)
        try:
            if not stat.S_ISDIR(os.lstat(target).st_mode):
                raise FuseOSError(errno.ENOTDIR)
            os.rmdir(target)
        except OSError as exc:
            raise FuseOSError(exc.errno or errno.EIO) from exc

    def rename(self, old, new, flags=0):
        self.runtime_guard()
        if flags:
            raise FuseOSError(errno.EINVAL)
        source = self._pack_path(old)
        target = self._pack_path(new, allow_missing=True)
        try:
            if stat.S_ISLNK(os.lstat(source).st_mode):
                raise FuseOSError(errno.ELOOP)
            os.rename(source, target)
        except OSError as exc:
            raise FuseOSError(exc.errno or errno.EIO) from exc

    def flush(self, path, fh):
        self.runtime_guard()
        with self.handle_lock:
            managed = fh in self.pack_handles
        if managed:
            self._pack_handle(path, fh)
            try:
                os.fsync(fh)
            except OSError as exc:
                raise FuseOSError(errno.EIO) from exc
        return 0

    def fsync(self, path, datasync, fh):
        return self.flush(path, fh)

    def release(self, path, fh):
        with self.handle_lock:
            handle = self.pack_handles.pop(fh, None)
        if handle is not None:
            try:
                os.fsync(fh)
            finally:
                os.close(fh)
        return 0

    def access(self, path, mode):
        if path == "/" or (path not in (PACK_VIRTUAL, PACK_VIRTUAL + "/")
                            and not path.startswith(PACK_VIRTUAL + "/")):
            if mode & os.W_OK:
                raise FuseOSError(errno.EROFS)
            if path != "/" and path.lstrip("/") not in self.names:
                raise FuseOSError(errno.ENOENT)
            return 0
        target = self._pack_path(path)
        self.runtime_guard()
        if not os.access(target, mode, follow_symlinks=False):
            raise FuseOSError(errno.EACCES)
        return 0

    def statfs(self, path):
        try:
            value = os.statvfs(self.pack_root)
        except OSError as exc:
            raise FuseOSError(errno.EIO) from exc
        return {
            "f_bsize": value.f_bsize, "f_frsize": value.f_frsize,
            "f_blocks": value.f_blocks, "f_bfree": value.f_bfree,
            "f_bavail": value.f_bavail, "f_files": value.f_files,
            "f_ffree": value.f_ffree, "f_favail": value.f_favail,
            "f_namemax": value.f_namemax,
        }

    def destroy(self, path):
        with self.handle_lock:
            handles = list(self.pack_handles)
            self.pack_handles.clear()
        for fd in handles:
            try:
                os.close(fd)
            except OSError:
                pass
        for item in self.local.values():
            try:
                os.close(item["fd"])
            except OSError:
                pass
        self.local.clear()
        self.cache.clear()
        self.cache_size = 0


def main():
    parser = argparse.ArgumentParser(description="Owner-fenced DeepSeek range mount for Maya")
    parser.add_argument("--mountpoint", required=True, help="existing empty absolute FUSE mountpoint")
    parser.add_argument("--manifest", default=str(Path(__file__).with_name("deepseek_v41_download_manifest.json")))
    parser.add_argument("--destination", required=True, help="existing private directory for verified disk fallback files")
    parser.add_argument("--pack-root", required=True, help="separate private writable directory for Maya's /maya-ds4 pack")
    parser.add_argument("--receipt-dir", default="/root/nox/state/deepseek_range_sha_receipts")
    parser.add_argument("--lease", required=True, help="current OneHost owner lease")
    parser.add_argument("--request", required=True, help="request ID matching the original lease")
    parser.add_argument("--cache-gib", type=float, default=4.0)
    args = parser.parse_args()

    if not args.request.isdigit() or not (0.25 <= args.cache_gib <= 32):
        parser.error("request must be numeric and cache-gib must be between 0.25 and 32")
    mountpoint = Path(args.mountpoint).expanduser()
    if (
        not mountpoint.is_absolute()
        or any(part.is_symlink() for part in (mountpoint, *mountpoint.parents))
        or not mountpoint.is_dir()
        or any(mountpoint.iterdir())
        or os.path.ismount(mountpoint)
    ):
        parser.error("mountpoint must be an existing empty absolute directory, not already mounted")
    owner_root = Path("/root/nox")
    fs = DeepSeekOwnerRangeFS(
        manifest_path=args.manifest,
        destination=args.destination,
        pack_root=args.pack_root,
        receipt_dir=args.receipt_dir,
        owner_root=owner_root,
        lease_path=args.lease,
        request_id=args.request,
        cache_bytes=int(args.cache_gib * 1024**3),
    )
    # We allow writes only under virtual /maya-ds4; the GGUF source paths stay
    # immutable. direct_io forces each model read through owner STOP/lease gates.
    FUSE(fs, str(mountpoint), foreground=True, ro=False, allow_other=False,
         direct_io=True, nothreads=False)


if __name__ == "__main__":
    try:
        main()
    except owner.Hold as exc:
        print(json.dumps({"state": "HOLD", "reason": str(exc)}))
        raise SystemExit(2)
