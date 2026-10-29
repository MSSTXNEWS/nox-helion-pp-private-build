"""E06 owner scope: apply ONE additive WPF -> Python diagnostic hook to pinned R08.
Stage only. Never writes originals, model files, user data or a second router.
"""
from __future__ import annotations
import hashlib, json, difflib, sys, stat, os, tempfile
from pathlib import Path

RUN_ID = "NOX-V16-E06-EXPRESS-ONEHOST-20261028-R10"
ORIGINAL_BRIDGE_SHA256 = "ee978b13a7f1058b1a509a506feef495efe440f410ab63103088fefa08e1d86f"
ORIGINAL_EXE_SHA256 = "4e488372cf3f6410d268a7ef72b3e4b359a7a3e6642c7a16ac2e6f7eb06fc5f3"
ANCHOR = 'case "models.preflight":\n                    await RunDiagnosticsAsync(requestId);\n                    return;'
REPLACEMENT = 'case "models.preflight":\n                    await RunDiagnosticsAsync(requestId);\n                    await ReportOriginalPythonDiagnosticAsync(requestId, route);\n                    return;'

def digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def trusted_path(value):
    path = Path(value).absolute()
    for node in (path, *path.parents):
        try:
            info = node.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or (getattr(info, "st_file_attributes", 0) &
                                         getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise SystemExit("OWNER6_REPARSE_PATH_HOLD")
    return path


def _identity(path):
    info = path.lstat()
    return (info.st_dev, info.st_ino)


def _owned(path, identity, content):
    try:
        trusted_path(path)
        return _identity(path) == identity and path.read_bytes() == content
    except (OSError, SystemExit):
        return False


def _prepare(path, content):
    """Prepare complete bytes beside their destination; never truncate a live file."""
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".e06-", dir=path.parent)
    temporary = Path(name)
    # mkstemp creates an owned inode, not an owned pathname forever. A foreign
    # replacement must never be unlinked merely because readback failed.
    created_identity = None
    try:
        with os.fdopen(fd, "wb") as target:
            info = os.fstat(target.fileno())
            created_identity = (info.st_dev, info.st_ino)
            if target.write(content) != len(content):
                raise OSError("OWNER6_SHORT_WRITE_HOLD")
            target.flush()
            os.fsync(target.fileno())
        if (_identity(temporary) != created_identity or
                temporary.read_bytes() != content or
                _identity(temporary) != created_identity):
            raise OSError("OWNER6_TEMP_READBACK_HOLD")
        return temporary
    except BaseException:
        if created_identity is not None:
            try:
                if _identity(temporary) == created_identity:
                    temporary.unlink()
            except FileNotFoundError:
                pass
        raise

