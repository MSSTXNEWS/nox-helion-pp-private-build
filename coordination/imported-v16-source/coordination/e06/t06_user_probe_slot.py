"""Read-only physical NSIS slot admission with ONE exact, CI-owned user-data probe.

Original publisher staging verification remains unchanged and strict. During
UPDATE/ROLLBACK an intentionally preserved unmanaged file makes that staging
verifier reject a valid installed backup. This verifier admits only the frozen
probe, after independently hashing EVERY manifest-owned file and checking all
original NSIS metadata and the complete directory tree. Not an E07 receipt.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat


def owned_file_handle_matches_path(path_stat, fd_stat):
    """Same NTFS file from pathname vs open descriptor, independent of API timestamp presentation.

    SHA-256 and full in-API pre/post timestamp+identity checks remain mandatory.
    A different file, hard link, or size is NEVER accepted as the same owner.
    """
    return (path_stat.st_ino != 0 and fd_stat.st_ino != 0 and
            path_stat.st_nlink == 1 and fd_stat.st_nlink == 1 and
            (path_stat.st_dev, path_stat.st_ino, path_stat.st_size) ==
            (fd_stat.st_dev, fd_stat.st_ino, fd_stat.st_size))


def unchanged_probe_snapshot(before, after):
    """Within the SAME stat API, require stable identity, size, links and timestamps.

    Never compare pathname and file-handle timestamps to each other: Windows
    exposes different timestamp presentations across those APIs.
    """
    return ((before.st_dev, before.st_ino, before.st_size, before.st_nlink,
             before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_nlink,
             after.st_mtime_ns, after.st_ctime_ns) and
            before.st_ino != 0 and before.st_nlink == 1)


def read_stable_manifest_bytes(path: Path) -> bytes:
    """Read one physical manifest without pathname/handle replacement races.

    A manifest can be modified after a safe(path) check, even if the decoded
    JSON looks valid. Require same NTFS identity across lstat/open and stable
    within-API metadata before, during and after the bounded read. The caller
    still enforces no-reparse ancestors before and after.
    """
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or
            before.st_ino == 0 or not 2 <= before.st_size <= 4 * 1024 * 1024):
        raise RuntimeError("T06_EXACT_PROBE_SLOT_MANIFEST_IDENTITY_HOLD")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if not owned_file_handle_matches_path(before, opened):
            raise RuntimeError("T06_EXACT_PROBE_SLOT_MANIFEST_IDENTITY_HOLD")
        raw = stream.read(4 * 1024 * 1024 + 1)
        if (len(raw) != before.st_size or
                not unchanged_probe_snapshot(opened, os.fstat(stream.fileno()))):
            raise RuntimeError("T06_EXACT_PROBE_SLOT_MANIFEST_RACE_HOLD")
    if not unchanged_probe_snapshot(before, path.lstat()):
        raise RuntimeError("T06_EXACT_PROBE_SLOT_MANIFEST_RACE_HOLD")
    return raw



def read_frozen_manifest_bytes(path: Path) -> tuple[bytes, os.stat_result]:
    """Bind verified manifest bytes to the same pre-read pathname identity.

    The caller compares the returned snapshot again after checking the whole
    installed tree. A same-inode write in the gap between the descriptor read
    and the former post-read snapshot must never acquire diagnostic PASS.
    """
    before = path.lstat()
    raw = read_stable_manifest_bytes(path)
    after = path.lstat()
    if not unchanged_probe_snapshot(before, after):
        raise RuntimeError("T06_EXACT_PROBE_SLOT_MANIFEST_RACE_HOLD")
    return raw, before



def verify_locked_nsis_metadata(path: Path, safe, *, marker: bool) -> bool:
    """Read owned R11 metadata from its actual single-link file handle.

    A safe(path) preflight is not a lease: bind the bytes to the lstat'ed
    object and reject path swaps or in-place edits before diagnostic PASS.
    This does not license a release or alter any real NSIS operation.
    """
    expected = b"NOXHELION.P01 V16\r\n"
    try:
        if not safe(path):
            return False
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_ino == 0:
            return False
        if marker:
            if before.st_size != len(expected):
                return False
        elif not 1024 <= before.st_size <= 104857600:
            return False
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if not owned_file_handle_matches_path(before, opened):
                return False
            if marker:
                if stream.read(len(expected) + 1) != expected:
                    return False
            elif stream.read(2) != b"MZ":
                return False
            if not unchanged_probe_snapshot(opened, os.fstat(stream.fileno())):
                return False
        return safe(path) and unchanged_probe_snapshot(before, path.lstat())
    except (OSError, ValueError):
        return False


def verify_exact_probe_slot(root: Path, probe_name: str, probe_bytes: bytes,
                            frozen_inode: tuple[int, int], base: Path) -> dict:
    def hold(reason: str) -> None:
        raise RuntimeError("T06_EXACT_PROBE_SLOT_" + reason + "_HOLD")

    def safe(p: Path, directory: bool = False) -> bool:
        try:
            if not p.is_relative_to(base) or p.is_symlink() or getattr(p, "is_junction", lambda: False)():
                return False
            for a in (p, *p.parents):
                if not a.exists() or a.is_symlink() or getattr(a, "is_junction", lambda: False)():
                    return False
                s = a.lstat()
                if getattr(s, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                    return False
                if a != p and not stat.S_ISDIR(s.st_mode):
                    return False
            s = p.lstat()
            return (stat.S_ISDIR(s.st_mode) if directory else
                    stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_ino != 0)
        except (OSError, ValueError):
            return False

    if not isinstance(root, Path) or not isinstance(base, Path) or not safe(root, True):
        hold("ROOT")
    if (type(probe_name) is not str or
            not re.fullmatch(r"nox-g4-unmanaged-[A-Za-z0-9._:-]{2,128}\.bin", probe_name) or
            type(probe_bytes) is not bytes or not probe_bytes or
            type(frozen_inode) is not tuple or len(frozen_inode) != 2):
        hold("PROBE_INPUT")
    marker = root / probe_name
    if not safe(marker):
        hold("PROBE_PATH")
    before = marker.lstat()
    if (before.st_nlink != 1 or before.st_ino == 0 or
            (before.st_dev, before.st_ino) != frozen_inode or
            before.st_size != len(probe_bytes)):
        hold("PROBE_IDENTITY")
    with marker.open("rb") as fp:
        opened = os.fstat(fp.fileno())
        if ((opened.st_dev, opened.st_ino) != frozen_inode or
                opened.st_nlink != 1 or opened.st_size != len(probe_bytes) or
                fp.read(len(probe_bytes) + 1) != probe_bytes):
            hold("PROBE_BYTES")
        # A concurrent in-place edit can retain the same NTFS file ID.
        # Check the open handle itself before accepting the preserved bytes.
        if not unchanged_probe_snapshot(opened, os.fstat(fp.fileno())):
            hold("PROBE_RACE")
    if not safe(marker) or not unchanged_probe_snapshot(before, marker.lstat()):
        hold("PROBE_RACE")
    manifest = root / "payload.sha256.json"
    if not safe(manifest):
        hold("MANIFEST")
    # Freeze the original backing file, not just its pathname. A concurrent
    # same-length writer must never turn an unchecked manifest into a PASS.
    try:
        manifest_bytes, frozen_manifest = read_frozen_manifest_bytes(manifest)
    except (RuntimeError, OSError, ValueError) as exc:
        hold("MANIFEST_IDENTITY" if not isinstance(exc, RuntimeError) else
             ("MANIFEST_RACE" if "MANIFEST_RACE" in str(exc) else "MANIFEST_IDENTITY"))
    if not safe(manifest):
        hold("MANIFEST_RACE")
    def unique_pairs(pairs):
        output = {}
        for k, v in pairs:
            if k in output:
                raise ValueError("duplicate JSON member")
            output[k] = v
        return output
    try:
        data = json.loads(manifest_bytes.decode("utf-8-sig"), object_pairs_hook=unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NaN")))
    except (UnicodeError, ValueError):
        hold("MANIFEST_JSON")
    if (type(data) is not dict or data.get("schema") != "NOX_P01_PAYLOAD_SHA256_V1" or
            data.get("entrypoint") != "NOX.P01.Shell.exe" or
            type(data.get("runId")) is not str or
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{1,127}", data["runId"]) or
            data["runId"] == "P01-UNSET" or type(data.get("version")) is not str or
            not re.fullmatch(r"[0-9]{1,5}(\.[0-9]{1,5}){2,3}", data["version"]) or
            type(data.get("files")) is not list or not 12 <= len(data["files"]) <= 50000):
        hold("MANIFEST_SCHEMA")
    metadata = {"payload.sha256.json", "nox-p01-owned.txt", "Uninstall.exe"}
    expected = {s.casefold() for s in metadata | {probe_name}}
    # Only directories implied by the publisher's immutable manifest exist in
    # a valid NSIS backup. Empty foreign directories are NOT harmless evidence.
    expected_directories = set()
    reserved = re.compile(r"(?i)^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$")
    for row in data["files"]:
        if type(row) is not dict:
            hold("ROW")
        rel = row.get("path")
        digest = row.get("sha256")
        size = row.get("bytes")
        if (type(rel) is not str or type(digest) is not str or
                not re.fullmatch(r"[a-fA-F0-9]{64}", digest) or
                type(size) is not int or not 0 <= size <= 2**63 - 1 or
                not rel or any(c in rel for c in '\\:*?"<>|') or rel.startswith("/") or
                any(not part or part in (".", "..") or part[-1] in " ." or reserved.fullmatch(part)
                    for part in rel.split("/")) or rel.casefold() in expected):
            hold("MANIFEST_PATH")
        parts = rel.split("/")
        for count in range(1, len(parts)):
            expected_directories.add("/".join(parts[:count]).casefold())
        path = root.joinpath(*parts)
        if not safe(path):
            hold("OWNED_SIZE_OR_PATH")
        before_owned = path.lstat()
        if before_owned.st_size != size:
            hold("OWNED_SIZE_OR_PATH")
        # Open the *same file* we lstat'ed, rather than hashing an untrusted
        # replacement reached by a second path lookup. A hard link to unrelated
        # user data is never an owned file, even if its bytes match the manifest.
        with path.open("rb") as fp:
            opened_owned = os.fstat(fp.fileno())
            # Windows path lstat vs fd fstat can present different timestamp
            # precision. Their *file identity* must still be identical, and
            # SHA-256 plus each API's own before/after metadata remain strict.
            if not owned_file_handle_matches_path(before_owned, opened_owned):
                hold("OWNED_IDENTITY")
            h = hashlib.sha256()
            while chunk := fp.read(1024 * 1024):
                h.update(chunk)
            after_owned = os.fstat(fp.fileno())
            # Compare handle to the same open handle, including both times:
            # this is an actual concurrent-write check, not a path API artifact.
            if (after_owned.st_dev, after_owned.st_ino, after_owned.st_size,
                    after_owned.st_nlink, after_owned.st_mtime_ns,
                    after_owned.st_ctime_ns) != (
                    opened_owned.st_dev, opened_owned.st_ino, opened_owned.st_size,
                    opened_owned.st_nlink, opened_owned.st_mtime_ns,
                    opened_owned.st_ctime_ns):
                hold("OWNED_RACE")
        if not safe(path):
            hold("OWNED_RACE")
        final_owned = path.lstat()
        if (final_owned.st_dev, final_owned.st_ino, final_owned.st_size,
                final_owned.st_mtime_ns, final_owned.st_ctime_ns) != (
                before_owned.st_dev, before_owned.st_ino, before_owned.st_size,
                before_owned.st_mtime_ns, before_owned.st_ctime_ns):
            hold("OWNED_RACE")
        if h.hexdigest() != digest.lower():
            hold("OWNED_SHA")
        expected.add(rel.casefold())
    if ("nox.p01.shell.exe" not in expected or
            "backend/nox_helion_private_candidate.exe" not in expected):
        hold("BINARIES")
    owner = root / "nox-p01-owned.txt"
    uninstaller = root / "Uninstall.exe"
    # G4: only the same file handle we attested may supply the owner marker
    # and native NSIS uninstaller metadata. A safe(path) preflight alone can race.
    if not (verify_locked_nsis_metadata(owner, safe, marker=True) and
            verify_locked_nsis_metadata(uninstaller, safe, marker=False)):
        hold("NSIS_METADATA")
    observed = set()
    for folder, dirs, files in os.walk(root, topdown=True, followlinks=False):
        for name in dirs:
            directory = Path(folder) / name
            if not safe(directory, True):
                hold("DIRECTORY_REPARSE")
            if directory.relative_to(root).as_posix().casefold() not in expected_directories:
                hold("UNEXPECTED_DIRECTORY")
        for name in files:
            path = Path(folder) / name
            if not safe(path):
                hold("FILE_REPARSE")
            rel = path.relative_to(root).as_posix().casefold()
            if rel not in expected or rel in observed:
                hold("UNEXPECTED_FILE")
            observed.add(rel)
    if observed != expected:
        hold("MISSING_OR_DUPLICATE")
    if not safe(manifest) or not unchanged_probe_snapshot(frozen_manifest, manifest.lstat()):
        hold("MANIFEST_FINAL_IDENTITY")
    if not safe(marker) or not unchanged_probe_snapshot(before, marker.lstat()):
        hold("PROBE_FINAL_IDENTITY")
    return {"status": "PASS_DIAGNOSTIC_ONLY", "manifest_files_checked": len(data["files"]),
            "unmanaged_probe_preserved": True, "release_accepted": False}
