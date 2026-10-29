"""Execute existing policy against native review-registry revision formats.

Native ModelArtifactReviewRegistry.TryPromote accepts 64-hex or sha256:64-hex
immutable revisions. These are digest references, not Git commit IDs. Fixtures
provide synthetic owner approval; no actual licenses or model pins are approved.
"""
import unittest
import p03_modelcenter_gate as g
from test_p03_modelcenter_gate import example


class NativeRevisionContract(unittest.TestCase):
    def admit(self, revision, *, kind="ollama", approved=True):
        evidence, context = example()
        evidence["immutableRevision"] = revision
        if kind == "gguf":
            evidence.update(kind="gguf", existingRoute="EnqueueVerifiedGgufAsync",
                            localGgufPath="C:/models/reviewed.gguf", nativeGgufMagicVerified=True,
                            nativeLocalFileSha256=evidence["artifactSha256"])
            context["verifiedPrerequisites"] = {"python": True, "git": True, "ollama": True}
        observed = []
        def attestor(ev, ctx):
            observed.append(ev["immutableRevision"])
            return approved
        decision = g.admit_for_existing_downloader(evidence, context, attestor)
        self.assertEqual(observed, [revision])  # no digest/Git conversion or normalization
        return decision

    def test_native_ollama_digest_revision_formats_reach_existing_queue(self):
        for revision in ["c" * 64, "C" * 64, "sha256:" + "c" * 64, "SHA256:" + "C" * 64]:
            with self.subTest(revision=revision):
                decision = self.admit(revision)
                self.assertTrue(decision.allowed, decision.reasons)
                self.assertEqual(decision.existing_route, "EnqueueVerifiedPullAsync")

    def test_historical_git_revision_contract_remains_distinct_and_supported(self):
        for kind in ["ollama", "gguf"]:
            self.assertTrue(self.admit("c" * 40, kind=kind).allowed)

    def test_ollama_digest_format_is_not_assumed_for_gguf_source_revision(self):
        decision = self.admit("sha256:" + "c" * 64, kind="gguf")
        self.assertIn("IMMUTABLE_REVISION_UNVERIFIED", decision.reasons)

    def test_digest_shape_does_not_grant_owner_review(self):
        decision = self.admit("sha256:" + "c" * 64, approved=False)
        self.assertFalse(decision.allowed)
        self.assertIn("OWNER_ATTESTATION_REJECTED", decision.reasons)

    def test_unpinned_malformed_and_zero_digest_references_hold(self):
        for revision in [None, "latest", "v1", "c" * 63, "c" * 65,
                         "sha256:" + "c" * 40, "sha256:" + "g" * 64,
                         "sha256:" + "0" * 64, "0" * 64, " " + "c" * 64,
                         "sha256:" + "c" * 64 + "\n"]:
            with self.subTest(revision=revision):
                decision = self.admit(revision)
                self.assertFalse(decision.allowed)
                self.assertIn("IMMUTABLE_REVISION_UNVERIFIED", decision.reasons)

    def test_missing_rights_checksum_and_disk_evidence_still_hold(self):
        for field in ["ownerRightsReceiptSha256", "artifactSha256", "manifestSha256", "requiredDiskBytes"]:
            evidence, context = example(); evidence["immutableRevision"] = "c" * 64
            evidence.pop(field)
            self.assertFalse(g.admit_for_existing_downloader(evidence, context, lambda e, c: True).allowed)


if __name__ == "__main__":
    unittest.main()
