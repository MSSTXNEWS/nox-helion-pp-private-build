"""Stage an authorized NOX Engram holder for a future Supervisor boot."""

from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass
import configparser
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat
import uuid


INSTANCE = 60509551
MODE = 0o644
HOLDER = ("root", "nox", "ops", "engram_cold_holder.py")
CONFIG = ("etc", "supervisor", "conf.d", "nox-engram-cold-holder.conf")
LEASE = ("root", "nox", "state", "owner_maintenance.lock")
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


class StageHold(RuntimeError):
    """Staging was refused or requires independent reconciliation."""


@dataclass(frozen=True)
class Payload:
    label: str
    path: tuple[str, ...]
    data: bytes
    digest: str


def require(condition, reason):
    if not condition:
        raise StageHold("HOLD_COLD_STAGE_" + reason)


def owner():
    return 0, 0


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def inode(info):
    return info.st_dev, info.st_ino


def trusted_directory(info):
    require(stat.S_ISDIR(info.st_mode) and not info.st_mode & 0o022
            and (info.st_uid, info.st_gid) == owner(), "DIRECTORY_SCOPE")


def directory(stack, root_fd, parts):
    current = root_fd
    for part in parts:
        current = os.open(part, DIR_FLAGS, dir_fd=current)
        stack.callback(os.close, current)
        trusted_directory(os.fstat(current))
    return current


def assert_directory(root_fd, parts, expected):
    with ExitStack() as stack:
        current = directory(stack, root_fd, parts)
        require(inode(os.fstat(current)) == inode(os.fstat(expected)),
                "DESTINATION_DIRECTORY_CHANGED")


def path_stat(parent, name):
    try:
        return os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return None


def exact_file(parent, name, payload):
    current = path_stat(parent, name)
    if current is None:
        return None
    require(stat.S_ISREG(current.st_mode) and stat.S_IMODE(current.st_mode) == MODE
            and (current.st_uid, current.st_gid) == owner() and current.st_nlink == 1
            and current.st_size == len(payload.data), "DESTINATION_METADATA")
    fd = os.open(name, FILE_FLAGS, dir_fd=parent)
    with os.fdopen(fd, "rb") as handle:
        opened = os.fstat(handle.fileno())
        require(stamp(opened) == stamp(current), "DESTINATION_CHANGED")
        raw = handle.read(len(payload.data) + 1)
        after = os.fstat(handle.fileno())
    final = path_stat(parent, name)
    require(final is not None and stamp(final) == stamp(after) == stamp(opened),
            "DESTINATION_CHANGED")
    require(raw == payload.data and hashlib.sha256(raw).hexdigest() == payload.digest,
            "DESTINATION_CONTENT")
    return stamp(final)


def verify_payloads(holder, holder_sha256, config, config_sha256):
    payloads = (
        Payload("holder", HOLDER, holder, holder_sha256),
        Payload("config", CONFIG, config, config_sha256),
    )
    for payload, max_bytes in zip(payloads, (128 * 1024, 8192), strict=True):
        require(isinstance(payload.data, bytes) and 0 < len(payload.data) <= max_bytes
                and isinstance(payload.digest, str) and
                re.fullmatch(r"[a-f0-9]{64}", payload.digest) and
                hashlib.sha256(payload.data).hexdigest() == payload.digest, "PAYLOAD_SHA")
    try:
        compile(holder, HOLDER[-1], "exec")
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.read_string(config.decode("utf-8"))
        section = "program:nox-engram-cold-holder"
        require(parser.sections() == [section] and not parser.defaults(), "CONFIG_SCOPE")
        config_contract = {
            "command": "/usr/bin/python3 -I -B /root/nox/ops/engram_cold_holder.py",
            "directory": "/root/nox", "user": "root", "autostart": "true",
            "autorestart": "false", "startsecs": "1", "startretries": "0",
            "priority": "10", "stopsignal": "TERM", "stopwaitsecs": "30",
            "stopasgroup": "false", "killasgroup": "false", "redirect_stderr": "true",
            "stdout_logfile": "/dev/stdout", "stdout_logfile_maxbytes": "0",
        }
        require(dict(parser[section]) == config_contract, "CONFIG_CONTRACT")
    except (SyntaxError, UnicodeError, configparser.Error) as error:
        raise StageHold("HOLD_COLD_STAGE_SOURCE_SYNTAX") from error
    return payloads


def verify_preflight(source_sha, request_id, preflight, payloads):
    require(isinstance(source_sha, str) and re.fullmatch(r"[a-f0-9]{40}", source_sha)
            and isinstance(request_id, str) and re.fullmatch(r"[0-9]{1,20}", request_id),
            "OWNER_CONTEXT")
    require(isinstance(preflight, Mapping) and
            preflight.get("schema") == "NOX_COLD_STAGE_PREFLIGHT_V1" and
            preflight.get("instance_id") == INSTANCE and preflight.get("instance_bound") is True
            and preflight.get("source_sha") == source_sha and preflight.get("request_id") == request_id
            and preflight.get("stage_eligible") is True and preflight.get("reboot_verified") is False,
            "PREFLIGHT_CONTEXT")
    checks = preflight.get("checks")
    pair = checks.get("staged_pair") if isinstance(checks, Mapping) else None
    require(isinstance(pair, Mapping), "PREFLIGHT_FILES")
    states = {}
    for payload in payloads:
        row = pair.get(payload.label)
        require(isinstance(row, Mapping) and row.get("state") in ("ABSENT", "MATCH"),
                "PREFLIGHT_FILES")
        states[payload.label] = row["state"]
        if row["state"] == "MATCH":
            require(row.get("sha256") == payload.digest and
                    row.get("size_bytes") == len(payload.data), "PREFLIGHT_PAYLOAD_SHA")
    return states


