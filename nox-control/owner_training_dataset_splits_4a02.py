"""NOX 4A02 source-only RU/ES train/dev/holdout splitter.

No dataset is downloaded, no training is started, and this module cannot mint
original295 acceptance. Output is a content-hash/provenance manifest, not data.
A trusted operator must verify source licenses and native acceptance separately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import unicodedata

LANGUAGES = ("ru", "es")
DOMAINS = ("memory", "speech", "planning", "tools", "code", "behavior")
SCHEMA = "NOX_4A02_PROVENANCE_SPLIT_SOURCE_V1"


class SplitHold(ValueError):
    """Reject insufficient or ambiguous evidence rather than leak holdout."""


def _norm(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _digest(value):
    return hashlib.sha256(value.encode("utf-8", "strict")).hexdigest()


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SplitHold("HOLD_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def split_manifest(records, *, seed="nox-4a02-v1"):
    """Stable grouped splits; the same origin+goal never enters two partitions.

    Each of twelve RU/ES × domain strata needs at least three independent
    origin+goal groups. Exact/normalized duplicate examples are removed only
    within a group; cross-group duplicates HOLD for explicit provenance review.
    """
    if type(seed) is not str or not 1 <= len(seed) <= 128:
        raise SplitHold("HOLD_SEED")
    groups = {}
    seen_ids = set()
    seen_content = {}
    duplicate_count = 0
    count = 0
    for row in records:
        count += 1
        if count > 300000 or type(row) is not dict:
            raise SplitHold("HOLD_INPUT_LIMIT_OR_SHAPE")
        for field in ("id", "lang", "domain", "goal", "text", "source_id", "license"):
            if type(row.get(field)) is not str or not row[field].strip():
                raise SplitHold("HOLD_REQUIRED_PROVENANCE")
        if (row["lang"] not in LANGUAGES or row["domain"] not in DOMAINS
                or len(row["id"]) > 200 or len(row["goal"]) > 2000
                or len(row["text"]) > 262144 or len(row["source_id"]) > 1000
                or len(row["license"]) > 200):
            raise SplitHold("HOLD_DATASET_FIELD")
        if row["id"] in seen_ids:
            raise SplitHold("HOLD_DUPLICATE_RECORD_ID")
        seen_ids.add(row["id"])
        goal = _norm(row["goal"])
        origin = _norm(row["source_id"])
        if not goal or not origin or not _norm(row["text"]):
            raise SplitHold("HOLD_EMPTY_NORMALIZED_FIELD")
        group = (row["lang"], row["domain"], origin, goal)
        fingerprint = _digest(_norm(row["text"]))
        prior = seen_content.get(fingerprint)
        if prior is not None:
            if prior != group:
                raise SplitHold("HOLD_CROSS_GROUP_DUPLICATE")
            duplicate_count += 1
            continue
        seen_content[fingerprint] = group
        groups.setdefault(group, []).append({
            "record_id": row["id"],
            "raw_sha256": _digest(row["text"]),
            "normalized_sha256": fingerprint,
            "source_id": row["source_id"],
            "license_claim": row["license"],
        })

    if count == 0:
        raise SplitHold("HOLD_NO_DATA")
    split_rows = {"train": [], "dev": [], "holdout": []}
    coverage = {}
    group_splits = {}
    for lang in LANGUAGES:
        for domain in DOMAINS:
            stratum = (lang, domain)
            keys = [key for key in groups if key[:2] == stratum]
            if len(keys) < 3:
                raise SplitHold("HOLD_INSUFFICIENT_INDEPENDENT_GROUPS:" + lang + ":" + domain)
            # Sort by a seed-bound hash, not input order or raw dataset text.
            keys.sort(key=lambda key: (_digest(seed + "\x1f" + "\x1f".join(key)), key))
            n = len(keys)
            dev = max(1, math.ceil(n * .15))
            holdout = max(1, math.ceil(n * .15))
            if dev + holdout >= n:
                raise SplitHold("HOLD_SPLIT_COVERAGE")
            partition = (["dev"] * dev + ["holdout"] * holdout
                         + ["train"] * (n - dev - holdout))
            coverage[lang + ":" + domain] = {"groups": n, "train": n - dev - holdout,
                                               "dev": dev, "holdout": holdout}
            for key, dest in zip(keys, partition):
                group_sha = _digest("\x1f".join(key))
                if group_sha in group_splits:
                    raise SplitHold("HOLD_GROUP_COLLISION")
                group_splits[group_sha] = dest
                for item in groups[key]:
                    split_rows[dest].append({
                        "id": item["record_id"], "lang": lang, "domain": domain,
                        "group_sha256": group_sha, **item,
                    })
    for rows in split_rows.values():
        rows.sort(key=lambda row: row["id"])
    manifest = {
        "schema": SCHEMA, "seed": seed,
        "status": "SOURCE_MANIFEST_ONLY_NOT_NATIVE_ACCEPTED",
        "license_review": "DECLARED_ONLY_NOT_INDEPENDENTLY_VERIFIED",
        "counts": {"input": count, "deduplicated": duplicate_count,
                   "kept": sum(len(rows) for rows in split_rows.values())},
        "coverage": coverage, "splits": split_rows,
    }
    canonical = json.dumps(manifest, sort_keys=True, ensure_ascii=False,
                           allow_nan=False, separators=(",", ":"))
    manifest["manifest_sha256"] = _digest(canonical)
    return manifest


def write_manifest(path, manifest):
    """Atomic same-directory publish; never create partial verified manifests."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise SplitHold("HOLD_OUTPUT_SYMLINK")
    fd, temp = tempfile.mkstemp(dir=str(target.parent), prefix=".nox4a02-",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as sink:
            json.dump(manifest, sink, sort_keys=True, ensure_ascii=False, indent=2,
                      allow_nan=False)
            sink.write("\n")
            sink.flush()
            os.fsync(sink.fileno())
        if target.is_symlink():
            raise SplitHold("HOLD_OUTPUT_SYMLINK")
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Source-only NOX 4A02 split manifest")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", default="nox-4a02-v1")
    args = parser.parse_args(argv)
    def rows():
        with args.input.open("r", encoding="utf-8") as source:
            for line in source:
                if len(line) > 300000:
                    raise SplitHold("HOLD_INPUT_LINE_SIZE")
                if line.strip():
                    yield json.loads(line, object_pairs_hook=_strict_object,
                                     parse_constant=lambda _: (_ for _ in ()).throw(
                                         SplitHold("HOLD_NONFINITE_JSON")))
    write_manifest(args.output, split_manifest(rows(), seed=args.seed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
