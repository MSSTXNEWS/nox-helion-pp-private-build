"""Fixed-path owner-side wrapper for R65. Static evidence only; never dispatch.

Run from an independently pinned, owner-reviewed checkout, after read-only
authorization. The CLI accepts only the expected current source digest, not
a path. No source bytes, filenames, or exception strings are returned.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from b0_proxy_wire_static_evidence import inspect, LIMIT

TASK = "B0-R66-FIXED-PATH-LOCAL-WIRE-ATTESTATION-20261124"
ROOT = Path("/root/nox")


def hold(reason):
    return dict(task_id=TASK, decision=reason, post_authorized=False,
                native_accepted=False)


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_uid, info.st_gid, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns)


def open_fixed(root):
    # Never follow symlinks in any path component, including the leaf.
    if not root.is_absolute() or ".." in root.parts:
        raise ValueError("root")
    if not all(hasattr(os, name) for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK")):
        raise ValueError("flags")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    fds = []
    try:
        fds.append(os.open("/", flags | os.O_DIRECTORY))
        for part in (*root.parts[1:], "scripts"):
            fds.append(os.open(part, flags | os.O_DIRECTORY, dir_fd=fds[-1]))
        entry = os.stat("chat_proxy.py", dir_fd=fds[-1], follow_symlinks=False)
        if not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1:
            raise ValueError("type")
        fds.append(os.open("chat_proxy.py", flags | os.O_NONBLOCK, dir_fd=fds[-1]))
        if identity(entry) != identity(os.fstat(fds[-1])):
            raise ValueError("drift")
        return fds
    except BaseException:
        for fd in reversed(fds):
            os.close(fd)
        raise


def attest(expected, root=ROOT):
    if type(expected) is not str or not re.fullmatch(r"[0-9a-f]{64}", expected):
        return hold("HOLD_SOURCE_PIN_INVALID")
    fds = []
    check = []
    try:
        fds = open_fixed(root)
        before = os.fstat(fds[-1])
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            return hold("HOLD_FIXED_SOURCE_TYPE")
        if not 0 <= before.st_size <= LIMIT:
            return hold("HOLD_FIXED_SOURCE_SIZE")
        chunks = []
        remaining = LIMIT + 1
        while remaining:
            chunk = os.read(fds[-1], min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(fds[-1])
        if len(raw) > LIMIT or len(raw) != after.st_size or identity(before) != identity(after):
            return hold("HOLD_FIXED_SOURCE_DRIFT")
        # Re-open the fixed path after reading: pathname and parent identity
        # must still identify the same object and the same file metadata.
        check = open_fixed(root)
        dir_ids = lambda group: [(s.st_dev, s.st_ino) for s in
                                 (os.fstat(fd) for fd in group[:-1])]
        if dir_ids(fds) != dir_ids(check) or identity(os.fstat(check[-1])) != identity(after):
            return hold("HOLD_FIXED_SOURCE_DRIFT")
        result = inspect(raw, expected)
        result["task_id"] = TASK
        # This identity fingerprint is not an owner signature or serving proof.
        if "source_sha256" in result:
            result["file_identity_sha256"] = hashlib.sha256(
                ":".join(map(str, identity(after))).encode("ascii")).hexdigest()
        return result
    except (OSError, ValueError, RecursionError, MemoryError):
        return hold("HOLD_FIXED_SOURCE_UNAVAILABLE")
    finally:
        for fd in reversed(check + fds):
            os.close(fd)


def selftest():
    def check(condition):
        if not condition:
            raise AssertionError("fixed-source test failed")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        scripts = root / "scripts"
        scripts.mkdir()
        leaf = scripts / "chat_proxy.py"
        raw = b'raise RuntimeError("PRIVATE_SENTINEL")\ndef stream():\n yield f"id: {i}\\nevent: delta\\ndata: {x}\\n\\n"\n'
        digest = hashlib.sha256(raw).hexdigest()
        leaf.write_bytes(raw)
        result = attest(digest, root)
        check(result["literal_counts"]["named_delta"] == 1 and
              result["source_sha256"] == digest and
              len(result["file_identity_sha256"]) == 64 and
              not result["native_accepted"] and not result["post_authorized"] and
              "PRIVATE_SENTINEL" not in json.dumps(result))
        check(attest("0" * 64, root)["decision"] == "HOLD_SOURCE_UNVERIFIED")
        check(attest("bad", root)["decision"] == "HOLD_SOURCE_PIN_INVALID")
        leaf.unlink()
        check(attest(digest, root)["decision"] == "HOLD_FIXED_SOURCE_UNAVAILABLE")
        other = root / "other"
        other.write_bytes(raw)
        leaf.symlink_to(other)
        check(attest(digest, root)["decision"] == "HOLD_FIXED_SOURCE_UNAVAILABLE")
        leaf.unlink()
        os.link(other, leaf)
        check(attest(digest, root)["decision"] == "HOLD_FIXED_SOURCE_UNAVAILABLE")
        leaf.unlink()
        os.mkfifo(leaf)
        check(attest(digest, root)["decision"] == "HOLD_FIXED_SOURCE_UNAVAILABLE")
        leaf.unlink()
        with leaf.open("wb") as handle:
            handle.truncate(LIMIT + 1)
        check(attest(digest, root)["decision"] == "HOLD_FIXED_SOURCE_SIZE")
        leaf.unlink()
        scripts.rmdir()
        scripts.symlink_to(root, target_is_directory=True)
        check(attest(digest, root)["decision"] == "HOLD_FIXED_SOURCE_UNAVAILABLE")
    print("B0_R66_FIXED_SOURCE 9/9 SOURCE_ONLY NATIVE_ACCEPTED=false")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    elif len(sys.argv) == 2:
        print(json.dumps(attest(sys.argv[1]), sort_keys=True))
        raise SystemExit(2)
    else:
        raise SystemExit("usage: selftest OR EXPECTED_SOURCE_SHA256")
