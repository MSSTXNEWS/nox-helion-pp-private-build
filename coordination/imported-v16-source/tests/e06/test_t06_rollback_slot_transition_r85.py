"""Original NSIS /ROLLBACK lifecycle: disposable source regression, not E07."""
from __future__ import annotations
import ast
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"coordination/e06/t06_samevm_installed_smoke.py"

def load_admission():
    tree=ast.parse(SOURCE.read_text("utf-8"))
    names={"require","plain_parents","regular","rollback_slot_layout"}
    definitions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    if {n.name for n in definitions} != names:
        raise AssertionError("R85_ORIGINAL_ROLLBACK_SLOT_ADMISSION_MISSING")
    scope={"Path":Path}
    exec(compile(ast.Module(body=definitions,type_ignores=[]),str(SOURCE),"exec"),scope)
    return scope["rollback_slot_layout"]

class RollbackSlotR85(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.install=self.root/"NOX HELION"
        self.previous=self.root/"NOX HELION.__p01_previous"
        self.saved=self.root/"NOX HELION.__p01_rollback_saved"
        self.check=load_admission()
    def owned(self,slot):
        slot.mkdir()
        (slot/"nox-p01-owned.txt").write_text("NOXHELION.P01 V16\n",encoding="utf-8")
    def test_real_slot_transition(self):
        self.owned(self.install);self.owned(self.saved)
        result=self.check(self.install,self.previous,self.saved,self.root)
        self.assertTrue(result["previous_consumed"] and result["saved_owned"])
    def test_noop_rollback_exit_zero_rejected(self):
        self.owned(self.install);self.owned(self.previous)
        with self.assertRaisesRegex(RuntimeError,"T06_ROLLBACK_PREVIOUS_SLOT_NOT_CONSUMED"):
            self.check(self.install,self.previous,self.saved,self.root)
    def test_missing_saved_slot_rejected(self):
        self.owned(self.install)
        with self.assertRaisesRegex(RuntimeError,"T06_ROLLBACK_SAVED_SLOT_NOT_OWNED"):
            self.check(self.install,self.previous,self.saved,self.root)
    def test_unowned_saved_slot_rejected(self):
        self.owned(self.install);self.saved.mkdir()
        with self.assertRaisesRegex(RuntimeError,"T06_ROLLBACK_SAVED_SLOT_NOT_OWNED"):
            self.check(self.install,self.previous,self.saved,self.root)
    def test_redirected_saved_slot_rejected(self):
        self.owned(self.install)
        target=self.root/"outside";target.mkdir()
        try:self.saved.symlink_to(target,target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest("OS denies symlinks")
        with self.assertRaisesRegex(RuntimeError,"T06_ROLLBACK_SLOT_REPARSE_HOLD"):
            self.check(self.install,self.previous,self.saved,self.root)
    def test_both_original_powershell_verifier_slots_wired(self):
        source=SOURCE.read_text("utf-8")
        self.assertIn('for name,slot in (("restored",install),("superseded",saved)):',source)
        self.assertIn('report["installer_lifecycle"]["rollback_payload_"+name]=post_check',source)
        self.assertIn('require(post_check["code"]==0,"T06_ROLLBACK_SLOT_MANIFEST_VERIFY_HOLD:"+name)',source)
        self.assertIn('require(backup_check["code"]==0,"T06_UPDATE_BACKUP_MANIFEST_VERIFY_HOLD")',source)
if __name__=="__main__":unittest.main()
