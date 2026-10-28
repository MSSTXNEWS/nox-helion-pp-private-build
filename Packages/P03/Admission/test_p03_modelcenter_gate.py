"""Offline owner-3 policy regressions. No downloads, weights or new engine."""
import unittest
import p03_modelcenter_gate as g

# Synthetic unit-test verifier: NEVER a production/native authorization receipt.
TEST_ONLY_NATIVE_RECEIPT_VERIFIER = lambda previous, update: True


def example():
    e = dict(kind="ollama", modelTag="qwen3:0.6b", existingRoute="EnqueueVerifiedPullAsync",
             licenseAcknowledged=True, licenseEvidenceUrl="https://example.org/license", licenseId="LICENSE-REVIEWED",
             artifactSha256="a"*64, manifestSha256="b"*64, artifactBytes=500000,
             requiredDiskBytes=800000, immutableRevision="c"*40,
             ownerRightsReceiptSha256="d"*64, requiresGPU=True, requiredVramBytes=400000)
    c = dict(sourceCommit=g.BASE_COMMIT, sourceTree=g.BASE_TREE, owner3DonorHead=g.DONOR_OWNER3_HEAD,
             sessionTrusted=True, hostQueueAvailable=True, explicitUserDownloadConsent=True,
             verifiedPrerequisites={"ollama": True},
             nativeMeasuredHardware={"attested": True, "freeDiskBytes": 900000, "vramBytes": 900000},
             nativeSourceLock={"attested": True, "verifiedRawPartCount": 3,
                               "verifiedExtractedMemberCount": 729,
                               "ownerReceiptSha256": "a"*64,
                               "hostSourceReceiptSha256": "b"*64})
    return e, c


class Admission(unittest.TestCase):
    def assertHold(self, e, c, key, attestor=lambda _e, _c: True):
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
        e,c=example(); self.assertHold(e,c,"OWNER_ATTESTATION_REJECTED",lambda _e, _c: False)

    def test_16_verifier_exception(self):
        e,c=example(); self.assertHold(e,c,"OWNER_ATTESTATION_ERROR",lambda _e, _c: 1/0)

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
        e,c=example(); x=g.admit_for_existing_downloader(e,c,lambda _e, _c: True)
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
                         ("PREREQUISITE_CUDA_UNVERIFIED","PREREQUISITE_TORCH_UNVERIFIED",
                          "PREREQUISITE_PEFT_UNVERIFIED","PREREQUISITE_TRL_UNVERIFIED",
                          "PREREQUISITE_ACCELERATE_UNVERIFIED"))

    def test_27_retry_receipt(self):
        old=dict(attemptId="a",completedBytes=10)
        new=dict(attemptId="b",completedBytes=1,totalBytes=100,state="RUNNING")
        self.assertIn("RETRY_REQUIRES_NEW_QUEUE_JOB_RECEIPT",g.progress_gate(old,new,TEST_ONLY_NATIVE_RECEIPT_VERIFIER).reasons)

    def test_28_progress_monotonic(self):
        old=dict(attemptId="a",completedBytes=80)
        new=dict(attemptId="a",completedBytes=20,totalBytes=100,state="RUNNING")
        self.assertIn("NON_MONOTONIC_OR_INVALID_PROGRESS",g.progress_gate(old,new,TEST_ONLY_NATIVE_RECEIPT_VERIFIER).reasons)

    def test_29_stop_is_request(self):
        old=dict(attemptId="a",completedBytes=50)
        new=dict(attemptId="a",completedBytes=50,totalBytes=100,state="STOP")
        self.assertIn("STOP_REQUESTED_NOT_SERVER_CONFIRMED",g.progress_gate(old,new,TEST_ONLY_NATIVE_RECEIPT_VERIFIER).reasons)

    def test_30_completed_requires_receipt(self):
        old=dict(attemptId="a",completedBytes=60)
        new=dict(attemptId="a",completedBytes=100,totalBytes=100,state="COMPLETED")
        self.assertIn("COMPLETION_RECEIPT_OR_BYTES_MISSING",g.progress_gate(old,new,TEST_ONLY_NATIVE_RECEIPT_VERIFIER).reasons)

    def test_31_real_completed_receipt(self):
        old, new = queue_fixture()
        new.update(state="COMPLETED",completedBytes=100,
                   completedReceiptSha256="e"*64, observedArtifactSha256="d"*64,
                   nativeCompletionAttested=True)
        self.assertEqual(g.progress_gate(old,new,TEST_ONLY_NATIVE_RECEIPT_VERIFIER).status,"PASS_FOR_EXISTING_QUEUE")

    def test_65_empty_license_id_hold(self):
        e,c=example();e["licenseId"]="  "
        self.assertHold(e,c,"LICENSE_EVIDENCE_MISSING")

    def test_66_gguf_native_header_needed(self):
        e,c=example(); e.update(kind="gguf",existingRoute="EnqueueVerifiedGgufAsync",
                                localGgufPath="C:/model/verified.gguf",nativeLocalFileSha256="a"*64)
        c["verifiedPrerequisites"]={"python":True,"git":True}
        self.assertHold(e,c,"GGUF_NATIVE_MAGIC_UNVERIFIED")

    def test_67_gguf_digest_must_match_local(self):
        e,c=example(); e.update(kind="gguf",existingRoute="EnqueueVerifiedGgufAsync",
                                localGgufPath="C:/model/verified.gguf",nativeGgufMagicVerified=True,
                                nativeLocalFileSha256="e"*64)
        c["verifiedPrerequisites"]={"python":True,"git":True}
        self.assertHold(e,c,"GGUF_LOCAL_FILE_SHA_NOT_MATCHED")

    def test_68_gguf_native_header_digest_policy_pass(self):
        e,c=example(); e.update(kind="gguf",existingRoute="EnqueueVerifiedGgufAsync",
                                localGgufPath="C:/model/verified.gguf",nativeGgufMagicVerified=True,
                                nativeLocalFileSha256="a"*64)
        c["verifiedPrerequisites"]={"python":True,"git":True}
        self.assertEqual(g.admit_for_existing_downloader(e,c,lambda _e,_c:True).status,"PASS_FOR_EXISTING_QUEUE")

    def test_69_training_all_dependencies(self):
        self.assertEqual(g.prerequisite_gates(dict.fromkeys(
            ("python","git","cuda","torch","peft","trl","accelerate"),True),"TRAINING"),())

    def test_32_no_implicit_download(self):
        self.assertNotIn("requests",g.__dict__)
        self.assertNotIn("subprocess",g.__dict__)
        self.assertNotIn("urllib.request",g.__dict__)




