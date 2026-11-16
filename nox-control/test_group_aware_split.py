"""Synthetic regression fixtures for group-aware RU/ES split assignment."""
import unittest
from unittest.mock import patch

import group_aware_split as splitter
from group_aware_split import split_rows_by_lineage


RATIOS = {"train": 0.6, "dev": 0.2, "holdout": 0.2}


def fixtures():
    rows = []
    for group in range(10):
        language = "ru" if group % 2 == 0 else "es"
        for member in range(2):
            rows.append({
                "row_id": f"synthetic-{group:02d}-{member}",
                "provenance_source": f"fixture-source-{group:02d}",
                "teacher_model": "fixture-teacher-v1",
                "prompt_family": f"fixture-family-{group:02d}",
                "language": language,
                "text": f"synthetic only {group}/{member}",
            })
    return rows


class GroupAwareSplitTests(unittest.TestCase):
    def split(self, rows):
        return split_rows_by_lineage(rows, seed="fixture-seed", ratios=RATIOS)

    def test_stable_counts_and_ru_es_minimum_in_every_split(self):
        split_rows, manifest = self.split(fixtures())
        self.assertEqual(manifest["group_counts"], {"train": 6, "dev": 2, "holdout": 2})
        self.assertEqual(manifest["row_counts"], {"train": 12, "dev": 4, "holdout": 4})
        self.assertEqual(manifest["total_groups"], 10)
        self.assertEqual(manifest["total_rows"], 20)
        self.assertEqual(set(split_rows), {"train", "dev", "holdout"})
        for split in ("train", "dev", "holdout"):
            self.assertGreaterEqual(manifest["language_row_counts"][split]["ru"], 1)
            self.assertGreaterEqual(manifest["language_row_counts"][split]["es"], 1)

    def test_assignment_is_order_independent_and_groups_do_not_cross(self):
        rows = fixtures()
        first, _ = self.split(rows)
        second, _ = self.split(list(reversed(rows)))
        first_ids = {split: {row["row_id"] for row in values} for split, values in first.items()}
        second_ids = {split: {row["row_id"] for row in values} for split, values in second.items()}
        self.assertEqual(first_ids, second_ids)
        family_splits = {}
        for split, values in first.items():
            for row in values:
                family = row["prompt_family"]
                if family in family_splits:
                    self.assertEqual(family_splits[family], split)
                family_splits[family] = split
        self.assertEqual(len(family_splits), 10)

    def test_global_prompt_family_cannot_cross_source_or_model_tuples(self):
        rows = fixtures()
        rows.extend([
            {"row_id": "shared-ru", "provenance_source": "other-source-a", "teacher_model": "teacher-a",
             "prompt_family": "shared-global-family", "language": "ru", "text": "synthetic"},
            {"row_id": "shared-es", "provenance_source": "other-source-b", "teacher_model": "teacher-b",
             "prompt_family": "shared-global-family", "language": "es", "text": "synthetic"},
        ])
        split_rows, _ = self.split(rows)
        assignments = {row["row_id"]: split for split, values in split_rows.items() for row in values}
        self.assertEqual(assignments["shared-ru"], assignments["shared-es"])

    def test_hash_collisions_use_canonical_group_serialization_tiebreak(self):
        class ConstantDigest:
            def hexdigest(self):
                return "0" * 64

        rows = fixtures()
        with patch.object(splitter.hashlib, "sha256", side_effect=lambda *_args, **_kwargs: ConstantDigest()):
            first, _ = self.split(rows)
            second, _ = self.split(list(reversed(rows)))
        first_ids = {split: {row["row_id"] for row in values} for split, values in first.items()}
        second_ids = {split: {row["row_id"] for row in values} for split, values in second.items()}
        self.assertEqual(first_ids, second_ids)

    def test_missing_blank_or_unsupported_lineage_and_language_fail_closed(self):
        base = fixtures()[:1]
        for field in ("provenance_source", "teacher_model", "prompt_family", "language"):
            with self.subTest(field=field):
                missing = dict(base[0]); del missing[field]
                with self.assertRaisesRegex(ValueError, "missing_lineage_field"):
                    self.split([missing] + fixtures()[1:])
                blank = dict(base[0]); blank[field] = "  \t"
                with self.assertRaisesRegex(ValueError, "missing_lineage_field"):
                    self.split([blank] + fixtures()[1:])
        unsupported = dict(base[0]); unsupported["language"] = "fr"
        with self.assertRaisesRegex(ValueError, "unsupported_language"):
            self.split([unsupported] + fixtures()[1:])
        with self.assertRaisesRegex(ValueError, "at_least_three_prompt_families_required"):
            self.split([])

    def test_impossible_per_language_coverage_holds(self):
        rows = [
            {"provenance_source": "a", "teacher_model": "t", "prompt_family": "mixed", "language": "ru"},
            {"provenance_source": "b", "teacher_model": "u", "prompt_family": "mixed", "language": "es"},
            {"provenance_source": "c", "teacher_model": "t", "prompt_family": "ru-only", "language": "ru"},
            {"provenance_source": "d", "teacher_model": "u", "prompt_family": "es-only", "language": "es"},
        ]
        with self.assertRaisesRegex(ValueError, "HOLD_LANGUAGE_STRATA_UNSATISFIABLE"):
            self.split(rows)

    def test_invalid_ratios_and_too_few_prompt_families_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "ratios_must_sum_to_one"):
            split_rows_by_lineage(fixtures(), seed=1, ratios={"train": 0.7, "dev": 0.2, "holdout": 0.2})
        with self.assertRaisesRegex(ValueError, "at_least_three_prompt_families_required"):
            self.split(fixtures()[:2])


if __name__ == "__main__":
    unittest.main()
