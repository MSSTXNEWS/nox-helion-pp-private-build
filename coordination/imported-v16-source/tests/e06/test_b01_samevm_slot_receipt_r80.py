"""B01: real D06 backup probe receipts are NOT subprocess exit receipts.

Execute only the original production G4 bridge function, extracted from its
actual AST. Synthetic receipts below are negative/positive contract fixtures,
not physical Windows, an installer, or independent E07 evidence.
"""
from __future__ import annotations

import ast
import copy
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "coordination/e06/t06_local_onehost_bridge.py"


def load_original_gate():
    parsed = ast.parse(SOURCE.read_text(encoding="utf-8-sig"), filename=str(SOURCE))
    functions = [node for node in parsed.body if isinstance(node, ast.FunctionDef)
                 and node.name == "verified_samevm_lifecycle_state"]
    if len(functions) != 1:
        raise AssertionError("B01_G4_OWNER_GATE_SOURCE_DRIFT_HOLD")
    isolated = ast.Module(body=functions, type_ignores=[])
    namespace = {}
    exec(compile(ast.fix_missing_locations(isolated), str(SOURCE), "exec"), namespace)
    return namespace["verified_samevm_lifecycle_state"]


class TestOriginalG4ReceiptTypeParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gate = staticmethod(load_original_gate())

    def receipts(self):
        manifest_count = 484
        native_names = (
            "preflight_final", "install", "verify", "update", "rollback",
            "rollback_payload_superseded", "uninstall",
        )
        lifecycle = {key: {"code": 0} for key in native_names}
        probe = {
            "status": "PASS_DIAGNOSTIC_ONLY",
            "manifest_files_checked": manifest_count,
            "unmanaged_probe_preserved": True,
            "release_accepted": False,
        }
        lifecycle.update({
            "backup_payload_verify": copy.deepcopy(probe),
            "rollback_payload_restored": copy.deepcopy(probe),
            "original_wpf_gui": {"new_nav_ok": True, "new_python_ipc_handshake": True},
            "native_ipc": {
                "route": "models.installed", "run_id_matched": True,
                "request_id_matched": True, "real_model_inference_tested": False,
                "status": "PROVIDER_OFFLINE_HOLD",
                "model_inventory_route_verified": False,
            },
            "update_unmanaged_user_data": "PRESERVED_IN_BACKUP",
            "rollback_unmanaged_user_data": "PRESERVED_IN_RESTORED_INSTALL",
            "unmanageD_install_file_noloss": "PRESERVED_VERIFIED",
            "uninstall_owned_files_checked": manifest_count,
            "uninstall_registry_views_checked": 2,
            "uninstall_any_exit_no_loss": {
                "persistent_user_data": "PRESERVED",
                "unmanaged_install_data": "PRESERVED",
                "read_only": True, "independent_e07": "NOT_RUN",
                "release_accepted": False,
            },
        })
        # The production key is case-sensitive: keep a checked fixture.
        lifecycle["unmanaged_install_file_noloss"] = lifecycle.pop(
            "unmanageD_install_file_noloss")
        smoke = {
            "installer_lifecycle": lifecycle,
            "manifest_files_checked": manifest_count,
            "release_accepted": False,
            "e07_independent_acceptance": "NOT_RUN",
            "original_home_and_core01_sha_verified": True,
            "phase": "INSTALLED_GUI_IPC_UPDATE_ROLLBACK_NOLOSS_PROVIDER_OFFLINE_HOLD_NOT_E07",
        }
        return smoke, {"return_code": 0}

    def test_original_native_rollback_with_exact_owned_probe_stays_diagnostic(self):
        smoke, child = self.receipts()
        self.assertEqual(self.gate(smoke, child), "PROVIDER_OFFLINE_HOLD_NOT_E07")

    def test_provider_online_only_with_actual_owner_inventory(self):
        smoke, child = self.receipts()
        smoke["installer_lifecycle"]["native_ipc"]["status"] = "PASS"
        smoke["installer_lifecycle"]["native_ipc"]["model_inventory_route_verified"] = True
        smoke["phase"] = "INSTALLED_GUI_IPC_UPDATE_ROLLBACK_NOLOSS_PASS_NOT_E07"
        self.assertEqual(self.gate(smoke, child),
                         "INSTALLED_NATIVE_INVENTORY_DIAGNOSTIC_NOT_E07")

    def test_missing_or_forged_slot_receipt_fails_closed(self):
        for stage in ("backup_payload_verify", "rollback_payload_restored"):
            for key, value in (
                ("status", "SUCCESS"),
                ("unmanaged_probe_preserved", False),
                ("manifest_files_checked", 1),
                ("release_accepted", True),
                ("code", 0),
            ):
                with self.subTest(stage=stage, key=key):
                    smoke, child = self.receipts()
                    smoke["installer_lifecycle"][stage][key] = value
                    with self.assertRaisesRegex(RuntimeError,
                                                "T06_M1_REAL_WINDOWS_GUI_IPC_LIFECYCLE_GATE_HOLD"):
                        self.gate(smoke, child)
            smoke, child = self.receipts()
            del smoke["installer_lifecycle"][stage]
            with self.assertRaises(RuntimeError):
                self.gate(smoke, child)

    def test_no_loss_and_real_exit_guards_remain_strict(self):
        for key, value in (
            ("update_unmanaged_user_data", "HOLD"),
            ("rollback_unmanaged_user_data", "HOLD"),
            ("unmanaged_install_file_noloss", "HOLD"),
        ):
            with self.subTest(key=key):
                smoke, child = self.receipts()
                smoke["installer_lifecycle"][key] = value
                with self.assertRaises(RuntimeError):
                    self.gate(smoke, child)
        for stage in ("install", "verify", "uninstall"):
            with self.subTest(stage=stage):
                smoke, child = self.receipts()
                smoke["installer_lifecycle"][stage]["code"] = 1
                with self.assertRaises(RuntimeError):
                    self.gate(smoke, child)
        smoke, child = self.receipts()
        child["return_code"] = 1
        with self.assertRaises(RuntimeError):
            self.gate(smoke, child)

    def test_false_success_and_missing_provider_never_admitted(self):
        for key, value in (
            ("persistent_user_data", "HOLD"),
            ("unmanaged_install_data", "HOLD"),
            ("independent_e07", "PASS"),
            ("release_accepted", True),
        ):
            with self.subTest(key=key):
                smoke, child = self.receipts()
                smoke["installer_lifecycle"]["uninstall_any_exit_no_loss"][key] = value
                with self.assertRaises(RuntimeError):
                    self.gate(smoke, child)
        smoke, child = self.receipts()
        smoke["release_accepted"] = True
        with self.assertRaises(RuntimeError):
            self.gate(smoke, child)
        smoke, child = self.receipts()
        smoke["installer_lifecycle"]["native_ipc"]["status"] = "PASS"
        with self.assertRaises(RuntimeError):
            self.gate(smoke, child)


if __name__ == "__main__":
    unittest.main()
