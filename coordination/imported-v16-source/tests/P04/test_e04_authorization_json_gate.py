"""E04 actual-module authorization JSON parser regressions, CPU-only fixtures.

No real rights, weights, trained model, or CUDA operation is represented here.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"
spec = importlib.util.spec_from_file_location("nox_e04_authorization_json", SOURCE)
assert spec is not None and spec.loader is not None
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class AuthorizationJsonGateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.source = Path(temp.name) / "manifest-or-checkpoint.json"

    def read(self, text: str):
        self.source.write_text(text, encoding="utf-8")
        return worker.read_object(self.source)

    def test_valid_manifest_shape_is_unchanged(self):
        self.assertEqual(
            self.read('{"rights_status":"APPROVED","consent_status":"GRANTED","version":1.25}'),
            {"rights_status": "APPROVED", "consent_status": "GRANTED", "version": 1.25},
        )

    def test_duplicate_rights_status_cannot_hide_revocation(self):
        with self.assertRaisesRegex(ValueError, "INPUT_JSON_DUPLICATE_KEY"):
            self.read('{"rights_status":"REVOKED","rights_status":"APPROVED"}')

    def test_nested_duplicate_approval_claim_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "INPUT_JSON_DUPLICATE_KEY"):
            self.read('{"claims":{"owner_approval_id":"old","owner_approval_id":"new"}}')

    def test_duplicate_resume_checkpoint_step_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "INPUT_JSON_DUPLICATE_KEY"):
            self.read('{"global_step":1,"global_step":2}')

    def test_nonfinite_numeric_tokens_are_rejected(self):
        for token in ("NaN", "Infinity", "-Infinity", "1e99999", "-1e99999"):
            with self.subTest(token=token):
                with self.assertRaisesRegex(ValueError, "INPUT_JSON_NONFINITE"):
                    self.read('{"checkpoint_score":' + token + '}')

    def test_nonobject_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "EXPECTED_JSON_OBJECT"):
            self.read('["not an authorization object"]')

    def test_invalid_syntax_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "INPUT_INVALID_JSON"):
            self.read('{"rights_status":"APPROVED",')

    def test_missing_file_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "INPUT_NOT_REGULAR_FILE"):
            worker.read_object(self.source)


if __name__ == "__main__":
    unittest.main()
