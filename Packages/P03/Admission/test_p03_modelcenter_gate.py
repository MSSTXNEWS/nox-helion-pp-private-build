"""Offline owner-3 policy regressions. No downloads, weights or new engine."""
import unittest
import p03_modelcenter_gate as g


def example():
    e = dict(kind="ollama", modelTag="qwen3:0.6b", existingRoute="EnqueueVerifiedPullAsync",
             licenseAcknowledged=True, licenseEvidenceUrl="https://example.org/license", licenseId="LICENSE-REVIEWED",
             artifactSha256="a"*64, manifestSha256="b"*64, artifactBytes=500000,
             requiredDiskBytes=800000, immutableRevision="c"*40,
             ownerRightsReceiptSha256="d"*64, requiresGPU=True, requiredVramBytes=400000)
    c = dict(sourceCommit=g.BASE_COMMIT, sourceTree=g.BASE_TREE, owner3DonorHead=g.DONOR_OWNER3_HEAD,
             sessionTrusted=True, hostQueueAvailable=True, explicitUserDownloadConsent=True,
             verifiedPrerequisites={"ollama": True},
             nativeMeasuredHardware={"attested": True, "freeDiskBytes": 900000, "vramBytes": 900000})
    return e, c


class Admission(unittest.TestCase):
    def assertHold(self, e, c, key, attestor=lambda _e: True):
        x = g.admit_for_existing_downloader(e, c, attestor)
        self.assertEqual(x.status, "HOLD")
        self.assertIn(key, x.reasons)
        self.assertIsNone(x.existing_route)

    def test_01_canonical_25(self):
        self.assertEqual(len(g.OLLAMA_TAG_LEADS), 25)
        self.assertEqual(len(set(g.OLLAMA_TAG_LEADS)), 25)
        self.assertTrue(all(":" in x and not x.endswith(":latest") for x in g.OLLAMA_TAG_LEADS))

    def test_02_external_17(self):
        self.assertEqual(len(g.EXTERNAL_LEADS), 17)
        self.assertEqual(len({x[0] for x in g.EXTERNAL_LEADS}), 17)
        self.assertTrue({"ASR","TTS","IMAGE","VIDEO","TRAINING"} <= {x[1] for x in g.EXTERNAL_LEADS})

    def test_03_every_lead_hold(self):
        for name in g.OLLAMA_TAG_LEADS + tuple(x[0] for x in g.EXTERNAL_LEADS):
            self.assertEqual(g.review_lead(name).status, "HOLD")

    def test_04_unknown_hold(self):
        self.assertIn("UNKNOWN_MODEL", g.review_lead("new:latest").reasons)

    def test_05_no_attestor(self):
        e,c=example(); self.assertHold(e,c,"TRUSTED_OWNER_ATTESTOR_MISSING",None)

    def test_06_baseline_drift(self):
        e,c=example(); c["sourceCommit"]="f"*40; self.assertHold(e,c,"FROZEN_SOURCELOCK_MISMATCH")

    def test_07_owner_drift(self):
        e,c=example(); c["owner3DonorHead"]="e"*40; self.assertHold(e,c,"OWNER3_DONOR_DRIFT")

    def test_08_no_native_session(self):
        e,c=example(); c["sessionTrusted"]=False; self.assertHold(e,c,"UNTRUSTED_NATIVE_SESSION")

    def test_09_no_queue(self):
        e,c=example(); c["hostQueueAvailable"]=False; self.assertHold(e,c,"EXISTING_QUEUE_UNAVAILABLE")

    def test_10_no_consent(self):
        e,c=example(); c["explicitUserDownloadConsent"]=False; self.assertHold(e,c,"USER_DOWNLOAD_CONSENT_REQUIRED")

    def test_11_bad_rights(self):
        e,c=example(); e["licenseEvidenceUrl"]="http://example.org/license"; self.assertHold(e,c,"LICENSE_EVIDENCE_MISSING")

    def test_12_sha(self):
        e,c=example(); e["manifestSha256"]="0"*64; self.assertHold(e,c,"ARTIFACT_AND_MANIFEST_SHA_UNVERIFIED")

    def test_13_wrong_revision(self):
        e,c=example(); e["immutableRevision"]="latest"; self.assertHold(e,c,"IMMUTABLE_REVISION_UNVERIFIED")

    def test_14_no_owner_receipt(self):
        e,c=example(); e["ownerRightsReceiptSha256"]=None; self.assertHold(e,c,"OWNER_RIGHTS_RECEIPT_MISSING")

    def test_15_reject_verifier(self):
        e,c=example(); self.assertHold(e,c,"OWNER_ATTESTATION_REJECTED",lambda _e: False)

    def test_16_verifier_exception(self):
        e,c=example(); self.assertHold(e,c,"OWNER_ATTESTATION_ERROR",lambda _e: 1/0)

    def test_17_ui_vram_not_allowed(self):
        e,c=example(); c["nativeMeasuredHardware"]={"vramBytes":900000, "freeDiskBytes":900000}
        c["editableUiVram"]="99999"; self.assertHold(e,c,"NATIVE_HARDWARE_NOT_ATTESTED")

    def test_18_out_of_vram(self):
        e,c=example(); c["nativeMeasuredHardware"]["vramBytes"]=123; self.assertHold(e,c,"INSUFFICIENT_REAL_VRAM")

    def test_19_disk(self):
        e,c=example(); c["nativeMeasuredHardware"]["freeDiskBytes"]=123; self.assertHold(e,c,"INSUFFICIENT_REAL_DISK")

    def test_20_unknown_tag(self):
        e,c=example(); e["modelTag"]="foo:latest"; self.assertHold(e,c,"NOT_IN_OWNER3_EXACT_TAG_LEADS")

    def test_21_legacy_route_forbidden(self):
        e,c=example(); e["existingRoute"]="my_new_downloader"; self.assertHold(e,c,"WRONG_OR_NEW_DOWNLOADER_ROUTE")

    def test_22_ollama_missing(self):
        e,c=example(); c["verifiedPrerequisites"]["ollama"]="installed"; self.assertHold(e,c,"PREREQUISITE_OLLAMA_UNVERIFIED")

    def test_23_pass_only_for_existing_queue_after_trusted_attestor(self):
        e,c=example(); x=g.admit_for_existing_downloader(e,c,lambda _e: True)
        self.assertEqual(x.status,"PASS_FOR_EXISTING_QUEUE")
        self.assertEqual(x.existing_route,"EnqueueVerifiedPullAsync")

    def test_24_gguf_requires_local(self):
        e,c=example(); e.update(kind="gguf", existingRoute="EnqueueVerifiedGgufAsync")
        c["verifiedPrerequisites"]={"python":True,"git":True}
        self.assertHold(e,c,"LOCAL_GGUF_PATH_REQUIRED")

    def test_25_external_transport_hold(self):
        e,c=example(); e.update(kind="external", leadId="asr-whisper-small",existingRoute="other")
        c["verifiedPrerequisites"]={"python":True,"git":True}
        self.assertHold(e,c,"EXTERNAL_WEIGHT_TRANSPORT_NOT_IN_EXISTING_QUEUE")

    def test_26_training_cuda_peft(self):
        self.assertEqual(g.prerequisite_gates({"python":True,"git":True},"TRAINING"),
                         ("PREREQUISITE_CUDA_UNVERIFIED","PREREQUISITE_PEFT_UNVERIFIED"))

    def test_27_retry_receipt(self):
        old=dict(attemptId="a",completedBytes=10)
        new=dict(attemptId="b",completedBytes=1,totalBytes=100,state="RUNNING")
        self.assertIn("RETRY_REQUIRES_NEW_QUEUE_JOB_RECEIPT",g.progress_gate(old,new).reasons)

    def test_28_progress_monotonic(self):
        old=dict(attemptId="a",completedBytes=80)
        new=dict(attemptId="a",completedBytes=20,totalBytes=100,state="RUNNING")
        self.assertIn("NON_MONOTONIC_OR_INVALID_PROGRESS",g.progress_gate(old,new).reasons)

    def test_29_stop_is_request(self):
        old=dict(attemptId="a",completedBytes=50)
        new=dict(attemptId="a",completedBytes=50,totalBytes=100,state="STOP")
        self.assertIn("STOP_REQUESTED_NOT_SERVER_CONFIRMED",g.progress_gate(old,new).reasons)

    def test_30_completed_requires_receipt(self):
        old=dict(attemptId="a",completedBytes=60)
        new=dict(attemptId="a",completedBytes=100,totalBytes=100,state="COMPLETED")
        self.assertIn("COMPLETION_RECEIPT_OR_BYTES_MISSING",g.progress_gate(old,new).reasons)

    def test_31_real_completed_receipt(self):
        old=dict(attemptId="a",completedBytes=60)
        new=dict(attemptId="a",completedBytes=100,totalBytes=100,state="COMPLETED",completedReceiptSha256="a"*64)
        self.assertEqual(g.progress_gate(old,new).status,"PASS_FOR_EXISTING_QUEUE")

    def test_32_no_implicit_download(self):
        self.assertNotIn("requests",g.__dict__)
        self.assertNotIn("subprocess",g.__dict__)
        self.assertNotIn("urllib.request",g.__dict__)


if __name__ == "__main__":
    unittest.main()