def commit_stage(original, before, patched, dest, extra, out, receipt_bytes):
    """Exception-safe staging under the released owner lease.

    The lock excludes cooperating stage_onehost writers. OS rename is not a
    SHA-CAS against unrelated writers; detected foreign edits are never rolled
    back over. A crash leaves the lock/backups for inspection rather than guessing
    that an incomplete transaction succeeded.
    """
    lock = trusted_path(original.parent / ".e06-stage.lock")
    lock_bytes = (str(os.getpid()) + "\n").encode("ascii")
    # The exclusive lock itself is a side effect.  Acquisition errors must
    # release our *own* new inode even when write/flush/fsync is incomplete.
    lock_identity = None
    try:
        with lock.open("xb") as guard:
            info = os.fstat(guard.fileno())
            lock_identity = (info.st_dev, info.st_ino)
            if guard.write(lock_bytes) != len(lock_bytes):
                raise OSError("OWNER6_STAGE_LOCK_SHORT_WRITE_HOLD")
            guard.flush()
            os.fsync(guard.fileno())
    except BaseException:
        if lock_identity is not None:
            try:
                # Never unlink a foreign replacement lock, or an unknown inode.
                if _identity(lock) == lock_identity:
                    lock.unlink()
            except OSError:
                pass
        raise
    def require_lock_owned():
        if not _owned(lock, lock_identity, lock_bytes):
            raise RuntimeError("OWNER6_STAGE_LOCK_LOST_HOLD")
    prepared = []
    prepared_ids = {}
    published = []
    installed_identity = None
    before_identity = None
    keep_recovery = False
    try:
        if original.read_bytes() != before:
            raise RuntimeError("OWNER6_WPF_PREIMAGE_SHA_HOLD")
        before_identity = _identity(original)
        if dest.exists() or out.exists():
            raise RuntimeError("OWNER6_OUTPUT_CONFLICT_HOLD")
        for path, raw in ((original, patched), (dest, extra), (out, receipt_bytes),
                          (original, before)):
            temporary = _prepare(trusted_path(path), raw)
            prepared.append(temporary)
            prepared_ids[temporary] = _identity(temporary)
        backup = prepared[3]
        # Even the first published addon needs the cooperative owner lease.
        require_lock_owned()
        # A prepared pathname may change after fsync/readback; do not publish
        # substituted bytes under a valid stage owner lease.
        if (not _owned(prepared[0], prepared_ids[prepared[0]], patched) or
                not _owned(prepared[1], prepared_ids[prepared[1]], extra) or
                not _owned(prepared[2], prepared_ids[prepared[2]], receipt_bytes) or
                not _owned(backup, prepared_ids[backup], before)):
            raise RuntimeError("OWNER6_PREPARED_FILES_CHANGED_HOLD")
        # Hard-link publication is atomic and refuses an existing destination.
        os.link(prepared[1], trusted_path(dest))
        # Use the identity pinned during preparation: metadata reads here can fail
        # AFTER a successful link, before rollback knows this path is ours.
        published.append((dest, prepared_ids[prepared[1]], extra))
        if not _owned(original, before_identity, before):
            raise RuntimeError("OWNER6_WPF_PREIMAGE_SHA_HOLD")
        require_lock_owned()
        installed_identity = _identity(prepared[0])
        os.replace(prepared[0], trusted_path(original))
        if not _owned(original, installed_identity, patched) or dest.read_bytes() != extra:
            raise RuntimeError("OWNER6_SOURCE_READBACK_HOLD")
        # Receipt is the final commit marker; refuse a lost/foreign owner lease.
        require_lock_owned()
        os.link(prepared[2], trusted_path(out))
        # A published receipt must enter the rollback ledger without a fallible
        # post-link lstat; earlier preparation already pinned this inode.
        published.append((out, prepared_ids[prepared[2]], receipt_bytes))
        if any(not _owned(path, identity, raw) for path, identity, raw in published):
            raise RuntimeError("OWNER6_RECEIPT_READBACK_HOLD")
        require_lock_owned()
    except BaseException as cause:
        # A foreign takeover invalidates even best-effort rollback authority.
        if not _owned(lock, lock_identity, lock_bytes):
            keep_recovery = True
            raise RuntimeError("OWNER6_ROLLBACK_OWNER_LOCK_LOST_HOLD") from cause
        conflicts = []
        # Source replacement may fail before rename: distinguish original preimage.
        if installed_identity is not None:
            if _owned(original, installed_identity, patched):
                try:
                    if not _owned(backup, prepared_ids[backup], before):
                        raise RuntimeError("OWNER6_ROLLBACK_BACKUP_CHANGED_HOLD")
                    os.replace(backup, trusted_path(original))
                except BaseException:
                    conflicts.append(str(original))
            elif not _owned(original, before_identity, before):
                conflicts.append(str(original))
        for path, identity, raw in reversed(published):
            if _owned(path, identity, raw):
                try:
                    path.unlink()
                except BaseException:
                    conflicts.append(str(path))
            else:
                conflicts.append(str(path))
        if conflicts:
            keep_recovery = True
            raise RuntimeError("OWNER6_ROLLBACK_CONFLICT_HOLD:" +
                               ",".join(conflicts) + "; recovery lock=" + str(lock)) from cause
        raise
    finally:
        if not keep_recovery:
            try:
                for temporary in prepared:
                    # If _identity failed before the pin was recorded, never
                    # unlink a pathname whose inode we cannot prove we own.
                    identity = prepared_ids.get(temporary)
                    if identity is None:
                        continue
                    try:
                        if _identity(temporary) == identity:
                            temporary.unlink()
                    except FileNotFoundError:
                        pass
            finally:
                # A temporary cleanup error must not orphan our stage lease.
                # Preserve the original error but always attempt owner-only
                # lock release after successful rollback or source staging.
                if _owned(lock, lock_identity, lock_bytes):
                    lock.unlink()


