"""Deterministic, fail-closed RU/ES split assignment by global prompt family.

This source-only utility deliberately does not load or inspect dataset files. Callers
must supply trusted provenance, teacher/model, language, and globally canonical
prompt-family fields. Every occurrence of a prompt family is assigned to one split,
even when its source/model tuple differs. Each split must contain at least one RU
and one ES row, or the function fails closed.
"""
from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

SPLITS = ("train", "dev", "holdout")
LANGUAGES = ("ru", "es")
ALGORITHM = "sha256-ranked-global-prompt-family-v2"


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
    """Hamilton apportionment, with at least one family per split."""
    if n_groups < len(SPLITS):
        raise ValueError("at_least_three_prompt_families_required")
    quotas = {split: n_groups * ratios[split] for split in SPLITS}
    counts = {split: math.floor(quotas[split]) for split in SPLITS}
    remaining = n_groups - sum(counts.values())
    ranked = sorted(SPLITS, key=lambda split: (-(quotas[split] - counts[split]), SPLITS.index(split)))
    for split in ranked[:remaining]:
        counts[split] += 1
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


def _coverage_assignment(ranked_groups: list[tuple[str, str, bytes, str, dict[str, Any]]]) -> dict[str, str]:
    """Find a deterministic family assignment covering RU and ES in every split."""
    # Six bits represent (split, language) cells. Dynamic programming assigns
    # each family at most once and only records the first deterministic path per
    # coverage state; this is bounded to 64 states regardless of corpus size.
    states: dict[int, tuple[tuple[str, int], ...]] = {0: ()}
    for _, _, _, family, group in ranked_groups:
        family_bits = 0
        for language_index, language in enumerate(LANGUAGES):
            if group["language_rows"][language] > 0:
                family_bits |= 1 << language_index
        next_states = dict(states)  # skipping this family is always allowed
        for coverage, path in states.items():
            for split_index in range(len(SPLITS)):
                shifted_bits = family_bits << (split_index * len(LANGUAGES))
                updated = coverage | shifted_bits
                if updated != coverage and updated not in next_states:
                    next_states[updated] = path + ((family, split_index),)
        states = next_states
    required = (1 << (len(SPLITS) * len(LANGUAGES))) - 1
    if required not in states:
        raise ValueError("HOLD_LANGUAGE_STRATA_UNSATISFIABLE")
    return {family: SPLITS[split_index] for family, split_index in states[required]}


