#!/usr/bin/env python3
"""Verify the five persistent IQ2_XXS GGUF shards used with external Engram."""

import hashlib
import json
import mmap
import os
import re
import stat
from pathlib import Path


ROOT = Path("/root/nox/models/deepseek_v41_flash_iq2xxs")
MODEL = "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS"
SOURCE_REVISION = "65d53bc8be65123e255ff02f3ded958b6dbf54fd"
SHARDS = (
    (5_780_704, "f356f198561f56df36f7ab92d7238a926646d76de992c34f15bcb939a5f529b9"),
    (39_535_781_184, "25af3785ccf925f54137e1ead4c481a8952315dc0b1af6519a99407f67bce8f3"),
    (39_736_712_000, "8168d0998fc494def2e1952d83c131425a108660aae9d29190f5a8670ab62b48"),
    (39_036_908_384, "9eb9b4de1968f150dfc207eb31c27be9cd9b5666a9a6246bde8a22b184b4bee0"),
    (19_923_784_832, "7e35f6b4e6fc46f6c4b152b593d84d683c5ece695ae6ad734f556198c041bec1"),
)


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def verify_shard(path, expected_length, expected_sha256, owner):
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        return "MANIFEST_INVALID"
    if not hasattr(os, "O_DIRECT"):
        return "DIRECT_IO_UNAVAILABLE"
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC | os.O_DIRECT)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != owner
                or before.st_mode & 0o022 or before.st_size != expected_length):
            return "INVALID_FILE_METADATA"
        digest = hashlib.sha256()
        total = 0
        with mmap.mmap(-1, 8 * 1024 * 1024) as buffer, memoryview(buffer) as view:
            while count := os.readv(fd, [view]):
                if not total and buffer[:4] != b"GGUF":
                    return "INVALID_GGUF_MAGIC"
                with view[:count] as block:
                    digest.update(block)
                total += count
        if total != expected_length or identity(os.fstat(fd)) != identity(before):
            return "SHARD_CHANGED_DURING_READ"
        if identity(path.stat(follow_symlinks=False)) != identity(before):
            return "SHARD_PATH_CHANGED"
        if digest.hexdigest() != expected_sha256:
            return "SHA256_MISMATCH"
    finally:
        os.close(fd)
    return "VERIFIED"


def main():
    results = []
    for index, (length, sha256) in enumerate(SHARDS, start=1):
        path = ROOT / f"{MODEL}-{index:05d}-of-00006.gguf"
        try:
            state = verify_shard(path, length, sha256, owner=0)
        except OSError as error:
            state = f"FILE_UNAVAILABLE_{error.errno}"
        results.append({"part": index, "length": length, "state": state})
    verified = all(row["state"] == "VERIFIED" for row in results)
    print(json.dumps({
        "revision": SOURCE_REVISION,
        "expected_total_bytes": sum(length for length, _ in SHARDS),
        "persistent_backbone_verified": verified,
        "full_restart_verified": False,
        "parts": results,
    }, separators=(",", ":")), flush=True)
    return 0 if verified else 2


if __name__ == "__main__":
    raise SystemExit(main())
