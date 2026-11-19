"""Restore the exact public Engram quant into a cold NOX container's sealed memfd."""

import fcntl
import hashlib
import http.client
import json
import os
import re
import stat
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


REVISION = "81fd6e0a6f063344001bdecc6119ac53c80c8e63"
SOURCE = "https://huggingface.co/kerem266/DeepSeek-V4.1-Flash-Engram-IQ3_XXS/resolve/" + REVISION
CHUNK = 8 << 20
RESERVE = 4 << 30
MEMFD_NAME = "engram_iq3xxs"
POINTER = Path("/root/nox/models/engram_ram.gguf")
STATE = Path("/root/nox/state")
CGROUP = Path("/sys/fs/cgroup")
TARGET = re.compile(r"/proc/([1-9][0-9]*)/fd/([0-9]+)")
LEGACY_HOLDER = b"/root/nox/engram_ram/engram_memfd_holder.py"
OWNER_STOP_MARKERS = (
    "STOP", "STOP.flag", "stop.flag", ".stop", "program/STOP",
    "state/STOP", "state/STOP.flag", "state/OWNER_MAINTENANCE.flag",
)
# Linux UAPI values from <linux/fcntl.h>, for Python builds that omit their names.
ADD_SEALS = getattr(fcntl, "F_ADD_SEALS", 1033)
GET_SEALS = getattr(fcntl, "F_GET_SEALS", 1034)
SEALS = 0x0001 | 0x0002 | 0x0004 | 0x0008


@dataclass(frozen=True)
class Part:
    name: str
    size: int
    sha256: str


PARTS = (
    Part("engram.part00", 21474836480, "eecf98d8cd45239811f8f7b881b6e7175feacf1cd1f53aeb8bc5bce30be08429"),
    Part("engram.part01", 21474836480, "b9834592fda5eecedeed545adc802e2f1d68e2442680aca2e20f87c4ae669271"),
    Part("engram.part02", 21474836480, "97d483a3da717acb155eec046b1347c0060e06cd6e8337c294ab27363a61a203"),
    Part("engram.part03", 10841730276, "286828e9f44bd80093856f27c55611068baa6b168fd2a6738533d615ec2b9357"),
)
SIZE = 75266239716
assert sum(part.size for part in PARTS) == SIZE


class Hold(RuntimeError):
    """A failed prerequisite left any existing holder untouched."""


class RetryPart(Exception):
    """A transport failure permits discarding and re-fetching the current part."""


def safe_url(raw):
    url = urllib.parse.urlsplit(raw)
    host = url.hostname or ""
    if (url.scheme != "https" or url.username is not None or url.password is not None
            or url.port not in (None, 443)
            or not (host == "huggingface.co" or host.endswith(".huggingface.co")
                    or host.endswith(".hf.co"))):
        raise Hold("HOLD_HF_ENDPOINT")


class HuggingFaceRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        safe_url(url)
        return super().redirect_request(request, fp, code, message, headers, url)


def fetch_part(opener, part):
    url = f"{SOURCE}/{part.name}"
    safe_url(url)
    response = opener.open(
        urllib.request.Request(url, headers={"Accept-Encoding": "identity"}),
        timeout=45,
    )
    try:
        safe_url(response.geturl())
        if response.status != 200 or response.headers.get("Content-Encoding", "identity") != "identity":
            raise Hold("HOLD_HF_RESPONSE")
        length = response.headers.get("Content-Length")
        if length is not None and int(length) != part.size:
            raise Hold("HOLD_PART_SIZE")
    except BaseException:
        response.close()
        raise
    return response


def preflight_egress(opener, parts=PARTS):
    """Prove all pinned downloads are reachable without reserving model memory."""
    verified = []
    for index, part in enumerate(parts):
        url = f"{SOURCE}/{part.name}"
        safe_url(url)
        request = urllib.request.Request(
            url, headers={"Accept-Encoding": "identity", "Range": "bytes=0-3"},
        )
        with opener.open(request, timeout=15) as response:
            safe_url(response.geturl())
            if (response.status != 206
                    or response.headers.get("Content-Encoding", "identity") != "identity"
                    or response.headers.get("Content-Range") != f"bytes 0-3/{part.size}"
                    or response.headers.get("Content-Length", "4") != "4"):
                raise Hold("HOLD_HF_RANGE_RESPONSE")
            probe = response.read(5)
            if len(probe) != 4 or (index == 0 and probe != b"GGUF"):
                raise Hold("HOLD_HF_RANGE_CONTENT")
        verified.append({"name": part.name, "declared_bytes": part.size})
    return {"egress_reachable": True, "part_integrity_verified": False,
            "source_revision": REVISION, "parts": verified}


