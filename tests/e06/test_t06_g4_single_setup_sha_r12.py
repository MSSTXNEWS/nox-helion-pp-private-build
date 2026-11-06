"""G4 source-only executable unit cases: single immutable real Setup SHA.

Runs original Python helper with genuine temporary files. Not Windows/E07.
"""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"coordination"/"e06"))
import t06_samevm_installed_smoke as owner

class B03SingleSetupSHA(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.setup=self.root/"Setup.exe"
        self.setup.write_bytes(b"MZimmutable-g4")
        self.digest=hashlib.sha256(self.setup.read_bytes()).hexdigest()
        self.calls=[]
        self.report={}
        for attr,value in (("ROOT",self.root),("SETUP",self.setup)):
            patched=patch.object(owner,attr,value)
            patched.start()
            self.addCleanup(patched.stop)

    def fake(self,code=0,mutate=False):
        def invoke(args,timeout):
            self.calls.append((args,timeout))
            if mutate: self.setup.write_bytes(b"MZtampered-midprocess")
            return {"code":code,"elapsed":0.01}
        return invoke

    def test_three_native_phases_one_real_setup_sha(self):
        with patch.object(owner,"run",side_effect=self.fake()):
            for phase,flags in (("install",("/S",)),("update",("/S",)),
                                ("rollback",("/S","/ROLLBACK"))):
                result=owner.run_exact_pinned_nsis_setup(
                    phase,flags,250,self.digest,self.report)
                self.assertEqual(result["code"],0)
        self.assertEqual(len(self.calls),3)
        self.assertEqual(set(self.report),{"install","update","rollback"})

    def test_sha_changed_before_update_never_launches(self):
        self.setup.write_bytes(b"MZforeign")
        with patch.object(owner,"run",side_effect=self.fake()):
            with self.assertRaisesRegex(RuntimeError,"T06_G4_NSIS_SETUP_PRE_SHA_HOLD:update"):
                owner.run_exact_pinned_nsis_setup("update",("/S",),250,
                                                  self.digest,self.report)
        self.assertEqual(self.calls,[])

    def test_sha_drift_after_rollback_preserves_real_exit(self):
        with patch.object(owner,"run",side_effect=self.fake(code=1,mutate=True)):
            with self.assertRaisesRegex(RuntimeError,"T06_G4_NSIS_SETUP_POST_SHA_HOLD:rollback"):
                owner.run_exact_pinned_nsis_setup("rollback",("/S","/ROLLBACK"),
                                                  250,self.digest,self.report)
        self.assertEqual(self.report["rollback"]["code"],1)

    def test_wrong_phase_flags_never_launch(self):
        with patch.object(owner,"run",side_effect=self.fake()):
            with self.assertRaisesRegex(RuntimeError,"T06_G4_NSIS_PINNED_PHASE_INPUT_HOLD"):
                owner.run_exact_pinned_nsis_setup("install",("/ROLLBACK",),
                                                  250,self.digest,self.report)
        self.assertEqual(self.calls,[])

if __name__=="__main__":
    unittest.main()