def split_rows_by_lineage(
    rows: Iterable[Mapping[str, Any]],
    *,
    seed: str | int,
    ratios: Mapping[str, float] | None = None,
    source_field: str = "provenance_source",
    teacher_field: str = "teacher_model",
    prompt_family_field: str = "prompt_family",
    language_field: str = "language",
) -> tuple[dict[str, list[Mapping[str, Any]]], dict[str, Any]]:
    """Return RU/ES-stratified splits plus a content-free manifest.

    The globally canonical prompt-family key is the indivisible leakage group.
    Thus identical (source, teacher/model, prompt-family) tuples and reused prompt
    families across differing source/model tuples cannot cross split boundaries.
    Each split receives at least one row for each of RU and ES. Missing/unknown
    language, missing lineage, or impossible coverage fails closed.
    """
    if isinstance(seed, bool) or not isinstance(seed, (str, int)):
        raise ValueError("seed_must_be_string_or_integer")
    seed_text = str(seed)
    if not seed_text:
        raise ValueError("seed_must_not_be_empty")
    fields = (source_field, teacher_field, prompt_family_field, language_field)
    if not all(isinstance(field, str) and field.strip() for field in fields):
        raise ValueError("lineage_field_names_must_be_nonempty")
    if len(set(fields)) != len(fields):
        raise ValueError("lineage_field_names_must_be_distinct")
    fractions = _validate_ratios(ratios if ratios is not None else {"train": 0.8, "dev": 0.1, "holdout": 0.1})

    materialized = list(rows)
    groups: dict[str, dict[str, Any]] = {}
    row_families: list[str] = []
    row_languages: list[str] = []
    for index, row in enumerate(materialized):
        if not isinstance(row, Mapping):
            raise ValueError(f"row_must_be_mapping:{index}")
        # Validate full provenance/model lineage even though family is the global
        # leakage key. The tuple is retained only for the defensive overlap check.
        source = _required_text(row, source_field, index)
        teacher = _required_text(row, teacher_field, index)
        family = _required_text(row, prompt_family_field, index)
        raw_language = _required_text(row, language_field, index).casefold()
        if raw_language not in LANGUAGES:
            raise ValueError(f"unsupported_language:{index}:{language_field}")
        group = groups.setdefault(family, {
            "indices": [], "language_rows": {language: 0 for language in LANGUAGES},
            "lineage_tuples": set(),
        })
        group["indices"].append(index)
        group["language_rows"][raw_language] += 1
        group["lineage_tuples"].add((source, teacher, family))
        row_families.append(family)
        row_languages.append(raw_language)

    allocations = _group_counts(len(groups), fractions)
    seed_digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    ranked_groups: list[tuple[str, str, bytes, str, dict[str, Any]]] = []
    for family, group in groups.items():
        # Canonical serialization is the final deterministic tie-break, so even
        # a SHA-256 collision cannot make assignment depend on input order.
        canonical = json.dumps([family], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        group_digest = hashlib.sha256(canonical).hexdigest()
        rank_digest = hashlib.sha256((seed_digest + ":" + group_digest).encode("ascii")).hexdigest()
        ranked_groups.append((rank_digest, group_digest, canonical, family, group))
    ranked_groups.sort(key=lambda item: (item[0], item[1], item[2]))

    family_split = _coverage_assignment(ranked_groups)
    group_counts = {split: sum(1 for value in family_split.values() if value == split) for split in SPLITS}
    for _, _, _, family, _ in ranked_groups:
        if family in family_split:
            continue
        split = max(SPLITS, key=lambda name: (allocations[name] - group_counts[name], -SPLITS.index(name)))
        family_split[family] = split
        group_counts[split] += 1

    split_rows: dict[str, list[Mapping[str, Any]]] = {split: [] for split in SPLITS}
    split_family_sets: dict[str, set[str]] = {split: set() for split in SPLITS}
    split_lineage_sets: dict[str, set[tuple[str, str, str]]] = {split: set() for split in SPLITS}
    language_row_counts = {split: {language: 0 for language in LANGUAGES} for split in SPLITS}
    for index, row in enumerate(materialized):
        family = row_families[index]
        split = family_split[family]
        split_rows[split].append(row)
        split_family_sets[split].add(family)
        split_lineage_sets[split].update(groups[family]["lineage_tuples"])
        language_row_counts[split][row_languages[index]] += 1

    if any(split_family_sets[a] & split_family_sets[b] for i, a in enumerate(SPLITS) for b in SPLITS[i + 1:]):
        raise RuntimeError("prompt_family_crossed_split_boundary")
    if any(split_lineage_sets[a] & split_lineage_sets[b] for i, a in enumerate(SPLITS) for b in SPLITS[i + 1:]):
        raise RuntimeError("lineage_tuple_crossed_split_boundary")
    if any(language_row_counts[split][language] < 1 for split in SPLITS for language in LANGUAGES):
        raise RuntimeError("language_strata_minimum_not_met")

    manifest = {
        "algorithm": ALGORITHM,
        "seed": seed_text,
        "ratios": fractions,
        "group_policy": "global_prompt_family",
        "minimum_rows_per_language_per_split": 1,
        "languages": list(LANGUAGES),
        "row_counts": {split: len(split_rows[split]) for split in SPLITS},
        "language_row_counts": language_row_counts,
        "group_counts": {split: len(split_family_sets[split]) for split in SPLITS},
        "total_rows": len(materialized),
        "total_groups": len(groups),
        "lineage_fields": [source_field, teacher_field, prompt_family_field, language_field],
    }
    return split_rows, manifest
