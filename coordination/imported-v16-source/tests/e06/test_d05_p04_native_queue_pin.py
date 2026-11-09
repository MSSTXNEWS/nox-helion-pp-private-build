"""D05: the original S03 GPU/QLoRA queue must stage the exact reviewed Git blob.

This is a source-integrity regression, not physical Windows/NSIS or GPU training
evidence. Never skip pin validation to make an installer build pass.
"""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
STAGER = ROOT / "coordination/e06/stage_native_stdio.py"
QUEUE = ROOT / "src/nox_selfbuilder/onehost_queue.py"
SOURCE = "src/nox_selfbuilder/onehost_queue.py"
DEST = "nox_selfbuilder/onehost_queue.py"


class OriginalP04QueuePinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("nox_original_native_stage_d05", STAGER)
        cls.stager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.stager)

    def test_reviewed_queue_blob_matches_actual_source(self):
        rows = [entry for entry in self.stager.ADDONS if entry[0] == SOURCE]
        self.assertEqual(len(rows), 1, "the original S03 queue must be staged once")
        self.assertEqual(rows[0][1], DEST)
        raw = QUEUE.read_bytes()
        self.assertEqual(rows[0][2], self.stager.git_blob(raw))
        self.assertEqual(self.stager.pinned_bytes(QUEUE, rows[0][2]), raw)

    def test_outdated_queue_pin_remains_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, "E06_NATIVE_OWNER_BLOB_SHA_HOLD"):
            self.stager.pinned_bytes(QUEUE, "0" * 40)


if __name__ == "__main__":
    unittest.main()
