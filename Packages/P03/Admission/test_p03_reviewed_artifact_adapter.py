"""Execute Python adapter with synthetic exact native-export fixtures.
Does not execute C#, authorize rights, inject a production provider or download.
"""
import hashlib
import json
import unittest
from dataclasses import FrozenInstanceError
import p03_modelcenter_gate as gate
from p03_reviewed_artifact_adapter import read_native_reviewed_artifact, ReviewedArtifactHold
from test_p03_modelcenter_gate import example


def export_fixture():
    return dict(schema="NOX_P03_NATIVE_REVIEWED_ARTIFACT_V1", familyId="phi4", exactTag="phi4:mini",
                version="fixture-version", licenseId="LICENSE-REVIEWED",
                licenseEvidenceUrl="https://example.org/license", artifactBytes=500000,
                requiredDiskBytes=800000, recommendedRamBytes=800000, requiredVramBytes=400000,
                artifactSha256="a" * 64, manifestSha256="b" * 64, immutableRevision="c" * 64,
                compatibilityEvidenceUrl="https://example.org/compatibility", reviewerReceiptId="native-review-1")


class NativeReviewedArtifactAdapter(unittest.TestCase):
    def read(self, doc=None):
        raw = json.dumps(export_fixture() if doc is None else doc)
        return read_native_reviewed_artifact("phi4:mini", lambda tag: raw)

    def test_exact_original_registry_fields_return_frozen_identity_snapshot(self):
        doc = export_fixture(); raw = json.dumps(doc)
        result = read_native_reviewed_artifact("phi4:mini", lambda tag: raw)
        self.assertEqual(dict(result.fields), doc)
        self.assertEqual(result.export_sha256, hashlib.sha256(raw.encode()).hexdigest())
        with self.assertRaises(TypeError): result.fields["exactTag"] = "other:tag"
        with self.assertRaises(FrozenInstanceError): result.export_sha256 = "f" * 64
        self.assertFalse(hasattr(result, "allowed"))

    def test_exact_identity_matches_without_granting_queue_admission(self):
        snapshot = self.read(); evidence, context = example()
        evidence.update(modelTag="phi4:mini", immutableRevision="c" * 64, recommendedRamBytes=800000)
        self.assertTrue(snapshot.matches_artifact_identity(evidence))
        decision = gate.admit_for_existing_downloader(evidence, context, lambda e, c: True)
        self.assertIn("NOT_IN_OWNER3_EXACT_TAG_LEADS", decision.reasons)

    def test_any_selected_artifact_identity_drift_fails(self):
        snapshot = self.read(); evidence, _ = example()
        evidence.update(modelTag="phi4:mini", immutableRevision="c" * 64, recommendedRamBytes=800000)
        for key in ("modelTag", "licenseId", "licenseEvidenceUrl", "artifactBytes", "requiredDiskBytes",
                    "artifactSha256", "manifestSha256", "immutableRevision", "requiresGPU", "requiredVramBytes",
                    "recommendedRamBytes"):
            changed = dict(evidence); changed[key] = None
            self.assertFalse(snapshot.matches_artifact_identity(changed), key)
        changed = dict(evidence, artifactBytes=500000.0)
        self.assertFalse(snapshot.matches_artifact_identity(changed))

    def test_provider_must_be_native_callable_not_page_metadata_or_boolean(self):
        for provider in (None, True, export_fixture(), lambda tag: True, lambda tag: export_fixture()):
            with self.assertRaises(ReviewedArtifactHold):
                read_native_reviewed_artifact("phi4:mini", provider)

    def test_invalid_tag_never_calls_native_provider(self):
        calls = []
        for tag in ("phi4", "phi4:latest", "phi4:mini\n", "phi4:../file", "a" * 161, None):
            with self.assertRaises(ReviewedArtifactHold):
                read_native_reviewed_artifact(tag, lambda tag: calls.append(tag))
        self.assertEqual(calls, [])

    def test_provider_foreign_family_or_tag_cannot_substitute_artifact(self):
        for key, value in (("exactTag", "qwen3:0.6b"), ("familyId", "qwen3")):
            with self.assertRaises(ReviewedArtifactHold): self.read(dict(export_fixture(), **{key: value}))

    def test_duplicate_unknown_and_missing_fields_hold(self):
        raw = json.dumps(export_fixture())
        for payload in (raw[:-1] + ',"exactTag":"phi4:mini"}',
                        json.dumps(dict(export_fixture(), nativeApproved=True)), "{}", "[]"):
            with self.assertRaises(ReviewedArtifactHold):
                read_native_reviewed_artifact("phi4:mini", lambda tag: payload)

    def test_unbounded_nonfinite_and_invalid_utf8_exports_hold(self):
        for raw in (b"x" * 16385, b"\xff", '[NaN]', '"' + 'x' * 17000 + '"'):
            with self.assertRaises(ReviewedArtifactHold):
                read_native_reviewed_artifact("phi4:mini", lambda tag: raw)

    def test_bytes_memory_revision_and_rights_metadata_must_be_valid(self):
        for key, value in (("artifactBytes", True), ("requiredDiskBytes", 100),
                           ("recommendedRamBytes", -1), ("requiredVramBytes", 0),
                           ("artifactSha256", "0" * 64), ("manifestSha256", "x" * 64),
                           ("immutableRevision", "latest"), ("reviewerReceiptId", " "),
                           ("licenseEvidenceUrl", "https://localhost/license"),
                           ("compatibilityEvidenceUrl", "http://example.org/compatibility")):
            with self.subTest(key=key), self.assertRaises(ReviewedArtifactHold):
                self.read(dict(export_fixture(), **{key: value}))

    def test_cpu_only_artifact_uses_existing_ram_metadata(self):
        snapshot = self.read(dict(export_fixture(), requiredVramBytes=None))
        evidence, _ = example(); evidence.update(modelTag="phi4:mini", immutableRevision="c" * 64,
                                                requiresGPU=False, requiredVramBytes=None, recommendedRamBytes=800000)
        self.assertTrue(snapshot.matches_artifact_identity(evidence))
        evidence["requiresGPU"] = 0
        self.assertFalse(snapshot.matches_artifact_identity(evidence))

    def test_provider_failure_does_not_expose_private_diagnostics(self):
        def broken(tag): raise RuntimeError("private-token")
        with self.assertRaises(ReviewedArtifactHold) as raised:
            read_native_reviewed_artifact("phi4:mini", broken)
        self.assertNotIn("private-token", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