def verify_cgroup_root():
    unified = [line for line in Path("/proc/self/cgroup").read_text().splitlines()
               if line.startswith("0::")]
    mounts = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        mount, separator, filesystem = line.partition(" - ")
        fields = mount.split()
        if separator and len(fields) >= 5 and fields[4] == str(CGROUP):
            mounts.append((fields[3], filesystem.split()[0]))
    if unified != ["0::/"] or mounts != [("/", "cgroup2")]:
        raise Hold("HOLD_CGROUP_NAMESPACE")


def require_capacity(required, cgroup=CGROUP, meminfo=Path("/proc/meminfo")):
    try:
        headroom = int((cgroup / "memory.max").read_text()) - int((cgroup / "memory.current").read_text())
        host = re.search(r"^MemAvailable:\s+(\d+) kB$", meminfo.read_text(), re.M)
        host_available = int(host.group(1)) << 10 if host else -1
    except (OSError, ValueError) as exc:
        raise Hold("HOLD_MEMORY_CAPACITY_UNKNOWN") from exc
    if min(headroom, host_available) < required:
        raise Hold("HOLD_INSUFFICIENT_MEMORY")


def require_runtime_capacity(required):
    verify_cgroup_root()
    require_owner_running()
    require_capacity(required)


def open_memfd():
    if (sys.platform != "linux" or not hasattr(os, "memfd_create")
            or not hasattr(os, "MFD_ALLOW_SEALING") or not hasattr(os, "MFD_CLOEXEC")):
        raise Hold("HOLD_MEMFD_PLATFORM")
    return os.memfd_create(MEMFD_NAME, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)


def preflight_seals():
    try:
        fd = open_memfd()
        try:
            fcntl.fcntl(fd, ADD_SEALS, SEALS)
            if fcntl.fcntl(fd, GET_SEALS) & SEALS != SEALS:
                raise Hold("HOLD_MEMFD_KERNEL_SUPPORT")
        finally:
            os.close(fd)
    except OSError as exc:
        raise Hold("HOLD_MEMFD_KERNEL_SUPPORT") from exc


def fetch_with_retry_classification(opener, part):
    try:
        return fetch_part(opener, part)
    except urllib.error.HTTPError as error:
        if error.code not in (408, 429, 500, 502, 503, 504):
            raise
        error.close()
        raise RetryPart from error
    except urllib.error.URLError as error:
        if not isinstance(error.reason, (ConnectionError, TimeoutError)):
            raise
        raise RetryPart from error
    except (ConnectionError, TimeoutError, http.client.IncompleteRead) as error:
        raise RetryPart from error


def read_response(response, length):
    try:
        return response.read(length)
    except (ConnectionError, TimeoutError, http.client.IncompleteRead) as error:
        raise RetryPart from error


def stream_part(output, opener, part, require, combined):
    sha = hashlib.sha256()
    remaining = part.size
    with fetch_with_retry_classification(opener, part) as response:
        while remaining:
            block = read_response(response, min(remaining, CHUNK))
            if not block:
                raise RetryPart("truncated")
            if len(block) > remaining:
                raise Hold("HOLD_PART_SIZE")
            require(len(block) + RESERVE)
            if output.write(block) != len(block):
                raise Hold("HOLD_WRITE")
            sha.update(block)
            combined.update(block)
            remaining -= len(block)
        if read_response(response, 1) or sha.hexdigest() != part.sha256:
            raise Hold("HOLD_PART_INTEGRITY")


def fill_memfd(output, opener, parts=PARTS, require=require_runtime_capacity, wait=time.sleep):
    combined = hashlib.sha256()
    require(sum(part.size for part in parts) + RESERVE)
    for part in parts:
        start = output.tell()
        for delay in (1, 3, None):
            trial = combined.copy()
            try:
                stream_part(output, opener, part, require, trial)
            except RetryPart as error:
                output.truncate(start)
                output.seek(start)
                if delay is None:
                    raise Hold("HOLD_PART_TRANSPORT_RETRIES_EXHAUSTED") from error
                require(part.size + RESERVE)
                wait(delay)
                require(part.size + RESERVE)
            else:
                combined = trial
                break
    output.flush()
    return combined.hexdigest()


