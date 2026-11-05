"""G4 original C07 WebView2 SHA admission works on Windows PowerShell 5.1.

SOURCE_ONLY. A real Windows E06/NSIS compile is still required.
"""
from pathlib import Path
import re
import unittest

BUILDER = Path(__file__).resolve().parents[2] / "coordination/e06/build_onehost_installer.ps1"
EXPECTED_LEGACY_SHA = "a61e2e7adcbf836109249829f4d103e0d991873c0088483b0b3550216a4b4c8e"


class PS51WebViewLegacyGate(unittest.TestCase):
    def test_c07_legacy_sha_still_fails_closed_without_net5_api(self):
        source = BUILDER.read_text(encoding="utf-8-sig")
        self.assertEqual(source.count("$alreadyCanonical=($webviewLegacy -ceq $canonicalWebviewBlock)"), 1)
        start = source.index("if (!$alreadyCanonical) {")
        end = source.index("  $knownC07Legacy=", start)
        gate = source[start:end]
        self.assertNotIn("[Convert]::ToHexString(", gate)
        self.assertNotIn("[Security.Cryptography.SHA256]::HashData(", gate)
        self.assertEqual(gate.count("[Security.Cryptography.SHA256]::Create()"), 1)
        self.assertIn("$legacyHasher.ComputeHash($legacyBytes)", gate)
        self.assertIn("[BitConverter]::ToString($legacyDigest).Replace('-','').ToLowerInvariant()", gate)
        self.assertIn("finally { $legacyHasher.Dispose() }", gate)
        self.assertIn('($webviewLegacy -replace "`r`n","`n")', gate)
        self.assertIn("'E06_WEBVIEW2_PREFLIGHT_HASH_ENGINE_HOLD'", gate)
        self.assertIn("'E06_WEBVIEW2_PREFLIGHT_HASH_READBACK_HOLD'", gate)
        self.assertIn("$knownC07Legacy=($legacySha -ceq '" + EXPECTED_LEGACY_SHA + "')", source)
        self.assertIn("if (!$knownC07Legacy)", source)
        self.assertIn("throw 'E06_WEBVIEW2_PREFLIGHT_UNKNOWN_SOURCE_HOLD'", source)
        self.assertLess(source.index("$legacyHasher.ComputeHash($legacyBytes)"), source.index("$knownC07Legacy="))
        self.assertRegex(source, r"\$legacyDigest\.Length -ne 32")


if __name__ == "__main__":
    unittest.main()
