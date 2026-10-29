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
    try:
        with os.fdopen(fd, "wb") as target:
            if target.write(content) != len(content):
                raise OSError("OWNER6_SHORT_WRITE_HOLD")
            target.flush()
            os.fsync(target.fileno())
        if temporary.read_bytes() != content:
            raise OSError("OWNER6_TEMP_READBACK_HOLD")
        return temporary
    except BaseException:
        temporary.unlink(missing_ok=True)
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
    with lock.open("xb") as guard:
        guard.write(lock_bytes)
        guard.flush()
        os.fsync(guard.fileno())
    lock_identity = _identity(lock)
    def require_lock_owned():
        if not _owned(lock, lock_identity, lock_bytes):
            raise RuntimeError("OWNER6_STAGE_LOCK_LOST_HOLD")
    prepared = []
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
            prepared.append(_prepare(trusted_path(path), raw))
        backup = prepared[3]
        # Hard-link publication is atomic and refuses an existing destination.
        os.link(prepared[1], trusted_path(dest))
        published.append((dest, _identity(prepared[1]), extra))
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
        published.append((out, _identity(prepared[2]), receipt_bytes))
        if any(not _owned(path, identity, raw) for path, identity, raw in published):
            raise RuntimeError("OWNER6_RECEIPT_READBACK_HOLD")
        require_lock_owned()
    except BaseException as cause:
        conflicts = []
        # Source replacement may fail before rename: distinguish original preimage.
        if installed_identity is not None:
            if _owned(original, installed_identity, patched):
                try:
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
            for temporary in prepared:
                temporary.unlink(missing_ok=True)
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