def main():
    if len(sys.argv) != 4:
        raise SystemExit("USAGE: stage_onehost.py STAGED_R11 E06_ADDON_CS PYTHON_EXE")
    stage = trusted_path(sys.argv[1])
    e06 = trusted_path(sys.argv[2])
    python_exe = trusted_path(sys.argv[3])
    original = trusted_path(stage / "Integration" / "Pack01HostBridge.cs")
    if not original.is_file() or original.is_symlink():
        raise SystemExit("OWNER6_WPF_SOURCE_MISSING")
    before = original.read_bytes()
    if digest(before) != ORIGINAL_BRIDGE_SHA256:
        raise SystemExit("OWNER6_WPF_PREIMAGE_SHA_HOLD")
    old = before.decode("utf-8-sig")
    if old.count(ANCHOR) != 1:
        raise SystemExit("OWNER6_WPF_ROUTE_PREIMAGE_DRIFT")
    new_text = old.replace(ANCHOR, REPLACEMENT)
    patched = new_text.encode("utf-8")
    if not e06.is_file() or e06.is_symlink():
        raise SystemExit("OWNER6_NEW_PARTIAL_MISSING")
    extra = e06.read_bytes()
    if b"ReportOriginalPythonDiagnosticAsync" not in extra:
        raise SystemExit("OWNER6_PARTIAL_FUNCTION_MISSING")
    if not python_exe.is_file() or python_exe.is_symlink() or digest(python_exe.read_bytes()) != ORIGINAL_EXE_SHA256:
        raise SystemExit("ORIGINAL_PYTHON_EXE_SHA_HOLD")
    dest = trusted_path(stage / "Integration" / "OriginalPythonDiagnosticBridge.cs")
    out = trusted_path(stage.parent / "E06_R10_SOURCE_RECEIPT.json")
    if out.exists():
        raise SystemExit("OWNER_CONFLICT_EXISTING_RECEIPT")
    if dest.exists():
        raise SystemExit("OWNER_CONFLICT_EXISTING_ADAPTER")
    patch = "".join(difflib.unified_diff(old.splitlines(True), new_text.splitlines(True),
                                         fromfile="Pack01HostBridge.cs.pre", tofile="Pack01HostBridge.cs.post"))
    records = [
        {"path": "R11/Integration/Pack01HostBridge.cs", "owner": 6,
         "pre_sha256": digest(before), "post_sha256": digest(patched),
         "patch_sha256": digest(patch.encode("utf-8"))},
        {"path": "R11/Integration/OriginalPythonDiagnosticBridge.cs", "owner": 6,
         "pre_sha256": None, "post_sha256": digest(extra),
         "patch_sha256": digest(extra)}
    ]
    receipt = {"schema": "NOX-E06-ONEHOST-R10-SOURCE-RECEIPT",
               "run_id": RUN_ID, "original_python_binary_sha256": ORIGINAL_EXE_SHA256,
               "original_archive_sha256": "ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a",
               "files": records, "owner3_compiler_overlay": "REQUIRES_OWNER_APPROVAL",
               "release_accepted": False, "windows_runtime_accepted": False}
    receipt_bytes = (json.dumps(receipt, ensure_ascii=False, indent=2)+"\n").encode("utf-8")
    commit_stage(original, before, patched, dest, extra, out, receipt_bytes)
    print("E06_R10_STAGED_ONEHOST_SHA_PIN_PASS", digest(patched), digest(extra))
if __name__ == "__main__":
    main()
