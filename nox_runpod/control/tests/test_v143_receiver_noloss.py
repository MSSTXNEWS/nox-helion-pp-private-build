"""V143 independent source-only NO-LOSS audit of ORIGINAL legacy Windows A40 receiver.

No Windows machine, RunPod, Vast API or SSH invocation. Never asserts the
unmapped owner /api/install/backup endpoint exists or that real backup succeeded.
"""
from pathlib import Path
import unittest

SOURCE = Path("nox_runpod/control/nox_windows_verified_receiver.ps1")


class ReceiverNoLossSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf8")

    def test_original_pinned_path_not_a_new_backend(self):
        self.assertIn("NOX_PRIME_FULL_WEIGHTS", self.source)
        self.assertIn("/opt/nox_full_parameter_A40", self.source)
        self.assertIn("NOT an implementation of the Windows owner /api/install/backup", self.source)

    def test_remote_controller_install_completely_removed(self):
        for forbidden in ("nox_control_repair.sh", "install_nox_master_poller.sh",
                          "curl -fsSL", "&& bash", "HOLD_CONTROLLER_REPAIR",
                          "69.30.85.188", "Restart-Service", "supervisorctl restart"):
            with self.subTest(pattern=forbidden):
                self.assertNotIn(forbidden, self.source)
        self.assertIn("progress.json", self.source)
        self.assertIn("BatchMode=yes", self.source)

    def test_existing_bad_destination_holds_before_scp(self):
        self.assertIn("HOLD_EXISTING_BACKUP_CONFLICT", self.source)
        self.assertIn("HOLD_PARTIAL_BACKUP_CONFLICT", self.source)
        self.assertIn("SKIP_VERIFIED", self.source)
        self.assertLess(self.source.index("HOLD_EXISTING_BACKUP_CONFLICT"),
                        self.source.index("& scp.exe @scpArgs"))

    def test_no_forced_overwrite_and_atomic_no_replace_publish(self):
        self.assertNotIn("Move-Item -LiteralPath $temp -Destination $dest -Force", self.source)
        self.assertNotIn('Move-Item "$marker.tmp" $marker -Force', self.source)
        self.assertIn("[System.IO.File]::Move($temp,$dest)", self.source)
        self.assertIn("[System.IO.File]::Move($proofTemp,$marker)", self.source)
        self.assertIn("[System.IO.FileMode]::CreateNew", self.source)

    def test_existing_marker_never_skips_without_receipt_shard_rehash(self):
        section=self.source.split("if(Test-Path -LiteralPath $marker){",1)[1].split(" $items=@($status.shards)",1)[0]
        for token in ("HOLD_VERIFIED_RECEIPT_MISSING","HOLD_VERIFIED_RECEIPT_STALE",
                      "HOLD_VERIFIED_SHARD_MISSING_OR_TAMPERED",
                      "Get-FileHash","$priorReceipt.shards",
                      "NOX_ALREADY_VERIFIED","HOLD_EXISTING_MARKER_CONFLICT"):
            with self.subTest(token=token):
                self.assertIn(token, section)
        self.assertLess(section.index("Get-FileHash"), section.index("NOX_ALREADY_VERIFIED"))

    def test_owner_safe_receipt_matches_cycle_and_steps(self):
        self.assertIn("RECEIPT_MISMATCH", self.source)
        self.assertIn("FINAL_SHA_FAILED", self.source)
        self.assertIn("SHA_FAILED", self.source)
        self.assertIn("SHA256_VERIFIED", self.source)

    def test_no_unconditional_native_deployment_or_model_change(self):
        for forbidden in ("Start-Process", "Restart-Service", "Remove-Item",
                          "Set-ExecutionPolicy", "Invoke-WebRequest", "Invoke-RestMethod",
                          "nox_windows_recover_and_chat.ps1", "nox2"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main()
