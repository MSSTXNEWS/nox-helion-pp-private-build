#!/usr/bin/env python3
"""Reassemble a NOX ZIP from a verified parts manifest. No archive contents are executed."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

CHUNK = 1024 * 1024

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()

def basename(value):
    if not isinstance(value, str) or not value or Path(value).name != value or "/" in value or "\\" in value or value in {".", ".."}:
        raise ValueError("Manifest contains a non-local filename")
    return value

def sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Manifest contains an invalid SHA256")
    return value

def assemble(manifest_path):
    manifest_path = manifest_path.resolve(strict=True)
    root = manifest_path.parent
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    if m.get("schema") != "NOX_SPLIT_ARCHIVE_V1":
        raise ValueError("Unsupported manifest schema")
    output = root / basename(m["archive"])
    expected_hash = sha(m["archive_sha256"])
    total = m["archive_bytes"]
    parts = m["parts"]
    if type(total) is not int or total <= 0 or not isinstance(parts, list) or not parts:
        raise ValueError("Invalid archive length or parts")
    names = [basename(p["file"]) for p in parts]
    if len(set(names)) != len(names) or output.name in names:
        raise ValueError("Duplicate or conflicting filenames")
    if any(type(p.get("bytes")) is not int or p["bytes"] <= 0 for p in parts):
        raise ValueError("Invalid part length")
    if sum(p["bytes"] for p in parts) != total:
        raise ValueError("Part lengths do not equal archive length")
    for part in parts:
        sha(part["sha256"])
        path = root / part["file"]
        if path.is_symlink() or not path.is_file() or path.stat().st_size != part["bytes"]:
            raise ValueError("Missing or incorrectly sized part: " + part["file"])
    if output.exists() or output.is_symlink():
        if not output.is_symlink() and output.is_file() and output.stat().st_size == total and digest(output) == expected_hash:
            print("Already assembled and SHA256 verified:", output)
            return output
        raise FileExistsError("Output already exists and differs; it was not overwritten")
    if shutil.disk_usage(root).free < total + 256 * 1024 * 1024:
        raise OSError("Insufficient space for the assembled archive and a 256 MiB reserve")
    temporary = root / (output.name + ".assembling-" + str(os.getpid()))
    created = False
    whole = hashlib.sha256()
    try:
        with temporary.open("xb") as target:
            created = True
            for index, part in enumerate(parts, 1):
                h = hashlib.sha256()
                count = 0
                with (root / part["file"]).open("rb") as source:
                    for block in iter(lambda: source.read(CHUNK), b""):
                        count += len(block)
                        if count > part["bytes"]:
                            raise ValueError("Part changed while being read")
                        h.update(block)
                        whole.update(block)
                        target.write(block)
                if count != part["bytes"] or h.hexdigest() != part["sha256"]:
                    raise ValueError("SHA256 mismatch: " + part["file"])
                print(f"Verified {index}/{len(parts)}: {part['file']}", flush=True)
            target.flush()
            os.fsync(target.fileno())
        if temporary.stat().st_size != total or whole.hexdigest() != expected_hash:
            raise ValueError("Complete archive SHA256 mismatch")
        # The folder is user-controlled; never intentionally replace an existing archive.
        if output.exists() or output.is_symlink():
            raise FileExistsError("Output appeared during assembly; not overwritten")
        temporary.rename(output)
        created = False
        print("Complete archive SHA256 verified:", expected_hash)
        print("ZIP:", output)
        return output
    finally:
        if created and temporary.exists():
            temporary.unlink()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", default=str(Path(__file__).with_name("parts_manifest.json")))
    args = parser.parse_args()
    assemble(Path(args.manifest))
