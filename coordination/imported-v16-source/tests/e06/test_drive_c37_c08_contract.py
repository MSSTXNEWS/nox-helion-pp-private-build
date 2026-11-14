"""NOX V16 · retain Google Drive P03 C37 / P01 C08 fixes on existing owners.

SOURCE-ONLY regressions for already integrated donor behavior, not Windows E07,
not a second model downloader, installer or release acceptance receipt.
P03 donor: https://drive.google.com/file/d/1G4w1wFA2D-o-0c950BabU3Cv6_dbZUW-/view
P01 contract: https://drive.google.com/file/d/1T0AtLfQVZPaAM4RL95ssSzXgzPC5vvPc/view
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P03 = ROOT / "Packages" / "P03" / "Source" / "P03.ModelCenter"
P01 = ROOT / "stage" / "proposals" / "P01" / "C09" / "Installer"


def validate_c37(worker, store, adapter):
    cancel = worker.split("public async Task<bool> CancelAsync", 1)[1].split(
        "public Task<ModelJob?> RetryAsync", 1)[0]
    begin = cancel.index("await store.UpdateAsync(id")
    signal = cancel.index("running.Cancel()")
    if begin >= signal or "ModelJobState.Cancelling" not in cancel[begin:signal]:
        raise AssertionError("P03_CANCEL_INTENT_NOT_DURABLE_BEFORE_SIGNAL")
    if ("ObjectDisposedException" not in cancel or
            "store.RequestCancelAsync" not in cancel):
        raise AssertionError("P03_CANCEL_CLAIM_RACE_UNGUARDED")

    recovery = store.split("public async Task<int> RecoverInterruptedAsync", 1)[1].split(
        "public async Task<ModelJob?> RetryAsync", 1)[0]
    if ("State = ModelJobState.Failed" not in recovery or
            'Error = "INTERRUPTED_RETRY_REQUIRED"' not in recovery or
            "State = ModelJobState.Queued" in recovery or
            "TryAcquireExecutionLease" not in recovery):
        raise AssertionError("P03_CRASH_REQUEUED_OR_STOLE_LIVE_JOB")

    pull = adapter.split("public async Task<string?> PullAsync", 1)[1].split(
        "public async Task<(long Bytes, string Sha256)> ImportGgufAsync", 1)[0]
    if ("terminalSuccess = false" not in pull or
            'update.Status, "success"' not in pull or
            'if (!terminalSuccess) throw new InvalidDataException("OLLAMA_PULL_STREAM_TRUNCATED_NO_SUCCESS")' not in pull or
            "OLLAMA_PULL_PINNED_DIGEST_MISMATCH" not in pull):
        raise AssertionError("P03_PULL_FALSE_SUCCESS_OR_UNPINNED_DIGEST")


def validate_c08(uninstaller):
    required = (
        "Assert-P01UniqueManifestMembers $manifestPath",
        "# PHASE 1", "# PHASE 2", "# PHASE 3",
        "Assert-VerifiedEntry",
        "P01_UNINSTALL_FILE_CHANGED_DURING_COMMIT",
        "P01_UNINSTALL_RESERVED_INSTALLER_METADATA",
        "P01_UNINSTALL_PATH_ESCAPE",
        "Remove-Item -LiteralPath $entry.Full",
    )
    if any(item not in uninstaller for item in required):
        raise AssertionError("P01_C08_NOLOSS_GUARD_MISSING")
    phase1, phase2, phase3 = (
        uninstaller.index("# PHASE 1"),
        uninstaller.index("# PHASE 2"),
        uninstaller.index("# PHASE 3"),
    )
    first_delete = uninstaller.index("Remove-Item -LiteralPath $entry.Full")
    if not (phase1 < phase2 < phase3 < first_delete):
        raise AssertionError("P01_UNINSTALL_DELETE_BEFORE_FULL_PREFLIGHT")
    if any("Assert-VerifiedEntry $entry" not in part for part in (
        uninstaller[phase1:phase2],
        uninstaller[phase2:phase3],
        uninstaller[phase3:],
    )):
        raise AssertionError("P01_UNINSTALL_INCOMPLETE_VERIFICATION")
    if (re.search(r"(?im)^\s*Remove-Item\b", uninstaller[:phase3]) or
            re.search(r"(?im)^\s*RMDir\s+/r\b", uninstaller)):
        raise AssertionError("P01_UNINSTALL_UNSAFE_RECURSIVE_OR_EARLY_DELETE")


class ExistingDriveDonorRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worker = (P03 / "ModelDownloadQueueWorker.cs").read_text("utf-8-sig")
        cls.store = (P03 / "ModelDownloadQueueStore.cs").read_text("utf-8-sig")
        cls.adapter = (P03 / "OllamaModelAdapter.cs").read_text("utf-8-sig")
        cls.uninstaller = (P01 / "Remove-InstalledPayload.ps1").read_text("utf-8-sig")

    def test_approved_p03_c37_cancellation_crash_and_stream_gates(self):
        validate_c37(self.worker, self.store, self.adapter)

    def test_old_crash_auto_requeue_is_blocked(self):
        before = 'State = ModelJobState.Failed,\n                    Status = "Interrupted'
        self.assertIn(before, self.store)
        broken = self.store.replace(before, 'State = ModelJobState.Queued,\n                    Status = "Interrupted', 1)
        with self.assertRaisesRegex(AssertionError, "P03_CRASH_REQUEUED"):
            validate_c37(self.worker, broken, self.adapter)

    def test_pull_stream_without_terminal_success_is_blocked(self):
        broken = self.adapter.replace("OLLAMA_PULL_STREAM_TRUNCATED_NO_SUCCESS",
                                      "TRUNCATION_ACCEPTED", 1)
        with self.assertRaisesRegex(AssertionError, "P03_PULL_FALSE_SUCCESS"):
            validate_c37(self.worker, self.store, broken)

    def test_approved_p01_c08_no_loss_uninstall(self):
        validate_c08(self.uninstaller)

    def test_source_only_qa_never_fabricates_native_route_counts(self):
        qa = (ROOT / "coordination/e06/gitlab_windows_source_qa.ps1").read_text("utf-8-sig")
        self.assertIn("nativeRoutesAccepted = $null", qa)
        self.assertIn("nativeRoutesPending = $null", qa)
        self.assertIn("nativeRoutesEvidence = 'NOT_ASSESSED_BY_SOURCE_QA'", qa)
        self.assertNotIn("nativeRoutesPending = 14", qa)

    def test_old_uninstall_that_deletes_before_validation_is_blocked(self):
        broken = self.uninstaller.replace(
            "# PHASE 3", "Remove-Item -LiteralPath $entry.Full\n# PHASE 3", 1)
        with self.assertRaisesRegex(AssertionError, "P01_UNINSTALL_DELETE_BEFORE_FULL_PREFLIGHT"):
            validate_c08(broken)


if __name__ == "__main__":
    unittest.main()
