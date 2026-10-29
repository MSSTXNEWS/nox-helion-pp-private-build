"""G3-A source-only R30: native owner attestor MUST follow all local gates.

These are offline unit tests using a synthetic callback, never rights evidence.
"""
import unittest
import p03_modelcenter_gate as gate
from test_p03_modelcenter_gate import example


class AttestorPreflightR30G3A(unittest.TestCase):
    def verify(self, change=None, outcome="HOLD", reason=None, mutate=False, raised=False):
        e, c = example()
        if change:
            change(e, c)
        calls = []
        def callback(_e, _c):
            calls.append(True)
            if mutate:
                c["explicitUserDownloadConsent"] = False
            if raised:
                raise RuntimeError("synthetic verifier failure")
            return True
        result = gate.admit_for_existing_downloader(e, c, callback)
        self.assertEqual(result.status, outcome)
        if reason:
            self.assertIn(reason, result.reasons)
        self.assertEqual(len(calls), 1 if change is None else 0)
        return result

    def test_consent_must_precede_native_callback(self):
        self.verify(lambda e,c:c.update(explicitUserDownloadConsent=False),
                    reason="USER_DOWNLOAD_CONSENT_REQUIRED")

    def test_rights_sha_must_precede_native_callback(self):
        self.verify(lambda e,c:e.update(ownerRightsReceiptSha256=None),
                    reason="OWNER_RIGHTS_RECEIPT_MISSING")

    def test_source_lock_must_precede_native_callback(self):
        self.verify(lambda e,c:c.update(sourceCommit="f"*40),
                    reason="FROZEN_SOURCELOCK_MISMATCH")

    def test_resource_measurement_must_precede_native_callback(self):
        self.verify(lambda e,c:c["nativeMeasuredHardware"].update(vramBytes=1),
                    reason="INSUFFICIENT_REAL_VRAM")

    def test_existing_route_must_precede_native_callback(self):
        self.verify(lambda e,c:e.update(existingRoute="second_engine"),
                    reason="WRONG_OR_NEW_DOWNLOADER_ROUTE")

    def test_dependency_must_precede_native_callback(self):
        self.verify(lambda e,c:c["verifiedPrerequisites"].update(ollama=False),
                    reason="PREREQUISITE_OLLAMA_UNVERIFIED")

    def test_valid_candidate_invokes_native_once(self):
        self.verify(outcome="PASS_FOR_EXISTING_QUEUE")

    def test_native_callback_mutation_stays_hold(self):
        self.verify(reason="OWNER_ATTESTATION_EVIDENCE_CHANGED",mutate=True)

    def test_native_callback_exception_stays_hold(self):
        self.verify(reason="OWNER_ATTESTATION_ERROR",raised=True)


if __name__ == "__main__":
    unittest.main()
