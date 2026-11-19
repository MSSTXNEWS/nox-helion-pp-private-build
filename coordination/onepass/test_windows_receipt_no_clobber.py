"""V147 original Windows preflight no-loss receipt regression, source-only."""
from __future__ import annotations
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).parent / "windows" / "NOX_ONEPASS_VERIFY_WINDOWS.ps1"
BEGIN = "# NOX_V147_RECEIPT_NO_CLOBBER_BEGIN"
END = "# NOX_V147_RECEIPT_NO_CLOBBER_END"

class WindowsReceiptNoClobber(unittest.TestCase):
    def test_original_source_fail_closed_and_no_false_owner_identity(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertEqual(source.count(BEGIN), 1)
        self.assertEqual(source.count(END), 1)
        region = source.split(BEGIN, 1)[1].split(END, 1)[0]
        for expected in ("[System.IO.FileMode]::CreateNew",
                         "[System.IO.FileShare]::None", "$stream.Flush($true)"):
            self.assertIn(expected, region)
        self.assertNotIn("Set-Content -LiteralPath $report_path", source)
        self.assertIn("windows_owner_pc_identity_attested = $false", source)
        self.assertIn("LOCAL_EXECUTION_HOST_NOT_OWNER_ATTESTED", source)
        self.assertIn("HOLD_RECEIPT_NO_REPLACE_FAILED", source)
        self.assertIn("windows_pc_owner_cookie_e2e = 'NOT_TESTED'", source)
        self.assertIn("release_92_functions_accepted = $false", source)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell required on CI")
    def test_real_powershell_duplicate_path_never_overwrites(self):
        source = SCRIPT.read_text(encoding="utf-8")
        region = source.split(BEGIN, 1)[1].split(END, 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            destination = pathlib.Path(tmp) / "receipt.json"
            escaped = str(destination).replace("'", "''")
            script = (
                region + "\n"
                + "$path = '" + escaped + "'\n"
                + "Write-NoClobberOnepassReceipt $path '{\"slot\":1}'\n"
                + "try { Write-NoClobberOnepassReceipt $path '{\"slot\":2}'; exit 99 }\n"
                + "catch { Write-Output 'COLLISION_HOLD' }\n"
            )
            run = subprocess.run(
                ["pwsh", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=20
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("COLLISION_HOLD", run.stdout)
            self.assertEqual(destination.read_bytes(), b'{"slot":1}')

if __name__ == "__main__":
    unittest.main()
