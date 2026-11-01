"""Read-only, SHA-pinned admission of a downloaded NOX acquisition library V2.

This is a data bridge for the *existing* FirstBootCoordinator. It never runs a
wheel, launches a tool, installs an Ollama model or creates a competing queue.
An owner-pinned database is not evidence that referenced files are present.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat

_HEX = re.compile(r"[a-f0-9]{64}\Z")
_FTS = re.compile(r"\bUSING\s+fts5\s*\(", re.IGNORECASE)
_MAX_DB = 256 * 1024 * 1024
_MAX_MANIFEST = 1024 * 1024
_MAX_FILES = 2048


class AcquisitionHold(ValueError):
    """The V2 catalog or physical acquisition bytes cannot be trusted."""


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def _regular(path: Path, roots: tuple[Path, ...], max_bytes: int) -> Path:
    if not isinstance(path, Path):
        raise AcquisitionHold("LIBRARY_PATH_INVALID")
    absolute = Path(os.path.abspath(path))
    if not absolute.is_absolute():
        raise AcquisitionHold("LIBRARY_ABSOLUTE_PATH_REQUIRED")
    if not roots or not any(os.path.commonpath((str(absolute), str(root))) == str(root)
                            for root in roots):
        raise AcquisitionHold("LIBRARY_OUTSIDE_APPROVED_ROOTS")
    cursor = absolute
    while True:
        try:
            info = cursor.lstat()
        except OSError as exc:
            raise AcquisitionHold("LIBRARY_FILE_MISSING") from exc
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise AcquisitionHold("LIBRARY_REPARSE_PATH_DENIED")
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    info = absolute.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= max_bytes:
        raise AcquisitionHold("LIBRARY_FILE_TYPE_OR_SIZE_INVALID")
    return absolute


def _sha(value: str) -> bool:
    return type(value) is str and _HEX.fullmatch(value) is not None and value != "0" * 64


def _relative(name: str) -> Path:
    if type(name) is not str or not 0 < len(name) <= 300 or "\\" in name or ":" in name:
        raise AcquisitionHold("LIBRARY_MANIFEST_PATH_INVALID")
    posix = PurePosixPath(name)
    if posix.is_absolute() or any(x in ("", ".", "..") for x in name.split("/")):
        raise AcquisitionHold("LIBRARY_MANIFEST_PATH_TRAVERSAL")
    return Path(*posix.parts)


def audit_library(db_path: str, expected_sha256: str, *, approved_roots,
                  manifest_path: str | None = None, manifest_sha256: str | None = None,
                  assets_root: str | None = None) -> dict:
    """Return bounded verified observations, never rights or install approvals.

    A signed native owner provides approved_roots and independent SHA pins.
    The optional physical manifest is separately SHA-pinned and data-only.
    """
    if not _sha(expected_sha256):
        raise AcquisitionHold("LIBRARY_DB_NATIVE_SHA_REQUIRED")
    roots = tuple(Path(os.path.abspath(p)) for p in approved_roots
                  if type(p) is str and Path(p).is_absolute())
    if len(roots) != len(approved_roots):
        raise AcquisitionHold("LIBRARY_APPROVED_ROOT_INVALID")
    database = _regular(Path(db_path), roots, _MAX_DB)
    if _digest(database) != expected_sha256:
        raise AcquisitionHold("LIBRARY_DB_SHA256_MISMATCH")
    try:
        db = sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=1)
        try:
            db.enable_load_extension(False)
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA trusted_schema=OFF")
            if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise AcquisitionHold("LIBRARY_SQLITE_INTEGRITY_HOLD")
            definitions = db.execute("SELECT name, sql FROM sqlite_schema WHERE type='table'").fetchall()
            fts = [name for name, sql in definitions
                   if type(sql) is str and _FTS.search(sql)]
            if not fts or len(fts) > 8:
                raise AcquisitionHold("LIBRARY_FTS5_TABLE_NOT_FOUND")
            counts = {}
            for name in fts:
                # Quote a SQLite-owned identifier, never a caller-provided SQL name.
                ident = '"' + name.replace('"', '""') + '"'
                count = db.execute(f"SELECT count(*) FROM {ident}").fetchone()[0]
                if type(count) is not int or count > 100000:
                    raise AcquisitionHold("LIBRARY_FTS5_BOUNDS_INVALID")
                counts[name] = count
        finally:
            db.close()
    except sqlite3.Error as exc:
        raise AcquisitionHold("LIBRARY_SQLITE_UNREADABLE") from exc
    verified = []
    if any(x is not None for x in (manifest_path, manifest_sha256, assets_root)):
        if not (manifest_path and _sha(manifest_sha256) and assets_root):
            raise AcquisitionHold("LIBRARY_PHYSICAL_MANIFEST_PIN_REQUIRED")
        manifest = _regular(Path(manifest_path), roots, _MAX_MANIFEST)
        if _digest(manifest) != manifest_sha256:
            raise AcquisitionHold("LIBRARY_MANIFEST_SHA256_MISMATCH")
        try:
            document = json.loads(manifest.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise AcquisitionHold("LIBRARY_MANIFEST_JSON_INVALID") from exc
        if not isinstance(document, dict) or document.get("schema") != "NOX-ACQUISITION-FILES-v1":
            raise AcquisitionHold("LIBRARY_MANIFEST_SCHEMA_INVALID")
        items = document.get("files")
        if not isinstance(items, list) or not 0 < len(items) <= _MAX_FILES:
            raise AcquisitionHold("LIBRARY_MANIFEST_COUNT_INVALID")
        root = Path(os.path.abspath(assets_root))
        if root not in roots and not any(os.path.commonpath((str(root), str(r))) == str(r) for r in roots):
            raise AcquisitionHold("LIBRARY_ASSETS_ROOT_UNAPPROVED")
        unique = set()
        for item in items:
            if type(item) is not dict or set(item) != {"path", "sha256", "bytes"}:
                raise AcquisitionHold("LIBRARY_MANIFEST_ITEM_INVALID")
            rel = _relative(item["path"])
            key = str(rel).casefold()
            if key in unique:
                raise AcquisitionHold("LIBRARY_MANIFEST_DUPLICATE_FILE")
            unique.add(key)
            if not _sha(item["sha256"]) or type(item["bytes"]) is not int or not 0 < item["bytes"] <= 100_000_000_000:
                raise AcquisitionHold("LIBRARY_FILE_PIN_INVALID")
            path = _regular(root / rel, (root,), item["bytes"])
            if path.stat().st_size != item["bytes"] or _digest(path) != item["sha256"]:
                raise AcquisitionHold("LIBRARY_PHYSICAL_FILE_SHA_OR_SIZE_MISMATCH")
            verified.append({"sha256": item["sha256"], "bytes": item["bytes"],
                             "status": "SOURCE_BYTES_VERIFIED_NOT_INSTALLED"})
    return {"schema": "NOX-ACQUISITION-AUDIT-v1",
            "status": "PHYSICAL_FILES_SHA256_VERIFIED" if verified else "SQLITE_FTS5_PINNED_NO_FILE_PROOF",
            "db_sha256": expected_sha256, "fts5_rows": counts,
            "physical_files_verified": len(verified), "physical_files": verified,
            "models_installed": False, "tools_installed": False,
            "source_executed": False, "release_accepted": False}
