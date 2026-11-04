"""R54: original release evidence counters must never be booleans or coerced values.

Source-only checks. A SOURCE_READY verdict is not an installed Windows E07 PASS.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from nox_selfbuilder.release_governor import source_ready


class ReleaseEvidenceAdmissionTests(unittest.TestCase):
    def evidence(self, **overrides):
        data = {
            "mandatory_total": 1,
            "source_verified": 1,
            "patch_tests_passed": 1,
            "integration_receipts": 1,
            "windows_runner_ready": False,
        }
        data.update(overrides)
        return source_ready(**data)

    def test_valid_counts_still_source_ready_without_release(self):
        proof = self.evidence(mandatory_total=3, source_verified=3,
                              patch_tests_passed=3, integration_receipts=3,
                              windows_runner_ready=True)
        self.assertEqual(proof["status"], "SOURCE_READY")
        self.assertEqual(proof["windows_runner"], "READY")
        self.assertIs(proof["windows_release"], False)

    def test_zero_denominator_is_hold(self):
        self.assertEqual(self.evidence(mandatory_total=0)["status"], "HOLD")

    def test_boolean_denominator_cannot_fake_single_source(self):
        proof = self.evidence(mandatory_total=True, source_verified=1,
                              patch_tests_passed=1, integration_receipts=1)
        self.assertEqual(proof["status"], "HOLD")
        self.assertEqual(proof["reason"], "UNKNOWN_DENOMINATOR")

    def test_boolean_receipts_cannot_fake_one_receipt(self):
        for field in ("source_verified", "patch_tests_passed", "integration_receipts"):
            with self.subTest(field=field):
                proof = self.evidence(**{field: True})
                self.assertEqual(proof["status"], "HOLD")
                self.assertEqual(proof["reason"], "INVALID_EVIDENCE_COUNTER")

    def test_true_and_false_not_accepted_as_evidence(self):
        for value in (True, False):
            with self.subTest(value=value):
                proof = self.evidence(source_verified=value)
                self.assertEqual(proof["status"], "HOLD")

    def test_truthy_windows_runner_claim_is_not_native_evidence(self):
        for value in (1, "READY", [True]):
            with self.subTest(value=value):
                proof = self.evidence(windows_runner_ready=value)
                self.assertEqual(proof["status"], "SOURCE_READY")
                self.assertEqual(proof["windows_runner"], "HOLD")
                self.assertIs(proof["windows_release"], False)

    def test_explicit_false_windows_runner_remains_hold(self):
        proof = self.evidence(windows_runner_ready=False)
        self.assertEqual(proof["status"], "SOURCE_READY")
        self.assertEqual(proof["windows_runner"], "HOLD")
        self.assertIs(proof["windows_release"], False)

    def test_incomplete_counts_remain_hold(self):
        self.assertEqual(self.evidence(source_verified=0)["reason"], "INCOMPLETE_SOURCE_READY")


if __name__ == "__main__":
    unittest.main()
