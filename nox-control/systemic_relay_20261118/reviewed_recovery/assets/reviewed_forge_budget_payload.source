#!/usr/bin/env python3
"""Fail-closed local verification of pinned train/dev/holdout JSONL splits.

This is an offline data-integrity check, NOT proof that a cited licence is valid,
that a trainer ran, or that a native writer lease was granted. It prints no
sample text, usernames, prompts, or answers.
"""
import argparse
import hashlib
import json
import math
import os
import re
import stat
import unicodedata
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

SPLITS = ("train", "dev", "holdout")
TASKS = {"memory", "speech", "planning", "tools", "code", "behavior"}
LANGS = {"ru", "es"}
HEX = re.compile(r"[0-9a-f]{64}\Z")
UNVERIFIED_LICENSES = {"unknown", "unverified", "unspecified", "none",
                       "all rights reserved", "proprietary", "no training",
                       "not for training"}


def no_duplicate_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def reject_nonfinite(token):
    raise ValueError("NONFINITE_JSON")


def parse_finite_float(token):
    """Reject JSON float exponents that overflow into Infinity."""
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("NONFINITE_JSON")
    return value


def normalize(s):
    return " ".join(unicodedata.normalize("NFKC", s).casefold().split())


def sha(data):
    return hashlib.sha256(data).hexdigest()


# RFC 3986: encoded ASCII unreserved octets identify the same URI.
# Do not decode reserved escapes or apply recursive percent-decoding.
_URI_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_URI_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")
_URI_BAD_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")


def source_component_key(component):
    if _URI_BAD_ESCAPE.search(component):
        raise ValueError("MALFORMED_SOURCE_URL_ESCAPE")

    def normalized(match):
        char = chr(int(match.group(1), 16))
        return char if char in _URI_UNRESERVED else "%" + match.group(1).upper()

    return _URI_ESCAPE.sub(normalized, component)


