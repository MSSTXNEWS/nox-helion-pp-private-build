"""One bounded NOX self-write cycle in a *disposable* native-owned workspace.

Not a production updater. P02/model output is untrusted. The native owner
provides a scope-bound ACK, three separate grants, and an isolated test runner.
No installed application, Git checkout, permissions, or user files are edited.
"""
from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile

from .selfwrite_native_gate import require_selfwrite_ack


class FirstCycleHold(RuntimeError):
    pass


_ALLOWED = "extensions/model_report/summary.py"
_SHA40 = re.compile(r"^[a-f0-9]{40}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _target(root, relative):
    if relative != _ALLOWED:
        raise FirstCycleHold("FIRSTCYCLE_TARGET_DENIED")
    base = Path(root)
    if not base.is_dir() or base.is_symlink() or (
        hasattr(base, "is_junction") and base.is_junction()
    ):
        raise FirstCycleHold("FIRSTCYCLE_WORKSPACE_DENIED")
    base = base.resolve(strict=True)
    path = base
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink() or (
            hasattr(path, "is_junction") and path.is_junction()
        ):
            raise FirstCycleHold("FIRSTCYCLE_REPARSE_DENIED")
    if not path.is_file() or not path.resolve().is_relative_to(base):
        raise FirstCycleHold("FIRSTCYCLE_EXISTING_TARGET_REQUIRED")
    if not stat.S_ISREG(path.lstat().st_mode):
        raise FirstCycleHold("FIRSTCYCLE_NONREGULAR_DENIED")
    return path


def _atomic_replace(path: Path, content: bytes):
    fd, tmp = tempfile.mkstemp(prefix=".nox-firstcycle-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class NativeFirstCycle:
    """A testable source candidate cycle, not an installation grant."""

    def __init__(self, *, workspace, source_head, task_id, session,
                 candidate, preimage_sha256, candidate_sha256, native_ack,
                 authorize, stopped, run_isolated_test):
        if not isinstance(source_head, str) or not _SHA40.fullmatch(source_head):
            raise FirstCycleHold("FIRSTCYCLE_SOURCE_HEAD_REQUIRED")
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9_.-]{2,79}", task_id):
            raise FirstCycleHold("FIRSTCYCLE_TASK_ID_REQUIRED")
        if not isinstance(session, str) or not 0 < len(session) <= 128:
            raise FirstCycleHold("FIRSTCYCLE_SESSION_REQUIRED")
        if type(candidate) is not bytes or not 0 < len(candidate) <= 16384:
            raise FirstCycleHold("FIRSTCYCLE_CANDIDATE_BOUNDS")
        for digest in (preimage_sha256, candidate_sha256):
            if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
                raise FirstCycleHold("FIRSTCYCLE_SHA256_REQUIRED")
        if sha256(candidate) != candidate_sha256:
            raise FirstCycleHold("FIRSTCYCLE_CANDIDATE_SHA_MISMATCH")
        if not all(callable(x) for x in (authorize, stopped, run_isolated_test)):
            raise FirstCycleHold("FIRSTCYCLE_NATIVE_CALLBACKS_REQUIRED")
        try:
            ast.parse(candidate.decode("utf-8"), filename=_ALLOWED)
        except (UnicodeError, SyntaxError) as exc:
            raise FirstCycleHold("FIRSTCYCLE_CANDIDATE_SYNTAX_HOLD") from exc
        path = _target(workspace, _ALLOWED)
        original = path.read_bytes()
        if sha256(original) != preimage_sha256:
            raise FirstCycleHold("FIRSTCYCLE_PREIMAGE_MISMATCH")
        if require_selfwrite_ack(native_ack).get("status") != "READY":
            raise FirstCycleHold("FIRSTCYCLE_NATIVE_ACK_REQUIRED")
        required = {
            "source_head": source_head, "task_id": task_id,
            "session": session, "path": _ALLOWED,
            "candidate_sha256": candidate_sha256,
            "preimage_sha256": preimage_sha256,
        }
        if not isinstance(native_ack, dict) or any(
            native_ack.get(key) != value for key, value in required.items()
        ) or type(native_ack.get("epoch")) is not int:
            raise FirstCycleHold("FIRSTCYCLE_NATIVE_ACK_SCOPE_HOLD")
        self.workspace = workspace
        self.path = path
        self.original = original
        self.pre = preimage_sha256
        self.post = candidate_sha256
        self.candidate = candidate
        self.head, self.task, self.session = source_head, task_id, session
        self.authorize = authorize
        self.stopped = stopped
        self.run_isolated_test = run_isolated_test
        self.tested = False
        self.applied = False
        self.restored = False

    def _check(self, action, expected):
        if self.stopped() is not False:
            raise FirstCycleHold("FIRSTCYCLE_STOP")
        path = _target(self.workspace, _ALLOWED)
        if path != self.path or sha256(path.read_bytes()) != expected:
            raise FirstCycleHold("FIRSTCYCLE_SOURCE_DRIFT")
        scope = {
            "source_head": self.head, "task_id": self.task,
            "session": self.session, "path": _ALLOWED,
            "preimage_sha256": self.pre, "candidate_sha256": self.post,
        }
        if self.authorize(self.session, action, scope) is not True:
            raise FirstCycleHold("FIRSTCYCLE_GRANT_DENIED")
        if self.stopped() is not False or sha256(path.read_bytes()) != expected:
            raise FirstCycleHold("FIRSTCYCLE_STOP_OR_DRIFT_AFTER_GRANT")

    def test(self):
        self._check("selfbuilder.source.test", self.pre)
        if self.run_isolated_test(self.candidate) is not True:
            raise FirstCycleHold("FIRSTCYCLE_TEST_FAILED")
        self.tested = True
        return {"status": "CANDIDATE_TESTED", "sha256": self.post}

    def apply(self):
        if not self.tested or self.applied:
            raise FirstCycleHold("FIRSTCYCLE_NOT_TESTED_OR_ALREADY_APPLIED")
        self._check("selfbuilder.source.apply", self.pre)
        _atomic_replace(self.path, self.candidate)
        if sha256(self.path.read_bytes()) != self.post:
            raise FirstCycleHold("FIRSTCYCLE_APPLY_READBACK_FAILED")
        self.applied = True
        return {"status": "SANDBOX_APPLIED", "sha256": self.post,
                "installed_exe": False, "release_accepted": False}

    def rollback(self):
        if not self.applied or self.restored:
            raise FirstCycleHold("FIRSTCYCLE_ROLLBACK_NOT_ALLOWED")
        self._check("selfbuilder.source.rollback", self.post)
        _atomic_replace(self.path, self.original)
        if self.path.read_bytes() != self.original:
            raise FirstCycleHold("FIRSTCYCLE_ROLLBACK_READBACK_FAILED")
        self.restored = True
        return {"status": "SANDBOX_ROLLBACK_VERIFIED", "sha256": self.pre,
                "installed_exe": False, "release_accepted": False}
