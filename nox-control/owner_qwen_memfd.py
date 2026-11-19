#!/usr/bin/env python3
"""Same-process sealed, public HF weight staging; no mount or cache deletion.

memfd pages count toward cgroup RAM. They do not use the /dev/shm filesystem's
mount quota. This holder lives inside the sole existing trainer process and
owns only its newly created descriptors and temporary symlinks.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import errno
import fcntl
import hashlib
import os
from pathlib import Path
import re
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request

from owner_qwen_training_contract import GIB, Hold

# Linux UAPI linux/fcntl.h, also used where Python omits these named constants.
F_ADD_SEALS = getattr(fcntl, "F_ADD_SEALS", 1024 + 9)
F_GET_SEALS = getattr(fcntl, "F_GET_SEALS", 1024 + 10)
SEALS = 0x0001 | 0x0002 | 0x0004 | 0x0008  # SEAL, SHRINK, GROW, WRITE
CHUNK = 1024 * 1024


def seal(fd):
    fcntl.fcntl(fd, F_ADD_SEALS, SEALS)
    if fcntl.fcntl(fd, F_GET_SEALS) & SEALS != SEALS:
        raise Hold("HOLD_MEMFD_SEALS_NOT_APPLIED")


def allowed_public_url(url):
    value = urllib.parse.urlsplit(url)
    host = value.hostname or ""
    if (value.scheme != "https" or value.username or value.password
            or not (host == "huggingface.co" or host.endswith(".huggingface.co") or host.endswith(".hf.co"))):
        raise Hold("HOLD_UNREVIEWED_PUBLIC_WEIGHT_REDIRECT")


class PublicHFRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class SealedModel:
    def __init__(self, parent, *, guard, streams=4, progress=lambda _: None):
        if streams not in range(1, 5) or not callable(guard):
            raise Hold("HOLD_MEMFD_STAGING_CONTRACT")
        parent = Path(parent)
        if (not parent.is_absolute() or parent.resolve() != parent
                or any(p.is_symlink() for p in (*parent.parents, parent))):
            raise Hold("HOLD_MEMFD_PARENT_SCOPE")
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.directory = Path(tempfile.mkdtemp(prefix=f"qwen-{os.getpid()}-", dir=parent))
        self.guard = guard
        self.streams = streams
        self.progress = progress
        self._lock = threading.Lock()
        self._abort = threading.Event()
        self._owned = {}
        self._links = set()
        self.verified = {}

    def _check(self, additional=0):
        if self._abort.is_set():
            raise Hold("HOLD_MEMFD_STAGE_CANCELLED")
        self.guard(additional)

    def _one(self, row):
        name, expected = row["path"], row["bytes"]
        if Path(name).name != name or name in (".", ".."):
            raise Hold("HOLD_MEMFD_FILE_NAME")
        self._check()
        fd = os.memfd_create("nox-qwen-" + name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        with self._lock:
            self._owned[name] = fd
        digest = hashlib.sha256()
        offset = 0
        next_report = GIB
        opener = urllib.request.build_opener(PublicHFRedirect())
        for attempt in range(1, 4):
            self._check()
            allowed_public_url(row["immutable_url"])
            headers = {"Accept-Encoding": "identity", "User-Agent": "NOX-owner-pinned-student/1"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            request = urllib.request.Request(row["immutable_url"], headers=headers)
            try:
                with opener.open(request, timeout=15) as response:
                    allowed_public_url(response.geturl())
                    if offset:
                        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                        if (response.status != 206 or not match or int(match[1]) != offset
                                or int(match[3]) != expected or int(match[2]) != expected - 1):
                            raise Hold("HOLD_MEMFD_RANGE_RESPONSE")
                    elif response.status != 200:
                        raise Hold("HOLD_MEMFD_HTTP_STATUS")
                    length = response.headers.get("Content-Length")
                    if length is not None and int(length) != expected - offset:
                        raise Hold("HOLD_MEMFD_CONTENT_LENGTH")
                    while offset < expected:
                        self._check(CHUNK)
                        block = response.read(min(CHUNK, expected - offset))
                        if not block:
                            raise OSError("truncated public weight response")
                        view = memoryview(block)
                        while view:
                            written = os.write(fd, view)
                            if written <= 0:
                                raise Hold("HOLD_MEMFD_WRITE")
                            view = view[written:]
                        digest.update(block); offset += len(block)
                        if offset >= next_report:
                            self.progress({"file": name, "bytes": offset, "total": expected})
                            next_report += GIB
                    if response.read(1):
                        raise Hold("HOLD_MEMFD_RESPONSE_EXCEEDS_MANIFEST")
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt == 3:
                    raise Hold("HOLD_MEMFD_PUBLIC_DOWNLOAD_INTERRUPTED") from exc
                if offset == expected:
                    raise Hold("HOLD_MEMFD_DOWNLOAD_TERMINATION_UNVERIFIED") from exc
        if offset != expected or digest.hexdigest() != row["sha256"]:
            raise Hold("HOLD_MEMFD_WEIGHT_SHA")
        seal(fd)
        path = self.directory / name
        path.symlink_to(f"/proc/{os.getpid()}/fd/{fd}")
        stat = os.fstat(fd)
        with self._lock:
            self._links.add(name)
            self.verified[name] = {"bytes": offset, "sha256": digest.hexdigest(),
                                   "device": stat.st_dev, "inode": stat.st_ino,
                                   "sealed": True, "attempts": attempt}
        return name

    def stage(self, files):
        if not files or len(files) > 32 or len({r["path"] for r in files}) != len(files):
            raise Hold("HOLD_MEMFD_FILE_SET")
        # Guard must account for the ENTIRE source plus model-load/optimizer
        # headroom before the first public download is opened.
        self._check(sum(r["bytes"] for r in files))
        try:
            with ThreadPoolExecutor(max_workers=self.streams, thread_name_prefix="nox-qwen-stage") as pool:
                futures = [pool.submit(self._one, row) for row in files]
                for future in as_completed(futures):
                    try:
                        future.result()
                    except BaseException:
                        self._abort.set()
                        for pending in futures:
                            pending.cancel()
                        raise
        except BaseException:
            self._abort.set()
            raise
        return {"state": "PUBLIC_WEIGHTS_SEALED_IN_SAME_PROCESS",
                "files": len(self.verified), "bytes": sum(r["bytes"] for r in self.verified.values()),
                "all_sha256_verified": True, "persistent_weights": False,
                "uses_dev_shm_mount_quota": False, "cgroup_ram_charged": True}

    def verify_path(self, path, expected_sha, expected_bytes):
        path = Path(path)
        name = path.name
        proof = self.verified.get(name)
        fd = self._owned.get(name)
        if (path.parent != self.directory or fd is None or not path.is_symlink()
                or os.readlink(path) != f"/proc/{os.getpid()}/fd/{fd}"
                or not proof or proof["sha256"] != expected_sha or proof["bytes"] != expected_bytes
                or fcntl.fcntl(fd, F_GET_SEALS) & SEALS != SEALS):
            raise Hold("HOLD_UNOWNED_OR_UNSEALED_MEMFD_PATH")
        owned, opened = os.fstat(fd), path.stat()
        if ((owned.st_dev, owned.st_ino, owned.st_size) != (opened.st_dev, opened.st_ino, opened.st_size)
                or (owned.st_dev, owned.st_ino, owned.st_size) != (proof["device"], proof["inode"], expected_bytes)):
            raise Hold("HOLD_MEMFD_IDENTITY_CHANGED")
        return True

    def close(self):
        self._abort.set()
        for name in self._links:
            path = self.directory / name
            fd = self._owned[name]
            if path.is_symlink() and os.readlink(path) == f"/proc/{os.getpid()}/fd/{fd}":
                path.unlink()
        for fd in self._owned.values():
            os.close(fd)
        self._owned.clear()
        try:
            self.directory.rmdir()
        except OSError:
            pass  # Do not delete any foreign/unexpected content.

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def tiny_safetensors_smoke(parent):
    """Real library mmap/read and Linux sealing, before any full-model staging."""
    import numpy as np
    import safetensors
    from safetensors import safe_open
    from safetensors.numpy import save
    tensor = np.arange(6, dtype=np.float32).reshape(2, 3)
    raw = save({"probe": tensor})
    fd = os.memfd_create("nox-qwen-tiny-smoke", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    directory = Path(tempfile.mkdtemp(prefix="qwen-tiny-", dir=parent))
    link = directory / "probe.safetensors"
    try:
        os.write(fd, raw); seal(fd)
        link.symlink_to(f"/proc/{os.getpid()}/fd/{fd}")
        with safe_open(str(link), framework="numpy", device="cpu") as reader:
            actual = reader.get_tensor("probe")
            if not np.array_equal(actual, tensor):
                raise Hold("HOLD_MEMFD_TINY_TENSOR_MISMATCH")
        try:
            os.pwrite(fd, b"X", 0)
        except OSError as exc:
            if exc.errno != errno.EPERM:
                raise
        else:
            raise Hold("HOLD_MEMFD_TINY_SEAL_WRITE_FAILED")
        return {"state": "REAL_SAFETENSORS_MEMFD_READ_AND_SEAL_VERIFIED",
                "safetensors_version": safetensors.__version__, "bytes": len(raw),
                "tensor_exact": True, "writes_rejected": True,
                "full_model_loaded": False}
    finally:
        if link.is_symlink() and os.readlink(link) == f"/proc/{os.getpid()}/fd/{fd}":
            link.unlink()
        directory.rmdir(); os.close(fd)
