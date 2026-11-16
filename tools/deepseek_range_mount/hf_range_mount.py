#!/usr/bin/env python3
"""Read-only, RAM-cached Hugging Face range mount for NOX DeepSeek.

Install the Linux FUSE package and fusepy, then run:
  python3 hf_range_mount.py --mountpoint /absolute/empty/mount --existing-dir /absolute/preserved/shards

This exposes pinned GGUF files as seekable local paths without materializing
them on disk. It is a byte-source adapter, not a model loader or proof that
Maya/CUDA can run the model.
"""
from __future__ import annotations

import argparse
import errno
import os
from collections import OrderedDict
from pathlib import Path
import re
import stat
import time
from urllib.parse import urlsplit
import urllib.request

from fuse import FUSE, FuseOSError, Operations

BLOCK_BYTES = 16 * 1024 * 1024
TIMEOUT_SECONDS = 60
LOCAL_REMAINDER = re.compile(
    r"^DeepSeek-V4\.1-Flash-1017-GSQ-RCO-IQ2_XXS-0000[16]-of-00006\.gguf$"
)
SOURCES = (
    (
        "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00005-of-00006.gguf",
        19923784832,
        "7e35f6b4e6fc46f6c4b152b593d84d683c5ece695ae6ad734f556198c041bec1",
        "https://huggingface.co/ISTA-DASLab/DeepSeek-V4.1-Flash-1017-GSQ-RCO-GGUF/resolve/65d53bc8be65123e255ff02f3ded958b6dbf54fd/DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00005-of-00006.gguf",
    ),
    (
        "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00002-of-00006.gguf",
        39535781184,
        "25af3785ccf925f54137e1ead4c481a8952315dc0b1af6519a99407f67bce8f3",
        "https://huggingface.co/ISTA-DASLab/DeepSeek-V4.1-Flash-1017-GSQ-RCO-GGUF/resolve/65d53bc8be65123e255ff02f3ded958b6dbf54fd/DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00002-of-00006.gguf",
    ),
    (
        "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00003-of-00006.gguf",
        39736712000,
        "8168d0998fc494def2e1952d83c131425a108660aae9d29190f5a8670ab62b48",
        "https://huggingface.co/ISTA-DASLab/DeepSeek-V4.1-Flash-1017-GSQ-RCO-GGUF/resolve/65d53bc8be65123e255ff02f3ded958b6dbf54fd/DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00003-of-00006.gguf",
    ),
    (
        "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00004-of-00006.gguf",
        39036908384,
        "9eb9b4de1968f150dfc207eb31c27be9cd9b5666a9a6246bde8a22b184b4bee0",
        "https://huggingface.co/ISTA-DASLab/DeepSeek-V4.1-Flash-1017-GSQ-RCO-GGUF/resolve/65d53bc8be65123e255ff02f3ded958b6dbf54fd/DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00004-of-00006.gguf",
    ),
    (
        "DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf",
        110595290816,
        "3dac4c54893ad7aa89103c0028500eadc78e74112cef3a2930a97e67dc9fb4f3",
        "https://huggingface.co/ISTA-DASLab/DeepSeek-V4.1-Flash-1017-GSQ-RCO-GGUF/resolve/65d53bc8be65123e255ff02f3ded958b6dbf54fd/DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf",
    ),
)


def _public_https(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or not (host == "huggingface.co" or host.endswith(".huggingface.co") or host.endswith(".hf.co"))
    ):
        raise RuntimeError("redirect left the pinned public Hugging Face domain set")
    return url


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _public_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _etag_ok(value):
    return bool(value) and not value.startswith("W/") and len(value) <= 256 and all(ord(c) >= 32 for c in value)


def _read_exact(response, length):
    data = bytearray()
    while len(data) < length:
        chunk = response.read(min(1024 * 1024, length - len(data)))
        if not chunk:
            raise RuntimeError("range ended early")
        data.extend(chunk)
    if response.read(1):
        raise RuntimeError("range returned excess data")
    return bytes(data)


def _absolute_directory(value, empty=False):
    path = Path(value).expanduser()
    if not path.is_absolute() or any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("directory must be absolute and contain no symlinked path components")
    if not path.is_dir():
        raise ValueError("directory does not exist")
    if empty and any(path.iterdir()):
        raise ValueError("mountpoint must be empty")
    return path


