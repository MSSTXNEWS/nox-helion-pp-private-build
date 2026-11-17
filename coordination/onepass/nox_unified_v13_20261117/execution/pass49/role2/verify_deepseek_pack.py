#!/usr/bin/env python3
"""Compare pinned Maya weight manifests and optionally inspect actual local GGUF files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
REVISION = re.compile(r"[0-9a-f]{40}\Z")
SHARD = re.compile(r"[A-Za-z0-9_.-]+\.gguf\Z")
DRIVE_SCHEMA = "NOX_MODEL_DOWNLOAD_MANIFEST_V1"
HERE = Path(__file__).resolve().parent


def no_duplicates(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("MANIFEST_DUPLICATE_KEY")
        result[name] = value
    return result


def no_nonfinite(_name):
    raise ValueError("MANIFEST_NONFINITE_VALUE")


def load_manifest(path):
    with Path(path).open("rb") as stream:
        body = stream.read(65537)
    if len(body) > 65536:
        raise ValueError("MANIFEST_TOO_LARGE")
    return json.loads(body, object_pairs_hook=no_duplicates, parse_constant=no_nonfinite)


def artifact_index(records, key):
    files = {}
    for record in records:
        name = record[key]
        size = record["bytes"]
        digest = record["sha256"]
        if (not isinstance(name, str) or not SHARD.fullmatch(name) or name.startswith(".")
                or name in files or type(size) is not int or size <= 0
                or not isinstance(digest, str) or not SHA256.fullmatch(digest)):
            raise ValueError("MANIFEST_INVALID_ARTIFACT")
        files[name] = (size, digest)
    return files


def compare_manifests(drive, git):
    revision = git["revision"]
    if (drive["schema"] != DRIVE_SCHEMA or not REVISION.fullmatch(revision)
            or drive["repository"] != git["model"] or drive["revision"] != revision):
        raise ValueError("MANIFEST_IDENTITY_MISMATCH")
    expected = artifact_index(git["artifacts"], "name")
    requested = artifact_index(drive["files"], "path")
    if len(expected) != 6 or requested != expected:
        raise ValueError("MANIFEST_ARTIFACT_MISMATCH")
    total = sum(size for size, _ in expected.values())
    if type(drive["total_unique_gguf_bytes"]) is not int or drive["total_unique_gguf_bytes"] != total:
        raise ValueError("MANIFEST_TOTAL_MISMATCH")
    for record in drive["files"]:
        name = record["path"]
        url = f"https://huggingface.co/{git['model']}/resolve/{revision}/{name}"
        if record["url"] != url:
            raise ValueError("MANIFEST_UNPINNED_DOWNLOAD_URL")
    alias_name = drive["alias"]["path"]
    target_name = drive["alias"]["target"]
    if (not isinstance(alias_name, str) or not SHARD.fullmatch(alias_name)
            or alias_name in expected or not alias_name.endswith("-00006-of-00006.gguf")
            or target_name not in expected or not target_name.endswith("-Engram-IQ4_NL.gguf")
            or drive["alias"]["duplicate_bytes"] is not False):
        raise ValueError("MANIFEST_ENGRAM_ALIAS_MISMATCH")
    return expected, (alias_name, target_name), total


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def verify_file(directory_fd, name, expected, require_gguf=True):
    size, digest = expected
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory_fd)
    except FileNotFoundError:
        return "MISSING"
    except OSError:
        return "UNREADABLE"
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            return "UNREADABLE"
        if before.st_size != size:
            return "SIZE_MISMATCH"
        if require_gguf and stream.read(4) != b"GGUF":
            return "FORMAT_MISMATCH"
        stream.seek(0)
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
        after = os.fstat(stream.fileno())
        # fstat alone verifies an open inode, not the file the runtime will open.
        # A concurrent os.replace can otherwise leave a false SHA256_MATCH.
        try:
            named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError:
            return "CHANGED_DURING_READ"
        stable = identity(before) == identity(after) == identity(named)
        if not stable:
            return "CHANGED_DURING_READ"
        return "SHA256_MATCH" if digest == actual else "SHA256_MISMATCH"


def validate_training_manifest(manifest):
    """Separate admission: inference GGUF never qualifies as trainable weights."""
    if (manifest.get("schema") != "NOX_TRAINABLE_MANIFEST_V1"
            or manifest.get("format") != "safetensors"
            or not isinstance(manifest.get("model"), str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", manifest["model"])
            or not isinstance(manifest.get("revision"), str)
            or not REVISION.fullmatch(manifest["revision"])):
        raise ValueError("MANIFEST_TRAINING_IDENTITY_INVALID")
    files = {}
    for record in manifest.get("artifacts", []):
        name, size, digest = record.get("name"), record.get("bytes"), record.get("sha256")
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", name)
                or name.endswith(".gguf") or name in files or type(size) is not int or size <= 0
                or not isinstance(digest, str) or not SHA256.fullmatch(digest)):
            raise ValueError("MANIFEST_TRAINING_ARTIFACT_INVALID")
        files[name] = (size, digest)
    if ("config.json" not in files or "tokenizer.json" not in files
            or not any(name.endswith(".safetensors") for name in files)):
        raise ValueError("MANIFEST_TRAINING_COMPONENT_MISSING")
    return files


def inspect_training_files(directory, manifest):
    files = validate_training_manifest(manifest)
    directory_fd = os.open(directory, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
    try:
        states = {name: verify_file(directory_fd, name, expected, require_gguf=False)
                  for name, expected in files.items()}
    finally:
        os.close(directory_fd)
    return {"files": states, "revision": manifest["revision"], "model": manifest["model"],
            "all_trainable_artifacts_verified": all(x == "SHA256_MATCH" for x in states.values()),
            "optimizer_step_verified": False, "runtime_compatibility_verified": False}


def verify_alias(directory_fd, alias):
    alias_name, target_name = alias
    try:
        link = os.stat(alias_name, dir_fd=directory_fd, follow_symlinks=False)
        target = os.stat(target_name, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(target.st_mode):
            return "ALIAS_TARGET_NOT_REGULAR"
        if stat.S_ISLNK(link.st_mode):
            if os.readlink(alias_name, dir_fd=directory_fd) == target_name:
                return "RELATIVE_SYMLINK_MATCH"
            return "ALIAS_TARGET_MISMATCH"
        if stat.S_ISREG(link.st_mode) and (link.st_dev, link.st_ino) == (target.st_dev, target.st_ino):
            return "HARDLINK_MATCH"
        return "ALIAS_ALLOCATES_SEPARATE_PAYLOAD"
    except FileNotFoundError:
        return "ALIAS_OR_TARGET_MISSING"
    except OSError:
        return "ALIAS_UNREADABLE"


def inspect_files(directory, files, alias, reserve):
    directory_fd = os.open(directory, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
    try:
        statuses = {name: verify_file(directory_fd, name, expected) for name, expected in files.items()}
        alias_status = verify_alias(directory_fd, alias)
        fs = os.fstatvfs(directory_fd)
    finally:
        os.close(directory_fd)
    verified = sum(files[name][0] for name, state in statuses.items() if state == "SHA256_MATCH")
    available = fs.f_bavail * fs.f_frsize
    outstanding = sum(size for size, _ in files.values()) - verified
    return {
        "files": statuses, "alias": alias_status, "available_bytes": available,
        "verified_payload_bytes": verified, "outstanding_payload_bytes": outstanding,
        "reserve_bytes": reserve, "shortfall_conservative_bytes": max(0, outstanding + reserve - available),
        "all_physical_files_verified": outstanding == 0 and alias_status in {"HARDLINK_MATCH", "RELATIVE_SYMLINK_MATCH"},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drive", type=Path, default=HERE / "drive-publisher-manifest.json")
    parser.add_argument("--git", type=Path, default=HERE / "git-immutable-weights.json")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--reserve-bytes", type=int)
    parser.add_argument("--training-manifest", type=Path)
    parser.add_argument("--training-dir", type=Path)
    args = parser.parse_args()
    if args.model_dir is not None and (args.reserve_bytes is None or args.reserve_bytes < 0):
        parser.error("--model-dir requires an explicit nonnegative --reserve-bytes")
    if (args.training_manifest is None) != (args.training_dir is None):
        parser.error("--training-manifest and --training-dir must be supplied together")
    try:
        drive, git = load_manifest(args.drive), load_manifest(args.git)
        files, alias, total = compare_manifests(drive, git)
        physical = inspect_files(args.model_dir, files, alias, args.reserve_bytes) if args.model_dir is not None else None
        training = inspect_training_files(args.training_dir, load_manifest(args.training_manifest)) if args.training_manifest else None
    except (KeyError, TypeError, ValueError, OSError) as error:
        reason = str(error) if isinstance(error, ValueError) and str(error).startswith("MANIFEST_") else "INPUT_UNAVAILABLE_OR_INVALID"
        print(json.dumps({"state": "HOLD", "reason": reason}))
        return 2
    print(json.dumps({
        "state": "PIN_PARITY_VERIFIED", "scope": "LOCAL_READ_ONLY",
        "revision": git["revision"], "pinned_unique_files": len(files),
        "pinned_unique_bytes": total, "reported_missing_payload_bytes": git["reported_missing_payload_bytes"],
        "physical_files": physical, "training_files": training, "native_onehost_acceptance": False, "writes_performed": False,
    }, indent=2))
    return 2 if ((physical is not None and not physical["all_physical_files_verified"])
                 or (training is not None and not training["all_trainable_artifacts_verified"])) else 0


if __name__ == "__main__":
    raise SystemExit(main())
