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
WEBVIEW = ROOT / "coordination/e06/OneHostP02WebView2Bridge.cs"


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


def assert_catalog_privacy(source):
    if 'artifacts=exact.Select(a=>new {' not in source:
        raise AssertionError("P03_UNTRUSTED_WEBVIEW_RECEIVED_RAW_OWNER_ARTIFACT")
    catalog = source.split('case "models.catalog":', 1)[1].split(
        'case "models.preflight":', 1)[0]
    for private in ("ReviewedRightsReceiptId", "ImmutableRevision",
                    "ExpectedSha256", "ExpectedManifestDigestSha256"):
        if "a." + private in catalog:
            raise AssertionError("P03_OWNER_PROOF_EXPOSED_TO_RENDERER")
    if not all(field in catalog for field in (
        "tag=a.ExactTag", "license=a.License",
        "licenseEvidenceUrl=a.LicenseEvidenceUri?.AbsoluteUri",
    )):
        raise AssertionError("P03_PUBLIC_CATALOG_FIELDS_MISSING")


def assert_background_lifetime(source):
    block = source.split("private void StartQueuedTransfer(Guid jobId)", 1)[1].split(
        "private static void RequireHardware(", 1)[0]
    create = block.index("pending = Task.Run")
    record = block.index("_transferTasks.Add(jobId, pending);")
    boundary = "\n        }\n        // Register completion AFTER"
    if boundary not in block:
        raise AssertionError("P03_SYNCHRONOUS_COMPLETION_BEFORE_REGISTRATION")
    release = block.index(boundary)
    continuation = block.index("_ = pending.ContinueWith(")
    if not (create < record < release < continuation):
        raise AssertionError("P03_SYNCHRONOUS_COMPLETION_BEFORE_REGISTRATION")
    if "_ownedHttp?.Dispose();" not in block.split("_transferTasks.Remove(jobId);", 1)[1]:
        raise AssertionError("P03_HTTP_DISPOSED_BEFORE_TRANSFER_COMPLETION")
    dispose = source.split("public void Dispose()", 1)[1]
    if not all(x in dispose for x in (
        "_transferStop.Cancel();",
        "if (_transferTasks.Count == 0)",
        "_transferStop.Dispose();",
        "_ownedHttp?.Dispose();",
        "StopMergedImport();",
    )):
        raise AssertionError("P03_TERMINATION_OWNERSHIP_LOST")


