"""Reassemble NOX V61 age ciphertext from the four Drive-delivered ZIP parts.

No network, private-key handling, or file deletion. Hashes are pinned to the
2026-11-14 verified native V61 backup; mismatches fail without overwriting.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

EXPECTED_SHA = "389a1378990a8cc55be09edc7dddecea746ba144ff82011ad71812d1fd9bd6b6"
EXPECTED_BYTES = 265876084
NAME = "NOX_V61_ENCRYPTED_CHECKPOINT_OPTIMIZER_20261114.tar.age"
INDEX_MAX_BYTES = 64 * 1024


def _valid_sha(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("HOLD_INDEX_DUPLICATE_KEY")
        obj[key] = value
    return obj


def _reject_constant(_value):
    raise ValueError("HOLD_INDEX_NONFINITE")


def _read_index(archive: zipfile.ZipFile, expected_sha: str, expected_bytes: int) -> dict:
    """Bound decompression before JSON parsing; validate all four typed entries."""
    info = archive.getinfo("NOX_V61_CHUNK_INDEX.json")
    if not 0 < info.file_size <= INDEX_MAX_BYTES:
        raise ValueError("HOLD_INDEX_SIZE")
    with archive.open(info) as source:
        raw = source.read(INDEX_MAX_BYTES + 1)
    if len(raw) != info.file_size or len(raw) > INDEX_MAX_BYTES:
        raise ValueError("HOLD_INDEX_SIZE")
    try:
        index = json.loads(raw, object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("HOLD_INDEX_JSON") from exc
    if not isinstance(index, dict):
        raise ValueError("HOLD_INDEX_OBJECT")
    if index.get("schema") != "NOX_V61_ENCRYPTED_CHUNKS_V1":
        raise ValueError("HOLD_CHUNK_SCHEMA")
    if type(index.get("part_count")) is not int or index["part_count"] != 4:
        raise ValueError("HOLD_PART_COUNT")
    if (type(index.get("ciphertext_total_bytes")) is not int
            or index["ciphertext_total_bytes"] != expected_bytes):
        raise ValueError("HOLD_TOTAL_BYTES")
    if index.get("ciphertext_sha256") != expected_sha:
        raise ValueError("HOLD_SOURCE_SHA")
    parts = index.get("parts")
    if not isinstance(parts, list) or len(parts) != 4:
        raise ValueError("HOLD_INDEX_PARTS")
    for i, entry in enumerate(parts, 1):
        if not isinstance(entry, dict):
            raise ValueError("HOLD_INDEX_ENTRY")
        if (type(entry.get("part")) is not int or entry["part"] != i
                or entry.get("file") != f"NOX_V61_CIPHER.part{i:02d}"):
            raise ValueError("HOLD_INDEX_ORDER")
        if (type(entry.get("size_bytes")) is not int
                or not 0 <= entry["size_bytes"] <= expected_bytes
                or not _valid_sha(entry.get("sha256"))):
            raise ValueError("HOLD_INDEX_ENTRY")
    if sum(entry["size_bytes"] for entry in parts) != expected_bytes:
        raise ValueError("HOLD_INDEX_SIZE_SUM")
    return index

def _sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1048576),b""):
            h.update(chunk)
    return h.hexdigest()

def restore(directory: Path, output: Path, *, expected_sha: str = EXPECTED_SHA,
            expected_bytes: int = EXPECTED_BYTES) -> dict:
    """Verifies every ZIP and part, concatenates bytes, pins final hash.

    Existing output with identical SHA is returned unchanged. Any conflicting
    existing output is a HOLD; the function never overwrites user files.
    """
    directory=Path(directory)
    output=Path(output)
    if not _valid_sha(expected_sha) or type(expected_bytes) is not int or expected_bytes<=0:
        raise ValueError("HOLD_PINNED_MANIFEST")
    if output.is_symlink():
        raise ValueError("HOLD_OUTPUT_SYMLINK")
    if output.exists():
        if output.is_file() and output.stat().st_size==expected_bytes and _sha(output)==expected_sha:
            return {"state":"ALREADY_PRESENT_SHA_VERIFIED","file":str(output),
                    "sha256":expected_sha,"bytes":expected_bytes}
        raise ValueError("HOLD_OUTPUT_EXISTS_HASH_MISMATCH")
    if not output.parent.is_dir():
        raise ValueError("HOLD_OUTPUT_FOLDER_MISSING")
    tmp=None
    full_digest=hashlib.sha256()
    total=0
    reference_index=None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent,prefix=".nox-v61-",
                                          suffix=".partial",delete=False) as sink:
            tmp=Path(sink.name)
            for i in range(1,5):
                archive=directory/f"NOX_V61_CIPHERTEXT_PART_{i:02d}_20261114.zip"
                if not archive.is_file() or archive.is_symlink():
                    raise ValueError("HOLD_PART_MISSING")
                with zipfile.ZipFile(archive) as z:
                    # A set hides duplicate ZIP entries; check exact member count.
                    names=z.namelist()
                    part_name=f"NOX_V61_CIPHER.part{i:02d}"
                    if len(names)!=2 or set(names)!={part_name,"NOX_V61_CHUNK_INDEX.json"}:
                        raise ValueError("HOLD_ARCHIVE_MEMBERS")
                    index=_read_index(z, expected_sha, expected_bytes)
                    if reference_index is None:
                        reference_index=index
                    elif index!=reference_index:
                        raise ValueError("HOLD_INDEX_CONFLICT")
                    entry=index["parts"][i-1]
                    part_hash=hashlib.sha256()
                    part_bytes=0
                    with z.open(part_name) as source:
                        while True:
                            buf=source.read(1024*1024)
                            if not buf:break
                            part_bytes+=len(buf)
                            total+=len(buf)
                            if part_bytes>entry["size_bytes"]:
                                raise ValueError("HOLD_PART_SHA_MISMATCH")
                            if total>expected_bytes:
                                raise ValueError("HOLD_SIZE_OVERFLOW")
                            part_hash.update(buf)
                            full_digest.update(buf)
                            sink.write(buf)
                    if part_bytes!=entry["size_bytes"] or part_hash.hexdigest()!=entry["sha256"]:
                        raise ValueError("HOLD_PART_SHA_MISMATCH")
            sink.flush()
            os.fsync(sink.fileno())
        if total!=expected_bytes or full_digest.hexdigest()!=expected_sha:
            raise ValueError("HOLD_TOTAL_SHA_MISMATCH")
        # Never os.rename() onto output: another process could create it
        # after exists() and lose its bytes. Hard-link publish is atomic
        # no-replace on the same filesystem as the verified temp file.
        try:
            os.link(tmp,output)
        except FileExistsError as ex:
            raise ValueError("HOLD_CONCURRENT_OUTPUT") from ex
        tmp.unlink()
        tmp=None
        return {"state":"REASSEMBLED_SHA_VERIFIED","file":str(output),
                "sha256":expected_sha,"bytes":total,"parts":4}
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)

def main():
    parser=argparse.ArgumentParser(description="Verify and reassemble V61 encrypted NOX checkpoint parts")
    parser.add_argument("--directory",type=Path,default=Path("."))
    parser.add_argument("--output",type=Path,default=Path(NAME))
    args=parser.parse_args()
    try:
        result=restore(args.directory,args.output)
    except (ValueError,OSError,zipfile.BadZipFile,KeyError,TypeError,IndexError) as ex:
        msg=str(ex)
        print(msg if msg.startswith("HOLD_") else "HOLD_RESTORE_FAILED")
        return 2
    print(json.dumps(result,sort_keys=True))
    print("OWNER_PRIVATE_KEY_DECRYPTION_NOT_PERFORMED=true")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
