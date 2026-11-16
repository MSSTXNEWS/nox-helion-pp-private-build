"""Synthetic regression fixtures for group-aware split assignment."""
import unittest

from group_aware_split import split_rows_by_lineage


RATIOS = {"train": 0.6, "dev": 0.2, "holdout": 0.2}


def fixtures():
    rows = []
    for group in range(10):
        for member in range(2):
            rows.append({
                "row_id": f"synthetic-{group:02d}-{member}",
                "provenance_source": f"fixture-source-{group:02d}",
                "teacher_model": "fixture-teacher-v1",
                "prompt_family": f"fixture-family-{group:02d}",
                "text": f"synthetic only {group}/{member}",
            })
    return rows


class GroupAwareSplitTests(unittest.TestCase):
    def split(self, rows):
        return split_rows_by_lineage(rows, seed="fixture-seed", ratios=RATIOS)

    def test_group_and_row_counts_are_stable(self):
        split_rows, manifest = self.split(fixtures())
        self.assertEqual(manifest["group_counts"], {"train": 6, "dev": 2, "holdout": 2})
        self.assertEqual(manifest["row_counts"], {"train": 12, "dev": 4, "holdout": 4})
        self.assertEqual(manifest["total_groups"], 10)
        self.assertEqual(manifest["total_rows"], 20)
        self.assertEqual(set(split_rows), {"train", "dev", "holdout"})

    def test_assignment_is_order_independent_and_no_group_crosses(self):
        rows = fixtures()
        first, _ = self.split(rows)
        second, _ = self.split(list(reversed(rows)))
        first_ids = {split: {row["row_id"] for row in values} for split, values in first.items()}
        second_ids = {split: {row["row_id"] for row in values} for split, values in second.items()}
        self.assertEqual(first_ids, second_ids)
        seen = {}
        for split, values in first.items():
            for row in values:
                lineage = (row["provenance_source"], row["teacher_model"], row["prompt_family"])
                if lineage in seen:
                    self.assertEqual(seen[lineage], split)
                seen[lineage] = split
        self.assertEqual(len(seen), 10)

    def test_missing_or_blank_lineage_fails_closed_for_each_key(self):
        base = fixtures()[:1]
        for field in ("provenance_source", "teacher_model", "prompt_family"):
            with self.subTest(field=field):
                missing = dict(base[0]); del missing[field]
                with self.assertRaisesRegex(ValueError, "missing_lineage_field"):
                    self.split([missing] + fixtures()[1:])
                blank = dict(base[0]); blank[field] = "  \t"
                with self.assertRaisesRegex(ValueError, "missing_lineage_field"):
                    self.split([blank] + fixtures()[1:])

    def test_invalid_ratios_and_too_few_groups_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "ratios_must_sum_to_one"):
            split_rows_by_lineage(fixtures(), seed=1, ratios={"train": 0.7, "dev": 0.2, "holdout": 0.2})
        with self.assertRaisesRegex(ValueError, "at_least_three_lineage_groups_required"):
            self.split(fixtures()[:2])


if __name__ == "__main__":
    unittest.main()
