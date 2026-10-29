"""NOX V16 P01 source-only adapter to the *existing* restic binary (BSD-2-Clause).

Only a trusted Windows owner supplies the pinned binary, paths, password-file,
permission callback, STOP callback and native snapshot selection. No web/user
field can select a path or command. Not yet installed, Host50-bound or E07-accepted.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Callable

HASH = re.compile(r"[a-f0-9]{64}\Z", re.I)
SNAPSHOT = re.compile(r"[a-f0-9]{8,64}\Z", re.I)
MAX_OUTPUT = 2 * 1024 * 1024

class BackupHold(RuntimeError):
    pass

class BackupDenied(PermissionError):
    pass

@dataclass(frozen=True)
class TrustedResticProfile:
    binary: Path
    binary_sha256: str
    repository: Path
    password_file: Path
    sources: tuple[Path, ...]
    empty_restore_target: Path


def _plain(path: Path, *, file: bool = False) -> Path:
    """Conservative lexical link check; Windows junction/race needs native QA."""
    if not isinstance(path, Path) or not path.is_absolute():
        raise BackupHold("NATIVE_ABSOLUTE_PATH_REQUIRED")
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise BackupHold("NATIVE_SYMLINK_REJECTED")
    if not (path.is_file() if file else path.is_dir()):
        raise BackupHold("NATIVE_SOURCE_NOT_PRESENT")
    return path.resolve(strict=True)


def _run_process(argv: list[str], *, stop: Callable[[], bool]) -> tuple[int, str]:
    # Reuse the verified binary, never shell=True or public network endpoints.
    with tempfile.TemporaryFile(mode="w+b") as stdout, tempfile.TemporaryFile(mode="w+b") as stderr:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stdout,
                                stderr=stderr, shell=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + 3600
        try:
            while proc.poll() is None:
                if stop() is True:
                    raise BackupHold("NATIVE_STOP_REQUESTED")
                if time.monotonic() > deadline:
                    raise BackupHold("RESTIC_TIMEOUT")
                if os.fstat(stdout.fileno()).st_size > MAX_OUTPUT or os.fstat(stderr.fileno()).st_size > MAX_OUTPUT:
                    raise BackupHold("RESTIC_OUTPUT_LIMIT")
                time.sleep(0.05)
            if stop() is True:
                raise BackupHold("NATIVE_STOP_REQUESTED")
            if os.fstat(stdout.fileno()).st_size > MAX_OUTPUT or os.fstat(stderr.fileno()).st_size > MAX_OUTPUT:
                raise BackupHold("RESTIC_OUTPUT_LIMIT")
            stdout.seek(0)
            return proc.returncode, stdout.read(MAX_OUTPUT + 1).decode("utf-8", errors="replace")
        except BaseException:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            raise


class P01ResticBackupPort:
    """Source candidate for one existing PACK01 owner=1 route. No auto-bind."""
    def __init__(self, profile: TrustedResticProfile, *,
                 native_permission: Callable[[object, str], bool],
                 native_snapshot: Callable[[object], str],
                 native_stop: Callable[[], bool],
                 runner: Callable | None = None):
        if (not isinstance(profile, TrustedResticProfile) or
            not all(callable(c) for c in (native_permission, native_snapshot, native_stop))):
            raise BackupHold("TRUSTED_NATIVE_OWNER_CALLBACKS_REQUIRED")
        self.profile = profile
        self.permission, self.snapshot, self.stop = native_permission, native_snapshot, native_stop
        self.runner = runner or _run_process

    def _check(self) -> tuple[Path, Path, Path, tuple[Path, ...], Path]:
        p = self.profile
        if type(p.binary_sha256) is not str or not HASH.fullmatch(p.binary_sha256):
            raise BackupHold("SIGNED_RESTIC_SHA256_REQUIRED")
        binary = _plain(p.binary, file=True)
        if sha256(binary.read_bytes()).hexdigest() != p.binary_sha256.lower():
            raise BackupHold("RESTIC_BINARY_HASH_DRIFT")
        repository = _plain(p.repository)
        secret = _plain(p.password_file, file=True)
        target = _plain(p.empty_restore_target)
        if (type(p.sources) is not tuple or not p.sources or len(p.sources) > 16):
            raise BackupHold("NATIVE_SOURCE_SELECTION_REQUIRED")
        sources = tuple(_plain(src) for src in p.sources)
        if target in sources or any(target == repository or src == repository for src in sources):
            raise BackupHold("BACKUP_SOURCE_DESTINATION_COLLISION")
        return binary, repository, secret, sources, target

    def available(self) -> bool:
        try:
            self._check()
            return self.stop() is False
        except (BackupHold, OSError, ValueError):
            return False

    def __call__(self, native_session: object, payload: dict) -> dict:
        if type(payload) is not dict or set(payload) != {"operation"} or payload["operation"] not in ("backup", "restore"):
            raise BackupDenied("NATIVE_FIXED_BACKUP_OPERATION_ONLY")
        operation = payload["operation"]
        if self.stop() is not False:
            raise BackupHold("NATIVE_STOP_REQUESTED")
        # This is IN ADDITION to PACK01 host ACL and per-action dangerous consent.
        if self.permission(native_session, operation) is not True:
            raise BackupDenied("NATIVE_BACKUP_OR_RESTORE_CONSENT_REQUIRED")
        binary, repository, secret, sources, target = self._check()
        argv = [str(binary), "--repo", str(repository), "--password-file", str(secret)]
        if operation == "backup":
            argv += ["backup", "--json", "--", *(str(src) for src in sources)]
        else:
            snapshot = self.snapshot(native_session)
            if type(snapshot) is not str or not SNAPSHOT.fullmatch(snapshot):
                raise BackupDenied("NATIVE_APPROVED_SNAPSHOT_ID_REQUIRED")
            if any(target.iterdir()):
                raise BackupHold("RESTORE_TARGET_MUST_BE_EMPTY")
            argv += ["restore", snapshot, "--target", str(target)]
        if self.stop() is not False or self.permission(native_session, operation) is not True:
            raise BackupDenied("NATIVE_CONSENT_REVOKED")
        rc, output = self.runner(argv, stop=self.stop)
        if self.stop() is not False:
            raise BackupHold("NATIVE_STOP_REQUESTED")
        if rc != 0:
            raise BackupHold("RESTIC_NONZERO_EXIT")
        if operation == "restore":
            return {"status": "RESTORE_EXIT_ZERO_NEEDS_NATIVE_FILE_VERIFICATION", "accepted": False}
        ids = []
        for line in output.splitlines():
            try:
                event = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(event, dict) and event.get("message_type") == "summary" and isinstance(event.get("snapshot_id"), str):
                if SNAPSHOT.fullmatch(event["snapshot_id"]):
                    ids.append(event["snapshot_id"])
        if len(ids) != 1:
            raise BackupHold("RESTIC_CONFIRMED_SNAPSHOT_RECEIPT_REQUIRED")
        return {"status": "RESTIC_SNAPSHOT_CREATED", "snapshot_id": ids[0], "accepted": False}
