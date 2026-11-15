"""Source-only safety tests for Windows double-click NOX preflight.

Does NOT run PowerShell on Linux or claim physical Windows acceptance.
"""
from pathlib import Path
import unittest


class WindowsOnepassReadOnlyContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path("coordination/onepass/windows")
        cls.ps=(root/"NOX_ONEPASS_VERIFY_WINDOWS.ps1").read_text(encoding="utf8")
        cls.cmd=(root/"RUN_ONEPASS_CHECK.cmd").read_text(encoding="utf8")
    def test_exact_artifact_hash_and_count(self):
        self.assertIn("45893adaf1fa49991dbb9f61f3d5cc4f2273eddf5d6f2e2548cf57d0b09fb947",self.ps)
        self.assertIn("expected_package_entries = 1091",self.ps)
        self.assertIn("site/nox-legacy-chat-bridge-v293.js",self.ps)
        self.assertIn("Get-FileHash",self.ps)
    def test_no_mutation_or_fake_acceptance(self):
        for keyword in ("Start-Process","Restart-Service","Stop-Service",
                        "Remove-Item","Invoke-WebRequest","Invoke-RestMethod",
                        "Set-ExecutionPolicy","Clear-Content","Expand-Archive"):
            self.assertNotIn(keyword,self.ps)
        self.assertIn("software_installed_or_services_restarted = $false",self.ps)
        self.assertIn("original_S03_weights_modified = $false",self.ps)
        self.assertIn("release_92_functions_accepted = $false",self.ps)
        self.assertIn("windows_pc_handler_registration_verified = $false",self.ps)
        self.assertIn("HTTP_404_AUTH_MASKED_OR_ROUTE_UNKNOWN",self.ps)
        self.assertIn("owner_authenticated_model_response = 'NOT_TESTED'",self.ps)
        self.assertIn("GPU_STOP_physical = 'NOT_TESTED'",self.ps)
    def test_one_click_only_executes_existing_verifier(self):
        self.assertIn('NOX_ONEPASS_VERIFY_WINDOWS.ps1',self.cmd)
        self.assertNotIn('NOX_START.ps1',self.cmd)
        self.assertNotIn('shutdown',self.cmd.lower())
        self.assertNotIn('del ',self.cmd.lower())
    def test_windows_ports_are_only_tcp_connect(self):
        self.assertIn("127.0.0.1",self.ps)
        self.assertIn("BeginConnect",self.ps)
        self.assertIn("TCP_REACHABLE_NOT_FUNCTIONAL_E2E",self.ps)
        self.assertNotIn("Authorization: Bearer",self.ps)
        self.assertNotIn("X-NOX-Session",self.ps)

if __name__=="__main__":
    unittest.main()
