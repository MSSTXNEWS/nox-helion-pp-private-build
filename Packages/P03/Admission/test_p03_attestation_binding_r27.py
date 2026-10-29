"""P03 policy uses the same immutable evidence before/after native callbacks."""
import unittest
from types import MappingProxyType
import p03_modelcenter_gate as g
from test_p03_modelcenter_gate import example, queue_fixture, retry_fixture


class AttestationBindingR27(unittest.TestCase):
    def test_model_artifact_mutation_during_attestation_holds(self):
        evidence, context = example()
        def attest(e, c):
            e['artifactSha256'] = 'e' * 64
            return True
        self.assertFalse(g.admit_for_existing_downloader(evidence, context, attest).allowed)

    def test_native_lock_mutation_during_attestation_holds(self):
        evidence, context = example()
        def attest(e, c):
            c['nativeSourceLock']['verifiedExtractedMemberCount'] = 1
            return True
        self.assertFalse(g.admit_for_existing_downloader(evidence, context, attest).allowed)

    def test_queue_receipt_mutation_after_identity_check_holds(self):
        old, new = queue_fixture()
        def attest(a, b):
            b['queueOwnerSessionId'] = 'different-session'
            return True
        self.assertFalse(g.progress_gate(old, new, attest).allowed)

    def test_retry_receipt_cannot_change_after_attestation(self):
        old, new = retry_fixture()
        def attest(a, b):
            b['queueJobReceiptSha256'] = 'f' * 64
            return True
        self.assertFalse(g.retry_gate(old, new, user_retry_consent=True,
            native_queue_attested=True, trusted_queue_verifier=attest).allowed)

    def test_nonfinite_extra_evidence_never_sent_for_attestation(self):
        evidence, context = example()
        evidence['metadata'] = {'temperature': float('nan')}
        seen = []
        decision = g.admit_for_existing_downloader(evidence, context,
            lambda *args: seen.append(args) or True)
        self.assertFalse(decision.allowed)
        self.assertFalse(seen)

    def test_immutable_mapping_evidence_still_accepted(self):
        evidence, context = example()
        context['nativeSourceLock'] = MappingProxyType(context['nativeSourceLock'])
        self.assertTrue(g.admit_for_existing_downloader(MappingProxyType(evidence),
            MappingProxyType(context), lambda *args: True).allowed)


if __name__ == '__main__':
    unittest.main()
