"""NOX E06 regression: the existing P01 verifier and builder must agree."""
from pathlib import Path
import re
import unittest


BUILDER = Path(__file__).resolve().parents[2] / "coordination" / "e06" / "build_onehost_installer.ps1"


class OneHostManifestContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = BUILDER.read_text(encoding="utf-8")

    def test_hidden_and_system_payload_files_are_hashed(self):
        self.assertRegex(
            self.source,
            r"Get-ChildItem\s+-LiteralPath\s+\$payload\s+-File\s+-Recurse\s+-Force\s+\|",
        )

    def test_owner_compatible_numeric_version_in_both_places(self):
        manifest = re.search(r"\$manifest=\[ordered\]@\{[^\n]+version='([^']+)'", self.source)
        cli = re.search(r"'/DAPP_VERSION=([^']+)'", self.source)
        self.assertIsNotNone(manifest)
        self.assertIsNotNone(cli)
        self.assertEqual(manifest.group(1), cli.group(1))
        self.assertRegex(manifest.group(1), r"^\d+\.\d+\.\d+$")
        self.assertNotIn("16.0.0-rc", self.source)

    def test_original_owner_verifier_and_release_hold_are_preserved(self):
        self.assertIn("Verify-Payload.ps1", self.source)
        self.assertIn("ORIGINAL_NSIS_PAYLOAD_SHA_GATE_HOLD", self.source)
        self.assertIn("release_accepted=$false", self.source)
        self.assertIn("installer_lifecycle_tested=$false", self.source)


if __name__ == "__main__":
    unittest.main()
