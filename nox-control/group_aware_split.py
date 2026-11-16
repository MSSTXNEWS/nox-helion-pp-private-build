"""Deterministic, fail-closed split assignment by source/model/prompt family.

This source-only utility deliberately does not load or inspect dataset files. Callers
must provide trusted row-level lineage fields, including a normalized prompt-family
key. All rows sharing the complete lineage tuple are assigned to one split.
"""
from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

SPLITS = ("train", "dev", "holdout")
ALGORITHM = "sha256-ranked-lineage-groups-v1"


def _validate_ratios(ratios: Mapping[str, float]) -> dict[str, float]:
    if not isinstance(ratios, Mapping) or set(ratios) != set(SPLITS):
        raise ValueError("ratios_must_define_train_dev_holdout")
    result: dict[str, float] = {}
    for split in SPLITS:
        value = ratios[split]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("ratios_must_be_finite_positive_numbers")
        value = float(value)
        if not math.isfinite(value) or value <= 0:
            raise ValueError("ratios_must_be_finite_positive_numbers")
        result[split] = value
    total = sum(result.values())
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("ratios_must_sum_to_one")
    return {split: result[split] / total for split in SPLITS}


def _required_text(row: Mapping[str, Any], field: str, index: int) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing_lineage_field:{index}:{field}")
    return unicodedata.normalize("NFC", value.strip())


def _group_counts(n_groups: int, ratios: Mapping[str, float]) -> dict[str, int]:
    """Hamilton apportionment, with at least one group in each split."""
    if n_groups < len(SPLITS):
        raise ValueError("at_least_three_lineage_groups_required")
    quotas = {split: n_groups * ratios[split] for split in SPLITS}
    counts = {split: math.floor(quotas[split]) for split in SPLITS}
    remaining = n_groups - sum(counts.values())
    ranked = sorted(SPLITS, key=lambda split: (-(quotas[split] - counts[split]), SPLITS.index(split)))
    for split in ranked[:remaining]:
        counts[split] += 1

    # Positive ratios can still round to zero at small group counts. Keep all
    # requested splits represented by moving the least costly group from a donor.
    for recipient in SPLITS:
        if counts[recipient] != 0:
            continue
        donors = [split for split in SPLITS if counts[split] > 1]
        if not donors:
            raise ValueError("unable_to_represent_all_splits")
        donor = max(donors, key=lambda split: (counts[split] - quotas[split], counts[split], -SPLITS.index(split)))
        counts[donor] -= 1
        counts[recipient] += 1
    return counts


def split_rows_by_lineage(
    rows: Iterable[Mapping[str, Any]],
    *,
    seed: str | int,
    ratios: Mapping[str, float] | None = None,
    source_field: str = "provenance_source",
    teacher_field: str = "teacher_model",
    prompt_family_field: str = "prompt_family",
) -> tuple[dict[str, list[Mapping[str, Any]]], dict[str, Any]]:
    """Return rows grouped into train/dev/holdout plus a content-free manifest.

    The tuple `(source, teacher/model, prompt-family)` is the leakage boundary.
    Missing lineage fails closed. Caller must establish the prompt-family key
    upstream; this function does not infer family similarity from prompt text.
    Assignment is deterministic and independent of input row order.
    """
    if isinstance(seed, bool) or not isinstance(seed, (str, int)):
        raise ValueError("seed_must_be_string_or_integer")
    seed_text = str(seed)
    if not seed_text:
        raise ValueError("seed_must_not_be_empty")
    if not all(isinstance(field, str) and field.strip() for field in
               (source_field, teacher_field, prompt_family_field)):
        raise ValueError("lineage_field_names_must_be_nonempty")
    if len({source_field, teacher_field, prompt_family_field}) != 3:
        raise ValueError("lineage_field_names_must_be_distinct")
    fractions = _validate_ratios(ratios if ratios is not None else {"train": 0.8, "dev": 0.1, "holdout": 0.1})
    materialized = list(rows)
    groups: dict[tuple[str, str, str], list[int]] = {}
    for index, row in enumerate(materialized):
        if not isinstance(row, Mapping):
            raise ValueError(f"row_must_be_mapping:{index}")
        key = (
            _required_text(row, source_field, index),
            _required_text(row, teacher_field, index),
            _required_text(row, prompt_family_field, index),
        )
        groups.setdefault(key, []).append(index)

    allocations = _group_counts(len(groups), fractions)
    seed_digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    ranked_groups = []
    for key in groups:
        canonical = json.dumps(key, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        group_digest = hashlib.sha256(canonical).hexdigest()
        rank_digest = hashlib.sha256((seed_digest + ":" + group_digest).encode("ascii")).hexdigest()
        ranked_groups.append((rank_digest, group_digest, key))
    ranked_groups.sort(key=lambda item: (item[0], item[1]))

    group_split: dict[tuple[str, str, str], str] = {}
    cursor = 0
    for split in SPLITS:
        for _, _, key in ranked_groups[cursor:cursor + allocations[split]]:
            group_split[key] = split
        cursor += allocations[split]

    split_rows: dict[str, list[Mapping[str, Any]]] = {split: [] for split in SPLITS}
    split_group_sets: dict[str, set[tuple[str, str, str]]] = {split: set() for split in SPLITS}
    for index, row in enumerate(materialized):
        key = (
            _required_text(row, source_field, index),
            _required_text(row, teacher_field, index),
            _required_text(row, prompt_family_field, index),
        )
        split = group_split[key]
        split_rows[split].append(row)
        split_group_sets[split].add(key)

    # Defensive invariant check: never return a result with cross-split groups.
    if any(split_group_sets[a] & split_group_sets[b] for i, a in enumerate(SPLITS) for b in SPLITS[i + 1:]):
        raise RuntimeError("lineage_group_crossed_split_boundary")

    manifest = {
        "algorithm": ALGORITHM,
        "seed": seed_text,
        "ratios": fractions,
        "row_counts": {split: len(split_rows[split]) for split in SPLITS},
        "group_counts": {split: len(split_group_sets[split]) for split in SPLITS},
        "total_rows": len(materialized),
        "total_groups": len(groups),
        "lineage_fields": [source_field, teacher_field, prompt_family_field],
    }
    return split_rows, manifest
