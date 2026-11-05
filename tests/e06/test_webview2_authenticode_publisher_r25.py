"""R25 exact Microsoft publisher regression on ORIGINAL Express WebView2 CI preflight.

Source-level only; not Windows native runtime/installed E07 approval.
"""
from pathlib import Path
import re
import unittest

ORIGINAL = Path(__file__).resolve().parents[2] / "coordination/e06/t06_samevm_installed_smoke.py"
SOURCE = ORIGINAL.read_text(encoding="utf-8")


class MicrosoftPublisherAdmissionR25(unittest.TestCase):
    def publisher_pattern(self):
        match = re.search(r"\$publisherOk = \$subject -cmatch '([^']+)'", SOURCE)
        self.assertIsNotNone(match, "WebView2 signer must have exact publisher policy")
        return re.compile(match.group(1).replace(r"\z", r"\Z"))

    def test_genuine_microsoft_subject(self):
        self.assertIsNotNone(self.publisher_pattern().search(
            "CN=Microsoft Corporation, O=Microsoft Corporation, "
            "L=Redmond, S=Washington, C=US"))

    def test_substring_subject_spoofs_deny(self):
        pattern = self.publisher_pattern()
        for subject in (
            "CN=Third Party, OU=Microsoft Corporation, O=Third Party",
            "CN=Microsoft Corporation Fake, O=Microsoft Corporation",
            "CN=Microsoft Corporation, O=Microsoft Corporation Evil",
            "CN=Other, O=Not Microsoft Corporation",
            "O=Microsoft Corporation, CN=Microsoft Corporation",
        ):
            with self.subTest(subject=subject):
                self.assertIsNone(pattern.search(subject))

    def test_authenticode_and_runtime_still_required(self):
        self.assertIn("Get-AuthenticodeSignature", SOURCE)
        self.assertIn("if ($s.Status -ne 'Valid' -or -not $publisherOk) {exit 7}", SOURCE)
        self.assertNotIn("$subject -notmatch 'Microsoft Corporation'", SOURCE)
        self.assertIn("T06_WEBVIEW2_RUNTIME_STILL_MISSING_AFTER_INSTALL", SOURCE)
        self.assertIn("NOX_M1_CI_INSTALL_WEBVIEW2", SOURCE)


if __name__ == "__main__":
    unittest.main()
