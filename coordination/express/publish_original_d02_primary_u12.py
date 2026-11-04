"""Publish the existing reviewed five actions into the disposable FULL-D02 HOME.

No new UI, backend or original archive modification. SourceLock provenance and
physical Windows UIA/E07 acceptance are separate checks.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from stage_original_five_primary import publish


def _regular(path: Path) -> bool:
    try:
        info = path.lstat()
        return (stat.S_ISREG(info.st_mode) and not path.is_symlink() and
                not getattr(path, "is_junction", lambda: False)() and
                not (getattr(info, "st_file_attributes", 0) & 0x400))
    except OSError:
        return False


def _plain_ancestors(path: Path) -> bool:
    return all(not node.is_symlink() and
               not getattr(node, "is_junction", lambda: False)()
               for node in (path, *path.parents))


def stage(source: Path, receipt_path: Path) -> dict:
    source = Path(source).absolute()
    receipt_path = Path(receipt_path).absolute()
    home = source / "Assets" / "index.html"
    staging = home.with_name("index.html.nox-u12-pending")
    if (source.name != "R11" or not source.is_dir() or
            not _regular(home) or not _plain_ancestors(home) or
            not receipt_path.parent.is_dir() or
            not _plain_ancestors(receipt_path) or receipt_path.exists() or
            receipt_path.is_symlink() or receipt_path.is_relative_to(source) or
            staging.exists() or staging.is_symlink()):
        raise ValueError("D02_PRIMARY_DISPOSABLE_PATH_HOLD")
    before = home.read_bytes()
    published, proof = publish(before)  # strict immutable original byte/SHA pins
    if hashlib.sha256(before).hexdigest() != proof["source_sha256"] or not (
            all(item.encode("utf-8") in published for item in
                ("data-nox-primary=\"CHAT\"", "data-nox-primary=\"INSTALL\"",
                 "data-nox-primary=\"MODELS\"", "data-nox-primary=\"LEARN\"",
                 "data-nox-primary=\"SETTINGS\"")) and
            published.count(b"data-nox-primary=") == 5 and
            proof["installed_ui_automation"] == "NOT_RUN" and
            proof["release_accepted"] is False):
        raise ValueError("D02_PRIMARY_SOURCE_PROOF_HOLD")
    try:
        with staging.open("xb") as stream:
            stream.write(published)
            stream.flush()
            os.fsync(stream.fileno())
        if (not _regular(staging) or not _regular(home) or
                home.read_bytes() != before or staging.read_bytes() != published):
            raise ValueError("D02_PRIMARY_STAGED_READBACK_HOLD")
        os.replace(staging, home)
        if home.read_bytes() != published:
            raise ValueError("D02_PRIMARY_ATOMIC_PUBLISH_HOLD")
        evidence = {**proof, "status": "STAGED_SOURCE_ONLY_NOT_UIA",
                    "original_source_archive_unchanged": True,
                    "published_payload_uiA": "NOT_RUN", "independent_e07": "HOLD"}
        # The parent source archive is immutable. Only the disposable R11 HOME
        # and a new evidence file are written; unknown files are never removed.
        with receipt_path.open("x", encoding="utf-8") as stream:
            json.dump(evidence, stream, sort_keys=True, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        if json.loads(receipt_path.read_text("utf-8")) != evidence:
            raise ValueError("D02_PRIMARY_RECEIPT_READBACK_HOLD")
        return evidence
    finally:
        # Unpublished temporary is owned by this operation; no recursive delete.
        if staging.is_file() and not staging.is_symlink():
            staging.unlink()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("USAGE: publish_original_d02_primary_u12.py R11_ROOT RECEIPT_PATH")
    stage(Path(sys.argv[1]), Path(sys.argv[2]))
    print("D02_EXISTING_FIVE_PRIMARY_STAGED_NOT_UIA_E07", flush=True)