def queue_fixture():
    old = dict(attemptId="attempt-001", queueJobId="original-p03-job-001",
               queueJobReceiptSha256="a"*64, manifestSha256="b"*64,
               expectedArtifactSha256="d"*64, totalBytes=100,
               completedBytes=60, state="RUNNING", nativeHostId="owner6-host-01",
               queueOwnerSessionId="native-session-001",eventSequence=10)
    new = dict(old)
    new.update(completedBytes=80,eventSequence=11)
    return old, new


class QueueStateRegression(unittest.TestCase):
    def expect(self, old, new, reason):
        got = g.progress_gate(old,new,TEST_ONLY_NATIVE_RECEIPT_VERIFIER)
        self.assertEqual(got.status,"HOLD")
        self.assertIn(reason,got.reasons)

    def test_33_same_job_monotonic(self):
        old, new = queue_fixture()
        self.assertEqual(g.progress_gate(old,new,TEST_ONLY_NATIVE_RECEIPT_VERIFIER).status,"PASS_FOR_EXISTING_QUEUE")

    def test_34_missing_job_identity(self):
        old, new = queue_fixture(); old.pop("queueJobId")
        self.expect(old,new,"QUEUE_JOB_ID_DRIFT_OR_MISSING")

    def test_35_changed_job_identity(self):
        old, new = queue_fixture(); new["queueJobId"] = "foreign-job"
        self.expect(old,new,"QUEUE_JOB_ID_DRIFT_OR_MISSING")

    def test_36_manifest_drift(self):
        old, new = queue_fixture(); new["manifestSha256"] = "e"*64
        self.expect(old,new,"QUEUE_JOB_PROVENANCE_DRIFT_OR_MISSING")

    def test_37_changed_target_sha(self):
        old, new = queue_fixture(); new["expectedArtifactSha256"] = "f"*64
        self.expect(old,new,"QUEUE_JOB_PROVENANCE_DRIFT_OR_MISSING")

    def test_38_changed_total_bytes(self):
        old, new = queue_fixture(); new["totalBytes"] = 200
        self.expect(old,new,"TOTAL_BYTES_UNVERIFIED_OR_CHANGED")

    def test_39_terminal_cannot_restart(self):
        old, new = queue_fixture(); old["state"]="COMPLETED"
        self.expect(old,new,"INVALID_OR_TERMINAL_QUEUE_TRANSITION")

    def test_40_cancelled_cannot_complete(self):
        old, new = queue_fixture(); old["state"]="CANCELLED";new["state"]="COMPLETED"
        self.expect(old,new,"INVALID_OR_TERMINAL_QUEUE_TRANSITION")

    def test_41_failed_cannot_resume(self):
        old, new = queue_fixture(); old["state"]="FAILED"
        self.expect(old,new,"INVALID_OR_TERMINAL_QUEUE_TRANSITION")

    def test_42_completing_without_actual_digest(self):
        old, new = queue_fixture(); new.update(state="COMPLETED",completedBytes=100,
           completedReceiptSha256="f"*64,nativeCompletionAttested=True)
        self.expect(old,new,"DOWNLOADED_ARTIFACT_SHA_MISMATCH")

    def test_43_wrong_observed_digest(self):
        old, new = queue_fixture(); new.update(state="COMPLETED",completedBytes=100,
           completedReceiptSha256="f"*64,nativeCompletionAttested=True,observedArtifactSha256="e"*64)
        self.expect(old,new,"DOWNLOADED_ARTIFACT_SHA_MISMATCH")

    def test_44_complete_without_native_attestation(self):
        old, new = queue_fixture(); new.update(state="COMPLETED",completedBytes=100,
           completedReceiptSha256="f"*64,observedArtifactSha256="d"*64)
        self.expect(old,new,"COMPLETION_RECEIPT_OR_BYTES_MISSING")

    def test_45_progress_cannot_exceed_total(self):
        old, new = queue_fixture(); new["completedBytes"] = 101
        self.expect(old,new,"NON_MONOTONIC_OR_INVALID_PROGRESS")

    def test_46_boolean_bytes_not_int(self):
        old, new = queue_fixture(); new["completedBytes"] = True
        self.expect(old,new,"NON_MONOTONIC_OR_INVALID_PROGRESS")

    def test_47_running_after_cancel_forbidden(self):
        old, new = queue_fixture(); old["state"]="CANCEL_REQUESTED"
        self.expect(old,new,"INVALID_OR_TERMINAL_QUEUE_TRANSITION")

    def test_48_cancel_requested_not_cancelled(self):
        old, new = queue_fixture(); new["state"]="CANCEL_REQUESTED"
        self.expect(old,new,"STOP_REQUESTED_NOT_SERVER_CONFIRMED")

    def test_49_cancelled_requires_native_ack(self):
        old, new = queue_fixture(); old["state"]="CANCELLING";new["state"]="CANCELLED"
        self.expect(old,new,"CANCELLATION_ACK_NOT_ATTESTED")

    def test_50_cancelled_with_native_ack(self):
        old, new = queue_fixture(); old["state"]="CANCELLING";new.update(state="CANCELLED",
                nativeCancelAttested=True,cancelAckReceiptSha256="f"*64)
        self.assertEqual(g.progress_gate(old,new,TEST_ONLY_NATIVE_RECEIPT_VERIFIER).status,"PASS_FOR_EXISTING_QUEUE")

    def test_51_failed_requires_native_receipt(self):
        old, new = queue_fixture(); new["state"]="FAILED"
        self.expect(old,new,"FAILURE_RECEIPT_NOT_ATTESTED")

    def test_52_failed_with_native_receipt(self):
        old, new = queue_fixture(); new.update(state="FAILED",nativeFailureAttested=True,
                                                failureReceiptSha256="f"*64)
        self.assertEqual(g.progress_gate(old,new,TEST_ONLY_NATIVE_RECEIPT_VERIFIER).status,"PASS_FOR_EXISTING_QUEUE")

    def test_53_retry_not_before_terminal(self):
        old, new = retry_fixture(); old["state"]="RUNNING"
        self.assertIn("RETRY_REQUIRES_CONFIRMED_TERMINAL_STATE",
                      g.retry_gate(old,new,trusted_queue_verifier=TEST_ONLY_NATIVE_RECEIPT_VERIFIER,user_retry_consent=True,native_queue_attested=True).reasons)

    def test_54_retry_unique_attempt(self):
        old, new = retry_fixture(); new["attemptId"] = old["attemptId"]
        self.assertIn("RETRY_ATTEMPT_NOT_UNIQUE",
                      g.retry_gate(old,new,trusted_queue_verifier=TEST_ONLY_NATIVE_RECEIPT_VERIFIER,user_retry_consent=True,native_queue_attested=True).reasons)

    def test_55_retry_new_queue_job(self):
        old, new = retry_fixture(); new["queueJobId"] = old["queueJobId"]
        self.assertIn("RETRY_QUEUE_JOB_NOT_UNIQUE",
                      g.retry_gate(old,new,trusted_queue_verifier=TEST_ONLY_NATIVE_RECEIPT_VERIFIER,user_retry_consent=True,native_queue_attested=True).reasons)

    def test_56_retry_needs_new_queue_receipt(self):
        old, new = retry_fixture(); new["queueJobReceiptSha256"] = old["queueJobReceiptSha256"]
        self.assertIn("RETRY_NEW_QUEUE_RECEIPT_MISSING",
                      g.retry_gate(old,new,trusted_queue_verifier=TEST_ONLY_NATIVE_RECEIPT_VERIFIER,user_retry_consent=True,native_queue_attested=True).reasons)

    def test_57_retry_no_manifest_swap(self):
        old, new = retry_fixture(); new["manifestSha256"] = "f"*64
        self.assertIn("RETRY_ARTIFACT_IDENTITY_DRIFT",
                      g.retry_gate(old,new,trusted_queue_verifier=TEST_ONLY_NATIVE_RECEIPT_VERIFIER,user_retry_consent=True,native_queue_attested=True).reasons)

    def test_58_retry_resets_bytes(self):
        old, new = retry_fixture(); new["completedBytes"] = 1
        self.assertIn("RETRY_BYTES_INVALID",
                      g.retry_gate(old,new,trusted_queue_verifier=TEST_ONLY_NATIVE_RECEIPT_VERIFIER,user_retry_consent=True,native_queue_attested=True).reasons)

    def test_59_retry_explicit_consent(self):
        old, new = retry_fixture()
        self.assertIn("RETRY_USER_CONSENT_REQUIRED",
                      g.retry_gate(old,new,trusted_queue_verifier=TEST_ONLY_NATIVE_RECEIPT_VERIFIER,user_retry_consent=False,native_queue_attested=True).reasons)

    def test_60_retry_native_ack(self):
        old, new = retry_fixture()
        self.assertIn("RETRY_NATIVE_ATTESTATION_REQUIRED",
                      g.retry_gate(old,new,trusted_queue_verifier=TEST_ONLY_NATIVE_RECEIPT_VERIFIER,user_retry_consent=True,native_queue_attested=False).reasons)

    def test_61_retry_new_job_after_terminal(self):
        old, new = retry_fixture()
        self.assertEqual(g.retry_gate(old,new,trusted_queue_verifier=TEST_ONLY_NATIVE_RECEIPT_VERIFIER,user_retry_consent=True,
                                      native_queue_attested=True).status,"PASS_FOR_EXISTING_QUEUE")

    def test_63_retry_unattested_failure_forbidden(self):
        old,new=retry_fixture();old.pop("nativeFailureAttested")
        self.assertIn("RETRY_PREVIOUS_FAILURE_UNATTESTED",
            g.retry_gate(old,new,trusted_queue_verifier=TEST_ONLY_NATIVE_RECEIPT_VERIFIER,user_retry_consent=True,native_queue_attested=True).reasons)

    def test_64_retry_unattested_cancel_forbidden(self):
        old,new=retry_fixture();old.pop("failureReceiptSha256");old["state"]="CANCELLED"
        self.assertIn("RETRY_PREVIOUS_CANCEL_UNATTESTED",
            g.retry_gate(old,new,trusted_queue_verifier=TEST_ONLY_NATIVE_RECEIPT_VERIFIER,user_retry_consent=True,native_queue_attested=True).reasons)

    def test_62_queued_does_not_equal_downloading(self):
        old, new = queue_fixture(); old.update(state="QUEUED",completedBytes=0);new.update(state="QUEUED",completedBytes=0)
        self.assertEqual(g.progress_gate(old,new,TEST_ONLY_NATIVE_RECEIPT_VERIFIER).status,"PASS_FOR_EXISTING_QUEUE")
        self.assertNotEqual(new["state"],"COMPLETED")


