#!/usr/bin/env python3
"""Read-only byte identity check: GitHub R8 source manifest vs owner NOX_NEW.

It never writes to NOX_NEW, changes ACLs, starts services or claims E2E/release.
Only run on an owner-authorized Windows source tree with matching build receipts.
Trust anchors MUST be independently read from the exact GitHub Windows artifact,
not copied from the same local folder as the manifest and receipt.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
REQUIRED = {"MainWindow.xaml.cs", "index.html", "NOX.HELION.csproj"}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def is_link(path):
    s = path.lstat()
    return path.is_symlink() or bool(getattr(s, "st_file_attributes", 0) & REPARSE)


def require_direct_ancestry(path):
    """Reject reparse links in lexical parents of owner source/EXE paths.

    Checking only the last path component misses C:\\parent-junction\\src.
    Do not call resolve(): it would erase the untrusted reparse witness.
    """
    candidate = Path(path)
    if ".." in candidate.parts:
        raise ValueError("OWNER_PATH_DOTDOT_HOLD")
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    for node in (candidate, *candidate.parents):
        if is_link(node):
            raise ValueError("OWNER_PATH_ANCESTOR_REPARSE_HOLD")


def valid_rel(name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        return False
    parts = PurePosixPath(name).parts
    return not (name.startswith("/") or any(x in ("", ".", "..") for x in parts)
                or "/".join(parts) != name)


def inventory(root):
    require_direct_ancestry(root)
    if is_link(root) or not root.is_dir():
        raise ValueError("LOCAL_SRC_UNSAFE_OR_MISSING")
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in dirs[:]:
            folder = base / name
            if is_link(folder):
                raise ValueError("LOCAL_SRC_REPARSE_HOLD")
            if name.lower() in ("bin", "obj"):
                dirs.remove(name)
        for name in files:
            f = base / name
            if is_link(f) or not f.is_file():
                raise ValueError("LOCAL_SRC_REPARSE_OR_NONFILE_HOLD")
            rel = f.relative_to(root).as_posix()
            if not valid_rel(rel):
                raise ValueError("LOCAL_SRC_INVALID_PATH_HOLD")
            folded = rel.casefold()
            if folded in result:
                raise ValueError("LOCAL_SRC_CASE_ALIAS_HOLD")
            result[folded] = (rel, f)
    return result


def attest(manifest_path, receipt_path, local_src, local_exe,
           trusted_manifest_sha256, trusted_receipt_sha256, trusted_git_sha):
    # Independent anchors prevent jointly forged manifest+receipt pairs from
    # declaring a different source and EXE to be a byte-identical owner build.
    if not (HEX64.fullmatch(trusted_manifest_sha256)
            and HEX64.fullmatch(trusted_receipt_sha256)
            and HEX40.fullmatch(trusted_git_sha)):
        raise ValueError("EXTERNAL_PROOF_ANCHORS_REQUIRED_HOLD")
    manifest_bytes = manifest_path.read_bytes()
    receipt_bytes = receipt_path.read_bytes()
    if (hashlib.sha256(manifest_bytes).hexdigest() != trusted_manifest_sha256
            or hashlib.sha256(receipt_bytes).hexdigest() != trusted_receipt_sha256):
        raise ValueError("EXTERNAL_PROOF_ANCHOR_MISMATCH_HOLD")
    manifest = json.loads(manifest_bytes.decode("utf-8-sig"))
    receipt = json.loads(receipt_bytes.decode("utf-8-sig"))
    if (manifest.get("schema") != "NOX_R8_BUILD_SRC_PROVENANCE_V1"
            or receipt.get("schema") != "NOX_R8_NATIVE_SINGLE_EXE_V1"
            or not HEX40.fullmatch(str(manifest.get("source_git_sha", "")))
            or manifest.get("source_git_sha") != trusted_git_sha
            or not HEX64.fullmatch(str(manifest.get("source_zip_sha256", "")))
            or not HEX64.fullmatch(str(receipt.get("exe_sha256", "")))
            or manifest.get("source_git_sha") != receipt.get("source_git_sha")
            or manifest.get("source_zip_sha256") != receipt.get("source_sha256")
            or hashlib.sha256(manifest_bytes).hexdigest() != receipt.get("staged_source_manifest_sha256")
            or receipt.get("owner_source_parity") != "NOT_VERIFIED"
            or receipt.get("accepted_full_release") is not False):
        raise ValueError("CLOUD_PROOF_BINDING_HOLD")
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) < 3 or len(rows) != receipt.get("staged_source_file_count"):
        raise ValueError("CLOUD_MANIFEST_COUNT_HOLD")
    expected = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("CLOUD_MANIFEST_ROW_HOLD")
        rel = row.get("path")
        count = row.get("bytes")
        sha = row.get("sha256")
        if (not valid_rel(rel) or type(count) is not int or count < 0
                or not HEX64.fullmatch(str(sha)) or rel.casefold() in expected):
            raise ValueError("CLOUD_MANIFEST_ROW_HOLD")
        expected[rel.casefold()] = (rel, count, sha)
    if not REQUIRED.issubset({v[0] for v in expected.values()}):
        raise ValueError("CLOUD_MANDATORY_SOURCE_MISSING_HOLD")

    current = inventory(local_src)
    missing = set(expected) - set(current)
    extras = set(current) - set(expected)
    mismatch = 0
    for key in set(expected) & set(current):
        _, size, sha = expected[key]
        _, path = current[key]
        if path.stat().st_size != size or digest(path) != sha:
            mismatch += 1
    require_direct_ancestry(local_exe)
    if is_link(local_exe) or not local_exe.is_file():
        raise ValueError("OWNER_EXE_MISSING_OR_REPARSE_HOLD")
    exe_match = digest(local_exe) == receipt["exe_sha256"]
    source_match = not (missing or extras or mismatch)
    return {
        "schema": "NOX_R8_OWNER_BYTE_PARITY_V1",
        "cloud_git_sha": manifest["source_git_sha"],
        "source_match": source_match,
        "exe_match": exe_match,
        "missing_files": len(missing),
        "unexpected_files": len(extras),
        "changed_files": mismatch,
        "result": "BYTE_PARITY_ONLY_NOT_E2E" if (source_match and exe_match) else "SOURCE_PARITY_HOLD",
        "owner_qwen_stream_stop_sqlite": "NOT_TESTED",
        "release": "HOLD",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--receipt", required=True, type=Path)
    p.add_argument("--local-src", required=True, type=Path)
    p.add_argument("--local-exe", required=True, type=Path)
    p.add_argument("--trusted-manifest-sha256", required=True,
                   help="Independent SHA256 of GitHub-runner SOURCE_PROVENANCE.json")
    p.add_argument("--trusted-receipt-sha256", required=True,
                   help="Independent SHA256 of same-run BUILD_RECEIPT.json")
    p.add_argument("--trusted-git-sha", required=True,
                   help="40-hex exact Git commit of the independently verified runner build")
    args = p.parse_args(argv)
    try:
        result = attest(args.manifest, args.receipt, args.local_src, args.local_exe,
                        args.trusted_manifest_sha256, args.trusted_receipt_sha256,
                        args.trusted_git_sha)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, UnicodeError) as exc:
        result = {"schema": "NOX_R8_OWNER_BYTE_PARITY_V1", "result": "PROVENANCE_UNVERIFIED_HOLD",
                  "reason": str(exc) if isinstance(exc, ValueError) else "SOURCE_UNREADABLE_HOLD",
                  "owner_qwen_stream_stop_sqlite": "NOT_TESTED", "release": "HOLD"}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 3
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["source_match"] and result["exe_match"] else 2


if __name__ == "__main__":
    sys.exit(main())
