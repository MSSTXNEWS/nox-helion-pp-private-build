#!/usr/bin/env python3
"""Paired RU/ES speech transcript WER report, split by noise label.

Input is a local CSV with columns: language, noise, reference, before, after.
The tool emits aggregates only; it never copies transcript text or case IDs to
the report. It does not load audio or call a network service.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

SCHEMA = "NOX_RU_ES_ASR_WER_V1"
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_ROWS = 5000
MAX_TEXT_CHARS = 4096
MAX_TOKENS_PER_UTTERANCE = 200
MAX_GROUPS = 64
MAX_ALIGNMENT_CELLS = 50_000_000
REQUIRED_COLUMNS = ("language", "noise", "reference", "before", "after")
NOISE_LABEL = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")


class InputError(ValueError):
    """Sanitized input-contract failure; message contains no transcript text."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize_transcript(value: str) -> list[str]:
    value = unicodedata.normalize("NFC", value).casefold()
    chars = []
    for char in value:
        if unicodedata.category(char).startswith("P"):
            chars.append(" ")
        else:
            chars.append(char)
    return " ".join("".join(chars).split()).split()


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    # Levenshtein distance with O(min(n, m)) memory.
    if len(hypothesis) > len(reference):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for row_index, ref_word in enumerate(reference, start=1):
        current = [row_index]
        for column_index, hyp_word in enumerate(hypothesis, start=1):
            substitution = previous[column_index - 1] + (ref_word != hyp_word)
            insertion = current[column_index - 1] + 1
            deletion = previous[column_index] + 1
            current.append(min(substitution, insertion, deletion))
        previous = current
    return previous[-1]


def normalize_language(value: str, row_number: int) -> str:
    language = value.strip().casefold().replace("_", "-")
    if language in ("ru", "ru-ru"):
        return "ru"
    if language in ("es", "es-es"):
        return "es"
    raise InputError(f"row {row_number}: language must be ru, ru-RU, es, or es-ES")


def parse_label(value: str, row_number: int) -> str:
    label = value.strip().casefold()
    if not NOISE_LABEL.fullmatch(label):
        raise InputError(f"row {row_number}: noise must be a short ASCII label")
    return label


def new_bucket() -> dict:
    return {
        "cases": 0,
        "reference_words": 0,
        "before_errors": 0,
        "after_errors": 0,
        "before_wins": 0,
        "after_wins": 0,
        "ties": 0,
    }


def add_case(bucket: dict, ref_count: int, before_errors: int, after_errors: int) -> None:
    bucket["cases"] += 1
    bucket["reference_words"] += ref_count
    bucket["before_errors"] += before_errors
    bucket["after_errors"] += after_errors
    if after_errors < before_errors:
        bucket["after_wins"] += 1
    elif after_errors > before_errors:
        bucket["before_wins"] += 1
    else:
        bucket["ties"] += 1


def percent(errors: int, words: int) -> float:
    return round(errors * 100.0 / words, 6)


def summarize(bucket: dict) -> dict:
    words = bucket["reference_words"]
    before = percent(bucket["before_errors"], words)
    after = percent(bucket["after_errors"], words)
    return {
        "cases": bucket["cases"],
        "reference_words": words,
        "before_edit_errors": bucket["before_errors"],
        "after_edit_errors": bucket["after_errors"],
        "before_wer_percent": before,
        "after_wer_percent": after,
        "wer_delta_percentage_points": round(after - before, 6),
        "cases_improved": bucket["after_wins"],
        "cases_regressed": bucket["before_wins"],
        "cases_tied": bucket["ties"],
    }


def build_report(raw: bytes, before_revision: str, after_revision: str) -> dict:
    if not raw or len(raw) > MAX_INPUT_BYTES:
        raise InputError("CSV size must be between 1 byte and 8 MiB")
    try:
        decoded = raw.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        raise InputError("CSV must be valid UTF-8") from None

    csv.field_size_limit(MAX_TEXT_CHARS)
    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    fields = reader.fieldnames
    if not isinstance(fields, list) or len(fields) != len(set(fields)):
        raise InputError("CSV header is missing or has duplicate columns")
    missing = [name for name in REQUIRED_COLUMNS if name not in fields]
    if missing:
        raise InputError("CSV is missing required columns: " + ",".join(missing))

    groups = {}
    row_count = 0
    alignment_cells = 0
    for row_number, row in enumerate(reader, start=2):
        if row_count >= MAX_ROWS:
            raise InputError("CSV row limit exceeded")
        if None in row:
            raise InputError(f"row {row_number}: too many columns")
        if any(row.get(name) is None for name in REQUIRED_COLUMNS):
            raise InputError(f"row {row_number}: missing required value")
        for name in ("reference", "before", "after"):
            if len(row[name]) > MAX_TEXT_CHARS:
                raise InputError(f"row {row_number}: transcript exceeds size limit")

        language = normalize_language(row["language"], row_number)
        noise = parse_label(row["noise"], row_number)
        reference = normalize_transcript(row["reference"])
        before = normalize_transcript(row["before"])
        after = normalize_transcript(row["after"])
        if not reference:
            raise InputError(f"row {row_number}: reference is empty after normalization")
        if max(len(reference), len(before), len(after)) > MAX_TOKENS_PER_UTTERANCE:
            raise InputError(f"row {row_number}: token limit exceeded")

        cells = (len(reference) + 1) * (len(before) + 1)
        cells += (len(reference) + 1) * (len(after) + 1)
        if alignment_cells + cells > MAX_ALIGNMENT_CELLS:
            raise InputError("bounded alignment work budget exceeded")
        alignment_cells += cells
        before_errors = edit_distance(reference, before)
        after_errors = edit_distance(reference, after)

        key = (language, noise)
        if key not in groups:
            if len(groups) >= MAX_GROUPS:
                raise InputError("noise-stratum limit exceeded")
            groups[key] = new_bucket()
        add_case(groups[key], len(reference), before_errors, after_errors)
        row_count += 1

    if row_count == 0:
        raise InputError("CSV contains no data rows")

    strata = [
        {"language": language, "noise": noise, **summarize(bucket)}
        for (language, noise), bucket in sorted(groups.items())
    ]
    return {
        "schema": SCHEMA,
        "created_at_utc": utc_now(),
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "normalization": "UTF-8; NFC; casefold; punctuation-as-space; whitespace-collapse",
        "metric": "corpus word error rate (Levenshtein edit errors / reference words)",
        "before_revision_label": before_revision,
        "after_revision_label": after_revision,
        "row_count": row_count,
        "strata": strata,
    }


def revision_label(value: str, name: str) -> str:
    label = value.strip()
    if not label or len(label) > 80 or any(ord(char) < 32 for char in label):
        raise InputError(f"{name} must be a non-empty printable label of at most 80 characters")
    return label


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute paired RU/ES WER by noise stratum.")
    parser.add_argument("--input", required=True, help="Local UTF-8 CSV; transcript data stays local.")
    parser.add_argument("--before-revision", required=True, help="Label for the pre-patch recognizer.")
    parser.add_argument("--after-revision", required=True, help="Label for the post-patch recognizer.")
    args = parser.parse_args()
    try:
        before = revision_label(args.before_revision, "before revision")
        after = revision_label(args.after_revision, "after revision")
        raw = Path(args.input).read_bytes()
        report = build_report(raw, before, after)
    except (OSError, InputError, csv.Error) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
