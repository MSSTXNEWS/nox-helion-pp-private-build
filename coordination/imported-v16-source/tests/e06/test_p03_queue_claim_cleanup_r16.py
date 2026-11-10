"""NOX V16 ModelCenter worker cleanup regression: source contract only."""
from pathlib import Path
import unittest

P = Path(__file__).resolve().parents[2] / "Packages/P03/Source/P03.ModelCenter/ModelDownloadQueueWorker.cs"

class QueueCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = P.read_text(encoding="utf-8")
        cls.region = cls.code.split("lock (_running) _running[job.Id] = linked;", 1)[1].split("using var monitorStop", 1)[0]

    def test_original_owner_queue(self):
        self.assertIn("_singleWorker.WaitAsync(ct)", self.code)
        self.assertIn("store.TryAcquireExecutionLease(job.Id)", self.code)

    def test_claim_exception_cleanup(self):
        self.assertIn("try { started = await store.TryStartQueuedAsync(job.Id, ct); }", self.region)
        self.assertIn("lock (_running) _running.Remove(job.Id);", self.region)
        self.assertIn("throw;", self.region)

    def test_null_claim_cleanup(self):
        self.assertIn("if (started is null)", self.region)
        self.assertEqual(self.region.count("_running.Remove(job.Id)"), 2)

    def test_original_cancel_preserved(self):
        self.assertIn("store.RequestCancelAsync(id, ct)", self.code)

if __name__ == "__main__":
    unittest.main()
