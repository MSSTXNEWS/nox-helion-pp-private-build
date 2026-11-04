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
    # A same-byte foreign inode must never be overwritten as our own HOME.
    original_info = home.lstat()
    if (not stat.S_ISREG(original_info.st_mode) or
            not original_info.st_ino or original_info.st_nlink != 1):
        raise ValueError("D02_PRIMARY_ORIGINAL_INODE_HOLD")
    original_identity = (original_info.st_dev, original_info.st_ino)
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
    created_identity = None
    receipt_identity = None
    receipt_committed = False
    try:
        # Reserve the receipt BEFORE modifying HOME. A concurrent receipt owner
        # cannot leave us with changed HOME and no trustworthy evidence.
        with receipt_path.open("x", encoding="utf-8") as reservation:
            info = os.fstat(reservation.fileno())
            if not stat.S_ISREG(info.st_mode) or not info.st_ino:
                raise ValueError("D02_PRIMARY_RECEIPT_RESERVATION_HOLD")
            receipt_identity = (info.st_dev, info.st_ino)
        with staging.open("xb") as stream:
            # This exclusive open is the ownership boundary. A file that
            # raced in after the earlier absence check belongs to someone else.
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not info.st_ino:
                raise ValueError("D02_PRIMARY_STAGED_IDENTITY_HOLD")
            created_identity = (info.st_dev, info.st_ino)
            stream.write(published)
            stream.flush()
            os.fsync(stream.fileno())
        if (not _regular(staging) or not _regular(home) or
                home.read_bytes() != before or staging.read_bytes() != published):
            raise ValueError("D02_PRIMARY_STAGED_READBACK_HOLD")
        # Validate and durably publish the evidence BEFORE replacing original
        # HOME. If the receipt disk/write fails, its owner reservation and
        # pending staged bytes are removed with the original HOME untouched.
        evidence = {**proof, "status": "STAGED_SOURCE_ONLY_NOT_UIA",
                    "original_source_archive_unchanged": True,
                    "published_payload_uiA": "NOT_RUN", "independent_e07": "HOLD"}
        # The parent source archive is immutable. Only the disposable R11 HOME
        # and a new evidence file are written; unknown files are never removed.
        # Write only to the inode reserved by this invocation.
        with receipt_path.open("r+", encoding="utf-8") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or
                    (info.st_dev, info.st_ino) != receipt_identity):
                raise ValueError("D02_PRIMARY_RECEIPT_OWNER_CHANGED_HOLD")
            json.dump(evidence, stream, sort_keys=True, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        if json.loads(receipt_path.read_text("utf-8")) != evidence:
            raise ValueError("D02_PRIMARY_RECEIPT_READBACK_HOLD")
        # Only after a verified, fsynced receipt may the single staged HOME
        # replace the disposable original. Foreign source archives stay intact.
        # Recheck exact owner inodes and bytes immediately before atomic publish.
        home_now = home.lstat()
        receipt_now = receipt_path.lstat()
        if (not _regular(home) or not _regular(receipt_path) or
                (home_now.st_dev, home_now.st_ino) != original_identity or
                (receipt_now.st_dev, receipt_now.st_ino) != receipt_identity or
                home_now.st_nlink != 1 or receipt_now.st_nlink != 1 or
                home.read_bytes() != before):
            raise ValueError("D02_PRIMARY_PREPUBLISH_OWNER_CHANGED_HOLD")
        # Check our own staged inode again immediately before replacing HOME.
        # A foreign writer may substitute even byte-identical pending content
        # after its early readback; that must never be published as our payload.
        staged_now = staging.lstat()
        if (not _regular(staging) or
                (staged_now.st_dev, staged_now.st_ino) != created_identity or
                staged_now.st_nlink != 1 or staging.read_bytes() != published):
            raise ValueError("D02_PRIMARY_PREPUBLISH_STAGED_OWNER_CHANGED_HOLD")
        os.replace(staging, home)
        # HOME is now altered; retain the already fsynced provenance receipt
        # if post-publish IO fails rather than erasing the only evidence.
        receipt_committed = True
        if home.read_bytes() != published:
            raise ValueError("D02_PRIMARY_ATOMIC_PUBLISH_HOLD")
        return evidence
    finally:
        # Only unlink a still-present inode created by THIS exclusive open.
        # If an unrelated writer won or replaced the path, preserve its bytes.
        if created_identity is not None:
            try:
                current = staging.lstat()
            except FileNotFoundError:
                pass
            else:
                if (_regular(staging) and
                        (current.st_dev, current.st_ino) == created_identity):
                    staging.unlink()
        # Never retain a false partial receipt; never remove foreign bytes.
        if receipt_identity is not None and not receipt_committed:
            try:
                current = receipt_path.lstat()
            except FileNotFoundError:
                pass
            else:
                if (_regular(receipt_path) and
                        (current.st_dev, current.st_ino) == receipt_identity):
                    receipt_path.unlink()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("USAGE: publish_original_d02_primary_u12.py R11_ROOT RECEIPT_PATH")
    stage(Path(sys.argv[1]), Path(sys.argv[2]))
    print("D02_EXISTING_FIVE_PRIMARY_STAGED_NOT_UIA_E07", flush=True)
