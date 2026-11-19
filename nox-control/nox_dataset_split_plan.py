#!/usr/bin/env python3
"""Build a deterministic metadata-only RU/ES train/dev/holdout split plan.

This does not read example payloads, contact Drive, train a model or publish data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

INPUT_SCHEMA = "nox.training.source-manifest.v1"
OUTPUT_SCHEMA = "nox.training.split-plan.v1"
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_ROWS = 100_000
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z")
LICENSE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+:-]{0,79}\Z")
LANGUAGES = {"ru", "es"}
TOPICS = {"memory", "speech", "planning", "tools", "code", "behavior"}
SOURCE_KINDS = {"drive", "library", "verified_knowledge", "approved_teacher", "own_action"}
FIELDS = {
    "example_id", "goal_id", "language", "topic", "source_kind",
    "origin_sha256", "content_sha256", "license_id",
}


class Hold(ValueError):
    """The metadata manifest is unsafe or cannot produce an independent split."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise Hold("HOLD_" + code)


def _hash(value: object) -> bool:
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def read_manifest(path: str) -> tuple[dict, str]:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), "MANIFEST_NOT_REGULAR")
        require(info.st_uid == os.geteuid() and not info.st_mode & 0o022,
                "MANIFEST_OWNER_OR_MODE")
        require(0 < info.st_size <= MAX_MANIFEST_BYTES, "MANIFEST_SIZE")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_MANIFEST_BYTES + 1)
        require(len(raw) <= MAX_MANIFEST_BYTES, "MANIFEST_SIZE")
    finally:
        os.close(fd)
    try:
        manifest = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise Hold("HOLD_MANIFEST_JSON") from None
    require(isinstance(manifest, dict)
            and set(manifest) == {"schema", "split_seed", "examples"},
            "MANIFEST_SCHEMA")
    require(manifest["schema"] == INPUT_SCHEMA, "MANIFEST_VERSION")
    seed = manifest["split_seed"]
    require(isinstance(seed, str) and SAFE_ID.fullmatch(seed) is not None,
            "SPLIT_SEED")
    rows = manifest["examples"]
    require(isinstance(rows, list) and 1 <= len(rows) <= MAX_ROWS,
            "EXAMPLE_COUNT")
    return manifest, hashlib.sha256(raw).hexdigest()


def validate_row(row: object) -> dict:
    require(isinstance(row, dict) and set(row) == FIELDS, "EXAMPLE_SCHEMA")
    require(isinstance(row["example_id"], str)
            and SAFE_ID.fullmatch(row["example_id"]) is not None, "EXAMPLE_ID")
    require(isinstance(row["goal_id"], str)
            and SAFE_ID.fullmatch(row["goal_id"]) is not None, "GOAL_ID")
    require(isinstance(row["language"], str) and row["language"] in LANGUAGES,
            "LANGUAGE")
    require(isinstance(row["topic"], str) and row["topic"] in TOPICS, "TOPIC")
    require(isinstance(row["source_kind"], str)
            and row["source_kind"] in SOURCE_KINDS, "SOURCE_KIND")
    require(_hash(row["origin_sha256"]), "ORIGIN_HASH")
    require(_hash(row["content_sha256"]), "CONTENT_HASH")
    require(isinstance(row["license_id"], str)
            and LICENSE_ID.fullmatch(row["license_id"]) is not None,
            "LICENSE_ID")
    return dict(row)


def deduplicate(rows: list[dict]) -> tuple[list[dict], int]:
    ids = [row["example_id"] for row in rows]
    require(len(ids) == len(set(ids)), "DUPLICATE_EXAMPLE_ID")
    by_content: dict[str, dict] = {}
    for row in rows:
        digest = row["content_sha256"]
        existing = by_content.get(digest)
        if existing is None:
            by_content[digest] = {
                "example_ids": {row["example_id"]},
                "goal_id": row["goal_id"],
                "language": row["language"],
                "topic": row["topic"],
                "license_id": row["license_id"],
                "origin_sha256": {row["origin_sha256"]},
                "source_kinds": {row["source_kind"]},
                "content_sha256": digest,
            }
            continue
        require(all(existing[key] == row[key]
                    for key in ("goal_id", "language", "topic", "license_id")),
                "CONTENT_METADATA_CONFLICT")
        existing["example_ids"].add(row["example_id"])
        existing["origin_sha256"].add(row["origin_sha256"])
        existing["source_kinds"].add(row["source_kind"])
    result = []
    for item in by_content.values():
        result.append({
            "example_id": min(item["example_ids"]),
            "duplicate_example_ids": sorted(item["example_ids"]),
            "goal_id": item["goal_id"],
            "language": item["language"],
            "topic": item["topic"],
            "license_id": item["license_id"],
            "origin_sha256": sorted(item["origin_sha256"]),
            "source_kinds": sorted(item["source_kinds"]),
            "content_sha256": item["content_sha256"],
        })
    result.sort(key=lambda item: (item["language"], item["topic"],
                                  item["goal_id"], item["content_sha256"]))
    return result, len(rows) - len(result)


