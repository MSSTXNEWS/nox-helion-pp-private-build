"""Regression: original E06 staged app and pinned addons reject reparse ancestors.

Runs ACTUAL stage_native_stdio.py source in disposable temp directories;
never touches the user's installed NOX data or downloads model weights.
"""
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

STAGER = Path(__file__).resolve().parents[2] / "coordination/e06/stage_native_stdio.py"
ORIGINAL = ("import argparse\n\ndef main():\n"
            "    parser = argparse.ArgumentParser()\n"
            "    args = parser.parse_args()\n"
            "    return 0\n")


def _stager():
    spec = importlib.util.spec_from_file_location("nox_e06_reparse_r26", STAGER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ARG_ANCHOR = "    parser = argparse.ArgumentParser()"
    module.PARSE_ANCHOR = "    args = parser.parse_args()"
    module.STAGED_MODE = "    pass\n"
    module.ORIGINAL_APP_SHA256 = hashlib.sha256(ORIGINAL.encode()).hexdigest()
    module.ADDONS = ()
    return module


def _app(folder):
    folder.mkdir(parents=True, exist_ok=True)
    app = folder / "app.py"
    app.write_text(ORIGINAL, encoding="utf-8")
    return app


def _link_or_skip(case, link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        case.skipTest("Directory symlink unavailable: " + str(error))


class StageReparseR26Tests(unittest.TestCase):
    def test_normal_original_stage_preserves_onehost(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "stage"
            app = _app(source / "helion")
            module = _stager()
            result = module.stage(source)
            self.assertEqual(result["pinned_addons"], 0)
            self.assertFalse(result["installed_windows_exe_accepted"])
            self.assertIn("--native-stdio", app.read_text(encoding="utf-8"))

    def test_original_app_parent_link_cannot_modify_external_same_byte_app(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "stage"
            source.mkdir()
            external_app = _app(root / "outside" / "helion")
            _link_or_skip(self, source / "helion", external_app.parent)
            module = _stager()
            with self.assertRaisesRegex(RuntimeError, "E06_NATIVE_STAGING_REPARSE_HOLD"):
                module.stage(source)
            self.assertEqual(external_app.read_text(encoding="utf-8"), ORIGINAL)

    def test_in_tree_addon_parent_link_cannot_redirect_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "stage"
            _app(source / "helion")
            (source / "other").mkdir()
            _link_or_skip(self, source / "nox_selfbuilder", source / "other")
            donor_root = root / "donor"
            donor_root.mkdir()
            raw = b"answer = 42\n"
            (donor_root / "donor.py").write_bytes(raw)
            module = _stager()
            module.ROOT = donor_root
            module.ADDONS = (("donor.py", "nox_selfbuilder/probe.py",
                              module.git_blob(raw)),)
            with self.assertRaisesRegex(RuntimeError, "E06_NATIVE_STAGING_REPARSE_HOLD"):
                module.stage(source)
            self.assertFalse((source / "other" / "probe.py").exists())


if __name__ == "__main__":
    unittest.main()
