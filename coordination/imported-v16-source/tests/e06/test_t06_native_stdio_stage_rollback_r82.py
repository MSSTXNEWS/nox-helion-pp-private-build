"""R82: original Python stdio staging must rollback owned outputs on publish failure."""
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
from unittest import TestCase, main, mock

class StageRollback(TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        root=Path(self.t.name)
        self.dest=root/"source"
        app=self.dest/"helion"/"app.py"
        app.parent.mkdir(parents=True)
        self.original=(b"import argparse\n" b"def main():\n"
            b"    parser=argparse.ArgumentParser()\n"
            b"    parser.add_argument('--diagnose',action='store_true',help='headless functional contracts check')\n"
            b"    args=parser.parse_args()\n")
        app.write_bytes(self.original)
        self.app=app
        self.repo=root/"repo"
        owner=self.repo/"owner"/"module.py"
        owner.parent.mkdir(parents=True)
        self.extra=b"answer = 42\n"
        owner.write_bytes(self.extra)
        spec=importlib.util.spec_from_file_location("actual_original_stdio",os.environ["NOX_STAGE_FILE"])
        self.stage=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.stage)
        self.stage.ROOT=self.repo
        self.stage.ADDONS=(("owner/module.py","nox_selfbuilder/module.py",
            self.stage.git_blob(self.extra)),)
        self.stage.ORIGINAL_APP_SHA256=hashlib.sha256(self.original).hexdigest()
        self.target=self.dest/"nox_selfbuilder"/"module.py"

    def test_publisher_exception_restores_original_and_removes_owned_output(self):
        with mock.patch("os.replace",side_effect=OSError("R82 injected publish fault")):
            with self.assertRaisesRegex(OSError,"R82 injected publish fault"):
                self.stage.stage(self.dest)
        self.assertEqual(self.app.read_bytes(),self.original)
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.app.parent.glob(".nox-native-*.tmp")),[])

    def test_runtime_data_receipt_keeps_declared_posix_destinations(self):
        model=self.repo/"owner"/"approved.json"
        model.write_bytes(b'{"approved":false}\n')
        self.stage.ADDONS += (("owner/approved.json",
            "nox_selfbuilder/approved.json",
            self.stage.git_blob(model.read_bytes())),)
        receipt=self.stage.stage(self.dest)
        self.assertEqual(receipt["pinned_addons"],2)
        self.assertEqual(len(receipt["runtime_data_files"]),1)
        self.assertEqual(receipt["runtime_data_files"][0]["runtime_path"],
                         "nox_selfbuilder/approved.json")
        self.assertEqual(receipt["runtime_data_files"][0]["sha256"],
                         hashlib.sha256(model.read_bytes()).hexdigest())

    def test_success_stages_same_original_and_pinned_addon(self):
        receipt=self.stage.stage(self.dest)
        self.assertEqual(self.target.read_bytes(),self.extra)
        self.assertIn(b"native_stdio",self.app.read_bytes())
        self.assertEqual(receipt["pinned_addons"],1)
        self.assertFalse(receipt["installed_windows_exe_accepted"])

if __name__=="__main__": main()