def assign_splits(rows: list[dict], seed: str) -> list[dict]:
    parent = list(range(len(rows)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[max(a, b)] = min(a, b)

    origin_owner: dict[str, int] = {}
    for index, row in enumerate(rows):
        for origin in row["origin_sha256"]:
            previous = origin_owner.setdefault(origin, index)
            union(index, previous)

    groups: dict[int, list[int]] = {}
    for index in range(len(rows)):
        groups.setdefault(find(index), []).append(index)

    split_by_group = {}
    group_by_row = {}
    for root, members in groups.items():
        origins = sorted({origin for index in members
                          for origin in rows[index]["origin_sha256"]})
        group_digest = hashlib.sha256(
            (seed + "\n" + "\n".join(origins)).encode("ascii")
        ).hexdigest()
        bucket = int(group_digest[:8], 16) % 100
        split = "train" if bucket < 80 else ("dev" if bucket < 90 else "holdout")
        split_by_group[root] = (split, group_digest)
        for index in members:
            group_by_row[index] = root

    output = []
    for index, row in enumerate(rows):
        split, group_digest = split_by_group[group_by_row[index]]
        output.append({**row, "split": split, "split_group_sha256": group_digest})
    return output


def coverage(rows: list[dict]) -> tuple[list[dict], list[str]]:
    strata = sorted({(row["language"], row["topic"]) for row in rows})
    reports, holds = [], []
    for language, topic in strata:
        selected = [row for row in rows
                    if row["language"] == language and row["topic"] == topic]
        counts = {split: sum(row["split"] == split for row in selected)
                  for split in ("train", "dev", "holdout")}
        groups = {split: len({row["split_group_sha256"] for row in selected
                              if row["split"] == split})
                  for split in ("train", "dev", "holdout")}
        missing = [split for split, count in counts.items() if count == 0]
        reasons = []
        if len({row["split_group_sha256"] for row in selected}) < 3:
            reasons.append("FEWER_THAN_THREE_INDEPENDENT_SOURCE_GROUPS")
        if missing:
            reasons.append("MISSING_SPLITS:" + ",".join(missing))
        if reasons:
            holds.append(language + "/" + topic + ":" + ";".join(reasons))
        reports.append({"language": language, "topic": topic,
                        "counts": counts, "source_groups": groups,
                        "hold_reasons": reasons})
    return reports, holds


def build_plan(manifest: dict, manifest_sha256: str) -> dict:
    rows = [validate_row(row) for row in manifest["examples"]]
    unique, duplicates_removed = deduplicate(rows)
    planned = assign_splits(unique, manifest["split_seed"])
    strata, holds = coverage(planned)
    counts = {split: sum(row["split"] == split for row in planned)
              for split in ("train", "dev", "holdout")}
    return {
        "schema": OUTPUT_SCHEMA,
        "state": "SPLIT_PLAN_READY" if not holds else "HOLD_SPLIT_COVERAGE",
        "input_manifest_sha256": manifest_sha256,
        "split_seed": manifest["split_seed"],
        "ratios_percent": {"train": 80, "dev": 10, "holdout": 10},
        "input_rows": len(rows),
        "deduplicated_rows": len(unique),
        "duplicates_removed": duplicates_removed,
        "split_counts": counts,
        "coverage": strata,
        "hold_reasons": holds,
        "examples": planned,
        "payloads_read": 0,
        "drive_requests": 0,
        "writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a metadata-only, deterministic RU/ES split plan.")
    parser.add_argument("--manifest", required=True,
                        help="Owner-prepared metadata-only manifest; no payload text.")
    args = parser.parse_args(argv)
    try:
        manifest, digest = read_manifest(args.manifest)
        result = build_plan(manifest, digest)
    except (OSError, Hold) as exc:
        code = str(exc) if isinstance(exc, Hold) else "HOLD_MANIFEST_IO"
        print(json.dumps({"schema": OUTPUT_SCHEMA, "state": code},
                         sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True,
                     separators=(",", ":")))
    return 0 if result["state"] == "SPLIT_PLAN_READY" else 3


if __name__ == "__main__":
    raise SystemExit(main())
