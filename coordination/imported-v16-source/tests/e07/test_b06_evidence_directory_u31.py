"""Original E07 proof directory must be freshly owned and never reparse-backed."""
from __future__ import annotations
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"coordination"/"e07"))
import independent_setup_e07 as e07
from probe_final_same_setup import prepare_final_visual_directory


class B06EvidenceDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.target=self.root/"proof"

    def link(self,target:Path,*,to:Path):
        try:
            target.symlink_to(to,target_is_directory=True)
        except (OSError,NotImplementedError) as exc:
            self.skipTest("Windows runner lacks symlink privilege: "+type(exc).__name__)

    def test_fresh_directory_created(self):
        prepare_final_visual_directory(self.target,new_observation=True)
        self.assertTrue(e07.clean_dir(self.target))

    def test_continue_same_run_keeps_png(self):
        prepare_final_visual_directory(self.target,new_observation=True)
        photo=self.target/"D02_FINAL_SAME_SETUP.png"
        photo.write_bytes(b"immutable-existing-observation")
        prepare_final_visual_directory(self.target,new_observation=False)
        self.assertEqual(photo.read_bytes(),b"immutable-existing-observation")

    def test_reject_preexisting_empty_root(self):
        self.target.mkdir()
        with self.assertRaisesRegex(e07.Hold,"EVIDENCE_COLLISION"):
            prepare_final_visual_directory(self.target,new_observation=True)

    def test_reject_foreign_regular_file(self):
        self.target.write_text("foreign",encoding="utf-8")
        with self.assertRaisesRegex(e07.Hold,"EVIDENCE_COLLISION"):
            prepare_final_visual_directory(self.target,new_observation=True)

    def test_reject_fresh_symlink(self):
        self.link(self.target,to=self.root)
        with self.assertRaisesRegex(e07.Hold,"EVIDENCE_COLLISION"):
            prepare_final_visual_directory(self.target,new_observation=True)

    def test_reject_dangling_symlink(self):
        self.link(self.target,to=self.root/"missing")
        with self.assertRaisesRegex(e07.Hold,"EVIDENCE_COLLISION"):
            prepare_final_visual_directory(self.target,new_observation=True)

    def test_reject_parent_symlink(self):
        real=self.root/"real";real.mkdir()
        link=self.root/"alias";self.link(link,to=real)
        with self.assertRaisesRegex(e07.Hold,"EVIDENCE_PARENT"):
            prepare_final_visual_directory(link/"proof",new_observation=True)

    def test_reject_continuation_without_original(self):
        with self.assertRaisesRegex(e07.Hold,"EVIDENCE_DIR_REPARSE"):
            prepare_final_visual_directory(self.target,new_observation=False)

    def test_reject_continuation_symlink(self):
        self.link(self.target,to=self.root)
        with self.assertRaisesRegex(e07.Hold,"EVIDENCE_DIR_REPARSE"):
            prepare_final_visual_directory(self.target,new_observation=False)

    def test_reject_continuation_file(self):
        self.target.write_text("forged",encoding="utf-8")
        with self.assertRaisesRegex(e07.Hold,"EVIDENCE_DIR_REPARSE"):
            prepare_final_visual_directory(self.target,new_observation=False)


if __name__=="__main__":
    unittest.main()
