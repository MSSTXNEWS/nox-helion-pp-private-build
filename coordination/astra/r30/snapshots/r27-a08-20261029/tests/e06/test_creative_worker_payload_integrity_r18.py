"""Read-only regression for the original WPF creative worker launch path.

Run on an exact repository checkout:
  python -m unittest tests/e06/test_creative_worker_payload_integrity_r18.py -v

These tests check current source logic, not a Windows PE/NSIS execution.
"""
from pathlib import Path
import os
import re
import unittest

ROOT = Path(os.environ.get("NOX_SOURCE_ROOT", ".")).resolve()
SOURCE = ROOT / "integrations/creative/bridge/CreativeHostBridge.cs"
MANIFEST_BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"


class CreativeWorkerIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.builder = MANIFEST_BUILDER.read_text(encoding="utf-8")
        cls.start = cls.source.split("private async Task<Process> EnsureCreativeWorkerAsync()", 1)[1]

    def test_existing_worker_not_replaced(self):
        self.assertIn('new ProcessStartInfo(path)', self.start)
        self.assertIn('Process.Start(start)', self.start)
        self.assertIn('StopCreativeWorker()', self.source)

    def test_worker_verified_before_start(self):
        self.assertLess(self.start.index('HoldApprovedCreativeWorker(path)'),
                        self.start.index('Process.Start(start)'))
        self.assertRegex(self.start, r'using var verifiedWorker\s*=\s*HoldApprovedCreativeWorker\(path\)')

    def test_worker_path_is_fixed_not_page_supplied(self):
        self.assertIn('Path.Combine(AppContext.BaseDirectory,"Backend","Creative","NOX_CreativeWorker.exe")', self.start)
        self.assertIn('CREATIVE_WORKER_PATH_NOT_APPROVED', self.source)

    def test_reparse_ancestors_rejected(self):
        self.assertIn('CREATIVE_WORKER_PARENT_REPARSE_HOLD', self.source)
        self.assertIn('FileAttributes.ReparsePoint', self.source)

    def test_manifest_exists_and_is_bounded(self):
        self.assertIn('"payload.sha256.json"', self.source)
        self.assertIn('16_777_216', self.source)
        self.assertIn('CREATIVE_PAYLOAD_MANIFEST_HOLD', self.source)

    def test_original_p01_manifest_reused(self):
        self.assertIn('NOX_P01_PAYLOAD_SHA256_V1', self.source)
        self.assertIn("schema='NOX_P01_PAYLOAD_SHA256_V1'", self.builder)

    def test_exact_worker_path_manifest(self):
        self.assertIn('Backend/Creative/NOX_CreativeWorker.exe', self.source)
        self.assertIn('matches != 1', self.source)

    def test_exact_file_size(self):
        self.assertIn('handle.Length != expectedLength', self.source)

    def test_exact_sha256_bytes(self):
        self.assertIn('SHA256.HashData(handle)', self.source)
        self.assertIn('CREATIVE_WORKER_SHA256_MISMATCH', self.source)

    def test_byte_handle_kept_open_through_process_start(self):
        self.assertIn('FileShare.Read', self.source)
        self.assertLess(self.start.index('using var verifiedWorker'),
                        self.start.index('Process.Start(start)'))

    def test_no_second_event_or_model_backend(self):
        self.assertNotIn('new OllamaClient(', self.source)
        self.assertNotIn('new SqliteConnection(', self.source)
        self.assertNotIn('new EventV3Bridge(', self.source)

    def test_original_stop_paths_untouched(self):
        self.assertIn('if (action=="stop")', self.source)
        self.assertIn('status="STOPPED"', self.source)

    def test_safe_error_surface_to_page(self):
        self.assertIn('CREATIVE_DISPATCH_FAILED', self.source)
        self.assertNotIn('PostMessage(ex.ToString()', self.source)

    def test_original_binary_readonly_diagnose_not_modified(self):
        # E06's distinct pinned original Python bridge remains an independent
        # read-only diagnostic, not proof of a real creative runtime.
        self.assertNotIn('OriginalPythonDiagnosticBridge.cs', self.source)


if __name__ == "__main__":
    unittest.main()
