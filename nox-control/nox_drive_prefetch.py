#!/usr/bin/env python3
"""NOX Drive -> verified SSD / RAM warm-cache, owner-scoped and non-destructive.

This is a standalone staging utility, NOT a model loader or trainer. It never
changes active model paths, removes existing weights, or handles OAuth tokens.
Run with an explicit manifest SHA-256 and owner-authorized environment.
"""
from __future__ import annotations

import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time

GiB = 1024 ** 3
BLOCK = 8 * 1024 ** 2
SCHEMA = "nox.drive.prefetch.v1"
RECEIPT = "nox.drive.verified.v1"
SHA = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
REMOTE = re.compile(r"[A-Za-z0-9_-]+:[A-Za-z0-9_./-]+\Z")
SUFFIXES = {".gguf", ".safetensors", ".bin", ".pt", ".pth"}
# Exact parts consumed by the existing IQ3_XXS cold holder. The revision is
# 81fd6e0a6f063344001bdecc6119ac53c80c8e63 and each SHA is its LFS object ID.
ENGRAM_PARTS = {
    "engram.part00": (21474836480, "eecf98d8cd45239811f8f7b881b6e7175feacf1cd1f53aeb8bc5bce30be08429"),
    "engram.part01": (21474836480, "b9834592fda5eecedeed545adc802e2f1d68e2442680aca2e20f87c4ae669271"),
    "engram.part02": (21474836480, "97d483a3da717acb155eec046b1347c0060e06cd6e8337c294ab27363a61a203"),
    "engram.part03": (10841730276, "286828e9f44bd80093856f27c55611068baa6b168fd2a6738533d615ec2b9357"),
}
BLOCKED = {"s03", "checkpoints", "checkpoint", "optimizer", "training", "database", "sqlite"}
STOP = ["/root/nox/STOP", "/root/nox/STOP.flag", "/root/nox/state/STOP",
        "/root/nox/state/DRIVE_STOP.flag", "/root/nox/state/OWNER_MAINTENANCE.flag",
        "/workspace/NOX_STOP"]


class Hold(Exception):
    pass


def check(ok, code):
    if not ok:
        raise Hold("HOLD_DRIVE_" + code)


def sha_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(BLOCK), b""):
            h.update(block)
    return h.hexdigest()


def stopped(paths=STOP):
    return any(os.path.lexists(p) for p in paths)


def check_directory(path):
    path = Path(os.path.abspath(path))
    check(path.is_dir(), "DESTINATION_MISSING")
    check(not path.is_symlink() and not any(p.is_symlink() for p in path.parents), "SYMLINK")
    st = path.stat()
    check(st.st_uid == os.geteuid() and not st.st_mode & 0o022, "DESTINATION_PERMS")
    return path


def read_manifest(path, digest):
    check(bool(SHA.fullmatch(digest)), "EXPECTED_MANIFEST_HASH")
    path = Path(path)
    check(path.is_file() and not path.is_symlink() and path.stat().st_size <= 65536, "MANIFEST_FILE")
    data = path.read_bytes()
    check(hashlib.sha256(data).hexdigest() == digest, "MANIFEST_MISMATCH")
    try:
        m = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        raise Hold("HOLD_DRIVE_MANIFEST_JSON")
    check(isinstance(m, dict) and set(m) == {"schema", "remote", "assets"}, "MANIFEST_SCHEMA")
    check(m["schema"] == SCHEMA, "MANIFEST_VERSION")
    remote = m["remote"]
    check(isinstance(remote, str) and REMOTE.fullmatch(remote)
          and ".." not in remote and not remote.endswith("/"), "REMOTE")
    assets = m["assets"]
    check(isinstance(assets, list) and 0 < len(assets) <= 32, "ASSET_COUNT")
    seen = set()
    for a in assets:
        check(isinstance(a, dict) and set(a) == {"name", "size", "sha256"}, "ASSET_SCHEMA")
        n = a["name"]
        check(isinstance(n, str) and NAME.fullmatch(n)
              and (Path(n).suffix.lower() in SUFFIXES or n in ENGRAM_PARTS)
              and not any(word in n.lower().split(".") for word in BLOCKED), "ASSET_NAME")
        check(n not in seen, "ASSET_DUPLICATE")
        seen.add(n)
        check(type(a["size"]) is int and 0 < a["size"] <= 512 * GiB, "ASSET_SIZE")
        check(isinstance(a["sha256"], str) and SHA.fullmatch(a["sha256"]), "ASSET_HASH")
        if n in ENGRAM_PARTS:
            check((a["size"], a["sha256"]) == ENGRAM_PARTS[n], "ENGRAM_PART_PIN")
    if seen.intersection(ENGRAM_PARTS):
        check(ENGRAM_PARTS.keys() <= seen, "ENGRAM_PARTS_INCOMPLETE")
    return m


