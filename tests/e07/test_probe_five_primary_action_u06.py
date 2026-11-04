"""Fail-closed exact UIA click navigation receipt tests (no physical Windows PASS)."""
import importlib.util
import hashlib
import json
import tempfile
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[2] / "coordination" / "e07" / "probe_five_primary_action.py"
spec = importlib.util.spec_from_file_location("probe_primary", PATH)
import sys
sys.path.insert(0, str(PATH.parent))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def witness():
    return {"five_primary_buttons": {"status": "PASS", "buttons_present": list(module.PRIMARY)},
            "ui_chat_action_probe": {"action": "CHAT", "actions_invoked": 1,
                 "method": "NATIVE_UIA_INVOKEPATTERN", "navigation_verified": "PASS",
                 "navigation_proof": "NEW_VISIBLE_UIA_CHAT_HEADING"},
            "ui_safe_primary_navigation": {"actions_invoked": 4, "navigation_verified": "PASS",
                "per_action": {name: {"button_actuated": "OBSERVED", "navigation_verified": "PASS",
                                      "function_verified": "NOT_TESTED"} for name in module.PRIMARY[1:]}}}


class FiveButtonGate(unittest.TestCase):
    def test_full_five_click_navigation_not_release(self):
        result = module.evaluate(witness())
        self.assertEqual(result["actions_invoked"], 5)
        self.assertFalse(result["release_accepted"])
        self.assertFalse(result["live_inference_verified"])

    def test_button_presence_not_click(self):
        r = witness(); r["ui_chat_action_probe"]["actions_invoked"] = 0
        with self.assertRaises(module.Hold): module.evaluate(r)

    def test_no_preexisting_heading_false_pass(self):
        r = witness(); r["ui_chat_action_probe"]["navigation_proof"] = "NONE"
        with self.assertRaises(module.Hold): module.evaluate(r)

    def test_missing_one_of_four(self):
        r = witness(); r["ui_safe_primary_navigation"]["per_action"]["SETTINGS"]["navigation_verified"] = "NOT_TESTED"
        with self.assertRaises(module.Hold): module.evaluate(r)

    def test_legacy_reports_not_settings(self):
        r = witness(); r["five_primary_buttons"]["buttons_present"][-1] = "REPORTS"
        with self.assertRaises(module.Hold): module.evaluate(r)

    def test_wrong_action_set(self):
        r = witness(); r["ui_safe_primary_navigation"]["per_action"]["REPORTS"] = r["ui_safe_primary_navigation"]["per_action"].pop("SETTINGS")
        with self.assertRaises(module.Hold): module.evaluate(r)

    def test_untrusted_function_verification(self):
        r = witness(); r["ui_safe_primary_navigation"]["per_action"]["INSTALL"]["function_verified"] = "PASS"
        with self.assertRaises(module.Hold): module.evaluate(r)

    def _owned_fixture(self, root):
        shell = root / "NOX.P01.Shell.exe"
        shell.write_bytes(b"MZNOX-frozen-owned-shell")
        (root / "nox-p01-owned.txt").write_text("NOXHELION.P01 V16\n", encoding="utf-8")
        manifest = {"schema": "NOX_P01_PAYLOAD_SHA256_V1",
                    "entrypoint": shell.name,
                    "files": [{"path": shell.name, "bytes": shell.stat().st_size,
                               "sha256": hashlib.sha256(shell.read_bytes()).hexdigest()}]}
        (root / "payload.sha256.json").write_text(json.dumps(manifest), encoding="utf-8")
        return shell

    def test_real_owned_bytes_snapshot_stable_with_unowned_user_file(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._owned_fixture(root)
            user_file = root / "user-not-owned.txt"
            user_file.write_bytes(b"preserve me")
            baseline = module.snapshot_installed_owner(root)
            self.assertEqual(baseline, module.snapshot_installed_owner(root))
            self.assertEqual(len(baseline[0]), 1)
            self.assertEqual(user_file.read_bytes(), b"preserve me")

    def test_owned_executable_replaced_after_gui_must_hold(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            shell = self._owned_fixture(root)
            baseline = module.snapshot_installed_owner(root)
            shell.write_bytes(b"MZNOX-modified-owned-shell")
            with self.assertRaises(module.Hold):
                after = module.snapshot_installed_owner(root)
                module.require(after == baseline, "E07_PRIMARY_OWNED_PAYLOAD_CHANGED_DURING_UIA_HOLD")

    def test_owner_marker_mutation_after_gui_must_hold(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._owned_fixture(root)
            baseline = module.snapshot_installed_owner(root)
            owner = root / "nox-p01-owned.txt"
            owner.write_text("NOXHELION.P01 V16\nUNTRUSTED", encoding="utf-8")
            with self.assertRaises(module.Hold):
                after = module.snapshot_installed_owner(root)
                module.require(after == baseline, "E07_PRIMARY_OWNED_PAYLOAD_CHANGED_DURING_UIA_HOLD")

    def test_manifest_replaced_with_matching_files_must_hold_on_pre_post(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._owned_fixture(root)
            baseline = module.snapshot_installed_owner(root)
            manifest_path = root / "payload.sha256.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["extra"] = "altered"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            after = module.snapshot_installed_owner(root)
            with self.assertRaises(module.Hold):
                module.require(after == baseline, "E07_PRIMARY_OWNED_PAYLOAD_CHANGED_DURING_UIA_HOLD")

    def test_no_source_guess(self):
        with self.assertRaises(module.Hold):
            module.checked_source_setup(Path('/not/real'), 'bad', 'nope')

if __name__ == "__main__": unittest.main()