class P03NativeBackgroundQueueNoLoss(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ROUTES.read_text("utf-8-sig")
        cls.build = BUILDER.read_text("utf-8-sig")
        cls.webview = WEBVIEW.read_text("utf-8-sig")

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
        with self.assertRaisesRegex(
                AssertionError, "P03_UNTRUSTED_WEBVIEW_RECEIVED_RAW_OWNER_ARTIFACT"):
            assert_catalog_privacy(broken)

    def test_10_owner_rights_receipt_exposure_rejected(self):
        broken = self.data.replace(
            "license=a.License,", "license=a.License, receipt=a.ReviewedRightsReceiptId,", 1)
        with self.assertRaisesRegex(AssertionError, "P03_OWNER_PROOF_EXPOSED_TO_RENDERER"):
            assert_catalog_privacy(broken)

    def test_11_continuation_starts_after_tracked_task_and_gate_unlock(self):
        assert_background_lifetime(self.data)

    def test_12_old_inline_execute_synchronously_race_is_rejected(self):
        broken = self.data.replace(
            "        }\n        // Register completion AFTER", "        // Register completion AFTER", 1)
        with self.assertRaisesRegex(AssertionError,
                                    "P03_SYNCHRONOUS_COMPLETION_BEFORE_REGISTRATION"):
            assert_background_lifetime(broken)

    def test_13_disposing_http_during_active_transfer_is_rejected(self):
        original = """            if (_transferTasks.Count == 0)
            {
                _transferStop.Dispose();
                _ownedHttp?.Dispose();
            }"""
        broken = self.data.replace(
            original, "            _transferStop.Dispose();\n            _ownedHttp?.Dispose();", 1)
        with self.assertRaisesRegex(AssertionError, "P03_TERMINATION_OWNERSHIP_LOST"):
            assert_background_lifetime(broken)

    def test_14_bridge_reports_queued_transfer_not_fake_completion(self):
        self.assertIn('ownerState = jobState.GetString() switch', self.webview)
        self.assertIn('"Queued" => "QUEUED"', self.webview)
        self.assertIn('"Running" or "Cancelling" => "IN_PROGRESS"', self.webview)
        self.assertIn('"Completed" => "COMPLETED"', self.webview)
        self.assertIn('ownerState = "HOLD";', self.webview)
        self.assertNotIn('route=="chat.stop"?"STOP_REQUESTED":"COMPLETED"', self.webview)

    def test_15_model_cancel_bypasses_consent_not_native_acl(self):
        self.assertIn('route is not ("chat.stop" or "models.cancel")', self.webview)
        self.assertIn('!_nativeAcl(_ownerWindowsSid, route)', self.webview)
        self.assertIn('flag.ValueKind == JsonValueKind.True ? "STOP_REQUESTED" : "HOLD"',
                      self.webview)
        self.assertIn('_nativeOwnerAction(route, payload.Clone(), cancel)', self.webview)

    def test_16_existing_builder_pins_correct_bridge_blob(self):
        actual = git_blob(WEBVIEW.read_bytes())
        self.assertIn(
            "relative='coordination/e06/OneHostP02WebView2Bridge.cs';"
            "dest='Integration/OneHostP02WebView2Bridge.cs';blob='" + actual + "'",
            self.build
        )

    def test_17_existing_micro_ui_uses_same_authenticated_wpf(self):
        owner = (ROOT / "coordination/e06/MainWindow.NativeP02.cs").read_text("utf-8")
        self.assertIn("core.WebMessageReceived += OnP03WebMessageReceived;", owner)
        self.assertIn("web.WebMessageReceived -= OnP03WebMessageReceived;", owner)
        self.assertIn("ModelWowBridgeContract.TryParseCommand", owner)
        self.assertIn("NativeP02Acl(sid, route)", owner)
        self.assertIn("Interlocked.Read(ref _nativeDocumentEpoch) != epoch", owner)
        handler = owner.split("private async void OnP03WebMessageReceived(", 1)[1].split(
            "private void ShutdownNativeP02()", 1)[0]
        self.assertIn("var stopGeneration = _nativeModelsStop.Token;", handler)
        self.assertIn('command.Action == "stop" ? CancellationToken.None : stopGeneration;', handler)
        self.assertIn("await ConfirmP02NativeAsync(route, root, activeStopToken)", handler)
        self.assertIn("activeStopToken.IsCancellationRequested", handler)
        self.assertIn("activeStopToken.ThrowIfCancellationRequested();", handler)
        self.assertIn('command.Action is not ("stop" or "diagnose"), activeStopToken)', handler)
        self.assertNotIn("await ConfirmP02NativeAsync(route, root, CancellationToken.None)", handler)
        self.assertIn("ModelWowBridgeContract.SnapshotJson", owner)
        self.assertIn("ModelWowBridgeContract.EventJson(item)", owner)
        self.assertNotIn("new ModelDownloadQueueStore(", owner)

    def test_18_donor_micro_wow_assets_are_exactly_pinned(self):
        owner_ui = ROOT / "Packages/P03/Source/P03.ModelCenter.Wow"
        content = self.build.split("$microwowFiles=@(", 1)[1].split("\n  )", 1)[0]
        entries = re.findall(r"@\{relative='([^']+)';blob='([0-9a-f]{40})'\}", content)
        self.assertEqual(len(entries), 8)
        for name, expected in entries:
            with self.subTest(name=name):
                self.assertEqual(git_blob((owner_ui / name).read_bytes()), expected)
        js = (owner_ui / "ui.js").read_text("utf-8")
        self.assertIn("postMessage({type:'p03.ready.v1'})", js)
        self.assertIn("p03.command.ack.v1", js)

    def test_19_stager_pins_current_owner_and_p03_read_queue(self):
        stager = (ROOT / "coordination/e06/stage_native_p02.py").read_text("utf-8")
        owner = ROOT / "coordination/e06/MainWindow.NativeP02.cs"
        self.assertIn('ADDON_SHA="' + git_blob(owner.read_bytes()) + '"', stager)
        self.assertIn("sha='" + git_blob(owner.read_bytes()) + "'", self.build)
        self.assertIn("sha='" + git_blob((ROOT / "coordination/e06/stage_native_p02.py").read_bytes()) + "'", self.build)
        self.assertIn("public Task<IReadOnlyList<ModelJob>> ReadJobsAsync", self.data)

    def test_07_real_merge_evidence_still_synchronous(self):
        self.assertIn("await _worker.RunNextAsync(ct,job.Id);", self.data)
        self.assertIn("ModelLocalAttestation.VerifyReceiptAsync", self.data)

    def test_20_gguf_import_requires_selected_reviewed_model(self):
        # Source-only negative guard: a reviewed OTHER model must not enable import.
        ui = (ROOT / "Packages/P03/Source/P03.ModelCenter.Wow/ui.js").read_text("utf-8")
        self.assertIn("cap.importGguf===true&&verified&&$('licenseAck').checked", ui)
        self.assertIn("if(action==='importGguf'&&(!hasEvidence(current())||!$('licenseAck').checked))return;", ui)
        self.assertIn("blob='" + git_blob((ROOT / "Packages/P03/Source/P03.ModelCenter.Wow/ui.js").read_bytes()) + "'", self.build)


if __name__ == "__main__":
    unittest.main()
