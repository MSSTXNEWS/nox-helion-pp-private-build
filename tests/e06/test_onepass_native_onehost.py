"""NOX T06 single megablock source gate, not Windows E2E."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]/"coordination/e06"
class NativeOnehost(unittest.TestCase):
 def test_onehost_native_sha_receipt(self):
  b=(ROOT/"build_onehost_installer.ps1").read_text("utf-8")
  w=(ROOT/"onepass_native_onehost.ps1").read_text("utf-8")
  self.assertIn("T06_NATIVE_PROOF_NOT_ACCEPTABLE",b)
  self.assertIn("T06_NATIVE_WPF_SHA_READBACK_HOLD",b)
  self.assertLess(b.index("T06_NATIVE_WPF_SHA_READBACK_HOLD"),b.index("& dotnet publish $project"))
  self.assertIn("native_wpf_e2e_accepted=$false",b)
  self.assertIn("PythonNativeSmokeReceipt=$PythonNativeSmokeReceipt",w)
  self.assertIn("stage_p01.py",w)
  self.assertNotIn("Remove-Item",w)
