"""P03 upstream progress privacy: source contract, NOT a Windows/native proof."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "Packages/P03/Source/P03.ModelCenter/ModelDownloadQueueWorker.cs"


class ProgressPrivacySourceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = SOURCE.read_text(encoding="utf-8")
        cls.progress = cls.code.split("async ValueTask OnProgress(", 1)[1].split("string? digest;", 1)[0]
        cls.status = cls.code.split("private static string PublicProgressStatus(", 1)[1].split("private static string? PublicProgressDigest(", 1)[0]
        cls.digest = cls.code.split("private static string? PublicProgressDigest(", 1)[1].split("public async Task<bool> CancelAsync(", 1)[0]
        cls.failure = cls.code.split("catch (Exception ex)\n            {", 1)[1].split("\n            finally", 1)[0]

    def test_untrusted_status_never_reaches_queue_or_event(self):
        self.assertIn("PublicProgressStatus(u.Status)", self.progress)
        self.assertIn("Status = publicStatus", self.progress)
        self.assertIn('"progress", publicStatus', self.progress)
        self.assertNotIn("Status = u.Status", self.progress)
        self.assertNotIn('"progress", u.Status', self.progress)

    def test_digest_is_sha256_only(self):
        self.assertIn("PublicProgressDigest(u.Digest)", self.progress)
        self.assertIn("publicDigest, null, token", self.progress)
        self.assertNotIn("u.Digest, null, token", self.progress)
        self.assertIn("upstream.Length != 71", self.digest)
        self.assertIn('upstream.StartsWith("sha256:"', self.digest)
        self.assertIn("Uri.IsHexDigit(upstream[i])", self.digest)

    def test_progress_is_allowlisted_and_bounded(self):
        self.assertIn("upstream.Length > 128", self.status)
        self.assertIn('return "Transferring";', self.status)
        self.assertIn('return "Pulling layer";', self.status)
        self.assertIn('return "Transfer complete";', self.status)
        self.assertNotIn("return status;", self.status)
        self.assertNotIn("return upstream;", self.status)

    def test_exception_privacy_remains_fixed(self):
        self.assertIn('const string publicError = "P03_TRANSFER_FAILED";', self.failure)
        self.assertIn("Error = publicError", self.failure)
        self.assertNotIn("ex.Message", self.failure)

    def test_stop_cancel_numeric_progress_preserved(self):
        self.assertIn("CompletedBytes = u.Completed", self.progress)
        self.assertIn("TotalBytes = u.Total", self.progress)
        self.assertIn("linked.IsCancellationRequested", self.progress)
        self.assertIn("j.State == ModelJobState.Cancelling", self.failure)
        self.assertIn("store.RequestCancelAsync(id, ct)", self.code)


if __name__ == "__main__":
    unittest.main()
