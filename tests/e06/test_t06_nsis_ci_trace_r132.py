"""CI-only NSIS instrumentation must preserve approved original and fail on drift."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location("t06_ci_trace",ROOT/"coordination/e06/t06_package_original_onehost.py")
OWNER=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OWNER)
APPROVED=ROOT/"stage/proposals/P01/C09/Installer/NOX-HELION-Setup.nsi"

class TraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d=Path(self.tmp.name)/"Installer"
        d.mkdir()
        self.path=d/"NOX-HELION-Setup.nsi"
        self.original=APPROVED.read_bytes()
        self.path.write_bytes(self.original)

    def test_four_exact_phase_probes_and_original_unchanged(self):
        proof=OWNER.stage_ci_nsis_first_failure_trace(self.path)
        body=self.path.read_text("utf-8-sig")
        self.assertEqual(proof["trace_probes"],4)
        self.assertIs(proof["release_accepted"],False)
        self.assertEqual(body.count("PREFLIGHT_EXIT=$ExitCode"),1)
        self.assertEqual(body.count("VERIFY_EXIT=$ExitCode"),1)
        self.assertEqual(body.count("NOX_EXPRESS_CI_NSIS_TRACE.txt"),4)
        self.assertEqual(body.count("UNINSTALL_ENTER=0"),1)
        self.assertEqual(body.count("UNINSTALL_REMOVE_EXIT=$ExitCode"),1)
        install=body.split('Section "NOX HELION application" SEC_MAIN',1)[1].split("\nSectionEnd",1)[0]
        self.assertLess(install.index("PREFLIGHT_EXIT=$ExitCode"),install.index("Verify-Payload.ps1"))
        self.assertLess(install.index("Verify-Payload.ps1"),install.index("VERIFY_EXIT=$ExitCode"))
        uninstall=body.split('Section "Uninstall"',1)[1].split("\nSectionEnd",1)[0]
        self.assertLess(uninstall.index("UNINSTALL_ENTER=0"),uninstall.index("nsExec::ExecToStack"))
        self.assertLess(uninstall.index("nsExec::ExecToStack"),uninstall.index("UNINSTALL_REMOVE_EXIT=$ExitCode"))
        self.assertIn("WriteUninstaller",body)
        self.assertEqual(APPROVED.read_bytes(),self.original)

    def test_unrecognized_source_stays_unmodified(self):
        bad=self.original.replace(b"  Pop $CheckResult\n  ${If} $ExitCode != \"0\"",
                                  b"  Pop $CheckResult\n  ${If} $ExitCode == \"1\"",1)
        self.assertNotEqual(bad,self.original)
        self.path.write_bytes(bad)
        with self.assertRaisesRegex(RuntimeError,"GATE_HOLD"):
            OWNER.stage_ci_nsis_first_failure_trace(self.path)
        self.assertEqual(self.path.read_bytes(),bad)

    def test_repeat_source_refused(self):
        OWNER.stage_ci_nsis_first_failure_trace(self.path)
        frozen=self.path.read_bytes()
        with self.assertRaises(RuntimeError):
            OWNER.stage_ci_nsis_first_failure_trace(self.path)
        self.assertEqual(self.path.read_bytes(),frozen)

if __name__=="__main__": unittest.main()
