"""M10 source regression for original WPF owner HMAC teardown (no fake C# compilation)."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "coordination" / "e06" / "MainWindow.NativeP02.cs"

class WpfA1ShutdownProofTest(unittest.TestCase):
    def test_original_owner_shutdown_revokes_and_erases_key(self):
        code = SOURCE.read_text(encoding="utf-8")
        start = code.index("    private void ShutdownNativeP02()")
        end = code.index("\n    }", start)
        shutdown = code[start:end]
        kill = shutdown.index("var child=_nativeP02Process")
        self.assertLess(shutdown.index("_a1OwnerApprovedAction=null;"), kill)
        self.assertLess(shutdown.index("_a1OwnerApprovedEpoch=0;"), kill)
        self.assertLess(shutdown.index("_a1OwnerProofRunId=null;"), kill)
        self.assertLess(shutdown.index("CryptographicOperations.ZeroMemory(_a1OwnerProofKey);"), kill)
        self.assertLess(shutdown.index("_a1OwnerProofKey=null;"), kill)
        self.assertIn("_nativeModelsStop.Cancel()", shutdown)
        self.assertIn("_nativeP02Bridge?.Dispose()", shutdown)
        self.assertIn("_nativeP02Pipe.DisposeAsync()", shutdown)

if __name__ == "__main__":
    unittest.main()