def cgroup_raw_free(root="/sys/fs/cgroup"):
    try:
        maximum = (Path(root) / "memory.max").read_text().strip()
        if maximum == "max":
            # Unbounded/unknown cgroup budget is not evidence of safe RAM headroom.
            return 0
        return max(0, int(maximum) - int((Path(root) / "memory.current").read_text().strip()))
    except (OSError, ValueError):
        return 0


def requires_space(dest, size, *, ram, raw_free=None):
    free = shutil.disk_usage(dest).free
    check(free >= size + (4 if ram else 2) * GiB, "SPACE")
    if ram:
        # Inactive file cache is not counted as free RAM: never force reclaim to stage.
        raw_free = cgroup_raw_free() if raw_free is None else raw_free
        # Never skip RAM admission when the cgroup limit is unknown or malformed.
        check(type(raw_free) is int and raw_free >= size + 4 * GiB, "CGROUP_RAM")
    return free


def verified_hit(file, a, manifest_hash):
    meta = file.with_name(file.name + ".receipt.json")
    if not file.is_file() or file.is_symlink() or not meta.is_file() or meta.is_symlink():
        return False
    try:
        st = file.stat()
        doc = json.loads(meta.read_text())
        return (st.st_uid == os.geteuid() and st.st_nlink == 1
                and not st.st_mode & 0o022 and st.st_size == a["size"]
                and doc.get("schema") == RECEIPT and doc.get("manifest_sha256") == manifest_hash
                and doc.get("sha256") == a["sha256"] and doc.get("size") == a["size"]
                and doc.get("ino") == st.st_ino and doc.get("mtime_ns") == st.st_mtime_ns
                and doc.get("ctime_ns") == st.st_ctime_ns and doc.get("verified") is True)
    except (OSError, ValueError, TypeError):
        return False