def retry_fixture():
    old,new = queue_fixture()
    old.update(state="FAILED", nativeFailureAttested=True, failureReceiptSha256="f"*64)
    new.update(state="QUEUED", attemptId="attempt-002", queueJobId="original-p03-job-002",
               queueJobReceiptSha256="c"*64, completedBytes=0,eventSequence=1)
    return old,new

class TrustedNativeReceiptRegressions(unittest.TestCase):
    def test_70_progress_missing_verifier_is_hold(self):
        old, new = queue_fixture()
        result = g.progress_gate(old, new)
        self.assertEqual(result.status, "HOLD")
        self.assertIn("NATIVE_QUEUE_VERIFIER_MISSING", result.reasons)

    def test_71_progress_verifier_rejection_is_hold(self):
        old, new = queue_fixture()
        result = g.progress_gate(old, new, lambda _old, _new: False)
        self.assertIn("NATIVE_QUEUE_RECEIPT_REJECTED", result.reasons)

    def test_72_progress_verifier_error_is_hold(self):
        old, new = queue_fixture()
        def broken(_old, _new):
            raise OSError("native queue connection lost")
        result = g.progress_gate(old, new, broken)
        self.assertIn("NATIVE_QUEUE_VERIFIER_ERROR", result.reasons)

    def test_73_completion_without_queue_verifier_is_hold(self):
        old, new = queue_fixture()
        new.update(state="COMPLETED", completedBytes=100,
                   completedReceiptSha256="e"*64, observedArtifactSha256="d"*64,
                   nativeCompletionAttested=True)
        self.assertIn("NATIVE_QUEUE_VERIFIER_MISSING", g.progress_gate(old, new).reasons)

    def test_74_retry_boolean_only_without_verifier_is_hold(self):
        old, new = retry_fixture()
        result = g.retry_gate(old,new,user_retry_consent=True,native_queue_attested=True)
        self.assertEqual(result.status, "HOLD")
        self.assertIn("NATIVE_QUEUE_VERIFIER_MISSING", result.reasons)

    def test_75_retry_verifier_rejected_is_hold(self):
        old, new = retry_fixture()
        result = g.retry_gate(old,new,user_retry_consent=True,native_queue_attested=True,
                              trusted_queue_verifier=lambda _old, _new: "True")
        self.assertIn("NATIVE_QUEUE_RECEIPT_REJECTED", result.reasons)

    def test_76_verifier_sees_native_identity_and_bytes(self):
        old, new = queue_fixture()
        observed=[]
        def native_stub(a,b):
            observed.append((a["queueJobId"], b["queueJobId"],a["completedBytes"],b["completedBytes"]))
            return a["queueJobId"]==b["queueJobId"] and b["completedBytes"]==80
        self.assertEqual(g.progress_gate(old,new,native_stub).status,"PASS_FOR_EXISTING_QUEUE")
        self.assertEqual(observed,[("original-p03-job-001","original-p03-job-001",60,80)])

