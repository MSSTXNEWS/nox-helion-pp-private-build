"""Verify the subagent route's byte pins before any owner/native operation."""
from pathlib import Path
import hashlib
import importlib.util
import unittest

ROOT = Path(__file__).parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SourcePinClosureTests(unittest.TestCase):
    def test_scoped_bundle_matches_installer_and_exact_source_bytes(self):
        bundle = load("owner_native_operator_scoped_bundle_test",
                      "owner_native_operator_scoped_bundle.py")
        installer = load("owner_subagent_fresh_install_entry_test",
                         "owner_subagent_fresh_install_entry.py")
        pins = bundle.SUBAGENT_BUNDLE_PINS
        self.assertEqual(pins["owner_dispatcher_mentor.py"],
                         "d9368e7dc5b80c86a73c90eb2f92ff13cb3a61e8b915861a19be414d1e2808f4")
        self.assertEqual(pins["owner_task_lifecycle.py"],
                         "75d0718bf9986f1a2cdbfa4f42f4fea9a8dad4558f1273c460c62dadb816f2a0")
        self.assertEqual(pins["owner_senior_gateway.py"],
                         "40cbaec2e32e43f2aa78a1078ed296d4957c620256081695111b81136d2d3751")
        for filename, expected in pins.items():
            with self.subTest(filename=filename):
                actual = hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()
                self.assertEqual(actual, expected)

        self.assertEqual(pins["owner_subagent_dispatcher_fresh.py"],
                         "80af1988009263b7e7cdbd51701501aa39ced6f6b5edd4ce8b9565eae55f01b3")
        self.assertEqual(installer.NEW_CALLBACK,
                         pins["owner_subagent_dispatcher_fresh.py"])
        self.assertEqual(
            hashlib.sha256((ROOT / "owner_subagent_fresh_install_entry.py").read_bytes()).hexdigest(),
            "d40dcc31bdcb1b020622ff1ff6e2a87bfb7a380136ddd8e7a84ee1755e2c89f5",
        )
        self.assertEqual(installer.NEW_DEPENDENCIES["owner_autonomy_pool.py"],
                         pins["owner_autonomy_pool.py"])
        self.assertEqual(installer.NEW_DEPENDENCIES["owner_subagent_processes.py"],
                         pins["owner_subagent_processes.py"])
        self.assertEqual(installer.NEW_MENTOR_SHA,
                         pins["owner_dispatcher_mentor.py"])
        self.assertEqual(installer.NEW_LIFECYCLE_SHA,
                         pins["owner_task_lifecycle.py"])
        self.assertEqual(installer.NEW_GATEWAY_SHA,
                         pins["owner_senior_gateway.py"])
        self.assertEqual(installer.NATIVE_PREIMAGES["owner_task_lifecycle.py"],
                         "909502a75799096e094a622639fe959ecfa835cc70db705a4062541940cea27e")
        self.assertEqual(installer.NATIVE_PREIMAGES["owner_senior_gateway.py"],
                         "1fd1556009ce62fa806bdee0a9a34577d276344e728fe9d94b33f44eb151346e")
        self.assertEqual(installer.NATIVE_PREIMAGES["nox_dispatcher_t855u.py"],
                         "9ae0c67523967756206a0da31d1a1cab65281dc2f4f28989f2156cd27da43a21")
        self.assertEqual(installer.OLD_CONFIG_MODULE_PINS,
                         {"owner_subagent_dispatcher.py": installer.OLD_CALLBACK,
                          "owner_task_lifecycle.py": None,
                          "owner_senior_gateway.py": None,
                          "nox_dispatcher_t855u.py": None})
        self.assertEqual(installer.UNVERIFIED_NATIVE_PREIMAGES,
                         {"owner_autonomy_pool.py", "owner_subagent_processes.py", "owner_dispatcher_mentor.py"})
        self.assertEqual(set(installer.NATIVE_PREIMAGE_RECEIPTS),
                         installer.REQUIRED_PREIMAGE_FILES - installer.UNVERIFIED_NATIVE_PREIMAGES)
        for filename, expected in installer.ASSETS.items():
            with self.subTest(installer_asset=filename):
                actual = hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()
                self.assertEqual(actual, expected)


    def test_global_stop_detects_state_stop_flag(self):
        helper = load("owner_subagent_install_entry_stop_test", "owner_subagent_install_entry.py")
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "root"
            state = root / "state"
            state.mkdir(parents=True)
            workspace_stop = Path(folder) / "workspace" / "NOX_STOP"
            path_factory = lambda value: workspace_stop if str(value) == "/workspace/NOX_STOP" else Path(value)
            with patch.object(helper, "ROOT", root), patch.object(helper, "STATE", state), \
                 patch.object(helper, "Path", path_factory):
                self.assertFalse(helper.global_stop())
                (state / "STOP.flag").touch()
                self.assertTrue(helper.global_stop())

    def test_manual_subagent_route_skips_missing_legacy_operator_preimage(self):
        workflow = (ROOT.parent / ".github/workflows/nox-owner-maintenance-command.yml").read_text()
        self.assertIn("|backup|subagent)", workflow)
        self.assertIn("elif [ \"$NOX_ACTION\" = \"subagent\" ]; then", workflow)
        self.assertIn("owner_native_operator_scoped_bundle.py \"$NOX_ACTION\"", workflow)
        self.assertIn("if a=='subagent':", workflow)


if __name__ == "__main__":
    unittest.main()
