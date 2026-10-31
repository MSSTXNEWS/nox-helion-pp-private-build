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
from urllib.parse import urlsplit, unquote

SCHEMA = "NOX-E06-ONEHOST-DIAGNOSTIC-NSIS-v1"
PREFIX = "NOX-HELION-BOOTSTRAP-V2"
REPO = "/MSSTXNEWS/nox-helion-pp-private-build/releases/download/"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
TAG = re.compile(r"v?[0-9]+(?:\.[0-9]+){0,3}(?:-[A-Za-z0-9._-]{1,32})?\Z")
NAME = re.compile(r"[A-Za-z0-9._-]+\.exe\Z")
class Hold(ValueError):
    pass


def safe_regular(path: Path):
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise Hold("L02_SYMLINK_OR_REPARSE_HOLD")
    if not path.is_file():
        raise Hold("L02_REQUIRED_FILE_MISSING")
    st = path.stat()
    if not stat.S_ISREG(st.st_mode):
        raise Hold("L02_SPECIAL_FILE_HOLD")
    return st


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def pe_installer(path: Path):
    with path.open("rb") as stream:
        dos = stream.read(64)
        if len(dos) != 64 or dos[:2] != b"MZ":
            raise Hold("L02_SETUP_NOT_PE")
        offset = int.from_bytes(dos[60:64], "little")
        if not 64 <= offset <= 4096:
            raise Hold("L02_SETUP_INVALID_PE_OFFSET")
        stream.seek(offset)
        header = stream.read(26)
    # NSIS often emits an x86 bootstrap stub even while installing an x64 payload.
    # Do not reject a legitimate existing NSIS Setup solely for that reason.
    pair = (int.from_bytes(header[4:6], "little"), int.from_bytes(header[24:26], "little"))
    if len(header) < 26 or header[:4] != b"PE\0\0" or pair not in ((0x14c, 0x10b), (0x8664, 0x20b)):
        raise Hold("L02_SETUP_NOT_SUPPORTED_WINDOWS_PE")


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
        proof = json.loads(receipt.read_text(encoding="utf-8"))
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
    sha = sha256_file(setup)
    if sha != proof["installer_sha256"]:
        raise Hold("L02_SETUP_SHA_DISAGREES_WITH_OWNER_RECEIPT")
    if out.exists() or out.is_symlink() or not out.parent.is_dir():
        raise Hold("L02_MANIFEST_OUTPUT_UNSAFE_OR_EXISTS")
    for ancestor in (out.parent, *out.parent.parents):
        if ancestor.is_symlink():
            raise Hold("L02_MANIFEST_PARENT_SYMLINK")
    raw = f"{PREFIX}\n{version}\n{url}\n{st.st_size}\n{sha}\n".encode("ascii")
    if not 100 <= len(raw) <= 4095:
        raise Hold("L02_MANIFEST_SIZE_INVALID")
    # Atomic candidate publication; no implicit release or L01 pin activation.
    with out.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "schema": "NOX-L02-L01-MANIFEST-HANDOFF-v1",
        "status": "MANIFEST_SOURCE_CANDIDATE_NOT_OWNER_APPROVED",
        "manifest_file": out.name,
        "manifest_sha256_for_L01_rebuild_after_owner_review": hashlib.sha256(raw).hexdigest(),
        "setup_sha256": sha, "setup_bytes": st.st_size,
        "source_receipt_sha256": sha256_file(receipt),
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