class R05NativeBoundaryRegressions(unittest.TestCase):
    # These are pure synthetic fixtures; they are not native host attestations.
    def test_77_source_lock_parts_missing_hold(self):
        e,c=example(); c["nativeSourceLock"]["verifiedRawPartCount"]=2
        got=g.admit_for_existing_downloader(e,c,lambda ev,ctx:True)
        self.assertIn("CANONICAL_ORIGINAL_SOURCELOCK_UNVERIFIED",got.reasons)

    def test_78_source_lock_unattested_hold(self):
        e,c=example(); c["nativeSourceLock"].pop("attested")
        got=g.admit_for_existing_downloader(e,c,lambda ev,ctx:True)
        self.assertIn("CANONICAL_ORIGINAL_SOURCELOCK_UNVERIFIED",got.reasons)

    def test_79_source_lock_host_receipt_missing_hold(self):
        e,c=example(); c["nativeSourceLock"]["hostSourceReceiptSha256"]=None
        got=g.admit_for_existing_downloader(e,c,lambda ev,ctx:True)
        self.assertIn("CANONICAL_ORIGINAL_SOURCELOCK_UNVERIFIED",got.reasons)

    def test_80_attestor_rejects_context_mismatch(self):
        e,c=example()
        def native_boundary(ev,ctx):
            return ctx["nativeMeasuredHardware"]["freeDiskBytes"] == 123
        got=g.admit_for_existing_downloader(e,c,native_boundary)
        self.assertIn("OWNER_ATTESTATION_REJECTED",got.reasons)

    def test_81_legacy_attestor_cannot_skip_context(self):
        e,c=example()
        got=g.admit_for_existing_downloader(e,c,lambda ev:True)
        self.assertIn("OWNER_ATTESTATION_ERROR",got.reasons)

    def test_82_disallow_private_license_url(self):
        e,c=example(); e["licenseEvidenceUrl"]="https://127.0.0.1/license"
        got=g.admit_for_existing_downloader(e,c,lambda ev,ctx:True)
        self.assertIn("LICENSE_EVIDENCE_MISSING",got.reasons)

    def test_83_disallow_internal_hostname(self):
        e,c=example(); e["licenseEvidenceUrl"]="https://test.local/license"
        got=g.admit_for_existing_downloader(e,c,lambda ev,ctx:True)
        self.assertIn("LICENSE_EVIDENCE_MISSING",got.reasons)

    def test_84_gguf_relative_path_hold(self):
        e,c=example(); e.update(kind="gguf",existingRoute="EnqueueVerifiedGgufAsync",
           localGgufPath="../verified.gguf",nativeGgufMagicVerified=True,
           nativeLocalFileSha256="a"*64)
        c["verifiedPrerequisites"]={"python":True,"git":True}
        got=g.admit_for_existing_downloader(e,c,lambda ev,ctx:True)
        self.assertIn("LOCAL_GGUF_PATH_REQUIRED",got.reasons)

    def test_85_replayed_native_progress_sequence_hold(self):
        old,new=queue_fixture();new["eventSequence"]=old["eventSequence"]
        got=g.progress_gate(old,new,TEST_ONLY_NATIVE_RECEIPT_VERIFIER)
        self.assertIn("NON_MONOTONIC_NATIVE_EVENT_SEQUENCE",got.reasons)

    def test_86_foreign_native_session_progress_hold(self):
        old,new=queue_fixture();new["queueOwnerSessionId"]="other-session"
        got=g.progress_gate(old,new,TEST_ONLY_NATIVE_RECEIPT_VERIFIER)
        self.assertIn("QUEUE_NATIVE_HOST_OR_SESSION_DRIFT",got.reasons)

    def test_87_retry_preserves_native_session(self):
        old,new=retry_fixture();new["nativeHostId"]="foreign-host"
        got=g.retry_gate(old,new,user_retry_consent=True,native_queue_attested=True,
           trusted_queue_verifier=TEST_ONLY_NATIVE_RECEIPT_VERIFIER)
        self.assertIn("RETRY_NATIVE_SESSION_MISMATCH",got.reasons)

    def test_88_retry_sequence_starts_one(self):
        old,new=retry_fixture();new["eventSequence"]=25
        got=g.retry_gate(old,new,user_retry_consent=True,native_queue_attested=True,
           trusted_queue_verifier=TEST_ONLY_NATIVE_RECEIPT_VERIFIER)
        self.assertIn("RETRY_SEQUENCE_NOT_RESET",got.reasons)

    def test_89_untrusted_control_char_queue_id_hold(self):
        old,new=queue_fixture();new["queueJobId"]="original\njob"
        got=g.progress_gate(old,new,TEST_ONLY_NATIVE_RECEIPT_VERIFIER)
        self.assertIn("QUEUE_JOB_ID_DRIFT_OR_MISSING",got.reasons)

    def test_90_good_native_context_synthetic_pass_still_not_install(self):
        e,c=example(); captured=[]
        def local_fixture(ev,ctx):
            captured.append((ev["modelTag"],ctx["nativeSourceLock"]["verifiedRawPartCount"]))
            return True
        got=g.admit_for_existing_downloader(e,c,local_fixture)
        self.assertEqual(got.status,"PASS_FOR_EXISTING_QUEUE")
        self.assertEqual(captured,[("qwen3:0.6b",3)])
        self.assertFalse(hasattr(got,"installed"))

if __name__ == "__main__":
    unittest.main()
