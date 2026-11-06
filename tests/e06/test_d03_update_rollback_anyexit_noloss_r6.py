"""D03 original NSIS update/rollback any-exit read-only data identity tests.

SOURCE_ONLY: real filesystem tests, no Windows installer or E07.
"""
import os
from pathlib import Path
from unittest.mock import patch
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"coordination"/"e06"))
from t06_samevm_installed_smoke import original_no_loss_seed_identity, original_no_loss_anyexit_slot_snapshot

class D03AnyExitNoLoss(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.inst=self.root/"Programs"/"NOX HELION"
        self.inst.mkdir(parents=True)
        self.prev=Path(str(self.inst)+".__p01_previous")
        self.saved=Path(str(self.inst)+".__p01_rollback_saved")
        self.stage=Path(str(self.inst)+".__p01_stage")
        for p in (self.prev,self.saved,self.stage):p.mkdir()
        self.marker=self.root/"NOX_HELION"/"P01"/"state.bin"
        self.marker.parent.mkdir(parents=True)
        self.marker.write_bytes(b"persisted-data")
        self.unmanaged=self.inst/"user.dat"
        self.unmanaged.write_bytes(b"user-owned-bytes")
        self.mid=original_no_loss_seed_identity(self.marker,b"persisted-data",self.root)
        self.uid=original_no_loss_seed_identity(self.unmanaged,b"user-owned-bytes",self.root)

    def proof(self):
        return original_no_loss_anyexit_slot_snapshot(
            self.marker,b"persisted-data",self.mid,
            self.unmanaged.name,b"user-owned-bytes",self.uid,self.root,
            (("installed",self.inst),("previous",self.prev),
             ("rollback_saved",self.saved),("stage",self.stage)))

    def test_inaccessible_nsis_slot_readback_is_hard_hold(self):
        # Original update/rollback exits stay unchanged; an unreadable side
        # slot must not be mistaken for ABSENT, even if installed data survives.
        original_exists=Path.exists
        denied=self.stage/self.unmanaged.name
        def denied_slot(path,*args,**kwargs):
            if path==denied:
                raise PermissionError("simulated Windows slot access denied")
            return original_exists(path,*args,**kwargs)
        with patch.object(Path,"exists",autospec=True,side_effect=denied_slot):
            snapshot=self.proof()
        self.assertEqual(snapshot["persistent_user_data"],"PRESERVED")
        self.assertEqual(snapshot["unmanaged_install_data"],"HOLD")
        self.assertEqual(snapshot["unmanaged_slots_present"],["installed"])
        self.assertEqual(snapshot["unmanaged_slots_unreadable"],["stage"])
        self.assertIsNone(snapshot["original_unmanaged_slot"])

    def test_real_update_rename_and_rollback_restore(self):
        self.assertEqual(self.proof()["original_unmanaged_slot"],"installed")
        self.unmanaged.rename(self.prev/self.unmanaged.name)
        self.assertEqual(self.proof()["original_unmanaged_slot"],"previous")
        (self.prev/self.unmanaged.name).rename(self.unmanaged)
        self.assertEqual(self.proof()["original_unmanaged_slot"],"installed")

    def test_byte_identical_replacement_holds(self):
        f=self.inst/"replacement.bin"
        f.write_bytes(b"user-owned-bytes")
        os.replace(f,self.unmanaged)
        self.assertEqual(self.proof()["unmanaged_install_data"],"HOLD")

    def test_ambiguous_duplicate_holds(self):
        (self.prev/self.unmanaged.name).write_bytes(b"user-owned-bytes")
        self.assertEqual(self.proof()["unmanaged_install_data"],"HOLD")

    def test_missing_file_holds(self):
        self.unmanaged.unlink()
        self.assertEqual(self.proof()["unmanaged_install_data"],"HOLD")

    def test_replaced_persistent_file_holds(self):
        f=self.marker.parent/"replacement.bin"
        f.write_bytes(b"persisted-data")
        os.replace(f,self.marker)
        self.assertEqual(self.proof()["persistent_user_data"],"HOLD")

    def test_symlink_holds(self):
        self.unmanaged.unlink()
        try:self.unmanaged.symlink_to(self.marker)
        except (OSError,NotImplementedError):self.skipTest("symlink not permitted")
        self.assertEqual(self.proof()["unmanaged_install_data"],"HOLD")

    def test_empty_reparse_slot_is_not_absent(self):
        # A redirected but empty NSIS side slot used to count as ABSENT and
        # allow false PRESERVED from the legitimate installed user file.
        self.stage.rmdir()
        try:
            self.stage.symlink_to(self.root,target_is_directory=True)
        except (OSError,NotImplementedError):
            self.skipTest("directory symlink unsupported on this runner")
        snapshot=self.proof()
        self.assertEqual(snapshot["persistent_user_data"],"PRESERVED")
        self.assertEqual(snapshot["unmanaged_install_data"],"HOLD")
        self.assertEqual(snapshot["unmanaged_slots_unreadable"],["stage"])
        self.assertIsNone(snapshot["original_unmanaged_slot"])

    def test_non_directory_stage_slot_is_not_absent(self):
        # No elevated Windows privileges needed: an unexpected native
        # lifecycle side-slot FILE is just as untrusted as a reparse root.
        self.stage.rmdir()
        self.stage.write_bytes(b"foreign-slot")
        snapshot=self.proof()
        self.assertEqual(snapshot["unmanaged_install_data"],"HOLD")
        self.assertEqual(snapshot["unmanaged_slots_unreadable"],["stage"])

    def test_both_native_exit_gates_are_strict(self):
        s=(Path(__file__).resolve().parents[2]/
           "coordination/e06/t06_samevm_installed_smoke.py").read_text("utf-8")
        for phase in ("update","rollback"):
            self.assertIn(f'T06_{phase.upper()}_ANYEXIT_NOLOSS_HOLD',s)
            self.assertIn(f'report["installer_lifecycle"]["{phase}_any_exit_no_loss"]',s)

if __name__=="__main__":unittest.main()
