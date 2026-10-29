"""Atomic and immutable QLoRA receipt regression; no GPU, weights or datasets."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

WORKER = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"

def module_under_test():
    spec = importlib.util.spec_from_file_location("nox_qlora_receipt", WORKER)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    return worker

class ImmutableReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worker = module_under_test()

    def test_atomic_latest_and_immutable_archive(self):
        with tempfile.TemporaryDirectory() as location:
            output = Path(location)
            receipt = {"schema": "fixture-only", "run_id": "fixture-run", "status": "PAUSED"}
            sha, latest = self.worker.write_training_receipt(output, receipt)
            self.assertEqual(sha, self.worker.sha256_file(latest))
            archived = output / "receipts" / (sha + ".json")
            self.assertEqual(archived.read_bytes(), latest.read_bytes())
            again, _ = self.worker.write_training_receipt(output, receipt)
            self.assertEqual(again, sha)
            changed = dict(receipt, status="COMPLETED")
            different, _ = self.worker.write_training_receipt(output, changed)
            self.assertNotEqual(different, sha)
            self.assertEqual(self.worker.sha256_file(archived), sha)

    def test_modified_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as location:
            output = Path(location)
            receipt = {"schema": "fixture-only", "run_id": "fixture-run"}
            sha, latest = self.worker.write_training_receipt(output, receipt)
            before = latest.read_bytes()
            archive = output / "receipts" / (sha + ".json")
            archive.write_bytes(b"tampered receipt")
            with self.assertRaisesRegex(ValueError, "ARCHIVE_COLLISION"):
                self.worker.write_training_receipt(output, receipt)
            self.assertEqual(latest.read_bytes(), before)

if __name__ == "__main__":
    unittest.main()
