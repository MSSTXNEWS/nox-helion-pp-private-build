"""Focused source-only 4A02 partition provenance regressions (no native tasks)."""
import copy
import random
import tempfile
import unittest
from pathlib import Path

from owner_training_dataset_splits_4a02 import (
    LANGUAGES, DOMAINS, SCHEMA, SplitHold, split_manifest, write_manifest,
)


def rows_fixture():
    rows = []
    for lang in LANGUAGES:
        for domain in DOMAINS:
            for number in range(5):
                rows.append({
                    "id": f"{lang}-{domain}-{number}",
                    "lang": lang,
                    "domain": domain,
                    "goal": f"goal {number}",
                    "source_id": f"publisher/{lang}/{domain}/{number}",
                    "text": f"unique {lang} {domain} {number} example",
                    "license": "MIT",
                })
    return rows


class DatasetSplitTests(unittest.TestCase):
    def test_all_twelve_strata_holdout_isolated_and_deterministic(self):
        original = rows_fixture()
        first = split_manifest(original)
        randomized = list(original)
        random.Random(42).shuffle(randomized)
        second = split_manifest(randomized)
        self.assertEqual(first, second)
        self.assertEqual(first["schema"], SCHEMA)
        self.assertEqual(first["status"], "SOURCE_MANIFEST_ONLY_NOT_NATIVE_ACCEPTED")
        self.assertEqual(first["counts"]["kept"], 60)
        self.assertEqual(len(first["coverage"]), 12)
        for cell in first["coverage"].values():
            self.assertEqual(cell, {"groups": 5, "train": 3, "dev": 1, "holdout": 1})
        partitions = {}
        for name, records in first["splits"].items():
            self.assertEqual(len(records), {"train": 36, "dev": 12, "holdout": 12}[name])
            for record in records:
                self.assertNotIn("text", record)
                self.assertEqual(record["license_claim"], "MIT")
                group = record["group_sha256"]
                self.assertEqual(partitions.setdefault(group, name), name)
        self.assertEqual(len(partitions), 60)
        self.assertEqual(len(first["manifest_sha256"]), 64)

    def test_duplicate_within_one_group_is_deduplicated(self):
        rows = rows_fixture()
        duplicate = dict(rows[0], id="distinct-record-id")
        duplicate["text"] = "  UNIQUE  RU   MEMORY  0  example "
        result = split_manifest(rows + [duplicate])
        self.assertEqual(result["counts"], {"input": 61, "deduplicated": 1, "kept": 60})

    def test_duplicate_cross_group_holds(self):
        rows = rows_fixture()
        rows[1]["text"] = rows[0]["text"].upper()
        with self.assertRaisesRegex(SplitHold, "HOLD_CROSS_GROUP_DUPLICATE"):
            split_manifest(rows)

    def test_origin_goal_cannot_cross_language_or_domain_partitions(self):
        for offender_index in (5, -1):  # RU cross-domain; RU to ES
            with self.subTest(offender_index=offender_index):
                rows = rows_fixture()
                rows[offender_index]["source_id"] = (
                    "  " + rows[0]["source_id"].upper() + " "
                )
                rows[offender_index]["goal"] = "  " + rows[0]["goal"].upper() + " "
                # Different text hash: this checks provenance, not text deduplication.
                self.assertNotEqual(rows[offender_index]["text"], rows[0]["text"])
                with self.assertRaisesRegex(
                    SplitHold, "HOLD_CROSS_STRATUM_ORIGIN_GOAL"
                ):
                    split_manifest(rows)

    def test_absent_provenance_or_coverage_holds(self):
        rows = rows_fixture()
        for field in ("license", "source_id", "goal", "lang", "text"):
            altered = copy.deepcopy(rows)
            altered[0].pop(field)
            with self.subTest(field=field):
                with self.assertRaisesRegex(SplitHold, "HOLD_REQUIRED_PROVENANCE"):
                    split_manifest(altered)
        missing_group = [row for row in rows if not (
            row["lang"] == "ru" and row["domain"] == "memory" and
            row["id"] not in {"ru-memory-0", "ru-memory-1"})]
        with self.assertRaisesRegex(SplitHold, "HOLD_INSUFFICIENT_INDEPENDENT_GROUPS"):
            split_manifest(missing_group)

    def test_duplicate_ids_rejected_and_atomic_write(self):
        rows = rows_fixture()
        duplicate = dict(rows[0])
        with self.assertRaisesRegex(SplitHold, "HOLD_DUPLICATE_RECORD_ID"):
            split_manifest(rows + [duplicate])
        output = split_manifest(rows)
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "splits.json"
            write_manifest(destination, output)
            text = destination.read_text(encoding="utf-8")
            self.assertIn('"manifest_sha256"', text)
            self.assertNotIn("unique ru memory 0 example", text)
            self.assertFalse(any(Path(folder).glob(".nox4a02-*.tmp")))
            other = Path(folder) / "link.json"
            other.symlink_to(destination)
            with self.assertRaisesRegex(SplitHold, "HOLD_OUTPUT_SYMLINK"):
                write_manifest(other, output)


if __name__ == "__main__":
    unittest.main()
