"""Original NSIS payload inventory must fail closed on a directory junction.

Source test, not Windows installed E07.
"""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"coordination/e06/t06_package_original_onehost.py"
spec=importlib.util.spec_from_file_location("nox_nsis_payload_r58",SOURCE)
assert spec is not None and spec.loader is not None
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class OriginalNsisPayloadInventoryR58(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/"payload"
        self.root.mkdir()
        self.assets=self.root/"Assets"
        self.assets.mkdir()
        self.file=self.assets/"approved.bin"
        self.file.write_bytes(b"approved")

    def test_regular_directory_and_file(self):
        self.assertIsNone(module.verify_source_tree_entry(self.assets,self.root))
        self.assertIsNone(module.verify_source_tree_entry(self.file,self.root))

    def test_internal_directory_symlink_not_skipped_as_dir(self):
        alias=self.root/"other"
        try:
            alias.symlink_to(self.assets,target_is_directory=True)
        except (OSError,NotImplementedError):
            self.skipTest("directory symlink not allowed on this host")
        self.assertTrue(alias.is_dir())
        with self.assertRaisesRegex(RuntimeError,"REPARSE_HOLD"):
            module.verify_source_tree_entry(alias,self.root)
        with self.assertRaisesRegex(RuntimeError,"REPARSE_HOLD"):
            module.verify_source_tree_entry(alias/"approved.bin",self.root)

    def test_leaf_symlink_rejected(self):
        alias=self.assets/"other.bin"
        try:
            alias.symlink_to(self.file)
        except (OSError,NotImplementedError):
            self.skipTest("file symlink not allowed on this host")
        with self.assertRaisesRegex(RuntimeError,"REPARSE_HOLD"):
            module.verify_source_tree_entry(alias,self.root)

    def test_external_payload_path_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"OUTSIDE_TRUSTED_ROOT"):
            module.verify_source_tree_entry(self.root.parent/"foreign.exe",self.root)

    def test_missing_path_is_hold(self):
        with self.assertRaisesRegex(RuntimeError,"MISSING_OR_UNREADABLE"):
            module.verify_source_tree_entry(self.root/"missing",self.root)

    def test_special_fifo_not_admitted(self):
        if not hasattr(os,"mkfifo"):
            self.skipTest("FIFO not supported")
        fifo=self.assets/"fifo"
        os.mkfifo(fifo)
        with self.assertRaisesRegex(RuntimeError,"NONREGULAR_COMPONENT"):
            module.verify_source_tree_entry(fifo,self.root)

    def test_existing_asset_and_payload_loops_guard_before_skip(self):
        source=SOURCE.read_text("utf-8")
        self.assertIn('for file in original_assets.rglob("*"):\n        verify_source_tree_entry(file,root)\n        if file.is_dir():continue',source)
        self.assertIn('for file in sorted(payload.rglob("*")):\n        verify_source_tree_entry(file,payload)\n        if file.is_dir():continue',source)
        self.assertIn("verify_source_tree_entry(out.parent,payload)",source)
        self.assertIn("verify_source_tree_entry(out,payload)",source)

if __name__=="__main__": unittest.main()
