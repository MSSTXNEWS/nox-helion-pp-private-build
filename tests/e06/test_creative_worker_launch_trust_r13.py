"""E06 QA-only source gate for the EXISTING creative worker launch.

Run against an immutable checkout: python -m unittest discover -s tests/e06
-p 'test_creative_worker_launch_trust_r13.py' -v
This is STATIC SOURCE evidence, not installed Windows acceptance.
"""
import os
from pathlib import Path
import re
import unittest

ROOT = Path(os.environ.get('NOX_SOURCE_ROOT', '.')).resolve()
CREATIVE = ROOT / 'integrations/creative/bridge/CreativeHostBridge.cs'
CONTROL = ROOT / 'coordination/e06/OriginalPythonDiagnosticBridge.cs'


def before_launch(path, marker):
    source = path.read_text(encoding='utf-8')
    start = source.index(marker)
    launch = source.index('Process.Start(start)', start)
    return source[start:launch]


class CreativeWorkerLaunchTrust(unittest.TestCase):
    def test_existing_original_python_diagnostic_has_trust_gates(self):
        source = CONTROL.read_text(encoding='utf-8')
        self.assertIn('FileAttributes.ReparsePoint', source)
        self.assertIn('SHA256.HashDataAsync', source)
        self.assertIn('PinnedPythonExeSha256', source)

    def test_creative_worker_rejects_reparse_before_process_start(self):
        pre = before_launch(CREATIVE, 'EnsureCreativeWorkerAsync()')
        self.assertIn('File.Exists(path)', pre)
        self.assertRegex(pre, r'FileAttributes\.ReparsePoint|ResolveLinkTarget')

    def test_creative_worker_checks_pinned_binary_digest_before_launch(self):
        pre = before_launch(CREATIVE, 'EnsureCreativeWorkerAsync()')
        self.assertRegex(pre, r'SHA256\.HashData|SHA256\.Create|GetFileHash')
        self.assertRegex(pre, r'Pinned|Expected|Manifest|TrustedDigest')


if __name__ == '__main__':
    unittest.main()