def read_pinned_manifest(path):
    """Reject blocking/symlink/oversized manifests before parsing or hashing."""
    flags = (os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
             | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("MANIFEST_NOT_SINGLE_REGULAR_FILE")
        if before.st_size > 1_000_000:
            raise ValueError("MANIFEST_OVERSIZE")
        with os.fdopen(os.dup(fd), "rb") as stream:
            payload = stream.read(1_000_001)
        after = os.fstat(fd)
        if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise ValueError("MANIFEST_CHANGED_DURING_READ")
        if len(payload) > 1_000_000:
            raise ValueError("MANIFEST_OVERSIZE")
        return payload
    finally:
        os.close(fd)


def bounded_split_lines(stream, initial_size, row_limit):
    """Read raw chunks within the initial size and one growth-detection byte.

    The caller owns an unbuffered stream, so its reads cannot prefetch past
    this budget. No row beyond the declared count reaches the JSON parser.
    """
    remaining, emitted, start = initial_size, 0, 0
    pending = bytearray()
    while True:
        if emitted >= row_limit and len(pending) > start:
            raise ValueError("SPLIT_ROWS_EXCEEDED")
        end = pending.find(b"\n", start)
        if end >= 0:
            raw = bytes(pending[start:end + 1])
            if len(raw) > 2_000_000:
                raise ValueError("EMPTY_OR_OVERSIZE_ROW")
            start = end + 1
            emitted += 1
            yield raw
            continue
        # Compact once per chunk, not once for every short JSONL row.
        if start:
            del pending[:start]
            start = 0
        if len(pending) > 2_000_000:
            raise ValueError("EMPTY_OR_OVERSIZE_ROW")
        size = min(65_536, remaining + 1, 2_000_001 - len(pending))
        if emitted >= row_limit:
            size = min(size, 1)
        chunk = stream.read(size)
        if len(chunk) > remaining:
            raise ValueError("SPLIT_FILE_GREW")
        if not chunk:
            if pending:
                yield bytes(pending)
            return
        remaining -= len(chunk)
        pending.extend(chunk)


def validate(root, manifest_path, expected_manifest_sha):
    if not isinstance(expected_manifest_sha, str) or not HEX.fullmatch(expected_manifest_sha):
        raise ValueError("MANIFEST_SHA_REQUIRED")
    manifest_bytes = read_pinned_manifest(manifest_path)
    if sha(manifest_bytes) != expected_manifest_sha:
        raise ValueError("MANIFEST_SHA_MISMATCH")
    manifest = json.loads(manifest_bytes, object_pairs_hook=no_duplicate_keys,
                          parse_constant=reject_nonfinite, parse_float=parse_finite_float)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("splits"), dict) or set(manifest["splits"]) != set(SPLITS):
        raise ValueError("EXACT_TRAIN_DEV_HOLDOUT_REQUIRED")
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("CORPUS_DIRECTORY_REQUIRED")
    seen_ids, seen_origin, seen_source, seen_prompt, seen_url = {}, {}, {}, {}, {}
    coverage = {name: {"rows": 0, "languages": set(), "tasks": set(), "pairs": set(), "sha256": ""} for name in SPLITS}

    def check_cross(key, tag, split, unique_within=False):
        previous = key.get(tag)
        if previous is not None:
            if previous != split:
                raise ValueError("CROSS_SPLIT_LEAKAGE")
            if unique_within:
                raise ValueError("DUPLICATE_WITHIN_SPLIT")
        key[tag] = split

    for split in SPLITS:
        spec = manifest["splits"][split]
        if not isinstance(spec, dict):
            raise ValueError("BAD_SPLIT_SPEC")
        name = spec.get("path")
        if not isinstance(name, str) or not name or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or "\\" in name or PurePosixPath(name).as_posix() != name:
            raise ValueError("UNSAFE_SPLIT_PATH")
        if not isinstance(spec.get("sha256"), str) or not HEX.fullmatch(spec["sha256"]):
            raise ValueError("SPLIT_SHA_REQUIRED")
        if type(spec.get("rows")) is not int or spec["rows"] < 1:
            raise ValueError("SPLIT_ROWS_REQUIRED")
        candidate = root / name
        for parent in [candidate, *list(candidate.parents)[:-1]]:
            if parent == root:
                break
            if parent.is_symlink():
                raise ValueError("SPLIT_SYMLINK_REJECTED")
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(candidate, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError("SPLIT_NOT_SINGLE_REGULAR_FILE")
            digest = hashlib.sha256()
            with os.fdopen(os.dup(fd), "rb", buffering=0) as stream:
                for raw in bounded_split_lines(stream, before.st_size, spec["rows"]):
                    if len(raw) > 2_000_000 or not raw.strip():
                        raise ValueError("EMPTY_OR_OVERSIZE_ROW")
                    digest.update(raw)
                    row = json.loads(raw, object_pairs_hook=no_duplicate_keys,
                                     parse_constant=reject_nonfinite, parse_float=parse_finite_float)
                    if not isinstance(row, dict):
                        raise ValueError("BAD_SAMPLE")
                    for field in ("sample_id", "origin_id", "source_sha256", "source_url", "license", "language", "task", "goal", "prompt", "response"):
                        if not isinstance(row.get(field), str) or not row[field].strip():
                            raise ValueError("SAMPLE_FIELD_MISSING")
                    if not HEX.fullmatch(row["source_sha256"]):
                        raise ValueError("SOURCE_SHA_REQUIRED")
                    source_url = urlsplit(row["source_url"])
                    if (source_url.scheme != "https" or not source_url.hostname
                            or source_url.username is not None
                            or source_url.password is not None or source_url.fragment):
                        raise ValueError("SOURCE_URL_REQUIRED")
                    if normalize(row["license"]) in UNVERIFIED_LICENSES:
                        raise ValueError("LICENSE_REVIEW_REQUIRED")
                    if row["language"] not in LANGS or row["task"] not in TASKS:
                        raise ValueError("LANGUAGE_OR_TASK_UNKNOWN")
                    prompt_digest = sha(normalize(row["prompt"]).encode("utf-8"))
                    check_cross(seen_ids, row["sample_id"], split, unique_within=True)
                    check_cross(seen_origin, row["origin_id"], split, unique_within=True)
                    check_cross(seen_source, row["source_sha256"], split)
                    # Split by source document as well as origin/sample hashes: a
                    # revised document with new bytes must not enter holdout.
                    # Hostnames are case-insensitive; paths and queries retain
                    # their exact identities to avoid speculative URL merging.
                    source_key = (source_url.scheme, source_url.hostname.casefold().rstrip("."),
                                  source_url.port or 443, source_component_key(source_url.path),
                                  source_component_key(source_url.query))
                    check_cross(seen_url, source_key, split)
                    check_cross(seen_prompt, prompt_digest, split)
                    coverage[split]["rows"] += 1
                    coverage[split]["languages"].add(row["language"])
                    coverage[split]["tasks"].add(row["task"])
                    coverage[split]["pairs"].add((row["language"], row["task"]))
            after = os.fstat(fd)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError("SPLIT_CHANGED_DURING_READ")
            if digest.hexdigest() != spec["sha256"] or coverage[split]["rows"] != spec["rows"]:
                raise ValueError("SPLIT_SHA_OR_COUNT_MISMATCH")
            if coverage[split]["languages"] != LANGS:
                raise ValueError("RU_ES_COVERAGE_REQUIRED_PER_SPLIT")
            # A global union can hide a missing evaluation category in dev
            # or holdout. Each independent split must cover the declared tasks.
            if coverage[split]["tasks"] != TASKS:
                raise ValueError("TASK_COVERAGE_REQUIRED_PER_SPLIT")
            if coverage[split]["pairs"] != {(lang, task) for lang in LANGS for task in TASKS}:
                raise ValueError("LANGUAGE_TASK_COVERAGE_REQUIRED_PER_SPLIT")
            coverage[split]["sha256"] = digest.hexdigest()
        finally:
            os.close(fd)
    if set.union(*(coverage[s]["tasks"] for s in SPLITS)) != TASKS:
        raise ValueError("TASK_COVERAGE_REQUIRED")
    return {"status": "SOURCE_SPLITS_VERIFIED", "training_started": False,
            "licence_authenticity_independently_verified": False,
            "manifest_sha256": expected_manifest_sha,
            "coverage": {s: {"rows": c["rows"], "languages": sorted(c["languages"]),
                             "tasks": sorted(c["tasks"]), "sha256": c["sha256"]}
                         for s, c in coverage.items()},
            "cross_split_duplicates": 0}


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--manifest-sha256", required=True)
    p.add_argument("--corpus-dir", type=Path, required=True)
    args = p.parse_args()
    try:
        result = validate(args.corpus_dir, args.manifest, args.manifest_sha256)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"status": "HOLD", "training_started": False,
                  "reason": str(exc)[:256]}
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "SOURCE_SPLITS_VERIFIED" else 2

if __name__ == "__main__":
    raise SystemExit(main())
