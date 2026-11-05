"""M04: SHA-pinned external acquisition manifests reject ambiguous JSON keys.

Run: python -m unittest -v tests/test_m04_acquisition_manifest_duplicate_keys.py
A positive receipt proves physical SOURCE bytes only, never INSTALLED models.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "src/nox_selfbuilder/acquisition_library.py"
spec = importlib.util.spec_from_file_location("nox_m04_acquisition_library", SOURCE)
acq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acq)


class ManifestDuplicateKeysRegression(unittest.TestCase):
    def test_reject_ambiguous_keys_without_weakening_physical_sha(self):
        with tempfile.TemporaryDirectory(prefix="nox_m04_manifest_") as tmp:
            root = Path(tmp)
            db_path = root / "acquisitions.db"
            with sqlite3.connect(db_path) as db:
                db.execute("CREATE VIRTUAL TABLE records USING fts5(name)")
                db.execute("INSERT INTO records(name) VALUES ('safe')")
            db_sha = hashlib.sha256(db_path.read_bytes()).hexdigest()
            weight = root / "physical.gguf"
            weight.write_bytes(b"real-weights-sample")
            weight_sha = hashlib.sha256(weight.read_bytes()).hexdigest()
            manifest_path = root / "inventory.json"
            good = ('{"schema":"NOX-ACQUISITION-FILES-v1",'
                    '"files":[{"path":"physical.gguf","sha256":"' + weight_sha + '",'
                    '"bytes":19}]}')
            self.assertEqual(len(weight.read_bytes()), 19)

            def audit(raw):
                manifest_path.write_text(raw, encoding="utf-8")
                pin = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                return acq.audit_library(str(db_path), db_sha,
                                         approved_roots=[str(root)],
                                         manifest_path=str(manifest_path),
                                         manifest_sha256=pin,
                                         assets_root=str(root))

            good_receipt = audit(good)
            self.assertEqual(good_receipt["physical_files_verified"], 1)
            self.assertFalse(good_receipt["models_installed"])
            # Both duplicate manifests have a valid independent SHA256 pin.
            # Earlier json.loads silently accepted the second key.
            nested_duplicate = good.replace('"bytes":19', '"bytes":0,"bytes":19')
            top_duplicate = good.replace('"files":', '"schema":"NOX-ACQUISITION-FILES-v1","files":')
            for case in (nested_duplicate, top_duplicate):
                with self.subTest(raw=case[:110]):
                    with self.assertRaisesRegex(acq.AcquisitionHold, "LIBRARY_MANIFEST_DUPLICATE_KEY"):
                        audit(case)


if __name__ == "__main__":
    unittest.main()
