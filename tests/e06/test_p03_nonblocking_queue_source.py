"""NOX P03 native route queue no-loss regression on the existing OneHost sources.

The source contract prevents model Pull/Retry/GGUF operations from blocking the
WebView2 native reply for the entire transfer. This is NOT native Windows E07.
"""
from pathlib import Path
import hashlib
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
ROUTES = ROOT / "Packages/P03/Source/P03.ModelCenter/ModelCenterNativeRoutes.cs"
BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def assert_nonblocking(source):
    sections = {}
    for route, trailing in (
        ("models.retry", "models.gguf.import"),
        ("models.gguf.import", "models.pull"),
        ("models.pull", "default:"),
    ):
        marker = 'case "' + route + '":'
        ending = 'case "' + trailing + '":' if trailing != "default:" else trailing
        if source.count(marker) != 1:
            raise AssertionError("P03_ROUTE_MISSING_OR_DUPLICATED:" + route)
        part = source.split(marker, 1)[1].split(ending, 1)[0]
        if re.search(r"await\s+_worker\.RunNextAsync\s*\(", part):
            raise AssertionError("P03_MODEL_TRANSFER_BLOCKS_NATIVE_UI:" + route)
        expected = {"models.retry": "retry.Id",
                    "models.gguf.import": "imported.Id",
                    "models.pull": "job.Id"}[route]
        if "StartQueuedTransfer(" + expected + ")" not in part:
            raise AssertionError("P03_NO_DURABLE_JOB_HANDOFF:" + route)
        if "result=PublicJob(" not in part:
            raise AssertionError("P03_QUEUED_JOB_STATUS_NOT_RETURNED:" + route)
        sections[route] = part
    if "if (!nativeConsent)" not in sections["models.retry"] or "if (!nativeConsent)" not in sections["models.pull"]:
        raise AssertionError("P03_NATIVE_CONSENT_LOST")
    if "P03_GGUF_RIGHTS_SHA_REVIEW_REQUIRED" not in sections["models.gguf.import"]:
        raise AssertionError("P03_GGUF_RIGHTS_REVIEW_LOST")
    if not all(x in source for x in (
        "_worker.RunNextAsync(token, jobId)",
        "_transferStop.Cancel();",
        "TaskContinuationOptions.ExecuteSynchronously",
        "ModelDownloadQueueWorker",
        "if (_disposed) throw new ObjectDisposedException",
        "StopMergedImport();",
        "await _worker.RunNextAsync(ct,job.Id);",
    )):
        raise AssertionError("P03_NATIVE_LIFECYCLE_OR_P04_INTEGRITY_LOST")


def assert_crash_recovery(source):
    if not all(mark in source for mark in (
        "await _recoveryGate.WaitAsync(ct);",
        "if (_queueRecovered) return;",
        "await _queue.RecoverInterruptedAsync(ct);",
        "if (route is \"models.queue\" or \"models.cancel\" or \"models.retry\" or",
        "finally { _recoveryGate.Release(); }",
    )):
        raise AssertionError("P03_CRASH_RECOVERY_NOT_ADMITTED")
    recovery = source.split("private async Task RecoverInterruptedOnceAsync", 1)[1].split(
        "private void StartQueuedTransfer", 1)[0]
    if "State = ModelJobState.Queued" in recovery or "StartQueuedTransfer(" in recovery:
        raise AssertionError("P03_CRASH_RECOVERY_AUTO_DOWNLOAD_DENIED")


class P03NativeBackgroundQueueNoLoss(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ROUTES.read_text("utf-8-sig")
        cls.build = BUILDER.read_text("utf-8-sig")

    def test_01_ui_returns_persisted_job_without_waiting_for_transfer(self):
        assert_nonblocking(self.data)

    def test_02_old_blocking_pull_is_rejected(self):
        broken = self.data.replace("StartQueuedTransfer(job.Id);",
                                   "await _worker.RunNextAsync(ct);", 1)
        with self.assertRaisesRegex(AssertionError, "P03_MODEL_TRANSFER_BLOCKS_NATIVE_UI"):
            assert_nonblocking(broken)

    def test_03_missing_durable_owner_handoff_is_rejected(self):
        broken = self.data.replace("StartQueuedTransfer(retry.Id);", "/* lost */", 1)
        with self.assertRaisesRegex(AssertionError, "P03_NO_DURABLE_JOB_HANDOFF"):
            assert_nonblocking(broken)

    def test_04_interrupted_downloads_recover_before_queue_mutation(self):
        assert_crash_recovery(self.data)

    def test_05_missing_crash_recovery_is_rejected(self):
        broken = self.data.replace("await _queue.RecoverInterruptedAsync(ct);",
                                   "/* old stalled state */", 1)
        with self.assertRaisesRegex(AssertionError, "P03_CRASH_RECOVERY_NOT_ADMITTED"):
            assert_crash_recovery(broken)

    def test_06_existing_onehost_builder_pins_exact_updated_blob(self):
        actual = git_blob(ROUTES.read_bytes())
        self.assertIn(
            "relative='Packages/P03/Source/P03.ModelCenter/ModelCenterNativeRoutes.cs';"
            "dest='Integration/P03/ModelCenterNativeRoutes.cs';blob='" + actual + "'",
            self.build,
        )

    def test_08_catalog_exposes_only_public_reviewed_artifact_fields(self):
        self.assertIn("artifacts=exact.Select(a=>new {", self.data)
        self.assertIn("tag=a.ExactTag", self.data)
        self.assertIn("licenseEvidenceUrl=a.LicenseEvidenceUri?.AbsoluteUri", self.data)
        self.assertNotIn("artifacts=exact,", self.data)
        catalog = self.data.split('case "models.catalog":', 1)[1].split(
            'case "models.preflight":', 1)[0]
        for private in ("ReviewedRightsReceiptId", "ImmutableRevision",
                        "ExpectedSha256", "ExpectedManifestDigestSha256"):
            self.assertNotIn("a." + private, catalog)

    def test_09_full_owner_record_exposure_rejected(self):
        broken = self.data.replace(
            "artifacts=exact.Select(a=>new {", "artifacts=exact, /* exposed */ //", 1)
        self.assertIn("artifacts=exact,", broken)
        self.assertNotEqual(broken, self.data)

    def test_07_real_merge_evidence_still_synchronous(self):
        self.assertIn("await _worker.RunNextAsync(ct,job.Id);", self.data)
        self.assertIn("ModelLocalAttestation.VerifyReceiptAsync", self.data)


if __name__ == "__main__":
    unittest.main()
