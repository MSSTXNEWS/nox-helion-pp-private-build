"""G3-B R18 source-only review gate regression; NOT a C# runtime or native test."""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[5]
SOURCE = ROOT / "Packages/P03/Source/P03.ModelCenter/ModelDownloadQueueWorker.cs"
class G3BReviewedQueueContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.gate = cls.source.split("// Retain durable legacy jobs", 1)[1].split("// Hold one OS-backed lease", 1)[0]
    def test_reviewed_download_gate_keeps_privacy_stop(self):
        for token in ("job.LicenseAcknowledged", "Uri.UriSchemeHttps",
                      "licenseEvidence.UserInfo", "licenseEvidence.Fragment",
                      "pinnedRevision", "ExpectedOllamaDigest.All(Uri.IsHexDigit)",
                      "ExpectedLocalBytes is > 4", "ExpectedLocalSha256.All(Uri.IsHexDigit)",
                      "RightsReceiptId", "j.State == ModelJobState.Queued",
                      "Status = \"REVIEW_REQUIRED\"", "Error = \"UNPINNED_ARTIFACT\""):
            self.assertIn(token, self.gate, token)
        self.assertIn("PublicProgressStatus(u.Status)", self.source)
        self.assertIn("PublicProgressDigest(u.Digest)", self.source)
        self.assertIn("store.TryAcquireExecutionLease(job.Id)", self.source)
        self.assertIn("j.State == ModelJobState.Cancelling", self.source)
if __name__ == "__main__":
    unittest.main()