def require_private_directory(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise Hold("HOLD_DIRECTORY_OWNERSHIP")


def holder_snapshot(pointer):
    try:
        info = pointer.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISLNK(info.st_mode) or info.st_uid != 0:
        raise Hold("HOLD_POINTER_SCOPE")
    target = os.readlink(pointer)
    parsed = TARGET.fullmatch(target)
    if not parsed:
        raise Hold("HOLD_POINTER_TARGET")
    try:
        label = os.readlink(target)
        size = os.stat(target).st_size
    except FileNotFoundError as exc:
        if Path("/proc", parsed[1]).exists():
            raise Hold("HOLD_POINTER_HOLDER_AMBIGUOUS") from exc
        return info.st_dev, info.st_ino, target
    if (label.lstrip("/") == f"memfd:{MEMFD_NAME} (deleted)" and size == SIZE):
        raise Hold("HOLD_EXISTING_LIVE_HOLDER")
    raise Hold("HOLD_POINTER_HOLDER_MISMATCH")


def require_status_scope(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise Hold("HOLD_STATUS_SCOPE")


def reject_legacy_holder():
    for item in Path("/proc").iterdir():
        if not item.name.isdecimal():
            continue
        try:
            with (item / "cmdline").open("rb", buffering=0) as source:
                if LEGACY_HOLDER in source.read(16 << 10).split(b"\0"):
                    raise Hold("HOLD_EXISTING_LEGACY_HOLDER")
        except (FileNotFoundError, ProcessLookupError):
            continue


def inode(info):
    return info.st_dev, info.st_ino


def require_owner_running():
    paths = (*(STATE.parent / name for name in OWNER_STOP_MARKERS), Path("/workspace/NOX_STOP"))
    if any(os.path.lexists(path) for path in paths):
        raise Hold("HOLD_OWNER_STOP")


@contextmanager
def writer_lease(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Hold("HOLD_OWNER_WRITER_LEASE_BUSY") from exc
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
                or info.st_mode & 0o022 or inode(info) != inode(path.lstat())):
            raise Hold("HOLD_OWNER_WRITER_LEASE_SCOPE")
        yield
    finally:
        os.close(fd)


def read_status(path):
    require_status_scope(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != 0
                or info.st_mode & 0o022 or inode(info) != inode(path.lstat())):
            raise Hold("HOLD_STATUS_CHANGED")
        data = source.read(65537)
        if len(data) > 65536 or len(data) != info.st_size:
            raise Hold("HOLD_STATUS_SIZE")
        return info, data


def stage_status(path, data, mode):
    with path.open("xb") as handle:
        os.fchmod(handle.fileno(), mode)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def attest_owned_memfd(fd):
    target = f"/proc/{os.getpid()}/fd/{fd}"
    info = os.fstat(fd)
    sealed = fcntl.fcntl(fd, GET_SEALS)
    if (os.readlink(target).lstrip("/") != f"memfd:{MEMFD_NAME} (deleted)"
            or not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_size != SIZE or sealed & SEALS != SEALS):
        raise Hold("HOLD_MEMFD_OWNERSHIP")
    named = os.stat(target)
    if (named.st_dev, named.st_ino) != (info.st_dev, info.st_ino):
        raise Hold("HOLD_MEMFD_IDENTITY")
    return target, info


def process_start_ticks(pid):
    _, separator, process = Path(f"/proc/{pid}/stat").read_text().rpartition(") ")
    fields = process.split()
    if not separator or len(fields) <= 19 or not fields[19].isdigit():
        raise Hold("HOLD_HOLDER_PROCESS_IDENTITY")
    return int(fields[19])


def current_boot_id():
    return str(UUID(Path("/proc/sys/kernel/random/boot_id").read_text().strip()))


def parts_manifest():
    return {part.name: {"bytes": part.size, "sha256": part.sha256} for part in PARTS}


def verify_current(pointer, status):
    snapshot = read_status(status)
    if snapshot is None:
        raise Hold("HOLD_STATUS_MISSING")
    status_info, status_bytes = snapshot
    record = json.loads(status_bytes)
    if not isinstance(record, dict) or (
        record.get("state"), record.get("status"), record.get("ready"),
        record.get("source_revision"), record.get("bytes"), record.get("size"),
        record.get("link"), record.get("parts")
    ) != (
        "READY_SHA_OK", "READY_SHA_OK", True, REVISION, SIZE, SIZE,
        str(pointer), parts_manifest(),
    ):
        raise Hold("HOLD_STATUS_CONTENT")
    pid = record.get("holder_pid")
    fd_number = record.get("holder_fd")
    if (type(pid) is not int or pid < 2 or type(fd_number) is not int or fd_number < 0
            or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256", "")))):
        raise Hold("HOLD_STATUS_HOLDER_IDENTITY")
    target = f"/proc/{pid}/fd/{fd_number}"
    expected_generation = current_boot_id(), process_start_ticks(1), process_start_ticks(pid)
    if expected_generation != (
        record.get("boot_id"), record.get("container_pid1_start_ticks"),
        record.get("holder_start_ticks"),
    ):
        raise Hold("HOLD_STALE_ENGRAM_GENERATION")
    pointer_info = pointer.lstat()
    if (not stat.S_ISLNK(pointer_info.st_mode) or pointer_info.st_uid != 0
            or os.readlink(pointer) != target):
        raise Hold("HOLD_POINTER_TARGET")
    descriptor = os.open(target, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        sealed = fcntl.fcntl(descriptor, GET_SEALS)
        if (os.readlink(target).lstrip("/") != f"memfd:{MEMFD_NAME} (deleted)"
                or not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_size != SIZE
                or inode(info) != (record.get("device"), record.get("inode"))
                or sealed & SEALS != SEALS or os.pread(descriptor, 4, 0) != b"GGUF"):
            raise Hold("HOLD_ENGRAM_DESCRIPTOR")
        status_after = read_status(status)
        if (status_after is None or inode(status_after[0]) != inode(status_info)
                or status_after[1] != status_bytes or inode(pointer.lstat()) != inode(pointer_info)
                or os.readlink(pointer) != target or inode(os.stat(target)) != inode(info)
                or process_start_ticks(pid) != expected_generation[2]
                or process_start_ticks(1) != expected_generation[1]):
            raise Hold("HOLD_ENGRAM_CHANGED_DURING_VERIFY")
    finally:
        os.close(descriptor)
    return {
        "engram_ready": True, "model_health_verified": False,
        "holder_pid": pid, "holder_start_ticks": expected_generation[2],
        "container_pid1_start_ticks": expected_generation[1],
        "bytes": SIZE, "source_revision": REVISION,
    }


def publish(pointer, status, fd, sha256, prior_pointer):
    target, info = attest_owned_memfd(fd)
    record = {
        "state": "READY_SHA_OK", "status": "READY_SHA_OK", "ready": True, "size": SIZE, "bytes": SIZE,
        "sha256": sha256, "source_revision": REVISION, "holder_pid": os.getpid(),
        "holder_fd": fd, "device": info.st_dev, "inode": info.st_ino,
        "holder_start_ticks": process_start_ticks(os.getpid()),
        "container_pid1_start_ticks": process_start_ticks(1),
        "boot_id": current_boot_id(),
        "link": str(pointer),
        "parts": parts_manifest(),
        "updated_at": time.time(),
    }
    raw = (json.dumps(record, sort_keys=True) + "\n").encode()
    with (
        writer_lease(status.parent / "owner_maintenance.lock"),
        tempfile.TemporaryDirectory(prefix=".engram-", dir=pointer.parent) as pointer_stage,
        tempfile.TemporaryDirectory(prefix=".engram-", dir=status.parent) as status_stage,
    ):
        require_owner_running()
        require_runtime_capacity(RESERVE)
        reject_legacy_holder()
        if holder_snapshot(pointer) != prior_pointer:
            raise Hold("HOLD_POINTER_CHANGED")
        old_status = read_status(status)
        previous_status = Path(status_stage, "previous")
        if old_status is not None:
            stage_status(previous_status, old_status[1], stat.S_IMODE(old_status[0].st_mode))
        old_pointer = Path(pointer_stage, "previous")
        if prior_pointer is not None:
            old_pointer.symlink_to(prior_pointer[2])
        next_pointer = Path(pointer_stage, "next")
        next_pointer.symlink_to(target)
        next_status = Path(status_stage, "next")
        stage_status(next_status, raw, 0o640)
        pointer_id, status_id = inode(next_pointer.lstat()), inode(next_status.lstat())
        pointer_published = status_published = False
        try:
            # The link is the existing launcher's final admission signal.
            if old_status is None:
                os.link(next_status, status, follow_symlinks=False)
            else:
                current = read_status(status)
                if current is None or inode(current[0]) != inode(old_status[0]) or current[1] != old_status[1]:
                    raise Hold("HOLD_STATUS_CHANGED")
                os.replace(next_status, status)
            status_published = True
            # The no-clobber hard link is an internal staging alias.
            next_status.unlink(missing_ok=True)
            actual = read_status(status)
            if actual is None or inode(actual[0]) != status_id or actual[1] != raw:
                raise Hold("HOLD_STATUS_READBACK")
            sync_directory(status.parent)
            require_owner_running()
            require_runtime_capacity(RESERVE)
            if holder_snapshot(pointer) != prior_pointer:
                raise Hold("HOLD_POINTER_CHANGED")
            if prior_pointer is None:
                os.link(next_pointer, pointer, follow_symlinks=False)
            else:
                os.replace(next_pointer, pointer)
            pointer_published = True
            if (inode(pointer.lstat()) != pointer_id or os.readlink(pointer) != target
                    or inode(pointer.stat()) != inode(info)):
                raise Hold("HOLD_POINTER_READBACK")
            actual = read_status(status)
            if actual is None or inode(actual[0]) != status_id or actual[1] != raw:
                raise Hold("HOLD_STATUS_READBACK")
            sync_directory(pointer.parent)
        except BaseException:
            if pointer_published and pointer.is_symlink() and (
                inode(pointer.lstat()) == pointer_id and os.readlink(pointer) == target
            ):
                if prior_pointer is None:
                    pointer.unlink()
                else:
                    os.replace(old_pointer, pointer)
            if status_published and status.exists() and inode(status.lstat()) == status_id:
                if old_status is None:
                    status.unlink()
                else:
                    os.replace(previous_status, status)
            sync_directory(pointer.parent)
            sync_directory(status.parent)
            raise


def main():
    mode = sys.argv[1:]
    if os.geteuid() != 0 or mode not in ([], ["--verify-current"], ["--preflight-egress"]):
        raise Hold("HOLD_COLD_OWNER_CONTEXT")
    for directory in (STATE.parent, STATE, POINTER.parent):
        require_private_directory(directory)
    status = STATE / "ENGRAM_RAM.json"
    if mode == ["--verify-current"]:
        print(json.dumps(verify_current(POINTER, status), separators=(",", ":")), flush=True)
        return
    if mode == ["--preflight-egress"]:
        require_owner_running()
        verify_cgroup_root()
        preflight_seals()
        opener = urllib.request.build_opener(HuggingFaceRedirect())
        print(json.dumps(preflight_egress(opener), separators=(",", ":")), flush=True)
        return
    require_runtime_capacity(SIZE + RESERVE)
    preflight_seals()
    lock = os.open(STATE / "engram_cold_holder.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        lock_info = os.fstat(lock)
        if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != 0 or lock_info.st_mode & 0o077:
            raise Hold("HOLD_LOCK_SCOPE")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Hold("HOLD_COLD_HOLDER_LOCKED") from exc
        previous_pointer = holder_snapshot(POINTER)
        reject_legacy_holder()
        require_status_scope(status)
        with writer_lease(STATE / "owner_maintenance.lock"):
            require_owner_running()
        opener = urllib.request.build_opener(HuggingFaceRedirect())
        fd = open_memfd()
        with os.fdopen(fd, "wb", buffering=0) as output:
            sha256 = fill_memfd(output, opener)
            if os.fstat(fd).st_size != SIZE:
                raise Hold("HOLD_RESTORED_SIZE")
            if os.pread(fd, 4, 0) != b"GGUF":
                raise Hold("HOLD_RESTORED_FORMAT")
            fcntl.fcntl(fd, ADD_SEALS, SEALS)
            publish(POINTER, status, fd, sha256, previous_pointer)
            print("NOX_ENGRAM_COLD=READY_SHA_OK", flush=True)
            threading.Event().wait()
    finally:
        os.close(lock)


if __name__ == "__main__":
    try:
        main()
    except Hold as error:
        print(error, file=sys.stderr)
        raise SystemExit(2)
    except (OSError, ValueError) as error:
        print(f"HOLD_COLD_HOLDER_{type(error).__name__}", file=sys.stderr)
        raise SystemExit(2)
