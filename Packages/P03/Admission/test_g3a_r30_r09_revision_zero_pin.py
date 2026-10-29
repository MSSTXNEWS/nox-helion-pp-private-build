"""G3-A R30 R09: immutable-revision zero placeholder regression (source only).

Run on a checked-out private branch:
    python -m unittest discover -s Packages/P03/Admission -p 'test_g3a_r30_r09_revision_zero_pin.py' -v

The positive native callback is a synthetic unit fixture, NOT E06 attestation.
No download, external network, Windows build, or model load is performed.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p03_modelcenter_gate as gate


class ImmutableRevisionZeroPinTests(unittest.TestCase):
    def test_zero_forty_rejected_for_all_kinds(self):
        for kind in ("ollama", "gguf", "external"):
            with self.subTest(kind=kind):
                self.assertFalse(gate._immutable_revision("0" * 40, kind))

    def test_nonzero_forty_preserves_existing_kinds(self):
        for kind in ("ollama", "gguf", "external"):
            with self.subTest(kind=kind):
                self.assertTrue(gate._immutable_revision("a" * 40, kind))

    def test_invalid_forty_length_and_types_rejected(self):
        for value in ("0" * 39, "0" * 41, "", None, True, 1):
            with self.subTest(value=value):
                self.assertFalse(gate._immutable_revision(value, "ollama"))

    def test_ollama_zero_sixtyfour_still_rejected(self):
        self.assertFalse(gate._immutable_revision("0" * 64, "ollama"))
        self.assertFalse(gate._immutable_revision("sha256:" + "0" * 64, "ollama"))

    def test_nonzero_ollama_digest_still_accepted_as_syntax(self):
        self.assertTrue(gate._immutable_revision("b" * 64, "ollama"))
        self.assertTrue(gate._immutable_revision("SHA256:" + "b" * 64, "ollama"))
        self.assertFalse(gate._immutable_revision("b" * 64, "gguf"))

    @staticmethod
    def _fixture():
        evidence = {
            "kind": "ollama",
            "licenseAcknowledged": True,
            "licenseEvidenceUrl": "https://example.com/license",
            "licenseId": "fixture-license",
            "artifactSha256": "a" * 64,
            "manifestSha256": "b" * 64,
            "artifactBytes": 1024,
            "requiredDiskBytes": 2048,
            "immutableRevision": "0" * 40,
            "ownerRightsReceiptSha256": "c" * 64,
            "requiresGPU": False,
            "recommendedRamBytes": 4096,
            "requiredVramBytes": None,
            "modelTag": "qwen3:0.6b",
            "existingRoute": "EnqueueVerifiedPullAsync",
        }
        context = {
            "sourceCommit": gate.BASE_COMMIT,
            "sourceTree": gate.BASE_TREE,
            "owner3DonorHead": gate.DONOR_OWNER3_HEAD,
            "nativeSourceLock": {
                "attested": True,
                "verifiedRawPartCount": 3,
                "verifiedExtractedMemberCount": 729,
                "ownerReceiptSha256": "d" * 64,
                "hostSourceReceiptSha256": "e" * 64,
            },
            "sessionTrusted": True,
            "hostQueueAvailable": True,
            "explicitUserDownloadConsent": True,
            "nativeMeasuredHardware": {
                "attested": True,
                "availableRamBytes": 8192,
                "freeDiskBytes": 100000,
            },
            "verifiedPrerequisites": {"ollama": True},
        }
        return evidence, context

    def test_zero_forty_fails_before_native_attestor(self):
        evidence, context = self._fixture()
        calls = []
        decision = gate.admit_for_existing_downloader(
            evidence, context, lambda *_args: calls.append(1) or True
        )
        self.assertEqual(decision.status, "HOLD")
        self.assertIn("IMMUTABLE_REVISION_UNVERIFIED", decision.reasons)
        self.assertEqual(calls, [])

    def test_nonzero_forty_preserves_synthetic_positive_fixture(self):
        evidence, context = self._fixture()
        evidence["immutableRevision"] = "a" * 40
        calls = []
        decision = gate.admit_for_existing_downloader(
            evidence, context, lambda *_args: calls.append(1) or True
        )
        self.assertEqual(calls, [1])
        self.assertEqual(decision.status, "PASS_FOR_EXISTING_QUEUE")

    def test_missing_attestor_even_with_good_revision_still_holds(self):
        evidence, context = self._fixture()
        evidence["immutableRevision"] = "a" * 40
        decision = gate.admit_for_existing_downloader(evidence, context, None)
        self.assertEqual(decision.status, "HOLD")
        self.assertIn("TRUSTED_OWNER_ATTESTOR_MISSING", decision.reasons)


if __name__ == "__main__":
    unittest.main()
