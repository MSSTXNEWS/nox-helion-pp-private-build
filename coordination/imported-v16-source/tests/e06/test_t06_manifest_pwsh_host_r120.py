"""Verify original SHA-checked P01 manifest is executed by PowerShell 7 on CI.

This source regression does not assert a successful Windows Setup or E07.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "coordination/e06/t06_package_original_onehost.py"
OWNER = ROOT / "stage/proposals/P01/C09/Installer/Verify-Payload.ps1"

class P01VerifierPwshHost(unittest.TestCase):
    def test_original_verifier_arguments_and_pwsh_host(self):
        s = PACK.read_text(encoding="utf-8")
        anchor = 'proof=subprocess.run(["pwsh.exe","-NoProfile","-NonInteractive",'
        self.assertEqual(s.count(anchor), 1)
        tail = s.split(anchor, 1)[1].split("capture_output=True", 1)[0]
        for required in ('"-ExecutionPolicy","Bypass","-File"', '"Verify-Payload.ps1"',
                         '"-Root",str(payload)', '"-Manifest",str(manifest_file)'):
            self.assertIn(required, tail)
        self.assertNotIn('["powershell.exe","-NoProfile"', s)
        self.assertIn('T06_ORIGINAL_OWNER_MANIFEST_VERIFY_HOLD', s)
    def test_original_sha_verifier_is_retained(self):
        s = OWNER.read_text(encoding="utf-8-sig")
        self.assertIn("Get-FileHash", s)
        self.assertIn("SHA256", s)
        self.assertIn("P01_PAYLOAD_VERIFY_FAILED", s)

if __name__=="__main__":
    unittest.main()
