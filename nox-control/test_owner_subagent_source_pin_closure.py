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
        for filename, expected in pins.items():
            with self.subTest(filename=filename):
                actual = hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()
                self.assertEqual(actual, expected)

        self.assertEqual(installer.NEW_CALLBACK,
                         pins["owner_subagent_dispatcher_fresh.py"])
        self.assertEqual(installer.NEW_DEPENDENCIES["owner_autonomy_pool.py"],
                         pins["owner_autonomy_pool.py"])
        self.assertEqual(installer.NEW_DEPENDENCIES["owner_subagent_processes.py"],
                         pins["owner_subagent_processes.py"])
        self.assertEqual(installer.NEW_MENTOR_SHA,
                         pins["owner_dispatcher_mentor.py"])
        for filename, expected in installer.ASSETS.items():
            with self.subTest(installer_asset=filename):
                actual = hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()
                self.assertEqual(actual, expected)

    def test_manual_subagent_route_skips_missing_legacy_operator_preimage(self):
        workflow = (ROOT.parent / ".github/workflows/nox-owner-maintenance-command.yml").read_text()
        self.assertIn("|backup|subagent)", workflow)
        self.assertIn("elif [ \"$NOX_ACTION\" = \"subagent\" ]; then", workflow)
        self.assertIn("owner_native_operator_scoped_bundle.py \"$NOX_ACTION\"", workflow)
        self.assertIn("if a=='subagent':", workflow)


if __name__ == "__main__":
    unittest.main()
