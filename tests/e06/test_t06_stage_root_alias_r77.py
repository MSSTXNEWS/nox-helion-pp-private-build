"""R77: original native stdio stage must inspect named root before resolve."""
from pathlib import Path
import importlib.util
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"coordination/e06/stage_native_stdio.py"
spec=importlib.util.spec_from_file_location("r77_actual_native_stage",SOURCE)
stage_module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage_module)

class StageRootAlias(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.approved=self.root/"approved"
        self.approved.mkdir()

    def make_link(self,alias,target):
        try:
            alias.symlink_to(target,target_is_directory=True)
        except (OSError,NotImplementedError) as exc:
            self.skipTest("symlink creation is unavailable: "+str(exc))

    def test_direct_symlink_root_denied_before_source_open(self):
        alias=self.root/"alias"
        self.make_link(alias,self.approved)
        with self.assertRaisesRegex(RuntimeError,"E06_NATIVE_STAGING_ROOT_REPARSE_HOLD"):
            stage_module.stage(alias)
        self.assertEqual(sorted(self.approved.iterdir()),[])

    def test_symlink_parent_denied_before_source_open(self):
        parent=self.root/"parent-link"
        self.make_link(parent,self.approved)
        with self.assertRaisesRegex(RuntimeError,"E06_NATIVE_STAGING_ROOT_REPARSE_HOLD"):
            stage_module.stage(parent/"nested")
        self.assertEqual(sorted(self.approved.iterdir()),[])

    def test_regular_original_staging_path_keeps_existing_hold(self):
        with self.assertRaisesRegex(RuntimeError,"E06_ORIGINAL_APP_SOURCE_MISSING"):
            stage_module.stage(self.approved)
        self.assertEqual(sorted(self.approved.iterdir()),[])

if __name__=="__main__":
    unittest.main()