class DeepSeekRangeFS(Operations):
    def __init__(self, cache_bytes, existing_dir=None):
        self.opener = urllib.request.build_opener(PublicRedirect())
        self.cache_bytes_limit = cache_bytes
        self.cache = OrderedDict()
        self.cache_size = 0
        self.cache_lock = __import__("threading").RLock()
        self.started = time.time()
        self.remote = {}
        self.local = {}

        for name, length, sha256, url in SOURCES:
            request = urllib.request.Request(
                _public_https(url), headers={"Accept-Encoding": "identity"}, method="HEAD"
            )
            with self.opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                etag = response.headers.get("ETag", "")
                if (
                    response.status != 200
                    or response.headers.get("Content-Length") != str(length)
                    or response.headers.get("Content-Encoding", "identity").lower() != "identity"
                    or not _etag_ok(etag)
                ):
                    raise RuntimeError("pinned source HEAD metadata mismatch")
            self.remote[name] = {
                "name": name, "bytes": length, "sha256": sha256, "url": url, "etag": etag
            }

        if existing_dir:
            root = _absolute_directory(existing_dir)
            for path in root.iterdir():
                if LOCAL_REMAINDER.fullmatch(path.name):
                    if path.is_symlink() or not path.is_file() or path.name in self.remote:
                        raise RuntimeError("preserved local shard is not a unique regular file")
                    self.local[path.name] = path

    def getattr(self, path, fh=None):
        now = time.time()
        if path == "/":
            return {
                "st_mode": stat.S_IFDIR | 0o555, "st_nlink": 2,
                "st_uid": os.getuid(), "st_gid": os.getgid(), "st_size": 0,
                "st_atime": now, "st_mtime": self.started, "st_ctime": self.started,
            }
        name = path.lstrip("/")
        if "/" in name:
            raise FuseOSError(errno.ENOENT)
        item = self.remote.get(name)
        local = self.local.get(name)
        if item is None and local is None:
            raise FuseOSError(errno.ENOENT)
        length = item["bytes"] if item else local.stat().st_size
        return {
            "st_mode": stat.S_IFREG | 0o444, "st_nlink": 1,
            "st_uid": os.getuid(), "st_gid": os.getgid(), "st_size": length,
            "st_blksize": 4096, "st_blocks": (length + 511) // 512,
            "st_atime": self.started, "st_mtime": self.started, "st_ctime": self.started,
        }

    def readdir(self, path, fh):
        if path != "/":
            raise FuseOSError(errno.ENOENT)
        yield "."
        yield ".."
        yield from sorted(set(self.remote) | set(self.local))

    def open(self, path, flags):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise FuseOSError(errno.EROFS)
        name = path.lstrip("/")
        if name not in self.remote and name not in self.local:
            raise FuseOSError(errno.ENOENT)
        return 0

    def read(self, path, size, offset, fh):
        if size < 0 or offset < 0:
            raise FuseOSError(errno.EINVAL)
        name = path.lstrip("/")
        local = self.local.get(name)
        if local is not None:
            try:
                fd = os.open(local, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                try:
                    if not stat.S_ISREG(os.fstat(fd).st_mode):
                        raise FuseOSError(errno.EIO)
                    return os.pread(fd, size, offset)
                finally:
                    os.close(fd)
            except OSError as exc:
                raise FuseOSError(errno.EIO) from exc

        item = self.remote.get(name)
        if item is None:
            raise FuseOSError(errno.ENOENT)
        if offset >= item["bytes"] or size == 0:
            return b""
        end = min(item["bytes"], offset + size)
        output = bytearray()
        cursor = offset
        while cursor < end:
            index = cursor // BLOCK_BYTES
            block = self._block(item, index)
            start = index * BLOCK_BYTES
            within = cursor - start
            take = min(end - cursor, len(block) - within)
            if take <= 0:
                raise FuseOSError(errno.EIO)
            output.extend(block[within:within + take])
            cursor += take
        return bytes(output)

    def _block(self, item, index):
        key = (item["name"], index)
        with self.cache_lock:
            cached = self.cache.get(key)
            if cached is not None:
                self.cache.move_to_end(key)
                return cached

        start = index * BLOCK_BYTES
        length = min(BLOCK_BYTES, item["bytes"] - start)
        if length <= 0:
            raise FuseOSError(errno.EIO)
        headers = {
            "Range": "bytes=%d-%d" % (start, start + length - 1),
            "Accept-Encoding": "identity",
            "If-Range": item["etag"],
        }
        request = urllib.request.Request(_public_https(item["url"]), headers=headers)
        try:
            with self.opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                expected_range = "bytes %d-%d/%d" % (start, start + length - 1, item["bytes"])
                if (
                    response.status != 206
                    or response.headers.get("Content-Range") != expected_range
                    or response.headers.get("Content-Length") != str(length)
                    or response.headers.get("Content-Encoding", "identity").lower() != "identity"
                    or response.headers.get("ETag") != item["etag"]
                ):
                    raise RuntimeError("range response metadata mismatch")
                block = _read_exact(response, length)
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


def main():
    parser = argparse.ArgumentParser(description="Read-only RAM-cached DeepSeek GGUF range mount")
    parser.add_argument("--mountpoint", required=True, help="existing empty absolute directory")
    parser.add_argument("--existing-dir", help="preserved directory for local 00001/00006 backbone shards")
    parser.add_argument("--cache-gib", type=float, default=4.0, help="RAM LRU budget, 0.25 to 32 GiB")
    args = parser.parse_args()
    if not 0.25 <= args.cache_gib <= 32:
        parser.error("--cache-gib must be between 0.25 and 32")
    mountpoint = _absolute_directory(args.mountpoint, empty=True)
    if os.path.ismount(mountpoint):
        parser.error("mountpoint is already mounted")
    fs = DeepSeekRangeFS(int(args.cache_gib * 1024**3), args.existing_dir)
    FUSE(fs, str(mountpoint), foreground=True, ro=True, allow_other=False, nothreads=False)


if __name__ == "__main__":
    main()
