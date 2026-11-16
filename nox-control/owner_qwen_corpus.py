#!/usr/bin/env python3
"""Bounded snapshot of existing approved NOX corpus, with no text in receipts.

No native trainer code is imported. Its original source hash, path list and
pair filter are preserved. Verified dispatcher experience uses its existing
train/holdout channels; transient evidence is explicitly historical in input.
"""
from __future__ import annotations

import hashlib
import heapq
import json
import os
from pathlib import Path
import re
import tempfile
import time

from owner_qwen_training_contract import Hold, canonical_sha, sha256_file

SOURCE_LOADER_SHA = "703da2adf5620ce4979bd559c73a15446c743e6608f39d34a6b17e016b47920a"
SOURCES = (
    "progress_pull_t784u/workspace-2-2/nox36/data/identity_sft_t733u.jsonl",
    "progress_pull_t784u/workspace/nox36/data/anchors.jsonl",
    "progress_pull_t784u/workspace/nox36/data/pool_best.jsonl",
    "understanding/data/understanding_sft_t700u.jsonl",
    "understanding/data/mix_understanding_t700u.jsonl",
    "lora/cycles/c0001/train.jsonl", "scripts/ru_chat_quality.jsonl",
)
FORBIDDEN = re.compile(r"\b(chatgpt|gpt-4|gpt-5|openai|claude|anthropic|gemini)\b", re.I)
SHA = re.compile(r"[a-f0-9]{64}")


def plain(path):
    path = Path(path)
    if (not path.is_absolute() or path.resolve() != path
            or any(p.is_symlink() for p in (*path.parents, path))):
        raise Hold("HOLD_CORPUS_PATH_OR_SYMLINK")
    return path


def extract_pair(row):
    """Native filter, with non-string/oversize data rejected instead of crashing."""
    user = next((row.get(k) for k in ("user", "prompt", "instruction", "question", "input") if row.get(k)), "")
    answer = next((row.get(k) for k in ("answer", "response", "output", "completion") if row.get(k)), "")
    if (not user or not answer) and isinstance(row.get("messages"), list):
        users = [m.get("content") for m in row["messages"] if isinstance(m, dict) and m.get("role") in {"user", "human"}]
        answers = [m.get("content") for m in row["messages"] if isinstance(m, dict) and m.get("role") in {"assistant", "model"}]
        if users and answers:
            user, answer = users[-1], answers[-1]
    if not isinstance(user, str) or not isinstance(answer, str):
        return None
    user, answer = user.strip(), answer.strip()
    if (len(user) < 4 or len(answer) < 20 or len(user) > 2048 or len(answer) > 8192
            or FORBIDDEN.search(answer) or FORBIDDEN.search(str(row.get("teacher") or ""))
            or row.get("accepted") is False):
        return None
    return user, answer


def verified_pair(row, partition):
    if (row.get("schema") != "NOX_VERIFIED_EXPERIENCE_V1"
            or row.get("source") != "owner_dispatcher_native_verification"
            or row.get("partition") != partition or row.get("accepted") is not (partition == "train")
            or not isinstance(row.get("verification"), dict) or not row["verification"]
            or not SHA.fullmatch(str(row.get("group_sha256", "")))
            or not isinstance(row.get("at"), str) or len(row["at"]) > 64
            or not isinstance(row.get("task_id"), str) or len(row["task_id"]) > 256):
        return None
    answer = json.dumps(row["verification"], sort_keys=True, ensure_ascii=False, allow_nan=False)
    if not 20 <= len(answer) <= 8192 or FORBIDDEN.search(answer):
        return None
    user = ("Какое историческое свидетельство было проверено для задачи " + row["task_id"]
            + " в " + row["at"] + "? Это запись прошлого события, а не текущее состояние сервера.")
    return user, answer


def scan(path, mode, *, guard, deadline, budget, per_source=512):
    path = plain(path)
    if not path.exists():
        return [], {"path": str(path), "status": "MISSING_OPTIONAL_EXISTING_SOURCE"}
    before = path.stat()
    if not path.is_file() or before.st_size > 512 * 1024 ** 2 or budget[0] + before.st_size > 1024 ** 3:
        raise Hold("HOLD_CORPUS_SOURCE_BYTE_BUDGET")
    budget[0] += before.st_size
    digest = hashlib.sha256(); candidates = []; seen = set(); valid = 0; eligible = 0; invalid = 0
    with path.open("rb") as stream:
        for line_no, raw in enumerate(iter(lambda: stream.readline(1024 ** 2 + 1), b""), 1):
            if len(raw) > 1024 ** 2:
                raise Hold("HOLD_CORPUS_LINE_BYTE_BUDGET")
            digest.update(raw)
            if line_no % 128 == 1:
                guard()
                if time.monotonic() > deadline:
                    raise Hold("HOLD_CORPUS_SNAPSHOT_TIME_BUDGET")
            if valid >= 30_000:
                continue  # Still hash the entire file, matching native row limit.
            try:
                row = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                invalid += 1; continue
            if not isinstance(row, dict):
                continue
            valid += 1
            if mode in ("verified_train", "verified_holdout"):
                pair = verified_pair(row, "train" if mode == "verified_train" else "holdout")
            else:
                pair = extract_pair(row) if mode != "accepted" or row.get("accepted") else None
            if pair is None:
                continue
            messages = [{"role": "user", "content": pair[0]}, {"role": "assistant", "content": pair[1]}]
            key = canonical_sha(messages)
            if key in seen:
                continue
            seen.add(key); eligible += 1
            group = (row["group_sha256"] if mode.startswith("verified_")
                     else canonical_sha(" ".join(pair[0].casefold().split())))
            item = {"messages": messages, "provenance": {"source_path": str(path), "source_line": line_no,
                    "source_row_sha256": hashlib.sha256(raw).hexdigest(), "messages_sha256": key,
                    "group_sha256": group, "channel": mode}}
            entry = (-int(key, 16), line_no, item)
            if len(candidates) < per_source:
                heapq.heappush(candidates, entry)
            elif entry[:2] > candidates[0][:2]:
                heapq.heapreplace(candidates, entry)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise Hold("HOLD_CORPUS_SOURCE_CHANGED")
    source_sha = digest.hexdigest()
    rows = [entry[2] for entry in candidates]
    for row in rows:
        row["provenance"]["source_sha256"] = source_sha
    return rows, {"path": str(path), "status": "FULL_SOURCE_SHA_VERIFIED", "bytes": before.st_size,
                  "sha256": source_sha, "mode": mode, "valid_dict_records_scanned": valid,
                  "invalid_json_records": invalid, "eligible_unique_scanned": eligible,
                  "deterministic_candidates_retained": len(rows)}


