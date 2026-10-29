"""Existing policy chain fixtures; no actual native queue, network or weights.

The native source OllamaModelAdapter.PullAsync sums all discovered digest layers;
the aggregate grows when another layer appears. The fixture receipt verifier is
deliberately synthetic; native receipt/host acceptance remains a separate gate.
"""
import unittest
import p03_modelcenter_gate as g
from test_p03_modelcenter_gate import example, queue_fixture


class ConnectedDownloadChain(unittest.TestCase):
    def pass_progress(self, previous, **fields):
        update = dict(previous, eventSequence=previous["eventSequence"] + 1, **fields)
        got = g.progress_gate(previous, update, lambda a, b: a is previous and b is update)
        self.assertTrue(got.allowed, got.reasons)
        return update

    def test_selected_pull_through_layers_stop_retry_and_registered_receipt(self):
        evidence, context = example()
        admission = g.admit_for_existing_downloader(evidence, context, lambda e, c: True)
        self.assertEqual(admission.existing_route, "EnqueueVerifiedPullAsync")
        queued, _ = queue_fixture()
        queued.update(state="QUEUED", eventSequence=1, completedBytes=None, totalBytes=None,
                      expectedArtifactSha256=evidence["artifactSha256"], manifestSha256=evidence["manifestSha256"])
        running = self.pass_progress(queued, state="RUNNING", completedBytes=10, totalBytes=None)
        first = self.pass_progress(running, completedBytes=100, totalBytes=100)
        layers = self.pass_progress(first, completedBytes=110, totalBytes=500000)
        stop = dict(layers, state="CANCELLING", eventSequence=layers["eventSequence"] + 1)
        self.assertIn("STOP_REQUESTED_NOT_SERVER_CONFIRMED",
                      g.progress_gate(layers, stop, lambda a, b: True).reasons)
        cancelled = self.pass_progress(stop, state="CANCELLED", nativeCancelAttested=True,
                                       cancelAckReceiptSha256="f" * 64)
        retry = dict(cancelled, state="QUEUED", attemptId="attempt-002", queueJobId="native-retry-002",
                     queueJobReceiptSha256="e" * 64, eventSequence=1, completedBytes=None, totalBytes=None)
        self.assertTrue(g.retry_gate(cancelled, retry, user_retry_consent=True,
                        native_queue_attested=True, trusted_queue_verifier=lambda a, b: True).allowed)
        resumed = self.pass_progress(retry, state="RUNNING", completedBytes=120, totalBytes=500000)
        completed = self.pass_progress(resumed, state="COMPLETED", completedBytes=500000,
                                      nativeCompletionAttested=True, completedReceiptSha256="f" * 64,
                                      observedArtifactSha256=evidence["artifactSha256"])
        self.assertEqual(completed["state"], "COMPLETED")
        self.assertFalse(g.progress_gate(cancelled, completed, lambda a, b: True).allowed)

    def test_local_gguf_admission_unknown_bytes_failure_then_retry(self):
        evidence, context = example()
        evidence.update(kind="gguf", existingRoute="EnqueueVerifiedGgufAsync",
                        localGgufPath="C:/models/approved.gguf", nativeGgufMagicVerified=True,
                        nativeLocalFileSha256=evidence["artifactSha256"])
        context["verifiedPrerequisites"] = {"python": True, "git": True, "ollama": True}
        self.assertTrue(g.admit_for_existing_downloader(evidence, context, lambda e, c: True).allowed)
        running, _ = queue_fixture()
        running.update(totalBytes=None, completedBytes=10)
        failed = self.pass_progress(running, state="FAILED", nativeFailureAttested=True,
                                    failureReceiptSha256="f" * 64)
        retry = dict(failed, state="QUEUED", attemptId="new-attempt", queueJobId="new-job",
                     queueJobReceiptSha256="e" * 64, eventSequence=1, completedBytes=None, totalBytes=None)
        self.assertTrue(g.retry_gate(failed, retry, user_retry_consent=True,
                        native_queue_attested=True, trusted_queue_verifier=lambda a, b: True).allowed)

    def test_layer_growth_requires_native_receipts_and_identity(self):
        old, new = queue_fixture(); new.update(totalBytes=200, completedBytes=150)
        self.assertFalse(g.progress_gate(old, new).allowed)
        self.assertFalse(g.progress_gate(old, new, lambda a, b: False).allowed)
        for key in ("manifestSha256", "expectedArtifactSha256", "queueJobReceiptSha256"):
            changed = dict(new, **{key: "f" * 64})
            self.assertFalse(g.progress_gate(old, changed, lambda a, b: True).allowed)

    def test_partial_counters_remain_monotone_and_exact(self):
        old, _ = queue_fixture(); old.update(totalBytes=None, completedBytes=100)
        for done, total in [(99, None), (None, None), (True, None), (100.0, None),
                            (100, 0), (101, 100), (1 << 63, None)]:
            new = dict(old, eventSequence=11, completedBytes=done, totalBytes=total)
            self.assertFalse(g.progress_gate(old, new, lambda a, b: True).allowed, (done, total))
        self.pass_progress(old, completedBytes=110, totalBytes=None)

    def test_unknown_total_never_completes_and_wrong_sha_never_registers(self):
        old, new = queue_fixture()
        for total, done, digest in [(None, 100, "d" * 64), (100, 100, "f" * 64), (100, 80, "d" * 64)]:
            new.update(state="COMPLETED", totalBytes=total, completedBytes=done,
                       completedReceiptSha256="e" * 64, nativeCompletionAttested=True,
                       observedArtifactSha256=digest)
            self.assertFalse(g.progress_gate(old, new, lambda a, b: True).allowed)

    def test_total_cannot_shrink_or_grow_after_stop(self):
        old, new = queue_fixture(); new.update(totalBytes=90, completedBytes=80)
        self.assertFalse(g.progress_gate(old, new, lambda a, b: True).allowed)
        old.update(state="CANCELLING"); new.update(state="CANCELLED", totalBytes=200,
                            nativeCancelAttested=True, cancelAckReceiptSha256="f" * 64)
        self.assertFalse(g.progress_gate(old, new, lambda a, b: True).allowed)

    def test_gguf_cannot_enter_existing_ollama_create_chain_without_ollama(self):
        evidence, context = example()
        evidence.update(kind="gguf", existingRoute="EnqueueVerifiedGgufAsync",
                        localGgufPath="C:/models/approved.gguf", nativeGgufMagicVerified=True,
                        nativeLocalFileSha256=evidence["artifactSha256"])
        context["verifiedPrerequisites"] = {"python": True, "git": True}
        decision = g.admit_for_existing_downloader(evidence, context, lambda e, c: True)
        self.assertFalse(decision.allowed)
        self.assertIn("PREREQUISITE_OLLAMA_UNVERIFIED", decision.reasons)


if __name__ == "__main__":
    unittest.main()