def atomic_json(path, value):
    raw = (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")
    temp = path.with_name("." + path.name + ".new")
    fd = os.open(temp, os.O_WRONLY | os.O_EXCL | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def copy_with_stop(command, *, poll=0.3):
    with subprocess.Popen(command, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL) as child:
        while child.poll() is None:
            if stopped():
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                raise Hold("HOLD_DRIVE_STOP")
            time.sleep(poll)
        check(child.returncode == 0, "TRANSFER_FAILED")


def receipt(path, asset, manifest_hash):
    s = path.stat()
    atomic_json(path.with_name(path.name + ".receipt.json"), {
        "schema": RECEIPT, "manifest_sha256": manifest_hash,
        "sha256": asset["sha256"], "size": asset["size"],
        "ino": s.st_ino, "mtime_ns": s.st_mtime_ns, "ctime_ns": s.st_ctime_ns,
        "verified": True, "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })


def stage_one(manifest, asset, manifest_sha, dest, *, from_dir=None, ram=False):
    check(not stopped(), "STOP")
    target = dest / asset["name"]
    if verified_hit(target, asset, manifest_sha):
        return {"asset": asset["name"], "result": "CACHE_HIT"}
    check(not target.exists() and not target.is_symlink(), "UNVERIFIED_DESTINATION")
    requires_space(dest, asset["size"], ram=ram)
    temp = dest / ("." + asset["name"] + ".nox-partial")
    check(not temp.exists() and not temp.is_symlink(), "PARTIAL_ALREADY_EXISTS")
    try:
        if from_dir is not None:
            original = from_dir / asset["name"]
            check(verified_hit(original, asset, manifest_sha), "SSD_NOT_VERIFIED")
            # Copy without shell, copy into owned partial only.
            with original.open("rb") as src, temp.open("xb") as out:
                os.chmod(temp, 0o600)
                while True:
                    check(not stopped(), "STOP")
                    chunk = src.read(BLOCK)
                    if not chunk:
                        break
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
        else:
            check(bool(shutil.which("rclone")), "RCLONE_MISSING")
            command = ["rclone", "copyto", manifest["remote"] + "/" + asset["name"],
                       str(temp), "--transfers", "1", "--checkers", "2",
                       "--multi-thread-streams", "4", "--multi-thread-chunk-size", "8M",
                       "--buffer-size", "8M", "--tpslimit", "4", "--retries", "3",
                       "--low-level-retries", "3", "--stats", "0", "--log-level", "ERROR"]
            copy_with_stop(command)
        check(temp.is_file() and not temp.is_symlink(), "PARTIAL_MISSING")
        check(temp.stat().st_size == asset["size"] and sha_file(temp) == asset["sha256"],
              "FILE_HASH_MISMATCH")
        os.chmod(temp, 0o600)
        # Hard-link exposes completed bytes atomically and refuses to replace existing file.
        check(not stopped(), "STOP")
        os.link(temp, target, follow_symlinks=False)
        temp.unlink()
        receipt(target, asset, manifest_sha)
        return {"asset": asset["name"], "result": "VERIFIED_NEW"}
    finally:
        # Only the owned temporary file may be deleted; originals are preserved.
        temp.unlink(missing_ok=True)


def run(args):
    m = read_manifest(args.manifest, args.manifest_sha)
    dest = check_directory(args.destination)
    ram = args.mode == "ram"
    if ram:
        # Engram RAM is assembled and verified as one memfd by the cold holder.
        check(not any(a["name"] in ENGRAM_PARTS for a in m["assets"]), "ENGRAM_PARTS_DISK_ONLY")
        check(dest.is_relative_to(Path("/dev/shm")), "RAM_DEST")
        check(args.ssd is not None, "RAM_REQUIRES_SSD")
    source = check_directory(args.ssd) if args.ssd else None
    if source:
        check(source != dest, "SAME_SOURCE_DEST")
    if not args.execute:
        return {"schema": SCHEMA, "state": "PLAN_ONLY",
                "assets": [a["name"] for a in m["assets"]],
                "destination": str(dest), "mode": args.mode}
    lock_path = dest / ".nox-drive-prefetch.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        st = os.fstat(fd)
        check(stat.S_ISREG(st.st_mode) and st.st_nlink == 1
              and st.st_uid == os.geteuid() and not st.st_mode & 0o077, "LOCK")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Hold("HOLD_DRIVE_BUSY")
        output = []
        for a in m["assets"]:
            output.append(stage_one(m, a, args.manifest_sha, dest,
                                    from_dir=source, ram=ram))
        return {"schema": SCHEMA, "state": "VERIFIED_STAGE_NOT_LOADED",
                "mode": args.mode, "assets": output}
    finally:
        os.close(fd)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True)
    p.add_argument("--manifest-sha", required=True)
    p.add_argument("--destination", required=True)
    p.add_argument("--mode", choices=["disk", "ram"], default="disk")
    p.add_argument("--ssd", help="Exact verified SSD cache for RAM copy")
    p.add_argument("--execute", action="store_true", help="Actually transfer weights")
    args = p.parse_args(argv)
    try:
        print(json.dumps(run(args), sort_keys=True))
        return 0
    except Hold as e:
        print(json.dumps({"schema": SCHEMA, "state": str(e)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
