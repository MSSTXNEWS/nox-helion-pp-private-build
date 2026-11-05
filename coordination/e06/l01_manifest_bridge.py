"""NOX L02 -> existing L01 manifest bridge. No downloader, installer or release promotion.

Only a real existing E06 NSIS candidate with matching evidence may yield a
source-scoped, owner-review-only 5-line manifest. Never auto-pins a loader, ships
binary, or blesses a diagnostic Windows Setup as a release.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from urllib.parse import urlsplit, unquote

SCHEMA = "NOX-E06-ONEHOST-DIAGNOSTIC-NSIS-v1"
PREFIX = "NOX-HELION-BOOTSTRAP-V2"
REPO = "/MSSTXNEWS/nox-helion-pp-private-build/releases/download/"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
TAG = re.compile(r"v?[0-9]+(?:\.[0-9]+){0,3}(?:-[A-Za-z0-9._-]{1,32})?\Z")
NAME = re.compile(r"[A-Za-z0-9._-]+\.exe\Z")
class Hold(ValueError):
    pass


def _no_reparse_path(path: Path):
    """Reject Windows junctions/reparse entries as well as POSIX symlinks."""
    for node in (path, *path.parents):
        try:
            info = node.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode) or
            getattr(node, "is_junction", lambda: False)() or
            (getattr(info, "st_file_attributes", 0) & 0x400)):
            raise Hold("L02_SYMLINK_OR_REPARSE_HOLD")


def safe_regular(path: Path):
    _no_reparse_path(path)
    if not path.is_file():
        raise Hold("L02_REQUIRED_FILE_MISSING")
    st = path.stat()
    if not stat.S_ISREG(st.st_mode):
        raise Hold("L02_SPECIAL_FILE_HOLD")
    if st.st_nlink != 1:
        raise Hold("L02_HARDLINK_ALIAS_HOLD")
    return st


def _identity(st):
    return (st.st_dev, st.st_ino, st.st_nlink, st.st_size,
            st.st_mtime_ns, st.st_ctime_ns)


def sha256_file(path: Path, *, verify_pe: bool = False) -> str:
    before = safe_regular(path)
    h = hashlib.sha256()
    with path.open("rb") as stream:
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            raise Hold("L02_INPUT_FILE_IDENTITY_CHANGED_HOLD")
        if verify_pe:
            _pe_installer_stream(stream)
            stream.seek(0)
        for block in iter(lambda: stream.read(1024*1024), b""):
            h.update(block)
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            raise Hold("L02_INPUT_FILE_IDENTITY_CHANGED_HOLD")
    if _identity(safe_regular(path)) != _identity(before):
        raise Hold("L02_INPUT_FILE_IDENTITY_CHANGED_HOLD")
    return h.hexdigest()


def _pe_installer_stream(stream):
    dos = stream.read(64)
    if len(dos) != 64 or dos[:2] != b"MZ":
        raise Hold("L02_SETUP_NOT_PE")
    offset = int.from_bytes(dos[60:64], "little")
    if not 64 <= offset <= 4096:
        raise Hold("L02_SETUP_INVALID_PE_OFFSET")
    stream.seek(offset)
    header = stream.read(26)
    # NSIS x86 bootstrap is also valid for an x64 installed payload.
    pair = (int.from_bytes(header[4:6], "little"), int.from_bytes(header[24:26], "little"))
    if len(header) < 26 or header[:4] != b"PE\0\0" or pair not in ((0x14c, 0x10b), (0x8664, 0x20b)):
        raise Hold("L02_SETUP_NOT_SUPPORTED_WINDOWS_PE")


def pe_installer(path: Path):
    before = safe_regular(path)
    with path.open("rb") as stream:
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            raise Hold("L02_INPUT_FILE_IDENTITY_CHANGED_HOLD")
        _pe_installer_stream(stream)
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            raise Hold("L02_INPUT_FILE_IDENTITY_CHANGED_HOLD")
    if _identity(safe_regular(path)) != _identity(before):
        raise Hold("L02_INPUT_FILE_IDENTITY_CHANGED_HOLD")


def url_gate(value: str, setup_name: str):
    if not isinstance(value, str) or len(value) > 1024 or '\\' in value:
        raise Hold("L02_URL_INVALID")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.hostname != "github.com" or
        parsed.netloc != "github.com" or parsed.query or parsed.fragment or
        not parsed.path.startswith(REPO) or parsed.geturl() != value):
        raise Hold("L02_URL_UNTRUSTED_ORIGIN")
    rest = parsed.path[len(REPO):].split("/")
    if len(rest) != 2 or not TAG.fullmatch(rest[0]) or not NAME.fullmatch(rest[1]):
        raise Hold("L02_RELEASE_URL_NONCANONICAL")
    if rest[1] != setup_name or unquote(parsed.path) != parsed.path:
        raise Hold("L02_SETUP_FILENAME_OR_ESCAPE_MISMATCH")


def _unique_receipt_fields(pairs):
    # Ambiguous upstream owner receipts must never become a loader manifest.
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise Hold("L02_RECEIPT_DUPLICATE_KEY_HOLD")
        obj[key] = value
    return obj


def _reject_nonfinite_receipt_number(_value):
    raise Hold("L02_RECEIPT_NONFINITE_NUMBER_HOLD")


def emit(setup: Path, receipt: Path, url: str, version: int, out: Path) -> dict:
    if type(version) is not int or not 1 <= version <= 2147483647:
        raise Hold("L02_VERSION_INVALID")
    st = safe_regular(setup)
    safe_regular(receipt)
    if not 4096 <= st.st_size <= 2147483647:
        raise Hold("L02_SETUP_SIZE_INVALID")
    pe_installer(setup)
    url_gate(url, setup.name)
    try:
        receipt_before = safe_regular(receipt)
        receipt_raw = receipt.read_bytes()
        if (len(receipt_raw) > 1048576 or
            _identity(safe_regular(receipt)) != _identity(receipt_before)):
            raise Hold("L02_RECEIPT_IDENTITY_OR_SIZE_HOLD")
        proof = json.loads(
            receipt_raw.decode("utf-8"),
            object_pairs_hook=_unique_receipt_fields,
            parse_constant=_reject_nonfinite_receipt_number,
        )
    except Hold:
        raise
    except (ValueError, UnicodeError, OSError):
        raise Hold("L02_RECEIPT_NOT_JSON") from None
    if (not isinstance(proof, dict) or proof.get("schema") != SCHEMA or
        proof.get("one_visible_host") is not True or
        proof.get("release_accepted") is not False or
        proof.get("status") != "WINDOWS_INSTALLER_CANDIDATE_NOT_E07_ACCEPTED" or
        proof.get("installer_lifecycle_tested") is not False or
        type(proof.get("installer_bytes")) is not int or
        proof["installer_bytes"] != st.st_size or
        not isinstance(proof.get("installer_sha256"), str) or
        not HEX64.fullmatch(proof["installer_sha256"])):
        raise Hold("L02_RECEIPT_NOT_OWNER_E06_DIAGNOSTIC")
    sha = sha256_file(setup, verify_pe=True)
    if sha != proof["installer_sha256"]:
        raise Hold("L02_SETUP_SHA_DISAGREES_WITH_OWNER_RECEIPT")
    if out.exists() or out.is_symlink() or not out.parent.is_dir():
        raise Hold("L02_MANIFEST_OUTPUT_UNSAFE_OR_EXISTS")
    _no_reparse_path(out)
    raw = f"{PREFIX}\n{version}\n{url}\n{st.st_size}\n{sha}\n".encode("ascii")
    if not 100 <= len(raw) <= 4095:
        raise Hold("L02_MANIFEST_SIZE_INVALID")
    # A short write/fsync failure must not publish a partial final manifest.
    # Same-directory temporary bytes are durable before a no-clobber hardlink;
    # unlinking the temporary name keeps the final name atomic on NTFS/POSIX.
    # Do not use os.replace(): a concurrent owner candidate must never be lost.
    fd, temporary = tempfile.mkstemp(prefix=out.name + ".", suffix=".tmp", dir=out.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, out)
        except FileExistsError as exc:
            raise Hold("L02_MANIFEST_OUTPUT_UNSAFE_OR_EXISTS") from exc
    finally:
        os.unlink(temporary)
    return {
        "schema": "NOX-L02-L01-MANIFEST-HANDOFF-v1",
        "status": "MANIFEST_SOURCE_CANDIDATE_NOT_OWNER_APPROVED",
        "manifest_file": out.name,
        "manifest_sha256_for_L01_rebuild_after_owner_review": hashlib.sha256(raw).hexdigest(),
        "setup_sha256": sha, "setup_bytes": st.st_size,
        "source_receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
        "version": version,
        "native_windows_installed_e2e": "NOT_PROVEN",
        "independent_e07": "NOT_PROVEN",
        "loader_auto_pinned": False,
        "release_accepted": False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--setup", required=True, type=Path)
    p.add_argument("--receipt", required=True, type=Path)
    p.add_argument("--approved-url", required=True)
    p.add_argument("--version", type=int, required=True)
    p.add_argument("--out", required=True, type=Path)
    args=p.parse_args(argv)
    try:
        info=emit(args.setup,args.receipt,args.approved_url,args.version,args.out)
        print(json.dumps(info,sort_keys=True,separators=(",", ":")))
        return 0
    except (OSError, Hold) as exc:
        print(json.dumps({"status":"HOLD","reason":str(exc),"release_accepted":False}))
        return 2
if __name__ == "__main__":
    raise SystemExit(main())