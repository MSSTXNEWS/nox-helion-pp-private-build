"""D03 SOURCE_ONLY: genuine original T06 uninstaller failure must still attest NO-LOSS.

Never launches NSIS, downloads a model, grants consent or claims physical E07.
"""
from pathlib import Path
import os
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "coordination" / "e06"))
from t06_samevm_installed_smoke import original_no_loss_file_preserved


class UninstallAnyExitNoLoss(unittest.TestCase):
    def test_preserves_exact_user_and_unmanaged_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install = base / "Programs" / "NOX HELION"
            install.mkdir(parents=True)
            persistent = base / "NOX_HELION" / "P01" / "state.bin"
            persistent.parent.mkdir(parents=True)
            persistent.write_bytes(b"persistent-original")
            unmanaged = install / "unmanaged.bin"
            unmanaged.write_bytes(b"unmanaged-original")
            self.assertTrue(original_no_loss_file_preserved(persistent, b"persistent-original", base))
            self.assertTrue(original_no_loss_file_preserved(unmanaged, b"unmanaged-original", base))
            self.assertFalse(original_no_loss_file_preserved(unmanaged, b"other", base))
            unmanaged.write_bytes(b"changed")
            self.assertFalse(original_no_loss_file_preserved(unmanaged, b"unmanaged-original", base))
            unmanaged.unlink()
            self.assertFalse(original_no_loss_file_preserved(unmanaged, b"unmanaged-original", base))
            self.assertEqual(persistent.read_bytes(), b"persistent-original")

    def test_refuses_redirection_and_empty_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            good = base / "owned"
            good.write_bytes(b"evidence")
            self.assertFalse(original_no_loss_file_preserved(good, b"", base))
            self.assertFalse(original_no_loss_file_preserved(good, b"evidence", base / "elsewhere"))
            link = base / "link"
            try:
                link.symlink_to(good)
            except (OSError, NotImplementedError):
                self.skipTest("Symlink not available")
            self.assertFalse(original_no_loss_file_preserved(link, b"evidence", base))
            self.assertEqual(good.read_bytes(), b"evidence")


    def test_bounded_no_loss_proof_refuses_oversized_file(self):
        # The existing NO-LOSS marker is tiny. Swapping a huge file in its
        # place must fail closed without Path.read_bytes() (unbounded IO).
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            marker = base / "marker.bin"
            marker.write_bytes(b"z" * 1048576)
            with patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded read")):
                self.assertFalse(original_no_loss_file_preserved(marker, b"expected", base))
            self.assertEqual(marker.stat().st_size, 1048576)
            marker.write_bytes(b"expected")
            self.assertTrue(original_no_loss_file_preserved(marker, b"expected", base))


if __name__ == "__main__":
    unittest.main()