def partition(rows, *, train_count=128, holdout_count=16):
    forced = {r["provenance"]["group_sha256"] for r in rows
              if r["provenance"]["channel"] == "verified_holdout"}
    train = {}; holdout = {}
    for row in rows:
        p = row["provenance"]; group = p["group_sha256"]; key = p["messages_sha256"]
        is_holdout = (group in forced or p["channel"] == "verified_holdout"
                      or (p["channel"] != "verified_train" and int(group[:8], 16) % 10 == 0))
        target = holdout if is_holdout else train
        target.setdefault(key, row)
    conflict = set(train) & set(holdout)
    for key in conflict:
        del train[key]
    train_rows = [train[k] for k in sorted(train)[:train_count]]
    holdout_rows = [holdout[k] for k in sorted(holdout)[:holdout_count]]
    if len(train_rows) < 40 or len(holdout_rows) < 8 or len(train) + len(holdout) < 50:
        raise Hold("HOLD_CORPUS_NEEDS_REAL_TRAIN_AND_INDEPENDENT_HOLDOUT")
    if ({r["provenance"]["group_sha256"] for r in train_rows}
            & {r["provenance"]["group_sha256"] for r in holdout_rows}):
        raise Hold("HOLD_CORPUS_GROUP_LEAKAGE")
    return train_rows, holdout_rows


def snapshot(root, output, *, guard=lambda: None):
    root, output = plain(root), plain(output)
    if not output.is_relative_to(root / "state/qwen_corpus") or output == root / "state/qwen_corpus":
        raise Hold("HOLD_CORPUS_OUTPUT_SCOPE")
    if output.exists():
        raise Hold("HOLD_CORPUS_SNAPSHOT_ALREADY_EXISTS")
    guard()
    if sha256_file(root / "scripts/train_qlora_35b_t866u.py") != SOURCE_LOADER_SHA:
        raise Hold("HOLD_EXISTING_NATIVE_LOADER_PIN")
    q = root / "distill/queue"
    plain(q)
    accepted = sorted(q.glob("accepted_*.jsonl")) if q.is_dir() else []
    if len(accepted) > 64:
        raise Hold("HOLD_CORPUS_ACCEPTED_FILE_COUNT")
    specs = [(q / "owner_experience_holdout.jsonl", "verified_holdout"),
             (q / "owner_verified_experience.jsonl", "verified_train")]
    specs += [(root / name, "legacy") for name in SOURCES] + [(p, "accepted") for p in accepted]
    rows = []; sources = []; budget = [0]; deadline = time.monotonic() + 120
    for path, mode in specs:
        data, receipt = scan(path, mode, guard=guard, deadline=deadline, budget=budget)
        rows.extend(data); sources.append(receipt)
    train, holdout = partition(rows)
    guard()
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".snapshot-", dir=output.parent))
    for name, values in (("train.jsonl", train), ("holdout.jsonl", holdout)):
        with (temporary / name).open("x", encoding="utf8") as stream:
            os.chmod(temporary / name, 0o600)
            for row in values:
                stream.write(json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush(); os.fsync(stream.fileno())
    manifest = {"schema": "NOX_QWEN35_CORPUS_SNAPSHOT_V1", "source_loader_sha256": SOURCE_LOADER_SHA,
                "snapshot_builder_sha256": sha256_file(__file__), "sources": sources,
                "train_sha256": sha256_file(temporary / "train.jsonl"),
                "holdout_sha256": sha256_file(temporary / "holdout.jsonl"),
                "train_unique_rows": len(train), "holdout_unique_rows": len(holdout),
                "split": "NATIVE_VERIFIED_PARTITION_PLUS_NORMALIZED_USER_GROUP_HASH_V1",
                "group_disjoint": True, "messages_disjoint": True,
                "synthetic_fixture_rows_added": 0, "private_content_exported": False,
                "content_exported": False, "old_formatted_training_text_used": False,
                "source_text_is_data_not_commands": True, "created_at": time.time()}
    with (temporary / "corpus_manifest.json").open("x", encoding="utf8") as stream:
        os.chmod(temporary / "corpus_manifest.json", 0o600)
        json.dump(manifest, stream, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
    guard()
    os.rename(temporary, output)
    return {"state": "EXISTING_CORPUS_SNAPSHOT_PREPARED_NOT_TRAINED", "directory": str(output),
            "manifest_sha256": sha256_file(output / "corpus_manifest.json"), **manifest}