def verify_lease(parent, fd):
    data = os.fstat(fd)
    current = path_stat(parent, LEASE[-1])
    require(current is not None and stamp(current) == stamp(data)
            and stat.S_ISREG(data.st_mode) and data.st_nlink == 1
            and not data.st_mode & 0o022 and (data.st_uid, data.st_gid) == owner(),
            "OWNER_LEASE_CHANGED")


def unlink_own_inode(parent, name, expected):
    current = path_stat(parent, name)
    if current is None:
        return True
    if not stat.S_ISREG(current.st_mode) or inode(current) != expected:
        return False
    os.unlink(name, dir_fd=parent)
    os.fsync(parent)
    return True


def publish(parent, payload, created, recheck):
    name = payload.path[-1]
    temp = ".nox-engram-stage-" + uuid.uuid4().hex
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(temp, flags, 0o600, dir_fd=parent)
    with os.fdopen(fd, "wb") as out:
        ident = inode(os.fstat(out.fileno()))
        try:
            require(out.write(payload.data) == len(payload.data), "TEMP_WRITE")
            out.flush()
            os.fchmod(out.fileno(), MODE)
            os.fsync(out.fileno())
            recheck()
            temp_stat = path_stat(parent, temp)
            require(temp_stat is not None and inode(temp_stat) == ident
                    and stamp(temp_stat) == stamp(os.fstat(out.fileno())),
                    "TEMP_CHANGED")
            os.link(temp, name, src_dir_fd=parent, dst_dir_fd=parent,
                    follow_symlinks=False)
            created.append((parent, name, ident))
            # Unlink the staging alias before checking the live file's link count.
            require(unlink_own_inode(parent, temp, ident), "TEMP_CHANGED")
            matched = exact_file(parent, name, payload)
            require(matched is not None and matched[:2] == ident, "PUBLISH_READBACK")
            return matched
        finally:
            require(unlink_own_inode(parent, temp, ident), "TEMP_CLEANUP_SCOPE")


def stage_cold_holder(*, source_sha, request_id, preflight, holder, holder_sha256,
                      config, config_sha256, root=Path("/")):
    """Create or attest the two files after a separate authenticated preflight.

    The caller owns provider authentication. The owner maintenance lock and
    root-owned parent directories serialize cooperating writers. The holder is
    durable before the configuration becomes visible. No daemon reload occurs.
    """
    require((os.geteuid(), os.getegid()) == owner(), "ROOT_REQUIRED")
    payloads = verify_payloads(holder, holder_sha256, config, config_sha256)
    states = verify_preflight(source_sha, request_id, preflight, payloads)
    with ExitStack() as stack:
        root_fd = os.open(root, DIR_FLAGS)
        stack.callback(os.close, root_fd)
        trusted_directory(os.fstat(root_fd))
        lease_dir = directory(stack, root_fd, LEASE[:-1])
        lock_fd = os.open(LEASE[-1], FILE_FLAGS, dir_fd=lease_dir)
        stack.callback(os.close, lock_fd)
        verify_lease(lease_dir, lock_fd)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise StageHold("HOLD_COLD_STAGE_OWNER_LEASE_BUSY") from error
        verify_lease(lease_dir, lock_fd)
        parents = {payload.label: directory(stack, root_fd, payload.path[:-1])
                   for payload in payloads}
        known = {}
        for payload in payloads:
            current = exact_file(parents[payload.label], payload.path[-1], payload)
            require((current is None) == (states[payload.label] == "ABSENT"),
                    "PREFLIGHT_DESTINATION_CHANGED")
            known[payload.label] = current

        def recheck():
            assert_directory(root_fd, LEASE[:-1], lease_dir)
            verify_lease(lease_dir, lock_fd)
            for payload in payloads:
                parent = parents[payload.label]
                assert_directory(root_fd, payload.path[:-1], parent)
                require(exact_file(parent, payload.path[-1], payload) == known[payload.label],
                        "DESTINATION_CAS")

        created = []
        try:
            recheck()
            for payload in payloads:
                if known[payload.label] is None:
                    known[payload.label] = publish(parents[payload.label], payload,
                                                   created, recheck)
            recheck()
        except BaseException as error:
            clean = True
            for parent, name, ident in reversed(created):
                try:
                    clean = unlink_own_inode(parent, name, ident) and clean
                except OSError:
                    clean = False
            if not clean:
                raise StageHold("HOLD_COLD_STAGE_ROLLBACK_UNCERTAIN") from error
            raise
        return {
            "schema": "NOX_COLD_STAGE_RECEIPT_V1",
            "instance_id": INSTANCE, "source_sha": source_sha,
            "request_id": request_id, "stage_verified": True,
            "reboot_verified": False, "supervisor_touched": False,
            "files": {
                payload.label: {"path": "/" + "/".join(payload.path),
                                "sha256": payload.digest, "size_bytes": len(payload.data),
                                "disposition": ("CREATED" if states[payload.label] == "ABSENT"
                                                else "EXACT_EXISTING")}
                for payload in payloads
            },
        }
